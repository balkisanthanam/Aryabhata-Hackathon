import os
import sys
import json
import argparse
import logging
import uuid
import time
import psycopg2
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

# Add MultiStep to path to import db_client and gemini_client
cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
sys.path.insert(0, str(extraction_dir))

from db_client import DatabaseClient
from gemini_client import GeminiClient
from config import PipelineConfig, flash_assembly_config
from solver_engine import GoldenGenerator, PromptSet, DEFAULT_PROMPT_SET
from gate import solve_with_gate

# ---------------------------------------------------------------------------
# NCERT-specific PromptSet (Component 0 payoff: no JEE persona on NCERT rows)
# ---------------------------------------------------------------------------
NCERT_PROMPT_SET = PromptSet(
    solver_system=(
        "You are a cold, calculating expert in Mathematics, Physics, and Chemistry. "
        "Focus entirely on mathematical and scientific correctness. "
        "Parse the problem, compute logic, dimensional analysis, and raw step-by-step derivations. "
        "Do not worry about pedagogy or strict formatting beyond clear derivations. "
        "If textbook theory or context is provided, use it strictly to ground your calculations "
        "and prevent hallucination—never mathematically force or 'fudge' numbers to match an expected answer key. "
        "Return the raw textual derivations and final answer."
    ),
    tutor_system=(
        "You are a Master Teacher reviewing a TA's logic for a CBSE/NCERT student. "
        "Take the raw derivations provided and translate them into a pedagogical, step-by-step tutorial. "
        "Inject helpful conceptual explanations and 'nudge_hints' (tips for where students get stuck). "
        "Validate that the logic flows correctly and fix any subtle math, physics, or chemistry errors. "
        "CRITICAL: NEVER skip algebraic substitutions or calculations. You MUST explicitly write out the final mathematical simplification step that bridges the formulas to the exact final answer. "
        "CRITICAL RULE FOR HINTS: Your `nudge_hints` must be purely Socratic questions that guide the student to think. NEVER provide direct statements that quote the theory, and NEVER give away the exact next step or the answer. "
        "If the derivation references a textbook principle or law, DO NOT state it as a direct statement in your hint. Instead, formulate a question asking the student how that principle applies to this problem. "
        "Do not output JSON, just structure the pedagogical text clearly."
    ),
    formatter_system_prefix=DEFAULT_PROMPT_SET.formatter_system_prefix,  # generic — reuse verbatim
)

# Stage-3 schema instruction for NCERT (passed as system_prompt to generate_assembly_line)
_NCERT_SCHEMA_INSTRUCTION = (
    "Output a single JSON object with exactly these top-level keys:\n"
    "- 'steps': array of step objects. Each step has: "
    "step_number (int, 1-based), step_type (string: 'conceptual'|'calculation'|'visual'), "
    "nudge_hint (string, Socratic question), explanation (string), latex_formula (string).\n"
    "- 'final_answer': string (the answer, e.g. 'A', '42', '3.14 m/s').\n\n"
    "LaTeX rules: wrap all inline math in $...$, display math in $$...$$. "
    "CHEMISTRY: render every chemical formula and reaction using mhchem inside math mode "
    "($\\ce{H2O}$, $\\ce{2H2 + O2 -> 2H2O}$). Never use plain subscripts for chemistry. "
    "Return valid JSON only — no markdown fences, no prose outside the JSON."
)

