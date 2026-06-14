"""
Evaluate Saved Generations
Pulls existing generated solutions from `jee_question_bank` and evaluates them using UniversalEvaluator.
This is meant for post-generation representative sampling to calculate precision/pedagogy metrics securely.
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Setup Paths
cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
jee_dir = project_root / "pipelines" / "JEEAscentPipeline"

if str(extraction_dir) not in sys.path:
    sys.path.insert(0, str(extraction_dir))
if str(jee_dir) not in sys.path:
    sys.path.insert(0, str(jee_dir))

from evaluator_engine import get_evaluator, EvaluationResult
from db_writer import JEEExtractionDBWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("evaluate_saved")

def fetch_evaluated_batch(db_writer: JEEExtractionDBWriter, limit: int = 25, status_filter: str = "UNVERIFIED"):
    status_clause = "review_status IN ('UNVERIFIED', 'APPROVED')"
    if status_filter == "UNVERIFIED":
        status_clause = "review_status = 'UNVERIFIED'"
    elif status_filter == "APPROVED":
        status_clause = "review_status = 'APPROVED'"

    query = f"""
        SELECT id, nta_question_id, subject, question_content, answer_key, solution, review_status 
        FROM jee_question_bank 
        WHERE is_generated = TRUE AND solution IS NOT NULL
          AND {status_clause}
        ORDER BY RANDOM()
        LIMIT %s
    """
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]
    return rows

def mark_approved(db_writer: JEEExtractionDBWriter, question_id: int):
    query = "UPDATE jee_question_bank SET review_status = 'APPROVED' WHERE id = %s"
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (question_id,))
        conn.commit()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25, help="Number of questions to evaluate")
    parser.add_argument("--status", type=str, choices=["UNVERIFIED", "APPROVED", "ALL"], default="UNVERIFIED", help="Filter by current DB review_status")
    parser.add_argument("--auto-approve", action="store_true", help="Automatically flip DB status to APPROVED if eval passes 100%")
    parser.add_argument("--label", type=str, default="DB Sample Evaluation", help="Name of the run")
    args = parser.parse_args()

    evaluator = get_evaluator()
    db_writer = JEEExtractionDBWriter()

    questions = fetch_evaluated_batch(db_writer, limit=args.limit, status_filter=args.status)
    if not questions:
        LOGGER.error("No generated questions found in the database. Are you sure `is_generated = TRUE`?")
        sys.exit(1)

    LOGGER.info(f"Targeting {len(questions)} pre-generated questions for evaluation.")

    results = []

    for idx, row in enumerate(questions, 1):
        q_id = row['id']
        ans_key = row.get('answer_key')
        
        qc = row.get('question_content', {})
        if isinstance(qc, str):
            try: qc = json.loads(qc)
            except: pass
            
        sol = row.get('solution', {})
        if isinstance(sol, str):
            try: sol = json.loads(sol)
            except: pass

        LOGGER.info(f"[{idx}/{len(questions)}] Evaluating Question {q_id}...")

        # Construct payload for the evaluator
        payload_dict = {
            "problem_text": qc.get('raw_text', ''),
            "options": qc.get('options', [])
        }
        if ans_key:
            payload_dict["actual_answer_key"] = ans_key

        eval_result = evaluator.evaluate_solution(
            problem_payload=payload_dict,
            generated_solution=sol,
            actual_answer_key=ans_key
        )

        if args.auto_approve and eval_result.is_pass and row.get('review_status') != 'APPROVED':
            mark_approved(db_writer, q_id)
            LOGGER.info(f" -> Automatically APPROVED Question {q_id} in DB.")

        LOGGER.info(f"Verdict: {'PASS' if eval_result.is_pass else 'FAIL'} | Acc: {eval_result.accuracy_score} | Ped: {eval_result.pedagogy_score} | Fmt: {eval_result.formatting_score}")

        results.append({
            "question_id": q_id,
            "metrics": {
                "is_pass": eval_result.is_pass,
                "accuracy": eval_result.accuracy_score,
                "pedagogy": eval_result.pedagogy_score,
                "formatting": eval_result.formatting_score,
                "feedback": eval_result.feedback_notes
            }
        })

    # Summary
    passes = sum(1 for r in results if r["metrics"]["is_pass"])
    pass_rate = (passes / len(results)) * 100
    avg_acc = sum(r["metrics"]["accuracy"] for r in results) / len(results)
    avg_ped = sum(r["metrics"]["pedagogy"] for r in results) / len(results)
    avg_fmt = sum(r["metrics"]["formatting"] for r in results) / len(results)

    LOGGER.info("-" * 40)
    LOGGER.info(f"EVALUATION COMPLETE: {args.label}")
    LOGGER.info(f"Analyzed {len(results)} existing DB generations")
    LOGGER.info(f"Pass Rate: {pass_rate:.1f}% ({passes}/{len(results)})")
    LOGGER.info(f"Average Accuracy:   {avg_acc:.2f} / 5.0")
    LOGGER.info(f"Average Pedagogy:   {avg_ped:.2f} / 5.0")
    LOGGER.info(f"Average Formatting: {avg_fmt:.2f} / 5.0")
    LOGGER.info("-" * 40)

    # Save details
    run_dir = cwd / "runs"
    run_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = run_dir / f"DB_Evaluation_{ts}.json"

    export_payload = {
        "run_label": args.label,
        "timestamp": ts,
        "summary": {
            "total": len(results),
            "pass_rate": pass_rate,
            "avg_accuracy": avg_acc,
            "avg_pedagogy": avg_ped,
            "avg_formatting": avg_fmt
        },
        "details": results
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, indent=2, ensure_ascii=False)
        
    LOGGER.info(f"Saved highly detailed evaluation payload to: {out_file}")

if __name__ == "__main__":
    main()