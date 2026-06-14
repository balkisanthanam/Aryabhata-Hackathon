"""
Activity: Load a pipeline checkpoint step from the DB.
Wraps utils/checkpoint.load_step for use as a Durable Functions activity.
"""
import logging
from utils.checkpoint import load_step


def load_checkpoint_activity(input_data: dict) -> dict | None:
    """
    Load a checkpoint for a pipeline step.

    Args:
        input_data: {
            "job_id": str,
            "step_name": str
        }

    Returns:
        Step dict (status, started_at, completed_at, ...) or None if not checkpointed.
    """
    job_id = input_data["job_id"]
    step_name = input_data["step_name"]

    logging.info(f"Activity load_checkpoint: job={job_id}, step={step_name}")

    result = load_step(job_id, step_name)

    if result:
        logging.info(f"  Found checkpoint: status={result.get('status')}")
    else:
        logging.info(f"  No checkpoint found for {step_name}")

    return result
