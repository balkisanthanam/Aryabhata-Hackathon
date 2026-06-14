import json
import logging
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from config import PipelineConfig, GeminiModelConfig
from gemini_client import GeminiClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def build_judge_prompt(question_text: str, old_solution: str, new_solution: str) -> str:
    return f"""
You are an expert STEM teacher acting as an impartial judge. Your task is to compare two solutions to a given question.
The 'Old Solution' was generated with access to the entire textbook chapter.
The 'New Solution' was generated using a localized vector context approach and a self-correction pass.

You must evaluate if the New Solution matches or exceeds the quality of the Old Solution based on:
1. Mathematical/Scientific Accuracy (Correct final answer and valid intermediate steps)
2. Logical Leaps (Lack of missing steps)
3. Clarity and Formatting

Question:
{question_text}

---
Old Solution (Production DB):
{old_solution}

---
New Solution (Local Run):
{new_solution}

---
Provide a JSON object with your evaluation using EXACTLY this schema:
{{
  "old_score": <int 1-10>,
  "new_score": <int 1-10>,
  "winner": "Old" | "New" | "Tie",
  "rationale": "<Detailed explanation of why. Did the new solution miss anything critical because it didn't have the full text?>"
}}
"""

def extract_solution_text_from_blocks(solution_obj: Dict) -> str:
    """Helper to convert the JSON Solution format back to a readable string."""
    out = []
    for step in solution_obj.get("steps", []):
        out.append(f"Step {step.get('step_number')}: {step.get('explanation')}")
        if step.get('latex_formula'):
            out.append(f"Formula: {step.get('latex_formula')}")
    out.append(f"Final Answer: {solution_obj.get('final_answer')}")
    return "\n".join(out)

def main():
    parser = argparse.ArgumentParser(description="A/B Test Judge comparing Prod DB vs Local JSON solutions.")
    parser.add_argument("--json-path", type=str, required=True, help="Path to the Local Output solutions JSON (e.g. Output/keph205_solutions.json)")
    parser.add_argument("--limit", type=int, default=5, help="Number of solutions to compare")
    args = parser.parse_args()
    
    config = PipelineConfig.from_env()
    client = GeminiClient(config)
    
    from db_client import get_db_client
    db_client = get_db_client(use_managed_identity=True)
    
    # Load Local JSON
    json_path = Path(args.json_path)
    if not json_path.exists():
        logger.error(f"Cannot find JSON file: {json_path}")
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        local_data = json.load(f)
        
    # Standardize flat vs grouped JSON formats
    local_solutions = []
    if "solutions" in local_data and isinstance(local_data["solutions"], list):
        local_solutions = local_data["solutions"]
    elif "exercises" in local_data:
        for ex in local_data["exercises"]:
            local_solutions.extend(ex.get("solutions", []))
            
    if not local_solutions:
        logger.error("No solutions found in the JSON file.")
        sys.exit(1)
        
    logger.info(f"Loaded {len(local_solutions)} solutions from {json_path.name}")
    
    comparisons_made = 0
    results = []
    
    for sol in local_solutions:
        if comparisons_made >= args.limit:
            break
            
        full_q_ref = sol.get("question_id")
        q_text = sol.get("question_text", "Unknown Question")
        new_solution_text = extract_solution_text_from_blocks(sol)
        
        # We query Postgres for the existing solution using the exact pipeline_id matching logic.
        conn = db_client.connect()
        prod_solution_json = None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT q.solution 
                FROM questiondata q
                JOIN exercisedata e ON q.exerciseid = e.exerciseid
                WHERE (UPPER(REPLACE(REPLACE(e.exercise, ' ', '_'), '.', '_')) || '_Q' || q.question_ref) = %s
                   OR q.question_ref = %s
            """, (full_q_ref, full_q_ref))
            rows = cur.fetchall()
            
            # Use the first non-null solution found for this exact pipeline_id
            for row in rows:
                if row and row[0]:
                    prod_solution_json = row[0]
                    break
                
        if not prod_solution_json:
            logger.warning(f"Question {full_q_ref} not found in DB or has no solution. Skipping comparison.")
            continue
            
        old_solution_text = extract_solution_text_from_blocks(prod_solution_json)
        
        logger.info(f"Comparing Solution for {full_q_ref}...")
        prompt = build_judge_prompt(q_text, old_solution_text, new_solution_text)
        
        try:
            # We configure Gemini to guarantee JSON output
            judge_config = GeminiModelConfig(
                model_id=config.solver_model.model_id,
                temperature=0.0
            ) 
            
            response = client.generate(
                model_config=judge_config,
                prompt=prompt
            )
            
            # Sanitize response in case it's wrapped in markdown
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            evaluation = json.loads(raw_text.strip(), strict=False)
            
            results.append({
                "question_id": full_q_ref,
                "winner": evaluation.get("winner"),
                "old_score": evaluation.get("old_score"),
                "new_score": evaluation.get("new_score"),
                "rationale": evaluation.get("rationale")
            })
            logger.info(f"Result for {full_q_ref}: Winner ({evaluation.get('winner')}) | Reason: {evaluation.get('rationale')}")
            comparisons_made += 1
            
        except Exception as e:
            logger.error(f"Failed to judge question {full_q_ref}: {e}")
            
    # Print Summary
    logger.info("="*60)
    logger.info("A/B TEST SUMMARY")
    logger.info("="*60)
    winner_counts = {"Old": 0, "New": 0, "Tie": 0}
    for r in results:
        winner = r["winner"]
        if winner in winner_counts:
            winner_counts[winner] += 1
            
    for k, v in winner_counts.items():
        logger.info(f"{k} Wins: {v}")

    db_client.close()
    
if __name__ == "__main__":
    main()
