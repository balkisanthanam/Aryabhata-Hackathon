"""
JEE Solution Generation Pipeline (Bootstrap via Pro)

This script implements Milestone M2.2 of the E2E Solution Model Plan.
It pulls questions from `jee_question_bank` that lack solutions, generates a structured AI solution using the "Universal Payload" (Problem text + images + optional context) and the Gemini 3.1 Pro "Teacher" model via a 2-pass critique loop, and writes the JSONB solution back to the DB to serve as Ground Truth data for tuning.
"""

import sys
import os
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List
import textwrap

# Ensure settings are loaded
cwd = Path(__file__).resolve().parent
if str(cwd) not in sys.path:
    sys.path.insert(0, str(cwd))

from settings_loader import load_local_settings
load_local_settings()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import shared modules from SchoolDataExtraction
project_root = Path(__file__).resolve().parent.parent.parent
multi_step_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
sys.path.insert(0, str(multi_step_dir))

from gemini_client import GeminiClient
from config import PipelineConfig, flash_assembly_config
from solver_engine import GoldenGenerator
from gate import solve_with_gate

# Import our DB writer
from db_writer import JEEExtractionDBWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

def fetch_batch_from_db(db_writer: JEEExtractionDBWriter, limit: int = 10, offset: int = 0, year: int = None, shift: str = None, subject: str = None, exam_date: str = None) -> List[Dict[str, Any]]:
    # Pick tier 3 questions that lack solutions but have an answer key for certainty
    # State machine: Only grab items where retry_count < 3 to avoid infinite loops on fatally broken questions.
    clauses = ["solution IS NULL", "question_content IS NOT NULL", "is_generated = FALSE", "answer_key IS NOT NULL", "retry_count < 3"]
    params = []
    
    if year:
        clauses.append("year = %s")
        params.append(year)
    if shift:
        clauses.append("shift ILIKE %s")
        params.append(f"%{shift}%")
    if subject:
        clauses.append("subject ILIKE %s")
        params.append(subject)
    if exam_date:
        clauses.append("dateofexam = %s::date")
        params.append(exam_date)
        
    where_clause = " AND ".join(clauses)
    
    query = f"""
        SELECT id, nta_question_id, subject, question_content, answer_key 
        FROM jee_question_bank 
        WHERE {where_clause}
        ORDER BY id ASC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(columns, r)) for r in rows]

def update_solution_in_db(db_writer: JEEExtractionDBWriter, q_id: int, solution_json: str,
                          review_status: str = 'UNVERIFIED'):
    query = """
        UPDATE jee_question_bank
        SET solution = %s::jsonb, is_generated = TRUE, review_status = %s
        WHERE id = %s
    """
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (solution_json, review_status, q_id))
        conn.commit()

def build_smart_context_payload(q_id: int, db_writer: JEEExtractionDBWriter) -> str:
    """
    Fetches the DB tags for the given question and retrieves NCERT conceptual context.
    Returns a formatted markdown block to add to the problem payload.
    """
    query = """
        SELECT nch.concept_title, nch.embedding_text, nch.key_formulas, nch.ncert_solved_example
        FROM jee_question_tags jqt
        JOIN ncert_concept_hierarchy nch ON jqt.concept_id = nch.id
        WHERE jqt.question_id = %s
        ORDER BY jqt.similarity_score DESC
        LIMIT 5
    """
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (q_id,))
            rows = cur.fetchall()
            
    if not rows:
        return ""
        
    context_blocks = []
    for r in rows:
        title, emb_txt, formulas, example = r
        block = f"### Concept: {title}\n"
        if emb_txt: block += f"**Theory**: {emb_txt}\n"
        if formulas: block += f"**Formulas**: {formulas}\n"
        if example: block += f"**Example**: {example}\n"
        context_blocks.append(block)
        
    return "\n".join(context_blocks)

def main():
    parser = argparse.ArgumentParser(description="JEE Solution Generation Pipeline")
    parser.add_argument("--year", type=int, help="Scope generation to a specific year")
    parser.add_argument("--shift", type=str, help="Scope generation to a specific shift (e.g. 'Morning')")
    parser.add_argument("--subject", type=str, help="Scope generation to a specific subject (e.g. 'Physics')")
    parser.add_argument("--exam-date", type=str, help="Scope generation to a specific exam date (e.g., '2024-01-27')")
    parser.add_argument("--limit", type=int, default=100, help="Total number of questions to process (default: 100)")
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=10, help="Number of questions to fetch per batch (default: 10)")
    parser.add_argument("--use-assembly", action="store_true", help="Use the 3-pass assembly line (Solver->Tutor->Formatter) instead of single-pass generation")
    parser.add_argument("--solver-tier", dest="solver_tier", choices=["pro", "flash"], default="pro",
                        help="'flash' uses Flash Assembly Line + answer-key gate (default: 'pro', byte-identical)")
    parser.add_argument("--use-smart-context", action="store_true", help="Inject Smart Context joined from jee_question_tags")
    parser.add_argument("--prompt-filename", type=str, default="jee_solver_prompt.md", help="Which prompt template to use")
    args = parser.parse_args()

    db_writer = JEEExtractionDBWriter()
    db_writer.refresh_token()
    
    config = PipelineConfig()
    
    project_id = getattr(config, 'project_id', None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = getattr(config, 'location', None) or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if not project_id:
        LOGGER.error("GOOGLE_CLOUD_PROJECT not set. Exiting to prevent billing hardcoded fallback projects.")
        sys.exit(1)
        
    # Ensure config has these set
    config.project_id = project_id
    config.location = location
        
    client = GeminiClient(config)
    generator = GoldenGenerator(client, config)

    # Flash tier: built once, reused per row (default PromptSet = JEE persona, byte-identical)
    flash_gen = None
    pro_gen = None
    if args.solver_tier == "flash":
        flash_gen = GoldenGenerator(client, flash_assembly_config())
        pro_gen   = GoldenGenerator(client, config)   # Pro config for gate fallback

    prompt_file = Path(__file__).resolve().parent / "prompts" / args.prompt_filename
    if not prompt_file.exists():
        LOGGER.warning(f"Solver prompt not found at {prompt_file}, using default.")
        sys.exit(1)
        
    with open(prompt_file, "r") as f:
        system_prompt_template = f.read()

    # Target bulk bootstrapping parameters driven by CLI args
    TOTAL_TARGET = args.limit
    BATCH_SIZE = args.batch_size
    
    processed = 0
    offset = 0
    while processed < TOTAL_TARGET:
        batch = fetch_batch_from_db(db_writer, limit=BATCH_SIZE, offset=offset, year=args.year, shift=args.shift, subject=args.subject, exam_date=args.exam_date)
        if not batch:
            LOGGER.info("No more questions lacking solutions. Done.")
            break
            
        LOGGER.info(f"Fetched {len(batch)} questions for solving. Target progress {processed}/{TOTAL_TARGET}.")
        
        for row in batch:
            q_id = row['id']
            subject = row.get('subject', 'Unknown')
            answer_key = row.get('answer_key')
            
            LOGGER.info(f"Processing question {q_id} ({subject}) - NTA ID: {row.get('nta_question_id')}")
            
            qc = row.get('question_content', {})
            if isinstance(qc, str):
                try:
                    qc = json.loads(qc)
                except Exception:
                    LOGGER.warning(f"Could not parse question_content for Q {q_id}")
                    continue
                    
            problem_text = qc.get('raw_text', '')
            options = qc.get('options', [])
            
            # Key-blind base payload (D2: answer_key goes only to the gate, never the prompt)
            payload_dict = {
                "problem_text": problem_text,
                "options": options,
            }

            if args.use_smart_context:
                context_block = build_smart_context_payload(q_id, db_writer)
                if context_block:
                    payload_dict["ncert_theory_context"] = context_block

            image_urls = []
            if qc.get('figure_url'):
                image_urls.append(qc['figure_url'])

            if qc.get('option_figure_urls'):
                for o_url in qc['option_figure_urls']:
                     if o_url: image_urls.append(o_url)

            # KI-3: figure_url is NULL on 100% of jee_question_bank rows — the content
            # flag (not bool(image_urls)) is the correct D4 router signal.
            row_has_figure = bool(qc.get('has_figure'))

            system_prompt = system_prompt_template.replace("{{SUBJECT}}", subject)

            # Pro tier: re-add answer key (key-fed, byte-identical to prior behavior).
            # M2.2: "Do not assume an official answer key is always available."
            if args.solver_tier == "pro" and answer_key:
                payload_dict["actual_answer_key"] = answer_key

            user_prompt = f"Solve the following JEE {subject} problem. Only return the solution JSON object.\n\nProblem Payload:\n```json\n{json.dumps(payload_dict, indent=2)}\n```\n"

            try:
                if args.solver_tier == "flash":
                    LOGGER.info(f"Q {q_id}: flash gate | has_figure={row_has_figure} | {len(image_urls)} img(s)")
                    sol, review_status = solve_with_gate(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        answer_key=answer_key,
                        options=options,
                        image_urls=image_urls or None,
                        flash_generator=flash_gen,
                        pro_generator=pro_gen,
                        source="jee",
                        has_figure=row_has_figure,
                    )
                    solution_text = sol.text.strip()
                else:
                    LOGGER.info(f"Sending prompt to Gemini with {len(image_urls)} images... (Assembly Line: {args.use_assembly})")
                    if args.use_assembly:
                        # 3-pass assembly line — pro tier, key-fed (byte-identical)
                        response = generator.generate_assembly_line(
                            prompt=user_prompt,
                            system_prompt=system_prompt,
                            image_urls=image_urls if image_urls else None
                        )
                    else:
                        # Single pass — pro tier, key-fed (byte-identical)
                        response = generator.client.generate(
                            model_config=generator.config.solver_model,
                            prompt=user_prompt,
                            system_instruction=system_prompt,
                            image_urls=image_urls if image_urls else None
                        )
                    solution_text = response.text.strip()
                    review_status = 'UNVERIFIED'

                # Reuse canonical parse logic verbatim (G4: markdown strip + sanitize fallback)
                if solution_text.startswith("```json"):
                    solution_text = solution_text.split("```json", 1)[1]
                    if solution_text.rfind("```") != -1:
                        solution_text = solution_text[:solution_text.rfind("```")].strip()
                elif solution_text.startswith("```"):
                    solution_text = solution_text.split("```", 1)[1]
                    if solution_text.rfind("```") != -1:
                        solution_text = solution_text[:solution_text.rfind("```")].strip()

                try:
                    parsed = json.loads(solution_text)
                except json.JSONDecodeError as de:
                    LOGGER.warning(f"Initial JSON decode failed, attempting to sanitize escapes for Q {q_id}...")
                    sanitized_text = generator._sanitize_json_escapes(solution_text)
                    parsed = json.loads(sanitized_text)

                update_solution_in_db(db_writer, q_id, json.dumps(parsed), review_status)
                LOGGER.info(f"Successfully saved solution for Q {q_id} → {review_status}")
                processed += 1
                
                if processed >= TOTAL_TARGET:
                     break
                
            except Exception as e:
                LOGGER.error(f"Failed solving Q {q_id}: {e}")
                # State machine update: advance retry_count. If >= 3, mark as GENERATION_FAILED
                query = """
                    UPDATE jee_question_bank 
                    SET retry_count = retry_count + 1,
                        review_status = CASE WHEN retry_count >= 2 THEN 'GENERATION_FAILED' ELSE review_status END,
                        is_generated = CASE WHEN retry_count >= 2 THEN TRUE ELSE FALSE END
                    WHERE id = %s
                """
                with db_writer.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (q_id,))
                    conn.commit()

if __name__ == "__main__":
    main()
