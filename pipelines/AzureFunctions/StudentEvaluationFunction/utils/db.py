"""
PostgreSQL database access via psycopg2 with Azure AD token authentication.
"""
import logging
import os
import json
import psycopg2
from azure.identity import DefaultAzureCredential
from typing import Optional


def _get_connection():
    """
    Create a PostgreSQL connection using Azure AD token authentication.
    """
    host = os.environ.get("DB_HOST", "<DB_HOST>")
    dbname = os.environ.get("DB_NAME", "<DB_NAME>")
    user = os.environ.get("DB_USER")
    port = os.environ.get("DB_PORT", "5432")

    # Get Azure AD token for PostgreSQL
    credential = DefaultAzureCredential()
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    conn = psycopg2.connect(
        host=host,
        dbname=dbname,
        user=user,
        password=token.token,
        port=port,
        sslmode="require",
    )
    return conn


def read_evaluation(job_id: str) -> Optional[dict]:
    """
    Read a solution_evaluations record by ID and atomically set status to PROCESSING.
    Returns the record dict, or None if not found / already completed.
    
    Uses UPDATE ... RETURNING for atomic status transition:
      - PENDING → PROCESSING (new job)
      - PROCESSING → PROCESSING (recovery of crashed pipeline)
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Atomic: grab PENDING or PROCESSING rows (PROCESSING = crashed pipeline resume)
            cur.execute(
                """
                UPDATE solution_evaluations
                SET status = 'PROCESSING', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status IN ('PENDING', 'PROCESSING')
                RETURNING id, userid, class, board, subject, chapter_id,
                          chapter_title, chapter_number, pdffileurl, status,
                          problem_text_ref, problem_image_url, student_work_url,
                          feedback_json, created_at, updated_at,
                          pipeline_steps, current_step
                """,
                (job_id,),
            )
            row = cur.fetchone()
            conn.commit()

            if not row:
                logging.warning(f"Job {job_id}: not found or not in PENDING/PROCESSING state")
                return None

            columns = [
                "id", "userid", "class", "board", "subject", "chapter_id",
                "chapter_title", "chapter_number", "pdffileurl", "status",
                "problem_text_ref", "problem_image_url", "student_work_url",
                "feedback_json", "created_at", "updated_at",
                "pipeline_steps", "current_step",
            ]
            record = dict(zip(columns, row))
            # Convert UUID and datetime to strings for JSON serialization
            record["id"] = str(record["id"])
            record["created_at"] = str(record["created_at"])
            record["updated_at"] = str(record["updated_at"])
            logging.info(f"Job {job_id}: read and set to PROCESSING")
            return record
    except Exception as e:
        conn.rollback()
        logging.error(f"DB error reading evaluation {job_id}: {e}")
        raise
    finally:
        conn.close()


def update_evaluation(
    job_id: str,
    status: str,
    feedback_json: Optional[dict] = None,
    chapter_id: Optional[int] = None,
    chapter_title: Optional[str] = None,
    chapter_number: Optional[str] = None,
    pdffileurl: Optional[str] = None,
) -> bool:
    """
    Update a solution_evaluations record with status, feedback, and resolved chapter info.
    
    Args:
        job_id: UUID of the evaluation record
        status: New status (COMPLETED or FAILED)
        feedback_json: Optional JSONB feedback payload
        chapter_id: Resolved chapter ID from chapterdata
        chapter_title: Resolved chapter title
        chapter_number: Resolved chapter number
        pdffileurl: Chapter PDF blob URL
    
    Returns:
        True if updated successfully
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Build SET clauses dynamically for optional chapter fields
            set_parts = [
                "status = %s::solution_evaluation_status",
                "feedback_json = %s",
                "updated_at = CURRENT_TIMESTAMP",
            ]
            params: list = [
                status,
                json.dumps(feedback_json) if feedback_json else None,
            ]
            if chapter_id is not None:
                set_parts.append("chapter_id = %s")
                params.append(chapter_id)
            if chapter_title is not None:
                set_parts.append("chapter_title = %s")
                params.append(chapter_title)
            if chapter_number is not None:
                set_parts.append("chapter_number = %s")
                params.append(chapter_number)
            if pdffileurl is not None:
                set_parts.append("pdffileurl = %s")
                params.append(pdffileurl)

            params.append(job_id)
            sql = f"UPDATE solution_evaluations SET {', '.join(set_parts)} WHERE id = %s"
            cur.execute(sql, params)
            conn.commit()
            updated = cur.rowcount > 0
            logging.info(f"Job {job_id}: updated to {status} (rows={cur.rowcount})")
            return updated
    except Exception as e:
        conn.rollback()
        logging.error(f"DB error updating evaluation {job_id}: {e}")
        raise
    finally:
        conn.close()


