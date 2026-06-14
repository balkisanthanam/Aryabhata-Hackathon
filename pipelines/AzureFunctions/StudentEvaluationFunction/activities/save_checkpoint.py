"""
Activity: Save a pipeline checkpoint step to the DB.
Wraps utils/checkpoint.save_step for use as a Durable Functions activity.
"""
import logging
from utils.checkpoint import save_step


def save_checkpoint_activity(input_data: dict) -> dict:
    """
    Save a checkpoint for a pipeline step.

    Args:
        input_data: {
            "job_id": str,
            "step_name": str,
            "status": str ("started" | "completed" | "failed"),
            "result_summary": dict (optional),
            "model": str (optional),
            "prompt_version": str (optional),
            "token_usage": dict (optional),
            "artifact_urls": list (optional),
            "error": str (optional),
            "duration_ms": int (optional)
        }

    Returns:
        {"success": True}
    """
    job_id = input_data["job_id"]
    step_name = input_data["step_name"]
    status = input_data["status"]

    logging.info(f"Activity save_checkpoint: job={job_id}, step={step_name}, status={status}")

    save_step(
        job_id=job_id,
        step_name=step_name,
        status=status,
        result_summary=input_data.get("result_summary"),
        model=input_data.get("model"),
        prompt_version=input_data.get("prompt_version"),
        token_usage=input_data.get("token_usage"),
        artifact_urls=input_data.get("artifact_urls"),
        error=input_data.get("error"),
        duration_ms=input_data.get("duration_ms"),
    )

    return {"success": True}
