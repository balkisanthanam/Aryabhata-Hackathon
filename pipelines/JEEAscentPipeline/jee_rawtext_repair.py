"""One-time repair: fix questions where raw_text contains the full Flash JSON response string.

Root cause: Flash response was truncated at max_output_tokens=4096 → JSONDecodeError →
the crop pipeline stored the raw Flash text as raw_text instead of parsing fields.

This script:
1. Finds questions where raw_text starts with '{' (JSON blob stored as raw_text)
2. Tries to JSON-parse that value
3. If parseable: extracts raw_text, options, has_figure, figure_description and updates DB
4. If not parseable (truncated): flags for manual re-extraction

Usage:
    python jee_rawtext_repair.py --dry-run    # preview, no writes
    python jee_rawtext_repair.py              # fix all
    python jee_rawtext_repair.py --paper-ids 2,3,4   # limit to specific papers
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from settings_loader import load_local_settings
load_local_settings()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db_writer import JEEExtractionDBWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)


def fetch_broken_questions(
    db: JEEExtractionDBWriter,
    paper_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Fetch questions where raw_text looks like a JSON object (the Flash response blob)."""
    from psycopg2.extras import RealDictCursor

    clauses = ["(question_content->>'raw_text') LIKE '{%%'"]
    params: List[Any] = []

    if paper_ids:
        clauses.append("exam_paper_id = ANY(%s)")
        params.append(paper_ids)

    query = f"""
        SELECT id, exam_paper_id, nta_question_id, subject, section, answer_key,
               question_content
        FROM jee_question_bank
        WHERE {' AND '.join(clauses)}
        ORDER BY exam_paper_id, id
    """
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or [])
            return [dict(r) for r in cur.fetchall()]


def repair_question_content(
    db: JEEExtractionDBWriter,
    question_id: int,
    existing_content: Dict[str, Any],
    parsed_flash: Dict[str, Any],
) -> None:
    """Update question_content with correctly parsed Flash fields."""
    # Extract fields from the parsed Flash JSON
    real_raw_text = parsed_flash.get("raw_text", "")
    flash_options = parsed_flash.get("options") or []
    has_figure = bool(parsed_flash.get("has_figure", False))
    figure_description = parsed_flash.get("figure_description")

    # Rebuild options: if existing options have nta_option_ids, preserve them
    existing_options = existing_content.get("options") or []
    options_out = []

    if flash_options:
        for idx, opt_text in enumerate(flash_options[:4]):
            if isinstance(opt_text, dict):
                opt_text = opt_text.get("text", "")
            # Preserve nta_option_id from existing if available
            existing_opt = existing_options[idx] if idx < len(existing_options) else {}
            options_out.append({
                "nta_option_id": existing_opt.get("nta_option_id") if isinstance(existing_opt, dict) else None,
                "text": str(opt_text),
            })

    new_content = {
        **existing_content,
        "raw_text": real_raw_text,
        "options": options_out,
        "has_figure": has_figure,
        "figure_description": figure_description,
    }

    query = """
        UPDATE jee_question_bank
        SET question_content = %s::jsonb
        WHERE id = %s
    """
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (json.dumps(new_content), question_id))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair questions where raw_text contains raw Flash JSON response."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing.")
    parser.add_argument("--paper-ids",
                        help="Comma-separated exam_papers IDs to limit scope.")
    args = parser.parse_args()

    paper_ids = (
        [int(x.strip()) for x in args.paper_ids.split(",") if x.strip()]
        if args.paper_ids else None
    )

    db = JEEExtractionDBWriter()

    LOGGER.info("Fetching broken questions...")
    questions = fetch_broken_questions(db, paper_ids=paper_ids)
    LOGGER.info("Found %d questions with JSON blob in raw_text", len(questions))

    if not questions:
        LOGGER.info("Nothing to repair.")
        return

    if args.dry_run:
        LOGGER.info("=== DRY-RUN — no DB writes ===")

    repaired = 0
    truncated = 0

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        content = q["question_content"] or {}
        raw_text_blob = content.get("raw_text", "")

        LOGGER.info("[%d/%d] Q%d (paper=%d, %s %s) — raw_text length=%d",
                    i, len(questions), qid, q["exam_paper_id"],
                    q["subject"], q["section"], len(raw_text_blob))

        # Try to parse the blob as JSON
        try:
            parsed = json.loads(raw_text_blob)
        except json.JSONDecodeError:
            LOGGER.warning("  -> TRUNCATED (cannot parse JSON) — needs re-extraction")
            truncated += 1
            continue

        if not isinstance(parsed, dict) or "raw_text" not in parsed:
            LOGGER.warning("  -> Unexpected JSON structure: %s", list(parsed.keys()))
            truncated += 1
            continue

        LOGGER.info("  -> Parseable. real raw_text=%d chars, options=%d",
                    len(parsed.get("raw_text", "")), len(parsed.get("options") or []))

        if args.dry_run:
            LOGGER.info("  [DRY-RUN] Would repair Q%d", qid)
            repaired += 1
            continue

        if i % 20 == 1:
            db.refresh_token()

        repair_question_content(db, qid, content, parsed)
        repaired += 1
        LOGGER.info("  -> REPAIRED")

    LOGGER.info(
        "\n=== DONE ===\n  Repaired: %d\n  Truncated (needs re-extract): %d\n  Total: %d",
        repaired, truncated, len(questions),
    )
    if truncated > 0:
        LOGGER.info(
            "For truncated questions: increase max_output_tokens in crop pipeline (already done)"
            " then delete and re-run those specific papers."
        )


if __name__ == "__main__":
    main()