def lookup_chapter(
    class_val: str = None,
    board: str = None,
    subject: str = None,
    chapter_id: int = None,
    chapter_number: str = None,
    chapter_title: str = None,
) -> Optional[dict]:
    """
    Look up a chapter from ChapterData table.
    Priority: chapter_id (PK) → exact match → ILIKE fallback on title.
    
    Returns dict with ChapterId, Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, Board
    or None if not found.
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Note: PostgreSQL folds unquoted identifiers to lowercase.
            # The ChapterData table was created without quotes, so use lowercase column names.
            _cols = "chapterid, class, subject, chapternumber, chaptertitle, pdffileurl, board"

            # Strategy 1: Direct PK lookup
            if chapter_id:
                cur.execute(
                    f"SELECT {_cols} FROM chapterdata WHERE chapterid = %s",
                    (chapter_id,),
                )
                row = cur.fetchone()
                if row:
                    return _chapter_row_to_dict(row)

            # Strategy 2: Exact match on class + subject + chapter_number
            if class_val and subject and chapter_number:
                cur.execute(
                    f"SELECT {_cols} FROM chapterdata WHERE class = %s AND subject ILIKE %s AND chapternumber = %s",
                    (class_val, subject, str(chapter_number)),
                )
                row = cur.fetchone()
                if row:
                    return _chapter_row_to_dict(row)

            # Strategy 3: ILIKE on chapter title
            if chapter_title and subject:
                cur.execute(
                    f"SELECT {_cols} FROM chapterdata WHERE subject ILIKE %s AND chaptertitle ILIKE %s",
                    (subject, f"%{chapter_title}%"),
                )
                row = cur.fetchone()
                if row:
                    return _chapter_row_to_dict(row)

            logging.warning(
                f"Chapter not found: class={class_val}, subject={subject}, "
                f"chapter_id={chapter_id}, chapter_number={chapter_number}, title={chapter_title}"
            )
            return None
    except Exception as e:
        logging.error(f"DB error looking up chapter: {e}")
        raise
    finally:
        conn.close()


def get_chapter_titles(subject: str, class_val: str = None) -> list[str]:
    """
    Fetch all distinct chapter titles for a subject (and optionally class).
    Used for grounding Gemini prompts so it returns canonical titles.
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            if class_val:
                cur.execute(
                    "SELECT DISTINCT chaptertitle FROM chapterdata "
                    "WHERE subject ILIKE %s AND class = %s ORDER BY chaptertitle",
                    (subject, class_val),
                )
            else:
                cur.execute(
                    "SELECT DISTINCT chaptertitle FROM chapterdata "
                    "WHERE subject ILIKE %s ORDER BY chaptertitle",
                    (subject,),
                )
            return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logging.error(f"DB error fetching chapter titles: {e}")
        return []
    finally:
        conn.close()


def _chapter_row_to_dict(row) -> dict:
    """Convert a ChapterData row tuple to a dict."""
    columns = ["ChapterId", "Class", "Subject", "ChapterNumber", "ChapterTitle", "PDFFileURL", "Board"]
    return dict(zip(columns, row))
