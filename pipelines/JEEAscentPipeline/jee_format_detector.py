"""JEE paper format detector for M1b.

Classifies a question paper PDF as:
  PRE_2021   — single-column layout, older NTA format (pre-2021 papers)
  2021_PLUS  — two-column layout, modern NTA format (2021 onwards)
  UNKNOWN    — could not determine with confidence

Strategy:
  1. Render page 1 of the PDF as a PNG image using PyMuPDF.
  2. Send the image to Gemini Flash with a classification prompt.
  3. Parse the JSON response to extract the format label.

This avoids loading the entire PDF into Gemini for format detection,
keeping it fast and cheap (Flash model, single-page image).
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

VALID_FORMATS = {"PRE_2021", "2021_PLUS", "UNKNOWN"}

# Resolution for page rendering (DPI)
_RENDER_DPI = 150


def detect_format(
    pdf_path: Path,
    *,
    gemini_client: Any,
    model_config: Any,
    prompt_template: str,
) -> str:
    """Classify the layout format of a JEE question paper PDF.

    Args:
        pdf_path:        Local path to the downloaded PDF.
        gemini_client:   GeminiClient instance from the shared MultiStep module.
        model_config:    GeminiModelConfig for the Flash model.
        prompt_template: Loaded text of format_detection_prompt.txt.

    Returns:
        One of "PRE_2021", "2021_PLUS", or "UNKNOWN".
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Run: pip install PyMuPDF")

    page_image_path = _render_first_page(pdf_path)
    try:
        result_text = _call_gemini(
            page_image_path,
            gemini_client=gemini_client,
            model_config=model_config,
            prompt=prompt_template,
        )
        fmt = _parse_format(result_text)
    finally:
        page_image_path.unlink(missing_ok=True)

    LOGGER.info("Format detected for %s: %s", pdf_path.name, fmt)
    return fmt


def _render_first_page(pdf_path: Path) -> Path:
    """Render page 0 of a PDF to a temporary PNG and return its path."""
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        mat = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    finally:
        doc.close()

    out_path = pdf_path.parent / f"_fmt_detect_{pdf_path.stem}_p0.png"
    pix.save(str(out_path))
    LOGGER.debug("Rendered page 0 → %s", out_path)
    return out_path


def _call_gemini(
    image_path: Path,
    *,
    gemini_client: Any,
    model_config: Any,
    prompt: str,
) -> str:
    """Call Gemini Flash with a page image and return the raw response text."""
    result = gemini_client.generate(
        model_config=model_config,
        prompt=prompt,
        document_path=image_path,
    )
    return result.text


def _parse_format(raw_text: str) -> str:
    """Extract the format label from Gemini's JSON response."""
    # Try JSON parse first
    try:
        cleaned = raw_text.strip()
        # Strip markdown code fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        data = json.loads(cleaned)
        fmt = str(data.get("format", "UNKNOWN")).upper().strip()
        if fmt in VALID_FORMATS:
            return fmt
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: scan text for known format strings
    upper_text = raw_text.upper()
    if "2021_PLUS" in upper_text or "2021 PLUS" in upper_text:
        return "2021_PLUS"
    if "PRE_2021" in upper_text or "PRE 2021" in upper_text:
        return "PRE_2021"

    LOGGER.warning("Could not parse format from Gemini response: %r", raw_text[:200])
    return "UNKNOWN"
