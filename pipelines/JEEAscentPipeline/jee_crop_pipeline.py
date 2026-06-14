"""JEE Crop Pipeline — crop-based question extraction (M1b Phase 2).

Replaces the Gemini Pro full-PDF approach with per-question image crops sent to
Gemini Flash. Expected: ~3 min/paper vs ~90 min, ~$0.75 vs ~$30.

For each pending exam_papers row:
  1. Download PDF from Azure Blob
  2. Scan text layer: NTA question IDs + positions + option IDs
  3. Render per-question PNG crops
  4. Send each crop to Gemini Flash -> raw_text + options (LaTeX)
  5. Merge text-layer data (nta_id, option_ids) + Flash output + answer key lookup
  6. Bulk-insert into jee_question_bank
  7. Mark exam_papers.extraction_status = 'EXTRACTED'

Usage:
  python jee_crop_pipeline.py                    # all pending papers
  python jee_crop_pipeline.py --paper-ids 1,222  # specific papers
  python jee_crop_pipeline.py --year 2024        # filter by year
  python jee_crop_pipeline.py --dry-run          # no DB writes
  python jee_crop_pipeline.py --render-only      # crops only, no Flash/DB
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

PIPELINE_DIR = Path(__file__).resolve().parent
MULTISTEP_DIR = (
    PIPELINE_DIR.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
)
for _p in (str(PIPELINE_DIR), str(MULTISTEP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from settings_loader import load_local_settings
load_local_settings()

import fitz  # PyMuPDF

from db_writer import JEEExtractionDBWriter

CHECKPOINT_DIR = PIPELINE_DIR / "checkpoints"
LOG_DIR = PIPELINE_DIR / "logs"
TEMP_DIR = PIPELINE_DIR / "temp"
CROPS_DIR = TEMP_DIR / "crops"

CROP_DPI = 200

# NTA ID: 8–11 digits.  Must appear in a span containing "Question" (the question
# header line).  This filters out option IDs, cover-page IDs, and section headers.
NTA_ID_PATTERN = re.compile(r"\b(\d{8,11})\b")

# Option IDs look the same shape but appear in spans NOT containing "Question".
OPTION_ID_PATTERN = re.compile(r"\b(\d{8,12})\b")

# Concurrent Flash workers.  4 gives ~4x throughput with acceptable rate-limit
# risk on the preview endpoint.  Reduce to 2 if you see frequent 429s.
FLASH_WORKERS = 4

FLASH_PROMPT = """This is a cropped region from an NTA JEE Main question paper (bilingual).
Each question appears TWICE — first in English, then again in Hindi below it.

IMPORTANT: Extract ONLY the English version. Ignore the Hindi text completely.
DO NOT solve, reason about, or work out the question. Only transcribe exactly what is printed.

Extract the complete English question content using LaTeX for all mathematical notation:
- Use $...$ for inline math (e.g. $x^2 + y^2 = r^2$)
- Use \\frac{a}{b} for fractions, \\sqrt{x} for roots, \\int for integrals
- For piecewise/case functions use \\begin{cases}...\\end{cases}
- For options A/B/C/D, list each option text ONLY (no prefix labels needed)
- Do NOT include the NTA Question ID number or option ID numbers
- Do NOT include "Question Number:", "Question Id:", "Correct Marks:" header lines
- Do NOT include "Q.1", "Q.2" etc question numbering prefixes
- Describe any figures/diagrams briefly in [Figure: ...]