def robust_json_parse(jtext: str) -> dict:
    """Helper to safely rip out markdown code blocks and parse JSON."""
    jtext = jtext.strip()
    if jtext.startswith("```json"):
        jtext = jtext.split("```json", 1)[1]
    elif jtext.startswith("```"):
        jtext = jtext.split("```", 1)[1]
        
    if "```" in jtext:
        jtext = jtext[:jtext.rfind("```")].strip()
        
    try:
        return json.loads(jtext)
    except json.JSONDecodeError:
        # Raw LaTeX in JSON (\frac, \times) trips json.loads. Reuse the canonical
        # sanitizer (self-independent — pass None for self) and retry once.
        LOGGER.warning("JSON decode failed; retrying with LaTeX-escape sanitization...")
        try:
            return json.loads(GoldenGenerator._sanitize_json_escapes(None, jtext))
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse JSON even after sanitization. Output: {jtext[:200]}...")
            raise e

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def regenerate_core_math(gemini: GeminiClient, config: PipelineConfig, db_client: DatabaseClient,
                         question_content: dict, solution_candidate: dict, answer_key: str,
                         chapter_id: int = None) -> dict:
    """Task 1: Discard flawed legacy logic. Generate mathematically correct bare-bones steps matching the answer key.

    Smart Context: retrieves the top NCERT concept chunks for the question (pgvector over
    ncert_concept_embeddings) and feeds them to the solver to ground the *method*. Context
    is used ONLY in this solver pass — never in pedagogy/format, which would echo textbook
    prose (see NCERT_AssemblyLine_DesignNote.md gotcha #2).
    """
    system_prompt = (
        "You are an expert Math/Physics solver. The provided legacy solution contains broken mathematical logic.\n\n"
        "RULES:\n"
        "1. Start from scratch. Discard the legacy logic.\n"
        "2. Arrive EXACTLY at the provided TRUTH (ANSWER KEY).\n"
        "3. Ignore formatting restrictions or Socratic pedagogy right now. Focus ONLY on getting the raw math steps strictly correct.\n"
        "4. If NCERT TEXTBOOK CONTEXT is provided, use it to ground the method — do not copy it verbatim.\n"
        "5. Return valid JSON matching the 'steps' (array of objects) and 'final_answer' schema of the original solution.\n"
    )

    # --- Smart Context retrieval (pgvector over ncert_concept_embeddings) ---
    context_block = ""
    context_image_urls = []
    if chapter_id:
        try:
            qc = question_content if isinstance(question_content, dict) else {}
            q_text = (qc.get("question_text") or qc.get("text")
                      or qc.get("raw_text") or json.dumps(question_content))
            q_embed = gemini.embed_text(q_text, task_type="RETRIEVAL_DOCUMENT",
                                        output_dimensionality=768, model_id="text-embedding-004")
            chunks = db_client.get_smart_context_for_question(chapter_id, q_embed, top_k=10)
            snippets = []
            for c in chunks:
                ctext = c.get("chunk_text") or ""
                if ctext:
                    snippets.append(f"### {c.get('concept_title') or 'Concept'}\n{ctext}")
                if c.get("figure_url"):
                    context_image_urls.append(c["figure_url"])
            if snippets:
                context_block = "\n\n---\n".join(snippets)
                LOGGER.info(f"Smart Context: retrieved {len(snippets)} concept chunk(s) for chapter_id={chapter_id}")
        except Exception as e:
            LOGGER.warning(f"Smart Context retrieval failed (continuing without): {e}")

    context_section = (
        f"\nNCERT TEXTBOOK CONTEXT (ground the method; do not copy verbatim):\n{context_block}\n"
        if context_block else ""
    )

    user_prompt = f"""
PROBLEM CONTENT:
```json
{json.dumps(question_content, indent=2)}
```
{context_section}
TRUTH (ANSWER KEY):
{answer_key}

FLAWED LEGACY SOLUTION:
```json
{json.dumps(solution_candidate, indent=2)}
```

Emit the perfectly corrected JSON solution.
"""
    response = gemini.generate(model_config=config.solver_model, prompt=user_prompt,
                               system_instruction=system_prompt,
                               image_urls=context_image_urls if context_image_urls else None)
    parsed = robust_json_parse(response.text)
    if "steps" not in parsed or not isinstance(parsed["steps"], list):
        raise ValueError("Missing or invalid 'steps' array in LLM output")
    return parsed

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def inject_pedagogy(gemini: GeminiClient, config: PipelineConfig, solution_candidate: dict) -> dict:
    """Task 2: Inject conceptual mapping and Socratic nudges. Do not alter math."""
    system_prompt = (
        "You are a Master Teacher. The provided solution is mathematically correct.\n\n"
        "RULES:\n"
        "1. DO NOT change any equations, numbers, or mathematical logic.\n"
        "2. Socratic Nudges: Inject a guiding question into the 'nudge_hint' field of EVERY step. Make the student think.\n"
        "3. Strategy: Ensure there is a 'conceptual' step_type at the beginning mapping out the high level logic.\n"
        "4. Return valid JSON matching the provided schema.\n"
    )
    user_prompt = f"VERIFIED SOLUTION:\n```json\n{json.dumps(solution_candidate, indent=2)}\n```\n\nInject pedagogy."
    # Pedagogy is a reasoning task — use the tuned tutor model (Pro, temp 0.6).
    response = gemini.generate(model_config=config.tutor_model, prompt=user_prompt, system_instruction=system_prompt)
    parsed = robust_json_parse(response.text)
    if "steps" not in parsed or not isinstance(parsed["steps"], list):
        raise ValueError("Missing or invalid 'steps' array in LLM output")
    return parsed

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def apply_strict_formatting(gemini: GeminiClient, config: PipelineConfig, solution_candidate: dict) -> dict:
    """Task 3: Enforce strict KaTeX throughout the payload. Do not alter math or pedagogy."""
    system_prompt = (
        "You are a strict JSON Formatter and LaTeX enforcer. The provided solution is mathematically correct and pedagogically complete.\n\n"
        "RULES:\n"
        "1. DO NOT change the mathematical truths, logic steps, or Socratic nudges.\n"
        "2. Strict KaTeX: Wrap all numbers, units, variables, operators, and equations strictly in inline LaTeX ($m^2$, $-$, $\\times$, $^\\circ C$) or block LaTeX ($$ ... $$).\n"
        "3. Replace all bare unicode mathematical symbols (like − or ×) with LaTeX.\n"
        "4. CHEMISTRY: render every chemical formula, species, and reaction with mhchem inside math mode — $\\ce{C6H6}$, $\\ce{Co(NO3)2.6H2O}$, $\\ce{2H2 + O2 -> 2H2O}$. NEVER write chemical formulas as plain math subscripts like $C_{6}H_{6}$.\n"
        "5. CANONICAL SCHEMA — the output JSON must use exactly these keys:\n"
        "   - Top level: 'steps' (array) and 'final_answer' (string).\n"
        "   - Each step object: 'step_number' (int), 'step_type' (string), 'nudge_hint' (string), 'explanation' (string), 'latex_formula' (string).\n"
        "6. RENAME any legacy keys you encounter: 'hint' -> 'nudge_hint', 'formula' -> 'latex_formula'. Never emit the legacy key names.\n"
        "7. Do not add, drop, or reorder steps. Return valid JSON only.\n"
    )
    user_prompt = f"UNFORMATTED SOLUTION:\n```json\n{json.dumps(solution_candidate, indent=2)}\n```\n\nApply strict KaTeX formatting."
    # Formatting is mechanical schema/LaTeX enforcement — use the cheap Flash formatter model.
    response = gemini.generate(model_config=config.formatter_model, prompt=user_prompt, system_instruction=system_prompt)
    parsed = robust_json_parse(response.text)
    if "steps" not in parsed or not isinstance(parsed["steps"], list):
        raise ValueError("Missing or invalid 'steps' array in LLM output")
    return parsed


