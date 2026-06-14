"""Batch runner for the NCERT Concept Index pipeline.

Loops through a list of chapters, calls process_chapter() for each,
optionally pauses between chapters, and runs the verifier after each write.

Usage:
    # Run specific chapters
    python batch_run.py --chapter-ids 29,42,66

    # Run all Physics chapters with 60s pause and continue on failure
    python batch_run.py --subject physics --pause-seconds 60 --on-failure continue

    # Dry-run all class 12 Maths chapters
    python batch_run.py --class 12 --subject maths --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from concept_index_pipeline import (
    CHECKPOINT_DIR,
    LOG_DIR,
    ensure_runtime_dirs,
    load_checkpoint,
    parse_chapter_ids,
    process_chapter,
)
from db_writer import ConceptIndexDBWriter
from gemini_extractor import ConceptGeminiExtractor
from verifier import VerificationResult, verify_chapter

LOGGER = logging.getLogger(__name__)

SHORT_PAUSE_SECONDS = 5  # pause when extraction is already cached
DEFAULT_PAUSE_SECONDS = 45


class ChapterResult(NamedTuple):
    chapter_id: int
    subject: str
    node_count: int
    elapsed: float
    verification: Optional[VerificationResult]
    error: Optional[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-run the NCERT Concept Index pipeline for multiple chapters."
    )
    parser.add_argument(
        "--chapter-ids",
        help="Comma-separated chapter IDs, e.g. 29,42,66",
    )
    parser.add_argument(
        "--subject",
        help="Only chapters for this subject, e.g. physics",
    )
    parser.add_argument(
        "--class",
        dest="class_level",
        type=int,
        help="Only chapters for this class, e.g. 11",
    )
    parser.add_argument(
        "--pause-seconds",
        type=int,
        default=DEFAULT_PAUSE_SECONDS,
        help=f"Seconds to pause between chapters that need Gemini extraction (default: {DEFAULT_PAUSE_SECONDS})",
    )
    parser.add_argument(
        "--on-failure",
        choices=["stop", "continue"],
        default="stop",
        help="What to do when a chapter errors or verification fails (default: stop)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-chapter DB verification",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to each chapter (extract only, no DB writes)",
    )
    return parser.parse_args()


def _is_already_extracted(chapter_id: int) -> bool:
    """Return True if this chapter already has a completed extraction checkpoint.

    When True, no Gemini PDF extraction call will be made, so the long
    pause for rate-limiting is not needed.
    """
    path = CHECKPOINT_DIR / f"chapter_{chapter_id}.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("stages", {}).get("concepts_extracted"))
    except Exception:
        return False


def _get_node_count(chapter_id: int) -> int:
    path = CHECKPOINT_DIR / f"chapter_{chapter_id}.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data.get("nodes", {}))
    except Exception:
        return 0


def _print_summary(results: List[ChapterResult]) -> None:
    """Print a compact summary table at the end of the batch run."""
    print("\n" + "=" * 78)
    print(f"{'Ch':>4}  {'Subject':<18}  {'Nodes':>5}  {'Checks':>9}  {'Time':>7}  Status")
    print("-" * 78)

    total_ok = 0
    total_fail = 0

    for r in results:
        checks_str = "-"
        if r.verification:
            total = len(r.verification.passed) + len(r.verification.failed)
            checks_str = f"{len(r.verification.passed)}/{total}"

        if r.error:
            status = f"ERROR: {r.error[:28]}"
            total_fail += 1
        elif r.verification and not r.verification.is_ok:
            status = f"FAIL ({len(r.verification.failed)} checks)"
            total_fail += 1
        elif r.verification and r.verification.warnings:
            status = f"WARN ({len(r.verification.warnings)})"
            total_ok += 1
        else:
            status = "OK"
            total_ok += 1

        nodes_str = str(r.node_count) if r.node_count else "-"
        print(
            f"{r.chapter_id:>4}  {r.subject:<18}  {nodes_str:>5}  "
            f"{checks_str:>9}  {r.elapsed:>6.1f}s  {status}"
        )

    print("=" * 78)
    print(f"Result: {total_ok} OK, {total_fail} failed out of {len(results)} chapters")
    print("=" * 78 + "\n")


def main() -> None:
    ensure_runtime_dirs()

    log_path = LOG_DIR / f"batch_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )

    args = parse_args()

    db_writer = ConceptIndexDBWriter()
    extractor = ConceptGeminiExtractor()

    chapters = db_writer.fetch_chapters(
        chapter_ids=parse_chapter_ids(args.chapter_ids),
        subject=args.subject,
        class_level=args.class_level,
    )

    if not chapters:
        LOGGER.warning("No chapters matched the provided filters.")
        return

    LOGGER.info(
        "Batch run starting: %d chapter(s), pause=%ds, on-failure=%s, dry-run=%s",
        len(chapters),
        args.pause_seconds,
        args.on_failure,
        args.dry_run,
    )

    results: List[ChapterResult] = []

    for i, chapter in enumerate(chapters):
        ch_id = chapter["chapter_id"]
        subject = chapter.get("subject", "")
        title = chapter.get("chapter_title", "")

        LOGGER.info(
            "[%d/%d] Chapter %s — %s (%s)",
            i + 1,
            len(chapters),
            ch_id,
            title,
            subject,
        )

        start = time.monotonic()
        error_msg: Optional[str] = None
        vr: Optional[VerificationResult] = None

        try:
            process_chapter(
                chapter,
                extractor=extractor,
                db_writer=db_writer,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            LOGGER.exception("Chapter %s failed: %s", ch_id, exc)
            error_msg = str(exc)

        elapsed = time.monotonic() - start
        node_count = _get_node_count(ch_id)

        if not args.no_verify and not args.dry_run and not error_msg:
            LOGGER.info("Verifying chapter %s ...", ch_id)
            try:
                checkpoint = load_checkpoint(chapter, db_writer)
                vr = verify_chapter(ch_id, checkpoint, db_writer)

                if vr.is_ok:
                    warn_note = f", {len(vr.warnings)} warning(s)" if vr.warnings else ""
                    LOGGER.info(
                        "  ✓ Verification passed (%d checks%s)", len(vr.passed), warn_note
                    )
                    for w in vr.warnings:
                        LOGGER.warning("    ⚠  %s", w)
                else:
                    LOGGER.error("  ✗ Verification FAILED for chapter %s:", ch_id)
                    for f in vr.failed:
                        LOGGER.error("      FAIL: %s", f)
                    for w in vr.warnings:
                        LOGGER.warning("      WARN: %s", w)

            except Exception as exc:
                LOGGER.exception("Verifier raised exception for chapter %s: %s", ch_id, exc)
                error_msg = error_msg or f"Verifier error: {exc}"

        results.append(
            ChapterResult(
                chapter_id=ch_id,
                subject=subject,
                node_count=node_count,
                elapsed=elapsed,
                verification=vr,
                error=error_msg,
            )
        )

        should_stop = (
            args.on_failure == "stop"
            and (error_msg or (vr is not None and not vr.is_ok))
        )
        if should_stop:
            LOGGER.error(
                "Stopping batch after chapter %s failure (--on-failure=stop).", ch_id
            )
            break

        if i < len(chapters) - 1:
            next_ch_id = chapters[i + 1]["chapter_id"]
            already_extracted = _is_already_extracted(next_ch_id)
            pause = SHORT_PAUSE_SECONDS if already_extracted else args.pause_seconds
            next_title = chapters[i + 1].get("chapter_title", "")
            LOGGER.info(
                "Pausing %ds before chapter %s (%s) ...",
                pause,
                next_ch_id,
                next_title,
            )
            time.sleep(pause)

    _print_summary(results)


if __name__ == "__main__":
    main()