Return a JSON object with exactly these fields:
{
  "raw_text": "<full English question text with LaTeX>",
  "options": ["<option A text>", "<option B text>", "<option C text>", "<option D text>"],
  "has_figure": true/false,
  "figure_description": "<brief description or null>"
}
For integer/numerical questions (no options), return "options": [].
Return valid JSON only — no markdown fences."""

LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

def ensure_dirs() -> None:
    for d in (CHECKPOINT_DIR, LOG_DIR, TEMP_DIR, CROPS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    ensure_dirs()
    log_path = LOG_DIR / f"jee_crop_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Blob download
# ─────────────────────────────────────────────────────────────────────────────

def download_blob(blob_url: str, dest: Path) -> None:
    """Download from Azure Blob using DefaultAzureCredential."""
    if dest.exists():
        LOGGER.info("Already downloaded: %s", dest.name)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient as AzBlobClient

    LOGGER.info("Downloading %s -> %s", blob_url, dest.name)
    credential = DefaultAzureCredential()
    client = AzBlobClient.from_blob_url(blob_url, credential=credential)
    dest.write_bytes(client.download_blob().readall())
    LOGGER.info("Saved %d bytes", dest.stat().st_size)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Text layer scan
# ─────────────────────────────────────────────────────────────────────────────

def scan_text_layer(doc: fitz.Document) -> List[Dict[str, Any]]:
    """Walk every page and collect NTA question ID positions.

    Returns list of {nta_id, page, x0, y0, x1, y1} sorted by (page, y0).
    Filter: span must contain "Question" (rules out option IDs and cover-page noise).
    """
    found: List[Dict[str, Any]] = []
    seen: set = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if "Question" not in text:
                        continue
                    m = NTA_ID_PATTERN.search(text)
                    if not m:
                        continue
                    candidate = m.group(1)

                    bbox = span.get("bbox", (0, 0, 0, 0))
                    if bbox[0] > 200:
                        continue  # sidebar / cover-page column

                    if candidate in seen:
                        continue
                    seen.add(candidate)

                    found.append({
                        "nta_id": candidate,
                        "page": page_num,
                        "x0": bbox[0], "y0": bbox[1],
                        "x1": bbox[2], "y1": bbox[3],
                    })

    found.sort(key=lambda r: (r["page"], r["y0"]))
    return found


def scan_option_ids(doc: fitz.Document, positions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Collect up to 4 NTA option IDs per question from the text layer.

    Option IDs appear in spans that do NOT contain "Question". We collect them in
    document order within each question's crop region.

    Returns dict: nta_id -> [opt_id_A, opt_id_B, opt_id_C, opt_id_D]
    """
    # Single pass: collect all non-question spans with numeric IDs per page
    page_spans: Dict[int, List[Tuple[float, str]]] = {}  # page -> [(y0, text)]
    for pg in range(len(doc)):
        spans = []
        for block in doc[pg].get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text or "Question" in text:
                        continue
                    if not OPTION_ID_PATTERN.search(text):
                        continue
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    spans.append((bbox[1], text))
        page_spans[pg] = sorted(spans, key=lambda x: x[0])

    result: Dict[str, List[str]] = {}
    for i, pos in enumerate(positions):
        start_page, start_y = pos["page"], pos["y0"]
        if i + 1 < len(positions):
            end_page, end_y = positions[i + 1]["page"], positions[i + 1]["y0"]
        else:
            end_page = len(doc) - 1
            end_y = doc[end_page].rect.height

        opt_ids: List[str] = []
        seen: set = set()

        for pg in range(start_page, end_page + 1):
            y_top = start_y if pg == start_page else 0.0
            y_bot = end_y if pg == end_page else doc[pg].rect.height

            for y0, text in page_spans.get(pg, []):
                if y0 < y_top or y0 > y_bot:
                    continue
                m = OPTION_ID_PATTERN.search(text)
                if m:
                    oid = m.group(1)
                    if oid != pos["nta_id"] and oid not in seen:
                        seen.add(oid)
                        opt_ids.append(oid)

        result[pos["nta_id"]] = opt_ids[:4]

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Crop rendering
# ─────────────────────────────────────────────────────────────────────────────

def _stack_pixmaps(pixmaps: list) -> bytes:
    """Stack PyMuPDF Pixmap objects vertically; return PNG bytes."""
    import io
    from PIL import Image
    pil_imgs = [Image.open(io.BytesIO(p.tobytes("png"))) for p in pixmaps]
    total_h = sum(img.height for img in pil_imgs)
    max_w = max(img.width for img in pil_imgs)
    combined = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y = 0
    for img in pil_imgs:
        combined.paste(img, (0, y))
        y += img.height
    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue()


