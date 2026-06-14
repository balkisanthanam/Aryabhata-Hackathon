"""
Activity: Update the solution_evaluations record with final status and feedback.
"""
import logging
from utils.db import update_evaluation


def update_evaluation_activity(input_data: dict) -> dict:
    """
    Update the evaluation record in the database.
    
    Args:
        input_data: {
            "job_id": str,
            "status": str (COMPLETED or FAILED),
            "feedback_json": dict (optional),
            "chapter_id": int (optional, resolved chapter ID),
            "chapter_title": str (optional, resolved chapter title),
            "chapter_number": str (optional, resolved chapter number),
            "pdffileurl": str (optional, chapter PDF URL),
        }
    
    Returns:
        {"success": bool}
    """
    job_id = input_data["job_id"]
    status = input_data["status"]
    feedback_json = input_data.get("feedback_json")

    logging.info(f"Activity update_evaluation: job_id={job_id}, status={status}")

    try:
        success = update_evaluation(
            job_id, status, feedback_json,
            chapter_id=input_data.get("chapter_id"),
            chapter_title=input_data.get("chapter_title"),
            chapter_number=input_data.get("chapter_number"),
            pdffileurl=input_data.get("pdffileurl"),
        )
        if success:
            logging.info(f"Job {job_id}: updated to {status}")
        else:
            logging.warning(f"Job {job_id}: update returned no rows affected")
        return {"success": success}
    except Exception as e:
        logging.error(f"Job {job_id}: failed to update — {e}")
        raise
