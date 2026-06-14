"""
Activity: Read evaluation record from DB and set to PROCESSING.
"""
import logging
from utils.db import read_evaluation


def read_evaluation_activity(job_id: str) -> dict:
    """
    Read a solution_evaluations record by job_id.
    Atomically transitions PENDING → PROCESSING.
    
    Returns:
        Record dict if found and transitioned, or {"skip": True} if not eligible.
    """
    logging.info(f"Activity read_evaluation: job_id={job_id}")
    
    record = read_evaluation(job_id)
    
    if record is None:
        logging.warning(f"Job {job_id}: not found or already processed, skipping")
        return {"skip": True, "reason": "Not found or not in PENDING state"}
    
    logging.info(
        f"Job {job_id}: read successfully. "
        f"Path={'text_ref' if record.get('problem_text_ref') else 'image_ref'}, "
        f"subject={record.get('subject')}, chapter={record.get('chapter_title')}"
    )
    return record
