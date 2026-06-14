"""
End-to-end test for the Student Evaluation Durable Function pipeline.

Works against both local func host and deployed Azure Function App.
Use --target local (default) or --target deployed to choose.

This script:
1. Accepts local image files (student work + optional problem image(s)) via CLI
2. Uploads them to Azure Blob Storage (kalidasa) under feedback/test-uploads/
3. Inserts a PENDING solution_evaluations row in the database
4. Pushes the job_id to the feedback-jobs queue
5. Polls the DB every 5s until status changes to COMPLETED or FAILED
6. Prints the feedback summary and cleans up

Usage:
    # Test against local func host
    python tests/test_durable_e2e.py --student-work page1.jpg --text-ref "13.8, 13.9" \\
           --subject Physics --class 11

    # Test against deployed Azure Function App
    python tests/test_durable_e2e.py --target deployed \\
           --student-work page1.jpg --text-ref "13.8, 13.9" --subject Physics --class 11

    # Student work + problem images
    python tests/test_durable_e2e.py --target deployed \\
           --student-work hw1.jpg hw2.jpg --problem-image p1.jpg p2.jpg \\
           --text-ref "Problems 10-13 in 3D geometry" --subject Maths --class 11

    # Utility: check status / cleanup
    python tests/test_durable_e2e.py --status <job_id>
    python tests/test_durable_e2e.py --cleanup <job_id>

Prerequisites:
    - Azure CLI logged in (az login) for DefaultAzureCredential
    - local.settings.json configured with FEEDBACK_QUEUE_CONNECTION, DB_*, BLOB_STORAGE_URL
    - For --target local: func host running locally (./start-func.ps1)
    - For --target deployed: local func host should be STOPPED to avoid queue competition
"""
import os
import sys
import json
import time
import uuid
import socket
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local.settings.json")
if os.path.exists(SETTINGS_PATH):
    with open(SETTINGS_PATH) as f:
        settings = json.load(f).get("Values", {})
    for k, v in settings.items():
        if k not in os.environ:
            os.environ[k] = v

QUEUE_CONNECTION = os.environ.get("FEEDBACK_QUEUE_CONNECTION")
QUEUE_NAME = "feedback-jobs"
DB_HOST = os.environ.get("DB_HOST", "<DB_HOST>")
DB_NAME = os.environ.get("DB_NAME", "<DB_NAME>")
DB_USER = os.environ.get("DB_USER")
DB_PORT = os.environ.get("DB_PORT", "5432")
BLOB_STORAGE_URL = os.environ.get("BLOB_STORAGE_URL", "<BLOB_STORAGE_URL>")
TEST_USER_ID = 1  # Ensure this user exists in UserProfileData

POLL_INTERVAL = 5   # seconds
MAX_POLL_TIME = 600  # 10 minutes max wait

# Azure Function App (deployed target)
FUNC_APP_NAME = os.environ.get("FUNC_APP_NAME", "<FUNCTION_APP_NAME>")
FUNC_APP_RG = "rg-student-evaluation"
LOCAL_FUNC_PORT = 7072

# Blob container & path for test uploads
UPLOAD_CONTAINER = "feedback"
UPLOAD_PREFIX = "test-uploads"


# ─── Blob Upload ───────────────────────────────────────────────────────────────