def render_crops(
    positions: List[Dict[str, Any]],
    doc: fitz.Document,
    crop_dir: Path,
    *,
    dpi: int = CROP_DPI,
) -> List[Dict[str, Any]]:
    """Render one PNG per question region; return list with png_bytes + local_path.

    Skips questions whose PNG already exists (resumable).
    """
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    rendered = []

    for idx, pos in enumerate(positions):
        q_num = idx + 1
        start_page, start_y = pos["page"], pos["y0"]

        if idx + 1 < len(positions):
            end_page, end_y = positions[idx + 1]["page"], positions[idx + 1]["y0"]
        else:
            end_page = len(doc) - 1
            end_y = doc[end_page].rect.height

        # Build page-slice parts
        parts = []
        if start_page == end_page:
            w = doc[start_page].rect.width
            parts.append({"page": start_page,
                          "rect": fitz.Rect(0, start_y, w, end_y)})
        else:
            w = doc[start_page].rect.width
            parts.append({"page": start_page,
                          "rect": fitz.Rect(0, start_y, w, doc[start_page].rect.height)})
            for pg in range(start_page + 1, end_page):
                w = doc[pg].rect.width
                parts.append({"page": pg,
                              "rect": fitz.Rect(0, 0, w, doc[pg].rect.height)})
            w = doc[end_page].rect.width
            parts.append({"page": end_page,
                          "rect": fitz.Rect(0, 0, w, end_y)})

        page_range = (f"p{start_page+1}" if start_page == end_page
                      else f"p{start_page+1}-p{end_page+1}")
        fname = f"q{q_num:03d}_{pos['nta_id']}_{page_range}.png"
        out_path = crop_dir / fname

        if out_path.exists():
            png_bytes = out_path.read_bytes()
            LOGGER.debug("  q%03d already rendered — loaded from disk", q_num)
        else:
            pixmaps = [
                doc[part["page"]].get_pixmap(matrix=matrix, clip=part["rect"])
                for part in parts
            ]
            png_bytes = (pixmaps[0].tobytes("png") if len(pixmaps) == 1
                         else _stack_pixmaps(pixmaps))
            out_path.write_bytes(png_bytes)

        rendered.append({
            "nta_id": pos["nta_id"],
            "q_num": q_num,
            "page_range": page_range,
            "local_path": out_path,
            "png_bytes": png_bytes,
        })

    LOGGER.info("Rendered %d crops to %s", len(rendered), crop_dir)
    return rendered


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Gemini Flash transcription
# ─────────────────────────────────────────────────────────────────────────────

def build_flash_client():
    """Build Vertex AI genai.Client (same auth as existing pipeline)."""
    from google import genai
    from google.genai import types
    from config import PipelineConfig  # type: ignore

    cfg = PipelineConfig.from_env()
    client = genai.Client(vertexai=True, project=cfg.project_id, location=cfg.location)
    return client, types


def call_flash(client: Any, types: Any, png_bytes: bytes) -> Dict[str, Any]:
    """Send a crop PNG to Gemini Flash and parse the JSON response.

    Retries up to 3 times on transient network errors with exponential backoff.
    """
    _RETRY_DELAYS = [5, 15, 30]

    for attempt, delay in enumerate(_RETRY_DELAYS + [None], start=1):
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                    FLASH_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=8192,
                ),
            )
            break  # success
        except Exception as exc:
            if delay is None:
                # All retries exhausted — return error result instead of crashing
                LOGGER.warning("Flash call failed after %d attempts: %s", attempt - 1, exc)
                return {"raw_text": "", "options": [], "has_figure": False,
                        "figure_description": None, "_parse_error": True, "_network_error": str(exc)}
            LOGGER.warning("Flash call attempt %d failed (%s) — retrying in %ds", attempt, exc, delay)
            time.sleep(delay)

    if not response.text:
        # Blocked or empty response (safety filter / quota)
        return {"raw_text": "", "options": [], "has_figure": False,
                "figure_description": None, "_parse_error": True, "_empty_response": True}

    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_text": raw, "options": [], "has_figure": False,
                "figure_description": None, "_parse_error": True}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Question assembly
# ─────────────────────────────────────────────────────────────────────────────

