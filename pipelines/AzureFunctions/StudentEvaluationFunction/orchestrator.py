"""
Durable Functions Orchestrator for the Student Evaluation pipeline.
Unified single flow — always requires text reference for problem identification.
Textbook page images are optional reference context.

v4 — Unified flow: collapsed Path A / Path B into one pipeline.
     Always: fetch student images → parse text ref → validate → get PDF →
             optionally fetch textbook images → batch evaluate.
     No image splitting/cropping. Gemini locates work on student pages.
     Batch size parameterized (default 3 problems per Gemini call).
"""
import logging
import os
import azure.durable_functions as df


# RetryOptions for idempotent activities (5s initial, 3 attempts)
_RETRY = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)

# Max problems per Gemini evaluation call (configurable via env var or DB record)
DEFAULT_BATCH_SIZE = int(os.environ.get("EVAL_BATCH_SIZE", "3"))


def orchestrator_function(context: df.DurableOrchestrationContext):
    """
    Main orchestrator that coordinates the evaluation pipeline.
    
    Input: job_id (str) — UUID from solution_evaluations table.
    
    Unified flow (v4):
        fetch student images → (optionally fetch textbook images) →
        parse text ref → validate → get PDF → batch evaluate → save results.

    Checkpoint pattern:
        Each step saves "started" → execute → save "completed".
    """
    job_id = context.get_input()

    if not context.is_replaying:
        logging.info(f"Orchestrator started for job {job_id}")

    # ── Step 1: Read evaluation record (PENDING/PROCESSING → PROCESSING) ──
    context.set_custom_status("step:read_evaluation")
    record = yield context.call_activity("read_evaluation", job_id)

    if record.get("skip"):
        if not context.is_replaying:
            logging.info(f"Job {job_id}: skipping — {record.get('reason', 'already processed')}")
        return {"status": "skipped", "reason": record.get("reason")}

    # Save checkpoint for step 1
    yield context.call_activity("save_checkpoint", {
        "job_id": job_id,
        "step_name": "read_evaluation",
        "status": "completed",
        "result_summary": {
            "subject": record.get("subject"),
            "chapter_title": record.get("chapter_title"),
            "has_text_ref": bool(record.get("problem_text_ref")),
            "has_image_ref": bool(record.get("problem_image_url")),
        },
    })

    # Validate that text ref is present (required in v4)
    if not record.get("problem_text_ref"):
        yield context.call_activity("update_evaluation", {
            "job_id": job_id,
            "status": "FAILED",
            "feedback_json": {"error": "problem_text_ref is required — specify which problems to evaluate"},
        })
        return {"status": "FAILED", "error": "No problem_text_ref provided"}

    try:
        # ── Step 2: Fetch student work images ──
        context.set_custom_status("step:fetch_student_images")

        fetch_result = yield context.call_activity_with_retry(
            "fetch_student_images",
            _RETRY,
            {"student_work_url": record["student_work_url"]},
        )

        student_pages_b64 = [p["image_b64"] for p in fetch_result["pages"]]
        page_count = fetch_result["page_count"]

        yield context.call_activity("save_checkpoint", {
            "job_id": job_id,
            "step_name": "fetch_student_images",
            "status": "completed",
            "result_summary": {"pages_fetched": page_count},
        })

        if not student_pages_b64:
            yield context.call_activity("update_evaluation", {
                "job_id": job_id,
                "status": "FAILED",
                "feedback_json": {"error": "No student work images could be fetched"},
            })
            return {"status": "FAILED", "error": "No student images fetched"}

        # ── Step 2B: Optionally fetch textbook page images ──
        textbook_pages_b64 = []
        if record.get("problem_image_url"):
            context.set_custom_status("step:fetch_textbook_images")

            tb_fetch = yield context.call_activity_with_retry(
                "fetch_student_images",  # reuse same downloader activity
                _RETRY,
                {"student_work_url": record["problem_image_url"]},
            )

            textbook_pages_b64 = [p["image_b64"] for p in tb_fetch["pages"]]

            yield context.call_activity("save_checkpoint", {
                "job_id": job_id,
                "step_name": "fetch_textbook_images",
                "status": "completed",
                "result_summary": {"textbook_pages_fetched": len(textbook_pages_b64)},
            })

            if not context.is_replaying:
                logging.info(f"Job {job_id}: {len(textbook_pages_b64)} textbook page(s) fetched as reference")

        # Determine batch size: allow per-record override, else env, else 3
        batch_size = record.get("batch_size", DEFAULT_BATCH_SIZE)

        # ── Step 3: Parse text reference ──
        context.set_custom_status("step:parse_text_ref")

        parse_result = yield context.call_activity_with_retry(
            "parse_text_ref",
            _RETRY,
            {
                "problem_text_ref": record["problem_text_ref"],
                "class": record.get("class"),
                "board": record.get("board"),
                "subject": record["subject"],
                "chapter_title": record.get("chapter_title"),
            },
        )

        parsed = parse_result["parsed"]
        parse_meta = parse_result.get("_meta", {})

        yield context.call_activity("save_checkpoint", {
            "job_id": job_id,
            "step_name": "parse_text_ref",
            "status": "completed",
            "result_summary": {
                "total_problems": parse_meta.get("total_problems"),
                "exercises_count": parse_meta.get("exercises_count"),
            },
            "model": parse_meta.get("model"),
            "prompt_version": parse_meta.get("prompt_version"),
            "token_usage": parse_meta.get("usage_metadata"),
        })

        # ── Step 4: Validate inputs ──
        context.set_custom_status("step:validate_inputs")

        validation = yield context.call_activity("validate_inputs", {
            "record": record,
            "parsed_ref": parsed,
        })

        if not validation["valid"]:
            yield context.call_activity("save_checkpoint", {
                "job_id": job_id, "step_name": "validate_inputs",
                "status": "failed", "error": validation["error"],
            })
            yield context.call_activity("update_evaluation", {
                "job_id": job_id,
                "status": "FAILED",
                "feedback_json": {"error": f"Input validation failed: {validation['error']}"},
            })
            return {"status": "FAILED", "error": validation["error"]}

        resolved = validation["resolved"]

        yield context.call_activity("save_checkpoint", {
            "job_id": job_id,
            "step_name": "validate_inputs",
            "status": "completed",
            "result_summary": {
                "class": resolved["class"],
                "subject": resolved["subject"],
                "chapter_title": resolved.get("chapter_title"),
                "problems_count": len(resolved.get("problems", [])),
            },
        })

        # ── Step 5: Get chapter PDF ──
        context.set_custom_status("step:get_chapter_pdf")

        chapter = yield context.call_activity_with_retry(
            "get_chapter_pdf",
            _RETRY,
            {
                "class": resolved["class"],
                "board": resolved.get("board"),
                "subject": resolved["subject"],
                "chapter_id": resolved.get("chapter_id"),
                "chapter_number": resolved.get("chapter_number"),
                "chapter_title": resolved.get("chapter_title"),
            },
        )

        yield context.call_activity("save_checkpoint", {
            "job_id": job_id,
            "step_name": "get_chapter_pdf",
            "status": "completed",
            "result_summary": {
                "pdf_found": bool(chapter.get("pdf_size")),
                "pdf_url": chapter.get("pdf_url"),
            },
        })

        # ── Step 6: Batch evaluate — direct (fan-out) ──
        #    Send ALL student pages (+ optional textbook pages) to each batch.
        #    Gemini locates relevant work on the student pages.
        context.set_custom_status("step:evaluate_batches")

        # Build problem list from resolved data
        all_problems = []
        for prob in resolved.get("problems", []):
            all_problems.append({
                "problem_id": prob["problem_number"],
                "problem_number": prob["problem_number"],
                "exercise_label": prob.get("exercise_label"),
            })

        batches = _chunk(all_problems, batch_size)

        tasks = []
        for batch in batches:
            eval_input = {
                "problems": batch,
                "student_pages_b64": student_pages_b64,
                "class": resolved["class"],
                "subject": resolved["subject"],
                "chapter_title": resolved.get("chapter_title", ""),
                "pdf_url": chapter.get("pdf_url"),
            }
            if textbook_pages_b64:
                eval_input["textbook_pages_b64"] = textbook_pages_b64
            tasks.append(context.call_activity_with_retry(
                "evaluate_batch",
                _RETRY,
                eval_input,
            ))

        batch_results = yield context.task_all(tasks)

        for idx, br in enumerate(batch_results):
            batch_meta = br.get("_meta", {})
            batch_evals = br.get("evaluations", [])
            yield context.call_activity("save_checkpoint", {
                "job_id": job_id,
                "step_name": f"evaluate_batch_{idx}",
                "status": "completed",
                "result_summary": {
                    "problems_in_batch": batch_meta.get("problems_in_batch", len(batch_evals)),
                },
                "model": batch_meta.get("model"),
                "prompt_version": batch_meta.get("prompt_version"),
            })

        # ── Step 7: Aggregate and save ──
        context.set_custom_status("step:update_evaluation")
        expected_ids = [p["problem_number"] for p in all_problems]
        feedback = _aggregate_results(batch_results, expected_ids)
        yield context.call_activity("update_evaluation", {
            "job_id": job_id,
            "status": "COMPLETED",
            "feedback_json": feedback,
            "chapter_id": resolved.get("chapter_id"),
            "chapter_title": resolved.get("chapter_title"),
            "chapter_number": resolved.get("chapter_number"),
            "pdffileurl": chapter.get("pdf_url"),
        })

        yield context.call_activity("save_checkpoint", {
            "job_id": job_id,
            "step_name": "update_evaluation",
            "status": "completed",
            "result_summary": feedback.get("summary"),
        })

        context.set_custom_status("completed")
        return {"status": "COMPLETED", "problems_evaluated": len(all_problems)}

    except Exception as e:
        error_msg = str(e)
        if not context.is_replaying:
            logging.error(f"Job {job_id}: orchestrator failed — {error_msg}")

        # Try to update DB with failure (best effort)
        try:
            yield context.call_activity("update_evaluation", {
                "job_id": job_id,
                "status": "FAILED",
                "feedback_json": {"error": f"Pipeline error: {error_msg}"},
            })
        except Exception:
            pass  # If even the update fails, let it go

        return {"status": "FAILED", "error": error_msg}


