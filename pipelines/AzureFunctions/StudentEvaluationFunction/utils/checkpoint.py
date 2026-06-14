"""
Pipeline checkpoint utilities for micro-state tracking.
Saves/loads per-step state in solution_evaluations.pipeline_steps JSONB column.
"""
import logging
import json
from datetime import datetime, timezone
from typing import Optional
from utils.db import _get_connection


def save_step(
    job_id: str,
    step_name: str,
    status: str,
    result_summary: Optional[dict] = None,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    token_usage: Optional[dict] = None,
    artifact_urls: Optional[list] = None,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """
    Upsert a step entry into pipeline_steps JSONB and update current_step.

    Uses COALESCE + jsonb_set for atomic partial update — only touches the
    target step key, leaving other steps intact.

    Args:
        job_id: UUID of the evaluation record
        step_name: Step identifier (e.g. "split_student_hw", "evaluate_batch_0")
        status: "started" | "completed" | "failed"
        result_summary: Small summary dict (counts, metadata) — NOT full payloads
        model: Gemini model ID used (e.g. "gemini-3-pro-preview")
        prompt_version: Prompt file name (e.g. "Student_HW_Split.md")
        token_usage: {prompt_tokens, completion_tokens, total_tokens}
        artifact_urls: List of blob URLs for large artifacts
        error: Error message if status == "failed"
        duration_ms: Step duration in milliseconds
    """
    now = datetime.now(timezone.utc).isoformat()

    step_data = {"status": status}

    if status == "started":
        step_data["started_at"] = now
    elif status in ("completed", "failed"):
        step_data["completed_at"] = now

    if duration_ms is not None:
        step_data["duration_ms"] = duration_ms
    if model:
        step_data["model"] = model
    if prompt_version:
        step_data["prompt_version"] = prompt_version
    if token_usage:
        step_data["token_usage"] = token_usage
    if result_summary:
        step_data["result_summary"] = result_summary
    if artifact_urls:
        step_data["artifact_urls"] = artifact_urls
    if error:
        step_data["error"] = error

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Atomic upsert into JSONB:
            # 1. COALESCE existing pipeline_steps with empty object
            # 2. Merge the existing step entry (if any) with new data via ||
            # 3. Set into the pipeline_steps at the step_name key
            #
            # For "completed" status, we merge with the existing "started" entry
            # to preserve started_at timestamp.
            cur.execute(
                """
                UPDATE solution_evaluations
                SET pipeline_steps = jsonb_set(
                        COALESCE(pipeline_steps, '{}'::jsonb),
                        %s,
                        COALESCE(
                            (COALESCE(pipeline_steps, '{}'::jsonb) -> %s),
                            '{}'::jsonb
                        ) || %s::jsonb
                    ),
                    current_step = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    [step_name],         # jsonb path array
                    step_name,           # key to read existing step data
                    json.dumps(step_data),
                    step_name if status == "started" else (step_name if status == "failed" else None),
                    job_id,
                ),
            )
            conn.commit()
            logging.info(f"Job {job_id}: checkpoint {step_name} → {status}")
    except Exception as e:
        conn.rollback()
        logging.error(f"Job {job_id}: failed to save checkpoint {step_name}: {e}")
        raise
    finally:
        conn.close()


def load_step(job_id: str, step_name: str) -> Optional[dict]:
    """
    Read a single step entry from pipeline_steps JSONB.

    Args:
        job_id: UUID of the evaluation record
        step_name: Step identifier to look up

    Returns:
        Step dict (status, started_at, completed_at, ...) or None if not checkpointed.
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pipeline_steps -> %s
                FROM solution_evaluations
                WHERE id = %s
                """,
                (step_name, job_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0]  # psycopg2 auto-deserializes JSONB
            return None
    except Exception as e:
        logging.error(f"Job {job_id}: failed to load checkpoint {step_name}: {e}")
        raise
    finally:
        conn.close()


def load_all_steps(job_id: str) -> Optional[dict]:
    """
    Read the full pipeline_steps JSONB for a job.

    Returns:
        Full pipeline_steps dict or None.
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pipeline_steps
                FROM solution_evaluations
                WHERE id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
            return None
    except Exception as e:
        logging.error(f"Job {job_id}: failed to load all checkpoints: {e}")
        raise
    finally:
        conn.close()
