"""
Universal Evaluator Engine - Milestone M2.4

An automated grading script using Gemini 3.1 Pro as the Judge.
Takes a generated solution payload and compares it to problem context (and Truth if available).
Outputs a composite score (Dimensions: Accuracy, Pedagogy, Formatting) and a Binary Verdict.
Used for:
- SFT base-lining (Pro vs Flash precision tracking)
- NCERT retrospective cleanse
- RLHF reward/preference scoring
"""

import sys
import os
import json
import time
import logging
import psycopg2
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
sys.path.insert(0, str(extraction_dir))

from gemini_client import GeminiClient
from config import PipelineConfig
from solver_engine import GoldenGenerator
from db_client import DatabaseClient

@dataclass
class EvaluationResult:
    accuracy_score: int       # 0 - 5
    pedagogy_score: int       # 0 - 5
    formatting_score: int     # 0 - 5
    total_score: int          # 0 - 15
    feedback_notes: str       # Text feedback explaining deductions
    is_pass: bool             # PASS if total >= 13 and accuracy == 5
    
    @property
    def is_gold(self) -> bool:
        """Strict training-grade bar: a perfect score on all three dimensions."""
        return self.accuracy_score == 5 and self.pedagogy_score == 5 and self.formatting_score == 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy_score": self.accuracy_score,
            "pedagogy_score": self.pedagogy_score,
            "formatting_score": self.formatting_score,
            "total_score": self.total_score,
            "feedback_notes": self.feedback_notes,
            "is_pass": self.is_pass,
            "is_gold": self.is_gold
        }