# ─── Helper Functions ─────────────────────────────────────────────────────────


def _chunk(lst: list, size: int) -> list:
    """Split a list into chunks of given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def _normalize_problem_id(raw_id: str) -> str:
    """
    Normalize a problem_id returned by Gemini:
      - Strip 'Q' or 'q' prefix
      - Strip parenthetical suffixes like '(Student Page 1)'
      - Trim whitespace
    Examples:
      'Q4 (Student Page 1)' → '4'
      'Q13.9'              → '13.9'
      '  7  '              → '7'
    """
    import re
    pid = str(raw_id).strip()
    # Remove leading Q/q (e.g., "Q4", "q13.9")
    pid = re.sub(r'^[Qq]\s*', '', pid)
    # Remove parenthetical suffixes (e.g., "(Student Page 1)")
    pid = re.sub(r'\s*\([^)]*\)\s*$', '', pid)
    return pid.strip()


def _aggregate_results(batch_results: list, expected_ids: list[str] | None = None) -> dict:
    """
    Aggregate evaluation results from multiple batches into a single feedback JSON.
    
    Args:
        batch_results: List of dicts from evaluate_batch activities,
                       each with "evaluations" list and "_meta" dict.
        expected_ids:  Original list of problem IDs from parsed input.
                       Used for deduplication, missing detection, and ID normalization.
    
    Returns:
        Combined feedback dict for storage in solution_evaluations.feedback_json
    """
    all_evaluations = []
    for batch in batch_results:
        # New format: batch is {"evaluations": [...], "_meta": {...}}
        if isinstance(batch, dict) and "evaluations" in batch:
            all_evaluations.extend(batch["evaluations"])
        elif isinstance(batch, list):
            # Legacy fallback
            all_evaluations.extend(batch)
        else:
            all_evaluations.append(batch)

    # ── Phase 1: Normalize problem IDs ──
    for ev in all_evaluations:
        raw_id = ev.get("problem_id", "unknown")
        normalized = _normalize_problem_id(raw_id)
        if normalized != raw_id:
            logging.info(f"Normalized problem_id: '{raw_id}' → '{normalized}'")
            ev["problem_id"] = normalized
        # Also normalize inside the nested evaluation dict
        if isinstance(ev.get("evaluation"), dict):
            ev["evaluation"]["problem_id"] = normalized

    # ── Phase 2: Deduplicate by problem_id (keep non-error over error) ──
    seen: dict[str, dict] = {}
    for ev in all_evaluations:
        pid = ev.get("problem_id", "unknown")
        if pid in seen:
            existing_status = seen[pid].get("evaluation", {}).get("evaluation_status", "")
            new_status = ev.get("evaluation", {}).get("evaluation_status", "")
            # Prefer non-error evaluation
            if "Error" in existing_status and "Error" not in new_status:
                logging.info(f"Dedup: replacing error entry for '{pid}' with non-error")
                seen[pid] = ev
            else:
                logging.info(f"Dedup: discarding duplicate for '{pid}'")
        else:
            seen[pid] = ev

    deduped = list(seen.values())

    # ── Phase 3: Detect missing problems ──
    if expected_ids:
        returned_ids = set(seen.keys())
        for eid in expected_ids:
            if eid not in returned_ids:
                logging.warning(f"Problem '{eid}' missing from all batch responses — adding Not Evaluated entry")
                deduped.append({
                    "problem_id": eid,
                    "evaluation": {
                        "evaluation_status": "Error",
                        "error": "Problem was not evaluated — it may not have been found in the student's work or was missed by the evaluation model",
                    },
                })

    # ── Phase 4: Recompute summary statistics ──
    statuses = [e.get("evaluation", {}).get("evaluation_status", "Unknown") for e in deduped]
    correct = sum(1 for s in statuses if "Correct" in s and "Incorrect" not in s)
    acceptable = sum(1 for s in statuses if "Acceptable" in s)
    incorrect = sum(1 for s in statuses if "Incorrect" in s)
    errors = sum(1 for s in statuses if "Error" in s or "Unknown" in s or "Not Found" in s)

    return {
        "summary": {
            "total_problems": len(deduped),
            "correct": correct,
            "acceptable": acceptable,
            "incorrect": incorrect,
            "errors": errors,
        },
        "evaluations": deduped,
    }
