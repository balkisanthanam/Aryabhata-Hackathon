"""Upload crop PNGs for figure questions to blob and update figure_blob_url in DB.

For each question where has_figure=true and figure_blob_url IS NULL:
  1. Find the matching crop PNG in temp/crops/paper_<exam_paper_id>/
  2. Upload to kalidasa / jeedata / figures/<nta_question_id>.png
  3. UPDATE question_content.figure_blob_url in jee_question_bank

Usage:
    python jee_figure_uploader.py              # process all figure questions
    python jee_figure_uploader.py --dry-run    # preview matches, no uploads/writes
    python jee_figure_uploader.py --paper-ids 2,3,4   # limit to specific papers
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
CROPS_DIR = SCRIPT_DIR / "temp" / "crops"

# ── path setup ────────────────────────────────────────────────────────────────
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from settings_loader import load_local_settings  # noqa: E402

load_local_settings()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db_writer import JEEExtractionDBWriter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)

BLOB_ACCOUNT = "stevaluationstorage"
BLOB_CONTAINER = "onlineresources"
BLOB_PREFIX = "jee/figures"  # stevaluationstorage/onlineresources/jee/figures/<nta_question_id>.png

# Crop filenames: q001_<nta_question_id>_p2.png  (or _p1.png for single-page)
CROP_FILENAME_RE = re.compile(r"^q\d+_(\d+)_p\d+(?:-p\d+)?\.png$", re.IGNORECASE)


# ── blob helpers ──────────────────────────────────────────────────────────────

def _get_container_client():
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient

    credential = AzureCliCredential()
    account_url = f"https://{BLOB_ACCOUNT}.blob.core.windows.net"
    service = BlobServiceClient(account_url=account_url, credential=credential)
    return service.get_container_client(BLOB_CONTAINER)


def upload_png(local_path: Path, nta_question_id: str, dry_run: bool) -> Optional[str]:
    """Upload a PNG to blob and return its public URL. Returns None on failure."""
    blob_name = f"{BLOB_PREFIX}/{nta_question_id}.png"
    blob_url = f"https://{BLOB_ACCOUNT}.blob.core.windows.net/{BLOB_CONTAINER}/{blob_name}"

    if dry_run:
        LOGGER.info("  [DRY-RUN] Would upload %s → %s", local_path.name, blob_name)
        return blob_url

    try:
        from azure.storage.blob import ContentSettings
        container = _get_container_client()
        with open(local_path, "rb") as f:
            container.upload_blob(
                name=blob_name,
                data=f,
                overwrite=True,
                content_settings=ContentSettings(content_type="image/png"),
            )
        return blob_url
    except Exception as exc:
        LOGGER.error("  Upload failed for %s: %s", local_path.name, exc)
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────

def fetch_figure_questions(
    db: JEEExtractionDBWriter,
    paper_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Return questions with has_figure=true and figure_blob_url IS NULL."""
    from psycopg2.extras import RealDictCursor

    clauses = [
        "(question_content->>'has_figure')::boolean = true",
        "question_content->>'figure_blob_url' IS NULL",
    ]
    params: List[Any] = []

    if paper_ids:
        clauses.append("exam_paper_id = ANY(%s)")
        params.append(paper_ids)

    query = f"""
        SELECT id, exam_paper_id, nta_question_id, subject
        FROM jee_question_bank
        WHERE {' AND '.join(clauses)}
        ORDER BY exam_paper_id, id
    """
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


def update_figure_blob_url(db: JEEExtractionDBWriter, question_id: int, blob_url: str) -> None:
    """Set figure_blob_url inside question_content JSONB."""
    query = """
        UPDATE jee_question_bank
        SET question_content = jsonb_set(
            question_content,
            '{figure_blob_url}',
            %s::jsonb
        )
        WHERE id = %s
    """
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (json.dumps(blob_url), question_id))


# ── crop lookup ───────────────────────────────────────────────────────────────

def build_crop_index() -> Dict[str, Path]:
    """Walk temp/crops/paper_*/ and build {nta_question_id: png_path} index."""
    index: Dict[str, Path] = {}
    if not CROPS_DIR.exists():
        LOGGER.warning("Crops directory not found: %s", CROPS_DIR)
        return index

    for paper_dir in sorted(CROPS_DIR.iterdir()):
        if not paper_dir.is_dir():
            continue
        for png in paper_dir.glob("*.png"):
            m = CROP_FILENAME_RE.match(png.name)
            if m:
                nta_id = m.group(1)
                # Keep first match (shouldn't have duplicates)
                index.setdefault(nta_id, png)

    LOGGER.info("Crop index built: %d PNGs across %d paper dirs", len(index), sum(1 for d in CROPS_DIR.iterdir() if d.is_dir()))
    return index


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Suppress verbose Azure SDK HTTP logs
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="Upload crop PNGs for figure questions to blob and update DB."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview matches and uploads but skip all writes.")
    parser.add_argument("--paper-ids",
                        help="Comma-separated exam_papers IDs to limit scope.")
    args = parser.parse_args()

    paper_ids = (
        [int(x.strip()) for x in args.paper_ids.split(",") if x.strip()]
        if args.paper_ids else None
    )

    db = JEEExtractionDBWriter()

    LOGGER.info("Building crop index…")
    crop_index = build_crop_index()

    LOGGER.info("Fetching figure questions from DB…")
    questions = fetch_figure_questions(db, paper_ids=paper_ids)
    LOGGER.info("Found %d figure questions needing blob URL", len(questions))

    if not questions:
        LOGGER.info("Nothing to do.")
        return

    if args.dry_run:
        LOGGER.info("=== DRY-RUN — no uploads or DB writes ===")

    uploaded = 0
    missing_crop = 0
    failed = 0

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        nta_id = q["nta_question_id"]
        paper_id = q["exam_paper_id"]

        crop_path = crop_index.get(nta_id)
        if not crop_path:
            LOGGER.warning("[%d/%d] Q%d nta=%s — no crop PNG found (paper %d)",
                           i, len(questions), qid, nta_id, paper_id)
            missing_crop += 1
            continue

        LOGGER.info("[%d/%d] Q%d nta=%s -> %s", i, len(questions), qid, nta_id, crop_path.name)

        # Refresh token every 50 uploads
        if i % 50 == 1 and not args.dry_run:
            db.refresh_token()

        blob_url = upload_png(crop_path, nta_id, dry_run=args.dry_run)

        if blob_url is None:
            failed += 1
            continue

        if not args.dry_run:
            update_figure_blob_url(db, qid, blob_url)

        uploaded += 1

    LOGGER.info(
        "\n=== DONE ===\n  Uploaded: %d\n  Missing crop: %d\n  Failed: %d\n  Total: %d",
        uploaded, missing_crop, failed, len(questions),
    )


if __name__ == "__main__":
    main()