def upload_to_blob(local_path: str, blob_name: str) -> str:
    """
    Upload a local file to Azure Blob Storage and return the blob URL.
    Uses DefaultAzureCredential (same auth as the Function App).
    """
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.identity import DefaultAzureCredential

    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(account_url=BLOB_STORAGE_URL, credential=credential)
    container_client = blob_service.get_container_client(UPLOAD_CONTAINER)

    # Determine content type
    suffix = local_path.suffix.lower()
    content_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".pdf": "application/pdf",
    }
    content_type = content_types.get(suffix, "application/octet-stream")

    blob_client = container_client.get_blob_client(blob_name)

    with open(local_path, "rb") as f:
        blob_client.upload_blob(
            f,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    blob_url = f"{BLOB_STORAGE_URL}/{UPLOAD_CONTAINER}/{blob_name}"
    logger.info(f"  Uploaded {local_path.name} -> {blob_url}")
    return blob_url


def upload_test_images(student_work_paths: list[str], problem_image_paths: list[str] = None) -> dict:
    """
    Upload student work page(s) (and optional problem image(s)) to blob storage.
    Returns dict with 'student_work_url' (comma-separated if multiple) and
    optionally 'problem_image_url' (also comma-separated if multiple).
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    urls = {}

    # Student work pages (one or more)
    page_urls = []
    for idx, swp in enumerate(student_work_paths):
        ext = Path(swp).suffix
        blob_name = f"{UPLOAD_PREFIX}/{run_id}/student_work_{idx}{ext}"
        page_urls.append(upload_to_blob(swp, blob_name))
    # Store as comma-separated URL string (DB column is TEXT)
    urls["student_work_url"] = ",".join(page_urls)
    logger.info(f"  Uploaded {len(page_urls)} student work page(s)")

    # Problem image(s) (optional — only for Path B)
    if problem_image_paths:
        prob_urls = []
        for idx, pip in enumerate(problem_image_paths):
            ext = Path(pip).suffix
            blob_name = f"{UPLOAD_PREFIX}/{run_id}/problem_image_{idx}{ext}"
            prob_urls.append(upload_to_blob(pip, blob_name))
        urls["problem_image_url"] = ",".join(prob_urls)
        logger.info(f"  Uploaded {len(prob_urls)} problem image page(s)")

    return urls


# ─── Database ──────────────────────────────────────────────────────────────────

def get_db_connection():
    """Get a PostgreSQL connection using Azure AD token."""
    import psycopg2
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER,
        password=token.token, port=DB_PORT, sslmode="require",
    )


def insert_evaluation(
    student_work_url: str,
    problem_text_ref: str = None,
    problem_image_url: str = None,
    subject: str = "Physics",
    class_num: str = "11",
    board: str = "CBSE",
    chapter_title: str = None,
    chapter_number: str = None,
) -> str:
    """Insert a PENDING evaluation row. Returns job_id."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            job_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO solution_evaluations
                    (id, userid, class, board, subject, chapter_title, chapter_number,
                     status, problem_text_ref, problem_image_url, student_work_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s, %s, %s)
                RETURNING id
                """,
                (
                    job_id, TEST_USER_ID, class_num, board, subject,
                    chapter_title, chapter_number,
                    problem_text_ref, problem_image_url, student_work_url,
                ),
            )
            conn.commit()
            logger.info(f"  Inserted evaluation: id={job_id}")
            return job_id
    finally:
        conn.close()


def poll_evaluation(job_id: str, max_time: int = MAX_POLL_TIME) -> dict:
    """Poll the DB until evaluation completes or times out."""
    start = time.time()
    while time.time() - start < max_time:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, feedback_json FROM solution_evaluations WHERE id = %s",
                    (job_id,),
                )
                row = cur.fetchone()
                if not row:
                    logger.error(f"Job {job_id} not found in DB!")
                    return {"status": "NOT_FOUND"}

                status, feedback = row
                elapsed = int(time.time() - start)
                logger.info(f"  [{elapsed:>3d}s] Status: {status}")

                if status in ("COMPLETED", "FAILED"):
                    return {"status": status, "feedback_json": feedback}
        finally:
            conn.close()

        time.sleep(POLL_INTERVAL)

    logger.error(f"Timed out after {max_time}s waiting for job {job_id}")
    return {"status": "TIMEOUT"}


def read_evaluation_status(job_id: str) -> dict:
    """Read current status of an evaluation."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, feedback_json, updated_at FROM solution_evaluations WHERE id = %s",
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"status": "NOT_FOUND"}
            return {"status": row[0], "feedback_json": row[1], "updated_at": str(row[2])}
    finally:
        conn.close()


def cleanup_evaluation(job_id: str):
    """Delete a test evaluation row."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM solution_evaluations WHERE id = %s", (job_id,))
            conn.commit()
            logger.info(f"Cleaned up evaluation: {job_id}")
    finally:
        conn.close()


# ─── Queue ─────────────────────────────────────────────────────────────────────

def push_to_queue(job_id: str):
    """Push job_id to the feedback-jobs queue.
    
    Uses default base64 encoding to match the host.json
    extensions.queues.messageEncoding = "base64" setting.
    """
    from azure.storage.queue import QueueClient

    queue_client = QueueClient.from_connection_string(QUEUE_CONNECTION, QUEUE_NAME)
    queue_client.send_message(job_id)
    logger.info(f"  Pushed job_id={job_id} to queue '{QUEUE_NAME}'")


# ─── Pre-flight Checks ─────────────────────────────────────────────────────────

def _is_port_open(port: int) -> bool:
    """Check if a local port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def preflight_deployed():
    """Verify deployed target is ready to test."""
    # Warn if local func host is running — it will compete for queue messages
    if _is_port_open(LOCAL_FUNC_PORT):
        logger.warning(
            f"  Local func host detected on port {LOCAL_FUNC_PORT}!\n"
            f"  Both local and deployed functions will compete for the queue message.\n"
            f"  Stop the local host first (Ctrl+C or close the terminal) for reliable remote testing."
        )
        response = input("  Continue anyway? [y/N]: ").strip().lower()
        if response != "y":
            logger.info("  Aborted.")
            sys.exit(0)

    # Verify the function app is running
    logger.info(f"  Checking deployed function app '{FUNC_APP_NAME}'...")
    try:
        result = subprocess.run(
            ["az", "functionapp", "show", "--name", FUNC_APP_NAME,
             "--resource-group", FUNC_APP_RG, "--query", "state", "-o", "tsv"],
            capture_output=True, text=True, timeout=30,
        )
        state = result.stdout.strip()
        if state.lower() == "running":
            logger.info(f"  Function app '{FUNC_APP_NAME}' is Running")
        else:
            logger.warning(f"  Function app state: {state or 'unknown'} (expected Running)")
            if result.stderr.strip():
                logger.warning(f"  {result.stderr.strip()}")
    except FileNotFoundError:
        logger.warning("  'az' CLI not found — skipping function app health check")
    except subprocess.TimeoutExpired:
        logger.warning("  Timed out checking function app — continuing anyway")


