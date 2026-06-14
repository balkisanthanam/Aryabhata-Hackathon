"""Answer key PDF extractor for M1b.

Parses NTA JEE Main answer key PDFs (text-selectable) using PyMuPDF.
AK PDFs are structured as a multi-column table with 3 pairs of
  QUESTION ID | CORRECT OPTION ID
per page, covering all dates × shifts for a session.

Q ID digit counts by year:
  2021 : 10-digit Q ID, 11-digit option ID
  2022 : 6-digit sequential OR 11-digit NTA (mixed pages), option IDs vary
  2023 : 10-digit Q ID, 11-digit option ID
  2024 : 11-digit Q ID, 12-digit option ID
  2025 : 10-digit Q ID, 11-digit option ID

Integer-type answers: raw numbers (e.g. 18, 420) not wrapped in text.
Regex \b\d{6,}\b captures all year formats for Q IDs.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

LOGGER = logging.getLogger(__name__)

# Matches any run of 6+ digits (handles 6-digit 2022 IDs and 10-12 digit IDs)
_QID_RE = re.compile(r"\b(\d{6,})\b")

# NTA AK pages typically look like:
#   100001  1   200001  3   300001  2
#   100002  4   200002  A   300002  B
# The regex below captures a pair: (question_id, option_or_answer)
# Option/answer can be:
#   - 1-4 digit numeric (option number for MCQ, or raw integer answer)
#   - A/B/C/D letters (some years use letters)
#   - 11-12 digit numeric (option IDs in 2024 format)
_PAIR_RE = re.compile(
    r"(\d{6,})\s+([A-Da-d]|\d{1,12}(?!\d))",
    re.MULTILINE,
)


def _download_blob(blob_url: str, dest: Path) -> None:
    """Download a blob from Azure using DefaultAzureCredential."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient as AzBlobClient

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return

    LOGGER.info("Downloading AK PDF from blob: %s", blob_url)
    credential = DefaultAzureCredential()
    client = AzBlobClient.from_blob_url(blob_url, credential=credential)
    dest.write_bytes(client.download_blob().readall())
    LOGGER.info("Saved AK PDF to %s (%d bytes)", dest, dest.stat().st_size)


def extract_answer_key(
    blob_url: str,
    dest_path: Path,
    *,
    year: int,
) -> List[Dict[str, str]]:
    """Download (if needed) and parse an NTA answer key PDF.

    Returns a list of dicts:
        [{"nta_question_id": "...", "correct_option_id": "..."}, ...]

    The caller is responsible for inserting into jee_answer_mappings.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PyMuPDF not installed. Run: pip install PyMuPDF"
        )

    _download_blob(blob_url, dest_path)

    doc = fitz.open(str(dest_path))
    try:
        mappings = _parse_ak_document(doc, year=year)
    finally:
        doc.close()

    LOGGER.info(
        "Extracted %d Q-ID→option pairs from %s (year=%d)",
        len(mappings),
        dest_path.name,
        year,
    )
    return mappings


def _parse_ak_document(doc: Any, *, year: int) -> List[Dict[str, str]]:
    """Extract all Q-ID / correct-option pairs from an open PyMuPDF document."""
    seen: Dict[str, str] = {}  # nta_question_id → correct_option_id (dedup)

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        pairs = _parse_page_text(text, year=year)
        for qid, option in pairs:
            if qid not in seen:
                seen[qid] = option
            # If we see a duplicate with a different answer, keep the first
            # (AK PDFs repeat mappings across shifts; answers should be identical)

    return [{"nta_question_id": qid, "correct_option_id": opt} for qid, opt in seen.items()]


def _parse_page_text(text: str, *, year: int) -> List[Tuple[str, str]]:
    """Extract (question_id, correct_option_id) pairs from one page's text."""
    pairs: List[Tuple[str, str]] = []

    for match in _PAIR_RE.finditer(text):
        qid = match.group(1)
        option = match.group(2).strip()

        # Basic sanity: Q ID must meet minimum digit length for the year
        min_digits = _min_qid_digits(year)
        if len(qid) < min_digits:
            continue

        # Normalise letter options to uppercase
        option = option.upper() if option.isalpha() else option

        pairs.append((qid, option))

    return pairs


def _min_qid_digits(year: int) -> int:
    """Return the minimum digit count we expect for Q IDs given a year."""
    if year == 2022:
        return 6   # 2022 uses 6-digit sequential IDs on most pages
    return 8       # 2021/2023/2024/2025 all use 10-11+ digit IDs; 8 is safe lower bound


def validate_extraction(
    mappings: List[Dict[str, str]],
    *,
    year: int,
    expected_min: int = 300,
) -> Tuple[bool, str]:
    """Validate that the extraction looks reasonable.

    Returns (ok, message).
    """
    count = len(mappings)
    if count < expected_min:
        return False, f"Only {count} pairs extracted (expected >= {expected_min})"

    # Spot-check: Q IDs should all be numeric strings
    non_numeric = [m["nta_question_id"] for m in mappings if not m["nta_question_id"].isdigit()]
    if non_numeric:
        return False, f"Non-numeric Q IDs found: {non_numeric[:5]}"

    # Options should be short (1-12 chars)
    long_options = [m["correct_option_id"] for m in mappings if len(m["correct_option_id"]) > 12]
    if long_options:
        return False, f"Suspiciously long option IDs: {long_options[:3]}"

    return True, f"OK — {count} pairs extracted"
