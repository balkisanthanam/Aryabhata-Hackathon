import os
import sys
import json
import argparse
import logging
from pathlib import Path

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
from config import PipelineConfig
from evaluator_engine import UniversalEvaluator

def run_baseline(args):
    LOGGER.info(f"Starting NCERT Baseline Evaluation for Class {args.cls}, Subject {args.subject}")
    
    # Initialize clients
    db_client = DatabaseClient(use_managed_identity=True)
    config = PipelineConfig()
    gemini = GeminiClient(config)
    evaluator = UniversalEvaluator(gemini, config)
    
    results = []
    
    # Fetch questions with answers
    with db_client.connect() as conn:
        with conn.cursor() as cur:
            # If update_db is set, we only fetch LEGACY rows to process through the gate
            status_filter = "AND q.review_status = 'LEGACY'" if args.update_db else ""
            
            query = f"""
                SELECT q.questionid, c.chapternumber, e.exercise, q.question_ref, q.content, q.solution, q.answer_key
                FROM questiondata q
                JOIN exercisedata e ON q.exerciseid = e.exerciseid
                JOIN chapterdata c ON e.chapterid = c.chapterid
                WHERE c.class = %s 
                  AND c.subject ILIKE %s
                  AND q.solution IS NOT NULL
                  {status_filter}
                ORDER BY e.exerciseid, q.questionid
                LIMIT %s
            """
            cur.execute(query, (args.cls, f"%{args.subject}%", args.limit))
            rows = cur.fetchall()
            
    if not rows:
        LOGGER.warning("No rows found matching criteria.")
        return
        
    LOGGER.info(f"Found {len(rows)} questions to evaluate.")
    
    for row in rows:
        qid, chap, ex, q_ref, content_json, solution_json, ans_key = row
        LOGGER.info(f"Evaluating QID: {qid} | Ch: {chap} | Ex: {ex} | Ref: {q_ref}")
        
        try:
            eval_res = evaluator.evaluate_solution(content_json, solution_json, str(ans_key), mode=args.mode)
            
            res_dict = {
                "questionid": qid,
                "chapter": chap,
                "exercise": ex,
                "question_ref": q_ref,
                "evaluation": eval_res.to_dict()
            }
            results.append(res_dict)
            
            LOGGER.info(f"Score: {eval_res.total_score}/15 - Pass: {eval_res.is_pass}")
            
            # --- START DB UPDATE LOGIC ---
            if args.update_db:
                new_status = 'MATH_PASSED' if eval_res.is_pass else 'REJECTED'
                with db_client.connect() as update_conn:
                    with update_conn.cursor() as update_cur:
                        update_cur.execute(
                            "UPDATE questiondata SET review_status = %s WHERE questionid = %s",
                            (new_status, qid)
                        )
                    update_conn.commit()
                LOGGER.info(f"Updated QID {qid} status to -> {new_status}")
            # --- END DB UPDATE LOGIC ---
            
        except Exception as e:
            LOGGER.error(f"Failed to evaluate QID {qid}: {e}")
            
    # Export to JSON
    output_file = project_root / "TempLocal" / f"ncert_baseline_{args.cls}_{args.subject}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    LOGGER.info(f"Saved {len(results)} baseline evaluations to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run baseline evaluation on legacy NCERT solutions.")
    parser.add_argument("--class", dest="cls", required=True, help="Class (e.g., 11)")
    parser.add_argument("--subject", required=True, help="Subject (e.g., Physics, Maths)")
    parser.add_argument("--limit", type=int, default=10, help="Max number of items to evaluate")
    parser.add_argument("--mode", choices=["full", "accuracy_only"], default="full", help="Evaluation mode")
    parser.add_argument("--update-db", action="store_true", help="If flag is set, script will write MATH_PASSED or REJECTED to review_status column.")
    args = parser.parse_args()
    
    run_baseline(args)