class UniversalEvaluator:
    def __init__(self, client: GeminiClient, config: PipelineConfig):
        self.generator = GoldenGenerator(client, config)
        
    def evaluate_solution(self, problem_payload: dict, generated_solution: dict, actual_answer_key: Optional[str] = None, mode: str = "full") -> EvaluationResult:
        """
        Evaluate a candidate solution. Returns an EvaluationResult.
        mode: "full" (3-D evaluation) or "accuracy_only" (Fast gate)
        """
        LOGGER.info(f"Evaluating solution candidate (Mode: {mode})...")
        
        if mode == "accuracy_only":
            system_prompt = (
                "You are evaluating the strict mathematical/physical CORRECTNESS of a legacy NCERT answer.\n"
                "You are ignoring all formatting, pedagogy, or LaTeX rules.\n"
                "1. Accuracy (5 pts): Does the mathematical execution arrive at the correct Answer Key without any hallucinated steps?\n\n"
                "Return ONLY a JSON response validating this format:\n"
                "{\n"
                "   \"accuracy_score\": <int 0-5>,\n"
                "   \"feedback_notes\": \"<string detailing exact mistakes if any>\"\n"
                "}"
            )
        else:
            system_prompt = (
                "You are a strict QA Judge evaluating an AI-generated step-by-step solution for an IIT-JEE/NCERT problem. "
                "You must score the solution on three dimensions out of 5 points each:\n\n"
                "1. Accuracy (5 pts): Are the final answer and intermediary physics/math/chemistry correct?\n"
                "   - Physics: Check dimensional consistency across steps. Are limits and vector directions correct?\n"
                "   - Chemistry: Verify stoichiometry balancing, state symbols (s/l/g/aq), and proper stereochemistry.\n"
                "   - Math: Check calculus constraints, domain/range assumptions, and arithmetic drift.\n"
                "   - Deduct heavily for any hallucinatory leaps from step A to step B.\n\n"
                "2. Pedagogy (5 pts): Does the solution read like a good tutor guiding a student?\n"
                "   - Are 'nudge_hint' values useful questions instead of just giving away the next step?\n"
                "   - Is the conceptual explanation clear and not just robotic math transcription?\n\n"
                "3. Formatting (5 pts): Is the JSON schema intact?\n"
                "   - Is LaTeX properly formatted? (Inline: `$math$`, Display: `$$math$$`, Chem: `\\ce{H2O}`).\n"
                "   - Are quotes properly escaped inside the JSON payload?\n\n"
                "--- FEW-SHOT EXAMPLES ---\n"
                "EXAMPLE 1 (Math - Perfect Solution): \n"
                "CANDIDATE: [Perfect step-by-step conversion of degrees to radians, clear conceptual hints, flawless LaTeX.]\n"
                "EVALUATION: {\"accuracy_score\": 5, \"pedagogy_score\": 5, \"formatting_score\": 5, \"feedback_notes\": \"Excellent solution. Flawless mathematical accuracy, clear conceptual framework (starts by explaining pi/180 factor), and perfect LaTeX formatting.\"}\n\n"
                "EXAMPLE 2 (Physics - Pedagogy Jumper):\n"
                "CANDIDATE: [Calculates heat correctly but all step_types are 'calculation', nudge_hints are entirely empty, skips conceptual setup.]\n"
                "EVALUATION: {\"accuracy_score\": 5, \"pedagogy_score\": 1, \"formatting_score\": 5, \"feedback_notes\": \"Accuracy is perfect, but pedagogy is terrible. Nudge hints are completely empty. It jumps straight into calculations without any Socratic questioning or conceptual scaffolding.\"}\n\n"
                "EXAMPLE 3 (Physics - Confident Drift):\n"
                "CANDIDATE: [Solves KVL loop equations confidently but completely ignores the 10 ohm series resistor in the battery branch explicitly stated in the problem.]\n"
                "EVALUATION: {\"accuracy_score\": 1, \"pedagogy_score\": 4, \"formatting_score\": 5, \"feedback_notes\": \"Severe physics hallucination. The KVL loop 3 equation completely ignores the 10 ohm resistor in series with the battery, leading to entirely incorrect currents. Confident but fundamentally flawed physical modeling.\"}\n\n"
                "EXAMPLE 4 (Chemistry - Visual Hallucination):\n"
                "CANDIDATE: [Explains Lewis dot transfer in text but generates no actual LaTeX Lewis structures, yet the Final Answer claims 'The electron transfer is shown in the Lewis symbol diagrams above'.]\n"
                "EVALUATION: {\"accuracy_score\": 2, \"pedagogy_score\": 2, \"formatting_score\": 3, \"feedback_notes\": \"Failed to render Lewis structures using LaTeX/ASCII. Hallucinates and references 'diagrams above' that do not actually exist in the output, which will severely confuse the student.\"}\n"
                "-------------------------\n\n"
                "Return ONLY a JSON response validating this format:\n"
                "{\n"
                "   \"accuracy_score\": <int 0-5>,\n"
                "   \"pedagogy_score\": <int 0-5>,\n"
                "   \"formatting_score\": <int 0-5>,\n"
                "   \"feedback_notes\": \"<string detailing exact mistakes if any>\"\n"
                "}"
            )
        
        user_prompt = f"""
        PROBLEM:
        ```json
        {json.dumps(problem_payload, indent=2)}
        ```
        
        ACTUAL ANSWER KEY (IF ANY): {actual_answer_key or "None Provided - Derive truth independently"}
        
        CANDIDATE SOLUTION:
        ```json
        {json.dumps(generated_solution, indent=2)}
        ```
        
        Score this candidate strictly. Output JSON ONLY.
        """
        
        try:
            # Extract image URLs from the problem payload if present
            image_urls = []
            if isinstance(problem_payload, dict):
                # NCERT format
                if "figure_info" in problem_payload and isinstance(problem_payload["figure_info"], list):
                    for fig in problem_payload["figure_info"]:
                        if "url" in fig and fig["url"]:
                            image_urls.append(fig["url"])
                # JEE format
                if "figure_url" in problem_payload and problem_payload["figure_url"]:
                    image_urls.append(problem_payload["figure_url"])
                if "option_figure_urls" in problem_payload and isinstance(problem_payload["option_figure_urls"], list):
                    for url in problem_payload["option_figure_urls"]:
                        if url:
                            image_urls.append(url)
                        
            response = self.generator.client.generate(
                model_config=self.generator.config.solver_model,
                prompt=user_prompt,
                system_instruction=system_prompt,
                image_urls=image_urls if image_urls else None
            )
            
            jtext = response.text.strip()
            # clean backticks
            if jtext.startswith("```json"):
                jtext = jtext.split("```json", 1)[1]
                if "```" in jtext:
                    jtext = jtext[:jtext.rfind("```")].strip()
            elif jtext.startswith("```"):
                jtext = jtext.split("```", 1)[1]
                if "```" in jtext:
                    jtext = jtext[:jtext.rfind("```")].strip()
                    
            parsed = json.loads(jtext)
            
            if mode == "accuracy_only":
                acc = int(parsed.get("accuracy_score", 0))
                ped = 0
                fmt = 0
                total = acc
                is_pass = (acc == 5)
            else:
                acc = int(parsed.get("accuracy_score", 0))
                ped = int(parsed.get("pedagogy_score", 0))
                fmt = int(parsed.get("formatting_score", 0))
                total = acc + ped + fmt
                # Binary verdict logic: >=13 passing AND fully accurate
                is_pass = (total >= 13) and (acc == 5)
            
            return EvaluationResult(
                accuracy_score=acc,
                pedagogy_score=ped,
                formatting_score=fmt,
                total_score=total,
                feedback_notes=parsed.get("feedback_notes", ""),
                is_pass=is_pass
            )
            
        except Exception as e:
            LOGGER.error(f"Evaluating failed: {e}")
             # Default fallback on error
            return EvaluationResult(0, 0, 0, 0, f"Evaluation script error: {str(e)}", False)