def execute_write(db_client, sql, params, retries=4):
    """Run one write, reconnecting if the DB connection was dropped.

    Azure PostgreSQL can close the connection during the long gaps between LLM
    calls, and DatabaseClient.connect() reuses a cached handle whose `.closed`
    flag stays stale after a server-side drop. On OperationalError/InterfaceError
    we force a genuinely fresh connection and retry — each write is sub-second, so
    a freshly reconnected handle always succeeds.
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            conn = db_client.connect()
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
            return
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_err = e
            LOGGER.warning(f"DB write failed (attempt {attempt}/{retries}): "
                           f"{e.__class__.__name__} — reconnecting...")
            try:
                db_client.close()
            except Exception:
                pass
            db_client._connection = None  # force connect() to build a fresh handle
            time.sleep(min(2 * attempt, 10))
    raise last_err


def run_generate_task(args, db_client, gemini, config):
    """Key-blind Flash Assembly Line generation for NCERT (M3 Pipeline Integration, Component 5).

    Decision D2: prompt is always key-blind — answer_key goes ONLY to the gate.
    Decision D4: NCERT figures → Flash (proven ≈ Pro); no router needed.
    Decision D5: corrupt/unknown keys → KEY_UNVERIFIED, never a miss.
    Resumable: skips rows where solution IS NOT NULL or retry_count >= 3.
    """
    run_id = str(uuid.uuid4())[:8]
    LOGGER.info(
        f"[RunID: {run_id}] Task: generate | Class: {args.cls} | "
        f"Subject: {args.subject} | SmartCtx: {args.use_smart_context}"
    )

    flash_gen = GoldenGenerator(gemini, flash_assembly_config(), NCERT_PROMPT_SET)
    pro_gen   = GoldenGenerator(gemini, config, NCERT_PROMPT_SET)

    output_file = project_root / "TempLocal" / f"ncert_generate_{args.cls}_{args.subject}_{run_id}.jsonl"
    LOGGER.info(f"[RunID: {run_id}] Incremental JSONL backup → {output_file}")

    # Fetch rows without solutions (resumable by solution IS NULL)
    with db_client.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT q.questionid, c.chapternumber, e.exercise, q.question_ref,
                       q.content, q.answer_key, c.chapterid, c.subject
                FROM questiondata q
                JOIN exercisedata e ON q.exerciseid = e.exerciseid
                JOIN chapterdata  c ON e.chapterid  = c.chapterid
                WHERE c.class      = %s
                  AND c.subject ILIKE %s
                  AND q.solution   IS NULL
                  AND q.is_generated = FALSE
                  AND q.retry_count  < 3
                ORDER BY e.exerciseid, q.questionid
                LIMIT %s
                """,
                (args.cls, f"%{args.subject}%", args.limit),
            )
            rows = cur.fetchall()

    if not rows:
        LOGGER.info(f"[RunID: {run_id}] No unsolved rows found — nothing to do.")
        return

    LOGGER.info(f"[RunID: {run_id}] Generating solutions for {len(rows)} rows.")

    for row in rows:
        qid, chap, ex, q_ref, content_json, ans_key, chapter_id, subject = row
        LOGGER.info(f"[RunID: {run_id}] QID {qid} | Ch {chap} | Ex {ex} | Ref {q_ref}")

        if isinstance(content_json, str):
            try:
                content_json = json.loads(content_json)
            except Exception:
                LOGGER.warning(f"[RunID: {run_id}] QID {qid}: could not parse content JSON, skipping.")
                continue

        try:
            # Fix 1: robust question_text extraction — mirror the fallback chain in
            # regenerate_core_math (question_text / text / raw_text / full dump).
            q_text = (
                content_json.get("question_text")
                or content_json.get("text")
                or content_json.get("raw_text")
                or json.dumps(content_json)
            )

            # Build key-blind payload (D2: no answer_key in prompt)
            payload_dict = {"problem_text": q_text}
            options = content_json.get("options", [])
            if options:
                payload_dict["options"] = options

            # Smart context (optional PgVector retrieval)
            if args.use_smart_context and chapter_id:
                try:
                    q_embed = gemini.embed_text(
                        q_text, task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=768, model_id="text-embedding-004",
                    )
                    chunks = db_client.get_smart_context_for_question(chapter_id, q_embed, top_k=10)
                    snippets = [c.get("chunk_text") for c in chunks if c.get("chunk_text")]
                    if snippets:
                        payload_dict["ncert_context"] = "\n\n---\n".join(snippets)
                except Exception as ce:
                    LOGGER.warning(f"[RunID: {run_id}] QID {qid}: smart context failed (continuing): {ce}")

            user_prompt = (
                f"Solve the following NCERT {subject} problem. "
                "Return the solution as a JSON object only.\n\n"
                f"Problem:\n```json\n{json.dumps(payload_dict, indent=2)}\n```\n"
            )

            # Fix 2: figure URL — try figure_url directly first (consistent with JEE
            # pipeline), then fall back to figure_info[0].url (NCERT DB query alias).
            figure_url = content_json.get("figure_url")
            if not figure_url:
                fi_list = content_json.get("figure_info", [])
                if fi_list and isinstance(fi_list, list) and isinstance(fi_list[0], dict):
                    figure_url = fi_list[0].get("url")
            image_urls = [figure_url] if figure_url else None

            # Fix 3: unwrap {"answer": "..."} NCERT key format before gate.
            # answer_match expects a bare string (letter or number).
            gate_key = ans_key
            if isinstance(ans_key, str):
                try:
                    _kobj = json.loads(ans_key)
                    if isinstance(_kobj, dict) and "answer" in _kobj:
                        gate_key = _kobj["answer"]
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(ans_key, dict) and "answer" in ans_key:
                gate_key = ans_key["answer"]

            # Flash → gate → Pro cascade (always key-blind)
            sol, review_status = solve_with_gate(
                prompt=user_prompt,
                system_prompt=_NCERT_SCHEMA_INSTRUCTION,
                answer_key=gate_key,
                options=options,
                image_urls=image_urls,
                flash_generator=flash_gen,
                pro_generator=pro_gen,
            )
            parsed = robust_json_parse(sol.text)

            LOGGER.info(f"[RunID: {run_id}] QID {qid} → {review_status}")

            # Incremental JSONL backup (safe even if DB write fails)
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "questionid": qid, "question_ref": q_ref,
                    "review_status": review_status, "solution": parsed,
                }, ensure_ascii=False) + "\n")

            if args.update_db:
                execute_write(
                    db_client,
                    """UPDATE questiondata
                       SET solution = %s::jsonb,
                           review_status = %s,
                           is_generated = TRUE
                       WHERE questionid = %s""",
                    (json.dumps(parsed), review_status, qid),
                )
                LOGGER.info(f"[RunID: {run_id}] QID {qid} written → {review_status}")

        except Exception as e:
            LOGGER.error(f"[RunID: {run_id}] QID {qid} failed: {e}")
            if args.update_db:
                try:
                    execute_write(
                        db_client,
                        """UPDATE questiondata
                           SET retry_count = retry_count + 1,
                               review_status = CASE WHEN retry_count >= 2
                                                    THEN 'GENERATION_FAILED'
                                                    ELSE review_status END
                           WHERE questionid = %s""",
                        (qid,),
                    )
                except Exception as we:
                    LOGGER.error(f"[RunID: {run_id}] QID {qid}: could not update retry_count: {we}")

    LOGGER.info(f"[RunID: {run_id}] Generate run complete.")