_SUBJECTS = ["Physics", "Chemistry", "Mathematics"]
_POSITION_LABELS = ["A", "B", "C", "D"]


def assign_subject_section(q_number: int, total: int) -> Tuple[str, str]:
    """Map question number to (subject, section) based on standard JEE structure.

    Standard layouts:
      90 questions: 30/subject (20 MCQ Section A + 10 Integer Section B)
      75 questions: 25/subject (20 MCQ Section A + 5 Integer Section B)
    """
    qs_per_subj = 30 if total >= 88 else 25
    mcq_per_subj = 20

    subj_idx = min((q_number - 1) // qs_per_subj, 2)
    within = (q_number - 1) % qs_per_subj
    subject = _SUBJECTS[subj_idx]
    section = "MCQ" if within < mcq_per_subj else "Integer"
    return subject, section


def _resolve_answer_key(correct_option_id: str, options: List[Dict[str, Any]]) -> str:
    """Convert correct_option_id to A/B/C/D (MCQ) or the raw integer string (Section B)."""
    for idx, opt in enumerate(options):
        if opt.get("nta_option_id") == correct_option_id:
            return _POSITION_LABELS[idx] if idx < 4 else str(idx + 1)
    # No match — integer answer or unresolvable MCQ
    return correct_option_id


def assemble_question(
    q_number: int,
    nta_id: str,
    option_ids: List[str],
    flash_result: Dict[str, Any],
    ak_map: Dict[str, str],
    total_questions: int,
) -> Dict[str, Any]:
    """Build a jee_question_bank-ready dict from all sources."""
    subject, section = assign_subject_section(q_number, total_questions)

    # Flash returns options as a list of strings (just the text, no label prefix)
    flash_opts = flash_result.get("options") or []
    if isinstance(flash_opts, list) and flash_opts and isinstance(flash_opts[0], dict):
        # Fallback: Flash returned [{label, text}] objects instead of plain strings
        flash_opts = [o.get("text", "") for o in flash_opts]

    options_out = []
    if section == "MCQ":
        for idx, text in enumerate(flash_opts[:4]):
            options_out.append({
                "nta_option_id": option_ids[idx] if idx < len(option_ids) else None,
                "text": str(text),
            })

    question_content = {
        "nta_question_id": nta_id,
        "question_number": q_number,
        "raw_text": flash_result.get("raw_text", ""),
        "options": options_out,
        "has_figure": bool(flash_result.get("has_figure", False)),
        "figure_description": flash_result.get("figure_description"),
        "figure_blob_url": None,  # populated later with --upload-crops
    }

    correct_id = ak_map.get(nta_id)
    answer_key = _resolve_answer_key(correct_id, options_out) if correct_id else None

    return {
        "nta_question_id": nta_id,
        "subject": subject,
        "section": section,
        "question_content": question_content,
        "answer_key": answer_key,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_questions(questions: List[Dict[str, Any]], expected_min: int = 70) -> Tuple[bool, str]:
    count = len(questions)
    if count < expected_min:
        return False, f"Only {count} questions (expected >= {expected_min})"
    with_ak = sum(1 for q in questions if q.get("answer_key"))
    ak_pct = 100 * with_ak / count if count else 0
    note = " (check AKs were extracted first)" if ak_pct < 80 else ""
    ok = ak_pct >= 80
    return ok, f"{count} questions, {ak_pct:.0f}% answer key coverage{note}"


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoints
# ─────────────────────────────────────────────────────────────────────────────

def _cp_path(paper_id: int) -> Path:
    return CHECKPOINT_DIR / f"crop_paper_{paper_id}.json"


def _load_cp(paper_id: int) -> Dict[str, Any]:
    p = _cp_path(paper_id)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"paper_id": paper_id, "stages": {}, "completed": False}


def _save_cp(cp: Dict[str, Any]) -> None:
    cp["updated_at"] = datetime.now(timezone.utc).isoformat()
    _cp_path(cp["paper_id"]).write_text(json.dumps(cp, indent=2, default=str), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Per-paper processing
# ─────────────────────────────────────────────────────────────────────────────

def process_paper(
    paper: Dict[str, Any],
    *,
    db: JEEExtractionDBWriter,
    dry_run: bool,
    render_only: bool,
    flash_client: Any,
    flash_types: Any,
) -> Dict[str, Any]:
    paper_id = paper["id"]
    cp = _load_cp(paper_id)

    if cp.get("completed") and not dry_run:
        LOGGER.info("Paper id=%s already complete — skipping", paper_id)
        return cp

    LOGGER.info(
        "Processing paper id=%s  year=%s  %s  %s",
        paper_id, paper.get("year"), paper.get("dateofexam", ""), paper.get("shift", ""),
    )

    # Fresh token at the start of each paper — avoids mid-paper expiry hangs
    if not dry_run:
        db.refresh_token()

    # ── Download ──────────────────────────────────────────────────────────────
    dest = TEMP_DIR / f"paper_{paper_id}_{paper['filename']}"
    download_blob(paper["blob_url"], dest)
    cp["stages"]["downloaded"] = True
    _save_cp(cp)

    # ── Scan text layer ───────────────────────────────────────────────────────
    doc = fitz.open(str(dest))
    positions = scan_text_layer(doc)
    LOGGER.info("  Found %d NTA question IDs", len(positions))

    if len(positions) < 70:
        LOGGER.warning(
            "  Only %d IDs found for paper id=%s — may be PRE_2021 format (skip or investigate)",
            len(positions), paper_id,
        )
        if len(positions) == 0:
            doc.close()
            cp["stages"]["scan_failed"] = True
            cp["error"] = "0 NTA IDs found — unsupported format"
            _save_cp(cp)
            return cp

    option_id_map = scan_option_ids(doc, positions)
    cp["stages"]["scanned"] = len(positions)
    _save_cp(cp)

    # ── Render crops ──────────────────────────────────────────────────────────
    crop_dir = CROPS_DIR / f"paper_{paper_id}"
    crop_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_crops(positions, doc, crop_dir)
    doc.close()
    cp["stages"]["rendered"] = len(rendered)
    _save_cp(cp)

    if render_only:
        LOGGER.info("  --render-only: stopping here. Crops in %s", crop_dir)
        return cp

    # ── Flash transcription ───────────────────────────────────────────────────
    total = len(rendered)
    ak_map = db.lookup_answer_keys_bulk([r["nta_id"] for r in rendered])
    LOGGER.info("  AK lookup: %d/%d matched", len(ak_map), total)

    # Resume: load any questions already transcribed in a previous run
    questions: List[Dict[str, Any]] = cp.get("questions_done", [])
    done_ids = {q["nta_question_id"] for q in questions}
    parse_errors = cp.get("stages", {}).get("parse_errors", 0)

    pending = [c for c in rendered if c["nta_id"] not in done_ids]
    LOGGER.info("  Transcribing %d crops (%d already done) with %d workers",
                len(pending), len(done_ids), FLASH_WORKERS)

    # Thread-safe state for checkpoint saves
    cp_lock = Lock()

    def _transcribe_one(crop: Dict[str, Any]) -> Dict[str, Any]:
        """Worker: call Flash and assemble one question. Returns assembled question dict."""
        flash_result = call_flash(flash_client, flash_types, crop["png_bytes"])
        opt_ids = option_id_map.get(crop["nta_id"], [])
        return assemble_question(
            crop["q_num"], crop["nta_id"], opt_ids, flash_result, ak_map, total
        )

    with ThreadPoolExecutor(max_workers=FLASH_WORKERS) as executor:
        future_to_crop = {executor.submit(_transcribe_one, c): c for c in pending}

        for future in as_completed(future_to_crop):
            crop = future_to_crop[future]
            q_num, nta_id = crop["q_num"], crop["nta_id"]
            try:
                q = future.result()
            except Exception as exc:
                LOGGER.error("  q%03d (%s) worker exception: %s", q_num, nta_id, exc)
                q = assemble_question(q_num, nta_id, [], {"raw_text": "", "options": [], "has_figure": False, "figure_description": None}, ak_map, total)

            if q["question_content"].get("raw_text") == "" and not q["question_content"].get("options"):
                parse_errors += 1
                LOGGER.warning("  q%03d (%s): Flash parse/network error", q_num, nta_id)

            LOGGER.info(
                "  q%03d %s  subj=%-12s sect=%-8s opts=%d  ak=%s",
                q_num, nta_id, q["subject"], q["section"],
                len(q["question_content"]["options"]),
                q["answer_key"] or "-",
            )

            # Thread-safe checkpoint save after each completed question
            with cp_lock:
                questions.append(q)
                done_ids.add(nta_id)
                cp["questions_done"] = questions
                cp["stages"]["parse_errors"] = parse_errors
                _save_cp(cp)

    cp["stages"]["transcribed"] = len(questions)
    _save_cp(cp)

    # ── Validate ──────────────────────────────────────────────────────────────
    ok, msg = validate_questions(questions)
    level = logging.INFO if ok else logging.WARNING
    LOGGER.log(level, "  Validation: %s", msg)
    cp["validation"] = msg

    # ── DB write ──────────────────────────────────────────────────────────────
    if dry_run:
        LOGGER.info("  --dry-run: skipping DB writes")
    elif db.questions_exist_for_paper(paper_id):
        LOGGER.info("  Questions already exist for paper id=%s — skipping insert", paper_id)
        db.mark_paper_extracted(paper_id)
        cp["stages"]["db_written"] = 0
    else:
        count = db.bulk_insert_questions(questions, paper)
        LOGGER.info("  Inserted %d questions", count)
        db.mark_paper_extracted(paper_id)
        cp["stages"]["db_written"] = count

    cp["completed"] = not dry_run
    cp["summary"] = {
        "questions": len(questions),
        "ak_matched": len(ak_map),
        "parse_errors": parse_errors,
        "validation": msg,
    }
    _save_cp(cp)
    return cp


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="JEE crop-based extraction pipeline.")
    p.add_argument("--paper-ids", help="Comma-separated exam_papers IDs")
    p.add_argument("--year", type=int, help="Only process papers for this year")
    p.add_argument("--session", help="Filter by session name prefix")
    p.add_argument("--dry-run", action="store_true", help="No DB writes")
    p.add_argument("--render-only", action="store_true", help="Render crops only, skip Flash")
    return p.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    paper_ids = [int(x) for x in args.paper_ids.split(",")] if args.paper_ids else None

    db = JEEExtractionDBWriter()
    # When explicit IDs are given, fetch regardless of extraction_status
    # (allows re-running on already-extracted or dry-run papers).
    if paper_ids:
        papers = db.fetch_papers_by_ids(paper_ids)
    else:
        papers = db.fetch_pending_papers(year=args.year, session=args.session)

    if not papers:
        LOGGER.info("No pending papers found.")
        return

    LOGGER.info("Papers to process: %d", len(papers))

    flash_client = flash_types = None
    if not args.render_only:
        flash_client, flash_types = build_flash_client()

    # Pause between papers to let the rate-limit window reset.
    INTER_PAPER_PAUSE = 30  # seconds

    ok_count = fail_count = 0
    for i, paper in enumerate(papers):
        if i > 0 and not args.render_only:
            LOGGER.info("Pausing %ds before next paper...", INTER_PAPER_PAUSE)
            time.sleep(INTER_PAPER_PAUSE)
        try:
            cp = process_paper(
                paper,
                db=db,
                dry_run=args.dry_run,
                render_only=args.render_only,
                flash_client=flash_client,
                flash_types=flash_types,
            )
            if cp.get("error"):
                LOGGER.error("Paper id=%s failed: %s", paper["id"], cp["error"])
                fail_count += 1
            else:
                ok_count += 1
        except Exception as exc:
            LOGGER.exception("Paper id=%s raised exception: %s", paper["id"], exc)
            if not args.dry_run:
                try:
                    db.mark_paper_failed(paper["id"])
                except Exception:
                    pass
            fail_count += 1

    LOGGER.info("Done. OK=%d  FAILED=%d", ok_count, fail_count)


if __name__ == "__main__":
    main()