def get_evaluator() -> UniversalEvaluator:
    config = PipelineConfig()
    
    # ensure project_id and location exist on config for vertex
    if not hasattr(config, 'project_id') or not config.project_id:
        config.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "animated-rope-453904-j7")
    if not hasattr(config, 'location') or not config.location:
        config.location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        
    try:
        client = GeminiClient(config)
    except TypeError:
        # Fallback if old client init
        client = GeminiClient(config.project_id, config.location)
        
    return UniversalEvaluator(client, config)

def run_batch_evaluation():
    """
    Evaluates a random batch of NCERT solutions from the database.
    """
    import sys
    from pathlib import Path
    
    # Adjust path if script executed directly
    cwd = Path(__file__).resolve().parent
    extraction_dir = cwd.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
    if str(extraction_dir) not in sys.path:
        sys.path.insert(0, str(extraction_dir))
        
    from db_writer import JEEExtractionDBWriter
    
    evaluator = get_evaluator()
    db_writer = JEEExtractionDBWriter()
    
    LOGGER.info("Fetching a test batch from NCERT questiondata for evaluation...")
    query = """
        SELECT q.question_ref, c.class, c.subject, c.chaptertitle, q.content, q.solution 
        FROM questiondata q
        JOIN exercisedata e ON q.exerciseid = e.exerciseid
        JOIN chapterdata c ON e.chapterid = c.chapterid
        WHERE q.solution IS NOT NULL 
        LIMIT 5;
    """
    
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            batch = cur.fetchall()
            
    for row in batch:
        q_ref, cls_val, subj, chap, content, solution = row
        LOGGER.info(f"--- Evaluating {cls_val} {subj} {chap} | Q: {q_ref} ---")
        
        result = evaluator.evaluate_solution(
            problem_payload=content,
            generated_solution=solution
        )
        LOGGER.info(f"Verdict: {'PASS' if result.is_pass else 'FAIL'} | Accuracy: {result.accuracy_score}/5 | Pedagogy: {result.pedagogy_score}/5 | Format: {result.formatting_score}/5")
        LOGGER.info(f"Feedback: {result.feedback_notes}\n")

def run_db_evaluation(q_ref: str, cls: str = None, subject: str = None):
    """
    Evaluates a specific NCERT question by its question_ref, with optional class and subject filtering.
    """
    from jsonl_exporter import get_db_connection
    evaluator = get_evaluator()
    
    conn = get_db_connection()
    
    # Build query dynamically based on provided filters
    base_query = """
        SELECT q.question_ref, c.class, c.subject, c.chaptertitle, q.content, q.solution 
        FROM questiondata q
        JOIN exercisedata e ON q.exerciseid = e.exerciseid
        JOIN chapterdata c ON e.chapterid = c.chapterid
        WHERE q.question_ref = %s AND q.solution IS NOT NULL
    """
    
    params = [q_ref]
    if cls:
        base_query += " AND c.class = %s"
        params.append(cls)
    if subject:
        base_query += " AND c.subject ILIKE %s"
        params.append(subject)
        
    base_query += " LIMIT 1;"
    
    LOGGER.info(f"Fetching {q_ref} from NCERT questiondata (filters - class:{cls}, subject:{subject})...")
    
    with conn.cursor() as cur:
        cur.execute(base_query, tuple(params))
        row = cur.fetchone()
        
    if not row:
        LOGGER.error(f"Could not find question_ref '{q_ref}' with a non-null solution and the given filters.")
        return
        
    _, found_cls, found_subject, chapter, qc, solution = row
    LOGGER.info(f"--- Evaluating Q_REF: {q_ref} | Class: {found_cls} | Subject: {found_subject} | Chapter: {chapter} ---")
    
    result = evaluator.evaluate_solution(
        problem_payload=qc,
        generated_solution=solution,
        actual_answer_key=None
    )
    
    LOGGER.info(f"Score: Accuracy {result.accuracy_score}/5 | Pedagogy {result.pedagogy_score}/5 | Formatting {result.formatting_score}/5")
    LOGGER.info(f"Verdict Pass: {result.is_pass}")
    LOGGER.info(f"Feedback: {result.feedback_notes}\n")

