"""
Activity: Evaluate a batch of problems against the student's full work pages.

v4 — Unified flow: always text-ref based. Sends ALL student page images to
     Gemini along with a list of problem numbers (max BATCH_SIZE per call).
     Optionally includes textbook page images as reference context.
     No image cropping needed — Gemini locates the relevant work.

Backup of v1 (split-based): evaluate_batch_v1_split_based.py
"""
import logging
import base64
import os
from utils.gemini_client import call_gemini, MODEL_EVALUATION
from utils.prompt_loader import load_prompt, fill_template
from utils.blob_storage import fetch_blob_content

# Default batch size — max problems per Gemini call
DEFAULT_BATCH_SIZE = int(os.environ.get("EVAL_BATCH_SIZE", "3"))


def evaluate_batch_activity(input_data: dict) -> dict:
    """
    Evaluate a batch of problems by sending full student page images to Gemini.
    
    Args:
        input_data: {
            "problems": [
                {
                    "problem_id": str,
                    "problem_number": str,
                    "exercise_label": str (optional),
                }
            ],
            "student_pages_b64": [str],        — base64-encoded full student page images
            "class": str,
            "subject": str,
            "chapter_title": str,
            "pdf_url": str (optional — URL to chapter PDF in blob storage),
            "textbook_pages_b64": [str] (optional — full textbook page images for reference)
        }
    
    Returns:
        {
            "evaluations": [{"problem_id": str, "evaluation": dict}],
            "_meta": {...}
        }
    """
    problems = input_data["problems"]
    student_pages_b64 = input_data["student_pages_b64"]
    class_val = input_data["class"]
    subject = input_data["subject"]
    chapter_title = input_data.get("chapter_title", "")
    pdf_url = input_data.get("pdf_url")
    textbook_pages_b64 = input_data.get("textbook_pages_b64", [])

    logging.info(
        f"Activity evaluate_batch: {len(problems)} problem(s), "
        f"{len(student_pages_b64)} student page(s), "
        f"{len(textbook_pages_b64)} textbook page(s), "
        f"class={class_val}, subject={subject}"
    )

    return _evaluate_batch(
        problems=problems,
        student_pages_b64=student_pages_b64,
        class_val=class_val,
        subject=subject,
        chapter_title=chapter_title,
        pdf_url=pdf_url,
        textbook_pages_b64=textbook_pages_b64,
    )


def _evaluate_batch(
    problems: list,
    student_pages_b64: list,
    class_val: str,
    subject: str,
    chapter_title: str,
    pdf_url: str | None,
    textbook_pages_b64: list | None = None,
) -> dict:
    """
    Unified evaluation: sends all student pages + problem list to Gemini.
    Optionally includes full textbook page images as reference context.
    Returns per-problem evaluations.
    """
    # Build problem description for prompt
    problem_lines = []
    for p in problems:
        label = f"Exercise {p['exercise_label']}, " if p.get("exercise_label") else ""
        pid = p['problem_number']
        desc = f"- Problem ID: \"{pid}\" — {label}Problem {pid}"
        if chapter_title:
            desc += f" (Chapter: {chapter_title})"
        desc += f"\n  You MUST use problem_id \"{pid}\" exactly in your response."
        problem_lines.append(desc)
    problems_text = "\n".join(problem_lines)

    # Load and fill prompt
    prompt_template = load_prompt("Evaluation.txt")
    filled_prompt = fill_template(
        prompt_template,
        **{
            "class": class_val,
            "Subject": subject,
            "Problems": problems_text,
        }
    )

    # Build content parts: prompt → textbook pages → student pages → PDF
    content_parts = [filled_prompt]

    # Optional textbook page images (full pages, not crops)
    if textbook_pages_b64:
        for idx, tb_b64 in enumerate(textbook_pages_b64):
            tb_bytes = base64.b64decode(tb_b64)
            content_parts.append(f"\n[TEXTBOOK PAGE {idx + 1}]")
            content_parts.append({"mime_type": "image/jpeg", "data": tb_bytes})

    # Student work pages
    for idx, page_b64 in enumerate(student_pages_b64):
        page_bytes = base64.b64decode(page_b64)
        content_parts.append(f"\n[STUDENT PAGE {idx + 1}]")
        content_parts.append({"mime_type": "image/jpeg", "data": page_bytes})

    if pdf_url:
        try:
            pdf_bytes = fetch_blob_content(pdf_url, as_text=False)
            content_parts.append("\n[REFERENCE MATERIAL PDF]")
            content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})
            logging.info(f"PDF fetched for evaluation: {len(pdf_bytes)} bytes")
        except Exception as e:
            logging.warning(f"Could not fetch chapter PDF from {pdf_url}: {e}")

    try:
        gemini_response = call_gemini(
            model_id=MODEL_EVALUATION,
            content_parts=content_parts,
            response_json=True,
        )
        return _parse_batch_response(gemini_response, problems)
    except Exception as e:
        logging.error(f"Batch evaluation failed: {e}")
        return _error_fallback(problems, str(e))


def _parse_batch_response(gemini_response: dict, problems: list) -> dict:
    """Parse Gemini's batch response into per-problem evaluations."""
    parsed = gemini_response["parsed_result"]

    # The new prompt asks for {"evaluations": [...]}
    if isinstance(parsed, dict) and "evaluations" in parsed:
        evaluations = parsed["evaluations"]
    elif isinstance(parsed, list):
        evaluations = parsed
    else:
        # Single evaluation wrapped in dict — shouldn't happen, but handle gracefully
        evaluations = [parsed]

    results = []
    for eval_item in evaluations:
        results.append({
            "problem_id": eval_item.get("problem_id", "unknown"),
            "evaluation": eval_item,
            "_meta": {
                "model": gemini_response.get("model"),
                "usage_metadata": gemini_response.get("usage_metadata"),
            },
        })

    # Check if any requested problems are missing from response
    responded_ids = {e.get("problem_id") for e in evaluations}
    for p in problems:
        pid = p.get("problem_number", p.get("problem_id"))
        if pid not in responded_ids:
            logging.warning(f"Problem {pid} missing from Gemini response")
            results.append({
                "problem_id": pid,
                "evaluation": {
                    "evaluation_status": "Error",
                    "error": "Problem not included in Gemini response",
                },
            })

    return {
        "evaluations": results,
        "_meta": {
            "model": gemini_response.get("model"),
            "prompt_version": "Evaluation.txt (v4 unified)",
            "problems_in_batch": len(problems),
            "usage_metadata": gemini_response.get("usage_metadata"),
        },
    }


def _error_fallback(problems: list, error_msg: str) -> dict:
    """Return error results for all problems in the batch."""
    results = []
    for p in problems:
        pid = p.get("problem_number", p.get("problem_id"))
        results.append({
            "problem_id": pid,
            "evaluation": {
                "evaluation_status": "Error",
                "error": error_msg,
            },
        })
    return {
        "evaluations": results,
        "_meta": {
            "model": MODEL_EVALUATION,
            "prompt_version": "Evaluation.txt (v4 unified)",
            "problems_in_batch": len(problems),
            "error": error_msg,
        },
    }
