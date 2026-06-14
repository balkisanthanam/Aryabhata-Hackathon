"""Main pipeline entrypoint for Module M1b: JEE Papers Extraction.

Orchestrates two sequential phases:
  Phase 1 — Answer Key extraction
    For each PENDING exam_answer_keys row:
      - Download PDF from blob storage
      - Parse Q-ID → option-ID pairs using PyMuPDF
      - Bulk-insert into jee_answer_mappings
      - Mark exam_answer_keys.extraction_status = 'EXTRACTED'

  Phase 2 — Question paper extraction
    For each PENDING exam_papers row:
      - Download PDF from blob storage
      - Detect format (PRE_2021 / 2021_PLUS) via Gemini Flash
      - Extract all questions via Gemini Pro (full PDF pass)
      - Look up answer keys from jee_answer_mappings inline
      - Bulk-insert into jee_question_bank
      - Mark exam_papers.extraction_status = 'EXTRACTED'

Checkpoints are saved per-item so the pipeline is fully resumable.

Usage:
  # Full run (AKs first, then papers)
  python jee_extraction_pipeline.py

  # AKs only
  python jee_extraction_pipeline.py --ak-only

  # Format detection only (no extraction)
  python jee_extraction_pipeline.py --format-only

  # Specific papers
  python jee_extraction_pipeline.py --paper-ids 12,34,56

  # Filter by year / session
  python jee_extraction_pipeline.py --year 2024 --session "Session 1"

  # Dry run (extract + validate, no DB writes)
  python jee_extraction_pipeline.py --dry-run --year 2024
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from db_writer import JEEExtractionDBWriter
from jee_ak_extractor import extract_answer_key, validate_extraction as validate_ak
from jee_format_detector import detect_format
from jee_paper_extractor import extract_questions, validate_extraction as validate_paper
from settings_loader import load_local_settings

load_local_settings()

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


PIPELINE_DIR = Path(__file__).resolve().parent
CHECKPOINT_DIR = PIPELINE_DIR / "checkpoints"
LOG_DIR = PIPELINE_DIR / "logs"
PROMPTS_DIR = PIPELINE_DIR / "prompts"
TEMP_DIR = PIPELINE_DIR / "temp"

# Shared MultiStep libs location
MULTISTEP_DIR = (
    PIPELINE_DIR.parent
    / "ExtractionPipeline"
    / "SchoolDataExtraction"
    / "MultiStep"
)
if str(MULTISTEP_DIR) not in sys.path:
    sys.path.insert(0, str(MULTISTEP_DIR))

from config import GeminiModelConfig, PipelineConfig  # type: ignore  # noqa: E402
from gemini_client import GeminiClient  # type: ignore  # noqa: E402

LOGGER = logging.getLogger(__name__)


# ─────────────────────────── setup ────────────────────────────────


def ensure_runtime_dirs() -> None:
    for d in (CHECKPOINT_DIR, LOG_DIR, PROMPTS_DIR, TEMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    ensure_runtime_dirs()
    log_path = LOG_DIR / f"jee_extraction_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JEE Ascent M1b: extract questions from NTA PDFs.")
    parser.add_argument("--paper-ids", help="Comma-separated exam_papers IDs to process")
    parser.add_argument("--year", type=int, help="Only process papers/AKs for this year")
    parser.add_argument("--session", help="Filter papers by session (e.g. 'Session 1')")
    parser.add_argument("--ak-only", action="store_true", help="Run Phase 1 (AK extraction) only")
    parser.add_argument(
        "--format-only",
        action="store_true",
        help="Run format detection pass only (no question extraction or DB writes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and validate; skip all DB writes.",
    )
    parser.add_argument(
        "--inter-call-delay",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Seconds to wait between Gemini extraction calls (default: 60).",
    )
    return parser.parse_args()


def parse_ids(value: Optional[str]) -> Optional[List[int]]:
    if not value:
        return None
    return [int(p.strip()) for p in value.split(",") if p.strip()]


# ─────────────────────── checkpoint helpers ───────────────────────


def _cp_path(kind: str, item_id: int) -> Path:
    return CHECKPOINT_DIR / f"{kind}_{item_id}.json"


def _load_cp(kind: str, item_id: int) -> Dict[str, Any]:
    path = _cp_path(kind, item_id)
    if path.exists():
        cp = json.loads(path.read_text(encoding="utf-8"))
        cp.setdefault("errors", [])
        return cp
    return {"id": item_id, "kind": kind, "stages": {}, "errors": [], "summary": {}}


def _save_cp(cp: Dict[str, Any]) -> None:
    cp["updated_at"] = _utcnow()
    path = _cp_path(cp["kind"], cp["id"])
    path.write_text(json.dumps(cp, indent=2, default=str), encoding="utf-8")


def _save_cp_nonfatal(cp: Dict[str, Any]) -> None:
    try:
        _save_cp(cp)
    except Exception as exc:
        LOGGER.warning("Checkpoint save failed (non-fatal): %s", exc)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────── prompt loader ────────────────────────────


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ───────────────────── blob download helper ───────────────────────


def download_blob(blob_url: str, dest: Path) -> None:
    """Download from Azure Blob using DefaultAzureCredential."""
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient as AzBlobClient

    LOGGER.info("Downloading %s → %s", blob_url, dest)
    credential = DefaultAzureCredential()
    client = AzBlobClient.from_blob_url(blob_url, credential=credential)
    dest.write_bytes(client.download_blob().readall())
    LOGGER.info("Saved %d bytes to %s", dest.stat().st_size, dest)


# ─────────────────────── Phase 1: AK extraction ───────────────────


def process_answer_key(
    ak: Dict[str, Any],
    *,
    db_writer: JEEExtractionDBWriter,
    dry_run: bool,
) -> Dict[str, Any]:
    """Process one exam_answer_keys row."""
    cp = _load_cp("ak", ak["id"])
    if cp["stages"].get("completed"):
        LOGGER.info("AK id=%s already complete — skipping", ak["id"])
        return cp

    cp.update({"year": ak["year"], "session": ak["session"]})

    # Download
    dest = TEMP_DIR / f"ak_{ak['id']}_{ak.get('filename', 'key.pdf')}"
    if not cp["stages"].get("downloaded"):
        download_blob(ak["blob_url"], dest)
        cp["stages"]["downloaded"] = True
        _save_cp_nonfatal(cp)
    else:
        dest = Path(cp.get("local_path", dest))

    cp["local_path"] = str(dest)
    _save_cp_nonfatal(cp)

    # Parse
    if not cp["stages"].get("parsed"):
        mappings = extract_answer_key(ak["blob_url"], dest, year=ak["year"])
        ok, msg = validate_ak(mappings, year=ak["year"])
        if not ok:
            LOGGER.warning("AK validation warning (id=%s): %s", ak["id"], msg)
        cp["mappings_count"] = len(mappings)
        cp["stages"]["parsed"] = True
        cp["summary"]["validation"] = msg
        _save_cp_nonfatal(cp)
    else:
        # Re-parse from disk (idempotent)
        mappings = extract_answer_key(ak["blob_url"], dest, year=ak["year"])

    if dry_run:
        LOGGER.info("[dry-run] AK id=%s: %d pairs extracted", ak["id"], len(mappings))
        cp["stages"]["completed"] = True
        cp["summary"]["mode"] = "dry-run"
        _save_cp_nonfatal(cp)
        return cp

    # DB write
    if not cp["stages"].get("db_written"):
        if not db_writer.answer_key_mappings_exist(ak["id"]):
            inserted = db_writer.bulk_insert_answer_mappings(mappings, source_key_id=ak["id"])
            LOGGER.info("Inserted %d answer mappings for AK id=%s", inserted, ak["id"])
        else:
            LOGGER.info("Mappings already exist for AK id=%s — skipping insert", ak["id"])

        db_writer.mark_answer_key_extracted(ak["id"])
        cp["stages"]["db_written"] = True
        _save_cp_nonfatal(cp)

    cp["stages"]["completed"] = True
    cp["summary"]["mode"] = "full-run"
    _save_cp_nonfatal(cp)
    LOGGER.info("AK id=%s complete (%d pairs)", ak["id"], cp.get("mappings_count", 0))
    return cp


# ───────────────────── Phase 2: paper extraction ──────────────────


def process_paper(
    paper: Dict[str, Any],
    *,
    gemini_client: GeminiClient,
    format_model: GeminiModelConfig,
    extract_model: GeminiModelConfig,
    format_prompt: str,
    extract_prompt: str,
    db_writer: JEEExtractionDBWriter,
    dry_run: bool,
    format_only: bool,
    inter_call_delay: int = 60,
) -> Dict[str, Any]:
    """Process one exam_papers row through format detection + question extraction."""
    cp = _load_cp("paper", paper["id"])
    if cp["stages"].get("completed"):
        LOGGER.info("Paper id=%s already complete — skipping", paper["id"])
        return cp

    cp.update({
        "year": paper.get("year"),
        "dateofexam": str(paper.get("dateofexam", "")),
        "shift": paper.get("shift"),
    })

    # Download
    dest = TEMP_DIR / f"paper_{paper['id']}_{paper.get('filename', 'paper.pdf')}"
    if not cp["stages"].get("downloaded"):
        download_blob(paper["blob_url"], dest)
        cp["stages"]["downloaded"] = True
        cp["local_path"] = str(dest)
        _save_cp_nonfatal(cp)
    else:
        dest = Path(cp.get("local_path", dest))

    # Format detection
    if not cp["stages"].get("format_detected"):
        fmt = detect_format(
            dest,
            gemini_client=gemini_client,
            model_config=format_model,
            prompt_template=format_prompt,
        )
        cp["paper_format"] = fmt
        cp["stages"]["format_detected"] = True
        _save_cp_nonfatal(cp)

        if not dry_run:
            db_writer.update_paper_format(paper["id"], fmt)
    else:
        fmt = cp.get("paper_format", "UNKNOWN")

    LOGGER.info("Paper id=%s format=%s", paper["id"], fmt)

    if format_only:
        cp["stages"]["completed"] = True
        cp["summary"]["mode"] = "format-only"
        _save_cp_nonfatal(cp)
        return cp

    # Question extraction
    if not cp["stages"].get("questions_extracted"):
        questions = extract_questions(
            dest,
            gemini_client=gemini_client,
            model_config=extract_model,
            system_prompt=extract_prompt,
            paper=paper,
            db_writer=db_writer,
            inter_call_delay=inter_call_delay,
        )
        ok, msg = validate_paper(questions)
        if not ok:
            LOGGER.warning("Paper validation warning (id=%s): %s", paper["id"], msg)

        cp["question_count"] = len(questions)
        cp["stages"]["questions_extracted"] = True
        cp["questions"] = questions  # cached to avoid re-calling Gemini on retry
        cp["summary"]["validation"] = msg
        _save_cp_nonfatal(cp)
    else:
        # Load from checkpoint if available — avoids re-calling Gemini
        if cp.get("questions"):
            questions = cp["questions"]
            LOGGER.info(
                "Loaded %d questions from checkpoint (paper id=%s)", len(questions), paper["id"]
            )
        else:
            questions = extract_questions(
                dest,
                gemini_client=gemini_client,
                model_config=extract_model,
                system_prompt=extract_prompt,
                paper=paper,
                db_writer=db_writer,
                inter_call_delay=inter_call_delay,
            )

    if dry_run:
        LOGGER.info("[dry-run] Paper id=%s: %d questions extracted", paper["id"], len(questions))
        cp["stages"]["completed"] = True
        cp["summary"]["mode"] = "dry-run"
        _save_cp_nonfatal(cp)
        return cp

    # DB write
    if not cp["stages"].get("db_written"):
        if not db_writer.questions_exist_for_paper(paper["id"]):
            inserted = db_writer.bulk_insert_questions(questions, paper=paper)
            LOGGER.info("Inserted %d questions for paper id=%s", inserted, paper["id"])
        else:
            LOGGER.info("Questions already exist for paper id=%s — skipping insert", paper["id"])

        db_writer.mark_paper_extracted(paper["id"])
        cp["stages"]["db_written"] = True
        _save_cp_nonfatal(cp)

    cp["stages"]["completed"] = True
    cp["summary"]["mode"] = "full-run"
    _save_cp_nonfatal(cp)
    LOGGER.info("Paper id=%s complete (%d questions)", paper["id"], cp.get("question_count", 0))
    return cp


# ──────────────────────────── main ────────────────────────────────


def main() -> None:
    ensure_runtime_dirs()
    configure_logging()
    args = parse_args()

    db_writer = JEEExtractionDBWriter()

    config = PipelineConfig.from_env()
    gemini_client = GeminiClient(config)

    # Model configs
    format_model = GeminiModelConfig(
        model_id="gemini-3-flash-preview",
        temperature=0.1,
        response_mime_type="application/json",
    )
    extract_model = GeminiModelConfig(
        model_id="gemini-3.1-pro-preview",
        temperature=0.2,
        max_output_tokens=65536,
    )

    # Load prompts
    format_prompt = load_prompt("format_detection_prompt.txt")
    extract_prompt = load_prompt("question_extraction_system.txt")

    # ── Phase 1: Answer keys ──────────────────────────────────────
    aks = db_writer.fetch_pending_answer_keys(
        year=args.year,
        session=args.session,
    )
    LOGGER.info("Found %d PENDING answer key(s)", len(aks))

    ak_errors = 0
    for ak in aks:
        try:
            process_answer_key(ak, db_writer=db_writer, dry_run=args.dry_run)
        except Exception:
            ak_errors += 1
            LOGGER.exception("Failed processing AK id=%s (year=%s session=%s)", ak["id"], ak["year"], ak["session"])
            cp = _load_cp("ak", ak["id"])
            cp["errors"].append({"timestamp": _utcnow(), "message": "See log for traceback"})
            if not args.dry_run:
                try:
                    db_writer.mark_answer_key_failed(ak["id"])
                except Exception:
                    pass
            _save_cp_nonfatal(cp)

    LOGGER.info("Phase 1 complete. %d AKs processed, %d errors.", len(aks), ak_errors)

    if args.ak_only:
        return

    # ── Phase 2: Question papers ──────────────────────────────────
    papers = db_writer.fetch_pending_papers(
        paper_ids=parse_ids(args.paper_ids),
        year=args.year,
        session=args.session,
    )
    LOGGER.info("Found %d PENDING paper(s)", len(papers))

    paper_errors = 0
    for paper in papers:
        try:
            process_paper(
                paper,
                gemini_client=gemini_client,
                format_model=format_model,
                extract_model=extract_model,
                format_prompt=format_prompt,
                extract_prompt=extract_prompt,
                db_writer=db_writer,
                dry_run=args.dry_run,
                format_only=args.format_only,
                inter_call_delay=args.inter_call_delay,
            )
        except Exception:
            paper_errors += 1
            LOGGER.exception(
                "Failed processing paper id=%s (year=%s date=%s shift=%s)",
                paper["id"],
                paper.get("year"),
                paper.get("dateofexam"),
                paper.get("shift"),
            )
            cp = _load_cp("paper", paper["id"])
            cp["errors"].append({"timestamp": _utcnow(), "message": "See log for traceback"})
            if not args.dry_run:
                try:
                    db_writer.mark_paper_failed(paper["id"])
                except Exception:
                    pass
            _save_cp_nonfatal(cp)

    LOGGER.info("Phase 2 complete. %d papers processed, %d errors.", len(papers), paper_errors)


if __name__ == "__main__":
    main()