def run_json_evaluation(json_path: str):
    """
    Evaluates a problem/solution block exported or provided independently in a JSON file.
    """
    evaluator = get_evaluator()
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    LOGGER.info(f"--- Evaluating from JSON file: {json_path} ---")
    problem_payload = data.get("content", data.get("problem_payload", {}))
    generated_solution = data.get("solution", data.get("generated_solution", {}))
    ans_key = data.get("answer_key")
    
    result = evaluator.evaluate_solution(
        problem_payload=problem_payload,
        generated_solution=generated_solution,
        actual_answer_key=ans_key
    )
    
    LOGGER.info(f"Score: Accuracy {result.accuracy_score}/5 | Pedagogy {result.pedagogy_score}/5 | Formatting {result.formatting_score}/5")
    LOGGER.info(f"Verdict Pass: {result.is_pass}")
    LOGGER.info(f"Feedback: {result.feedback_notes}\n")

# ---------------------------------------------------------------------------
# Evaluation Gate (state-machine promotion)
# ---------------------------------------------------------------------------
# Pulls every row at --target-status, scores it with the Universal Evaluator,
# and promotes passing rows to --pass-status. The GOLD gate of the Runbook:
#   APPROVED -> APPROVED_GOLD  (mode=full, strict 5/5/5)
# The same gate, parameterised, also serves the (deferred) accuracy gate:
#   MATH_REGENERATED -> MATH_PASSED  (mode=accuracy_only)

GATE_SOURCES = {
    "ncert": {
        "table": "questiondata", "id_col": "questionid",
        "content_col": "content", "solution_col": "solution", "answer_key_col": "answer_key",
    },
    "jee": {
        "table": "jee_question_bank", "id_col": "id",
        "content_col": "question_content", "solution_col": "solution", "answer_key_col": "answer_key",
    },
}