def preflight_local():
    """Verify local target is ready to test."""
    if not _is_port_open(LOCAL_FUNC_PORT):
        logger.warning(
            f"  Local func host not detected on port {LOCAL_FUNC_PORT}.\n"
            f"  Start it first:  .\\start-func.ps1  or  func start --port {LOCAL_FUNC_PORT}\n"
            f"  (If the deployed function is running, queue messages will be picked up there instead.)"
        )


# ─── Test Runner ───────────────────────────────────────────────────────────────

def run_test(
    student_work_paths: list[str],
    problem_image_paths: list[str] = None,
    problem_text_ref: str = None,
    subject: str = "Physics",
    class_num: str = "11",
    board: str = "CBSE",
    chapter_title: str = "Oscillations",
    chapter_number: str = "13",
    no_poll: bool = False,
    no_cleanup: bool = False,
    target: str = "local",
):
    """Full test flow: upload -> insert -> queue -> poll -> report."""
    path_label = "Path A (text ref)" if problem_text_ref else "Path B (problem image)"
    target_label = f"DEPLOYED ({FUNC_APP_NAME})" if target == "deployed" else "LOCAL (func host)"
    logger.info("=" * 65)
    logger.info(f"  STUDENT EVALUATION E2E TEST  --  {path_label}")
    logger.info(f"  Target: {target_label}")
    logger.info("=" * 65)

    # Pre-flight checks
    if target == "deployed":
        preflight_deployed()
    else:
        preflight_local()

    # Step 1: Upload images
    logger.info(f"\n[1/4] Uploading {len(student_work_paths)} student page(s) to blob storage...")
    urls = upload_test_images(student_work_paths, problem_image_paths)

    # Step 2: Insert DB row
    logger.info("\n[2/4] Inserting PENDING evaluation row...")
    job_id = insert_evaluation(
        student_work_url=urls["student_work_url"],
        problem_text_ref=problem_text_ref,
        problem_image_url=urls.get("problem_image_url"),
        subject=subject,
        class_num=class_num,
        board=board,
        chapter_title=chapter_title,
        chapter_number=chapter_number,
    )

    # Step 3: Push to queue
    logger.info("\n[3/4] Pushing job to feedback-jobs queue...")
    push_to_queue(job_id)

    if no_poll:
        logger.info(f"\n  Job ID: {job_id}")
        logger.info("  --no-poll set. Monitor manually:")
        logger.info(f"    python tests/test_durable_e2e.py --status {job_id}")
        logger.info(f"    python tests/test_durable_e2e.py --cleanup {job_id}")
        return

    # Step 4: Poll for result
    logger.info(f"\n[4/4] Polling for completion (max {MAX_POLL_TIME}s)...")
    result = poll_evaluation(job_id)

    # ── Report ──
    logger.info("\n" + "-" * 65)
    if result["status"] == "COMPLETED":
        feedback = result["feedback_json"]
        if isinstance(feedback, str):
            feedback = json.loads(feedback)
        summary = feedback.get("summary", {})
        logger.info(f"  RESULT: COMPLETED")
        logger.info(f"  Total problems:     {summary.get('total_problems', 'N/A')}")
        logger.info(f"  Correct:            {summary.get('correct', 'N/A')}")
        logger.info(f"  Partially correct:  {summary.get('partially_correct', 'N/A')}")
        logger.info(f"  Incorrect:          {summary.get('incorrect', 'N/A')}")
        logger.info(f"\n  Full feedback (first 2000 chars):\n{json.dumps(feedback, indent=2)[:2000]}")
        logger.info("\n  >> TEST PASSED")
    elif result["status"] == "FAILED":
        feedback = result.get("feedback_json")
        if isinstance(feedback, str):
            try:
                feedback = json.loads(feedback)
            except (json.JSONDecodeError, TypeError):
                pass
        error_msg = feedback.get("error", "No error message") if isinstance(feedback, dict) else str(feedback)
        logger.warning(f"  RESULT: FAILED -- {error_msg}")
    else:
        logger.error(f"  RESULT: {result['status']}")
    logger.info("-" * 65)

    # Cleanup
    if not no_cleanup:
        logger.info("")
        cleanup_evaluation(job_id)
    else:
        logger.info(f"\n  --no-cleanup set. Clean up later with:")
        logger.info(f"    python tests/test_durable_e2e.py --cleanup {job_id}")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="E2E test for Student Evaluation Durable Function",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test against LOCAL func host (default)
  python tests/test_durable_e2e.py `
    --student-work ./my_hw.jpg --text-ref "13.8, 13.9" `
    --subject Physics --class 11

  # Test against DEPLOYED Azure Function App
  python tests/test_durable_e2e.py --target deployed `
    --student-work page1.jpg page2.jpg --text-ref "13.8, 13.9" `
    --subject Physics --class 11

  # Student work + problem images + text ref (deployed)
  python tests/test_durable_e2e.py --target deployed `
    --student-work hw1.jpg hw2.jpg `
    --problem-image p1.jpg p2.jpg `
    --text-ref "Problems 10-13 in 3D geometry" `
    --subject Maths --class 11

  # Fire-and-forget (no polling, no cleanup)
  python tests/test_durable_e2e.py --target deployed `
    --student-work ./my_hw.jpg --text-ref "13.8" `
    --subject Physics --class 11 --no-poll --no-cleanup

  # Utilities
  python tests/test_durable_e2e.py --status <job_id>
  python tests/test_durable_e2e.py --cleanup <job_id>
        """,
    )

    # Utility sub-commands (mutually exclusive with test flow)
    util_group = parser.add_argument_group("Utility commands")
    util_group.add_argument("--status", metavar="JOB_ID", help="Check status of a job")
    util_group.add_argument("--cleanup", metavar="JOB_ID", help="Delete a test evaluation row")

    # Test parameters
    test_group = parser.add_argument_group("Test parameters")
    test_group.add_argument("--student-work", nargs="+", metavar="FILE",
                           help="Path(s) to student work image(s) — one or more pages")
    test_group.add_argument("--problem-image", nargs="+", metavar="FILE",
                           help="Path(s) to problem/textbook image(s) — one or more pages (Path B)")
    test_group.add_argument("--text-ref", metavar="REF",
                           help='Problem text reference, e.g. "13.8, 13.9" (Path A)')

    # Chapter / subject info
    ctx_group = parser.add_argument_group("Context (subject defaults to Physics; chapter optional)")
    ctx_group.add_argument("--subject", default="Physics")
    ctx_group.add_argument("--class", dest="class_num", default="11")
    ctx_group.add_argument("--board", default="CBSE")
    ctx_group.add_argument("--chapter", dest="chapter_title", default=None,
                           help="Chapter title (optional — can be resolved from --text-ref)")
    ctx_group.add_argument("--chapter-num", dest="chapter_number", type=str, default=None,
                           help="Chapter number (optional — can be inferred from problem numbers)")

    # Behaviour
    parser.add_argument("--target", choices=["local", "deployed"], default="local",
                       help="Test target: 'local' func host (default) or 'deployed' Azure Function App")
    parser.add_argument("--no-poll", action="store_true",
                       help="Insert + queue only; don't wait for result")
    parser.add_argument("--no-cleanup", action="store_true",
                       help="Don't delete the evaluation row after test")

    args = parser.parse_args()

    # ── Utility commands ──
    if args.status:
        result = read_evaluation_status(args.status)
        print(json.dumps(result, indent=2, default=str))
        return

    if args.cleanup:
        cleanup_evaluation(args.cleanup)
        return

    # ── Test flow ──
    if not args.student_work:
        parser.error("--student-work is required to run a test")

    if not args.text_ref and not args.problem_image:
        parser.error("Provide at least --text-ref or --problem-image (or both)")

    for sw in args.student_work:
        if not os.path.isfile(sw):
            parser.error(f"Student work file not found: {sw}")

    if args.problem_image:
        for pi in args.problem_image:
            if not os.path.isfile(pi):
                parser.error(f"Problem image file not found: {pi}")

    run_test(
        student_work_paths=args.student_work,
        problem_image_paths=args.problem_image,
        problem_text_ref=args.text_ref,
        subject=args.subject,
        class_num=args.class_num,
        board=args.board,
        chapter_title=args.chapter_title,
        chapter_number=args.chapter_number,
        no_poll=args.no_poll,
        no_cleanup=args.no_cleanup,
        target=args.target,
    )


if __name__ == "__main__":
    main()