def run_orchestrator(args):
    run_id = str(uuid.uuid4())[:8]
    LOGGER.info(f"[RunID: {run_id}] Running Orchestrator | Class: {args.cls} | Subject: {args.subject} | Task: {args.task}")

    db_client = DatabaseClient(use_managed_identity=True)
    config = PipelineConfig()
    gemini = GeminiClient(config)

    # New key-blind production generation path (Component 5, M3 Pipeline Integration).
    # Kept separate from the Gold-Set curation task_map below — do not touch those tasks.
    if args.task == "generate":
        run_generate_task(args, db_client, gemini, config)
        return

    # Map task parameters to DB queries and handler functions
    task_map = {
        "regenerate": {
            "query_status": "REJECTED",
            "next_status": "MATH_REGENERATED",
            "needs_context": True
        },
        "pedagogy": {
            "query_status": "MATH_PASSED",
            "next_status": "PEDAGOGY_ADDED",
            "needs_context": False
        },
        "format": {
            "query_status": "PEDAGOGY_ADDED",
            "next_status": "APPROVED",
            "needs_context": False
        }
    }
    
    current_task = task_map[args.task]
    
    # Output JSONL target (used as backup/dry-run capture)
    output_file = project_root / "TempLocal" / f"ncert_orchestrator_{args.task}_{args.cls}_{args.subject}_{run_id}.jsonl"
    LOGGER.info(f"[RunID: {run_id}] Output will be appended incrementally to {output_file}")
    
    with db_client.connect() as conn:
        with conn.cursor() as cur:
            # Query builder
            query = f"""
                SELECT q.questionid, c.chapternumber, e.exercise, q.question_ref, q.content, q.solution, q.answer_key, c.chapterid
                FROM questiondata q
                JOIN exercisedata e ON q.exerciseid = e.exerciseid
                JOIN chapterdata c ON e.chapterid = c.chapterid
                WHERE c.class = %s 
                  AND c.subject ILIKE %s
                  AND q.review_status = '{current_task["query_status"]}'
                  AND q.solution IS NOT NULL
                ORDER BY e.exerciseid, q.questionid
                LIMIT %s
            """
            cur.execute(query, (args.cls, f"%{args.subject}%", args.limit))
            rows = cur.fetchall()
            
    if not rows:
        LOGGER.warning(f"[RunID: {run_id}] No rows found in '{current_task['query_status']}' status.")
        return
        
    LOGGER.info(f"[RunID: {run_id}] Targeting {len(rows)} rows for '{args.task}'.")
    
    # Per-row writes go through execute_write(), which reconnects if Azure drops the handle.
    for row in rows:
            qid, chap, ex, q_ref, content_json, solution_json, ans_key, chapter_id = row
            LOGGER.info(f"[RunID: {run_id}] [{args.task.upper()}] QID: {qid} | Ch: {chap} | Ex: {ex} | Ref: {q_ref}")
            
            try:
                if args.task == "regenerate":
                    new_sol = regenerate_core_math(gemini, config, db_client, content_json, solution_json, str(ans_key), chapter_id)
                elif args.task == "pedagogy":
                    new_sol = inject_pedagogy(gemini, config, solution_json)
                elif args.task == "format":
                    new_sol = apply_strict_formatting(gemini, config, solution_json)
                else:
                    raise ValueError("Invalid Task")
                
                res_dict = {
                    "questionid": qid,
                    "question_ref": q_ref,
                    "output_solution": new_sol
                }
                
                # Append to JSONL incrementally
                with open(output_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(res_dict, ensure_ascii=False) + "\n")
                
                # Persist row-by-row; execute_write reconnects if the handle was dropped.
                if args.update_db:
                    try:
                        execute_write(
                            db_client,
                            "UPDATE questiondata SET solution = %s, review_status = %s WHERE questionid = %s",
                            (json.dumps(new_sol), current_task["next_status"], qid),
                        )
                        LOGGER.info(f"[RunID: {run_id}] Updated QID {qid} -> {current_task['next_status']}")
                    except Exception as we:
                        LOGGER.error(f"[RunID: {run_id}] DB write failed for QID {qid} after retries: {we}. "
                                     f"Solution is in the JSONL; row left for re-run.")
                
            except Exception as e:
                LOGGER.error(f"[RunID: {run_id}] Failed to process QID {qid}: {e}")
                if args.update_db:
                    try:
                        execute_write(
                            db_client,
                            "UPDATE questiondata SET review_status = 'NEEDS_HUMAN_REVIEW' WHERE questionid = %s",
                            (qid,),
                        )
                        LOGGER.error(f"[RunID: {run_id}] Fallback: Updated QID {qid} -> NEEDS_HUMAN_REVIEW")
                    except Exception as we:
                        LOGGER.error(f"[RunID: {run_id}] Could not flag QID {qid}: {we}")
            
    LOGGER.info(f"[RunID: {run_id}] Run complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Assembly Line Orchestrator for NCERT extraction.")
    parser.add_argument("--class", dest="cls", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--task", choices=["regenerate", "pedagogy", "format", "generate"], required=True,
                        help="generate (key-blind Flash production path, targets solution IS NULL); "
                             "regenerate (targets REJECTED); pedagogy (targets MATH_PASSED); format (targets PEDAGOGY_ADDED)")
    parser.add_argument("--use-smart-context", action="store_true", dest="use_smart_context",
                        help="Inject PgVector NCERT concept context into the solver prompt (--task generate only)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--update-db", action="store_true", help="Writes the LLM output back to DB and advances review_status.")
    args = parser.parse_args()
    
    run_orchestrator(args)