def execute_write(db_client, sql, params, retries=4):
    """Run one write, reconnecting if the DB connection was dropped.

    Azure can close the connection during the long gaps between judge calls;
    DatabaseClient.connect() reuses a cached handle whose `.closed` flag stays
    stale after a server-side drop. On OperationalError/InterfaceError we force a
    fresh connection and retry — each write is sub-second, so a fresh handle works.
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
            db_client._connection = None
            time.sleep(min(2 * attempt, 10))
    raise last_err


def run_gate(args):
    """Evaluate rows at --target-status; promote passers, optionally demote failers."""
    import uuid

    src = GATE_SOURCES.get(args.source)
    if not src:
        LOGGER.error(f"Unknown --source '{args.source}'. Use one of: {list(GATE_SOURCES)}")
        return

    run_id = str(uuid.uuid4())[:8]
    rule = "accuracy == 5" if args.mode == "accuracy_only" else "strict 5/5/5"
    LOGGER.info(
        f"[Gate {run_id}] source={args.source} ({src['table']}) | target={args.target_status} | "
        f"mode={args.mode} ({rule}) | pass->{args.pass_status} | "
        f"fail->{args.fail_status or '(unchanged)'} | limit={args.limit} | dry_run={args.dry_run}"
    )

    evaluator = get_evaluator()
    db = DatabaseClient(use_managed_identity=True)

    log_dir = project_root / "TempLocal"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"gate_{args.source}_{args.target_status}_{run_id}.jsonl"

    # Fetch the target rows.
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {src['id_col']}, {src['content_col']}, {src['solution_col']}, {src['answer_key_col']} "
                f"FROM {src['table']} "
                f"WHERE review_status = %s AND {src['solution_col']} IS NOT NULL "
                f"ORDER BY {src['id_col']} LIMIT %s",
                (args.target_status, args.limit),
            )
            rows = cur.fetchall()

    if not rows:
        LOGGER.warning(f"[Gate {run_id}] No rows found at status '{args.target_status}'.")
        return

    LOGGER.info(f"[Gate {run_id}] Evaluating {len(rows)} row(s)...")
    promoted = not_gold = errored = 0

    # Writes go through execute_write() — Azure can drop the connection mid-loop.
    for rid, content, solution, answer_key in rows:
            if isinstance(content, str):
                try: content = json.loads(content)
                except Exception: pass
            if isinstance(solution, str):
                try: solution = json.loads(solution)
                except Exception: pass

            result = evaluator.evaluate_solution(
                problem_payload=content if isinstance(content, dict) else {},
                generated_solution=solution if isinstance(solution, dict) else {},
                actual_answer_key=str(answer_key) if answer_key else None,
                mode=args.mode,
            )

            scoreline = f"acc={result.accuracy_score} ped={result.pedagogy_score} fmt={result.formatting_score}"
            is_gold = (result.accuracy_score == 5) if args.mode == "accuracy_only" else result.is_gold

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": run_id, "source": args.source, "id": rid,
                    "accuracy": result.accuracy_score, "pedagogy": result.pedagogy_score,
                    "formatting": result.formatting_score, "is_gold": is_gold,
                    "feedback": result.feedback_notes,
                }, ensure_ascii=False) + "\n")

            # Distinguish a genuine evaluator failure from a real low score.
            if result.feedback_notes.startswith("Evaluation script error"):
                LOGGER.error(f"[Gate {run_id}] id={rid} EVAL ERROR — left unchanged ({result.feedback_notes})")
                errored += 1
                continue

            if is_gold:
                LOGGER.info(f"[Gate {run_id}] id={rid} GOLD ({scoreline}) -> {args.pass_status}")
                if not args.dry_run:
                    execute_write(db,
                        f"UPDATE {src['table']} SET review_status = %s WHERE {src['id_col']} = %s",
                        (args.pass_status, rid))
                promoted += 1
            else:
                tail = f" -> {args.fail_status}" if args.fail_status else ""
                LOGGER.info(f"[Gate {run_id}] id={rid} NOT gold ({scoreline}){tail}")
                if args.fail_status and not args.dry_run:
                    execute_write(db,
                        f"UPDATE {src['table']} SET review_status = %s WHERE {src['id_col']} = %s",
                        (args.fail_status, rid))
                not_gold += 1

    LOGGER.info(f"[Gate {run_id}] Done. gold={promoted} | not_gold={not_gold} | eval_errors={errored}")
    LOGGER.info(f"[Gate {run_id}] Verdict log: {log_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Universal Evaluator — single-row checks and the state-machine GOLD gate")
    # --- single-row / debug modes ---
    parser.add_argument("--batch", action="store_true", help="Evaluate 5 random NCERT solutions (debug)")
    parser.add_argument("--q-ref", type=str, help="Evaluate one NCERT question by question_ref (e.g. '11.1')")
    parser.add_argument("--class", dest="cls", type=str, help="Filter by class (with --q-ref)")
    parser.add_argument("--json-file", type=str, help="Evaluate a problem defined in a JSON file")
    # --- gate mode ---
    parser.add_argument("--target-status", dest="target_status", type=str,
                        help="GATE MODE: evaluate every row at this review_status and promote passers.")
    parser.add_argument("--source", type=str, choices=["ncert", "jee"],
                        help="Gate mode: ncert=questiondata, jee=jee_question_bank. Required with --target-status.")
    parser.add_argument("--subject", type=str, help="Filter by subject (with --q-ref)")
    parser.add_argument("--mode", type=str, choices=["full", "accuracy_only"], default="full",
                        help="Eval mode. full = 3-D strict 5/5/5 (GOLD gate); accuracy_only = accuracy==5.")
    parser.add_argument("--pass-status", dest="pass_status", type=str, default="APPROVED_GOLD",
                        help="Gate mode: review_status written to a passing row (default APPROVED_GOLD).")
    parser.add_argument("--fail-status", dest="fail_status", type=str, default=None,
                        help="Gate mode: review_status written to a failing row (default: leave unchanged).")
    parser.add_argument("--limit", type=int, default=50, help="Gate mode: max rows to evaluate (default 50).")
    parser.add_argument("--dry-run", action="store_true", help="Gate mode: evaluate + log only, no DB writes.")
    args = parser.parse_args()

    if args.target_status:
        if not args.source:
            parser.error("--source (ncert|jee) is required with --target-status")
        run_gate(args)
    elif args.batch:
        run_batch_evaluation()
    elif args.q_ref:
        run_db_evaluation(args.q_ref, args.cls, args.subject)
    elif args.json_file:
        run_json_evaluation(args.json_file)
    else:
        parser.print_help()
