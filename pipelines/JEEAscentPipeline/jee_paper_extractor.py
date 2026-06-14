"""JEE question paper extractor for M1b.

Sends a full question paper PDF to Gemini Pro and parses the structured
JSON response into a list of question records ready for jee_question_bank.

Each question record (question_content JSONB):
  {
    "nta_question_id": "...",         -- NTA Q ID string from the paper
    "question_number": 1,             -- sequential number within the paper
    "raw_text": "...",                -- full question text including LaTeX
    "options": [                      -- [] for Integer-type questions
      {"nta_option_id": "...", "text": "..."},  -- index 0=A, 1=B, 2=C, 3=D
      ...
    ],
    "has_figure": false,              -- true if question refers to a diagram
    "figure_description": null,       -- Gemini's text description of the figure
    "figure_blob_url": null           -- populated in a later pass (Phase 2)
  }

Top-level question record written to jee_question_bank:
  nta_question_id, subject, section ("MCQ"|"Integer"), question_content, answer_key
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

# Subjects we expect to see in a JEE Main paper
_VALID_SUBJECTS = {"Physics", "Chemistry", "Mathematics", "Maths"}
_VALID_SECTIONS = {"MCQ", "Integer"}


# (subject, section) pairs — 6 calls of ~10–20 questions each to stay within
# the model's effective output limit. Math questions carry heavy LaTeX and
# truncate at ~30 per call; splitting by section keeps each call small.
_SUBJECT_SECTION_CALLS = [
    ("Physics", "MCQ"),
    ("Physics", "Integer"),
    ("Chemistry", "MCQ"),
    ("Chemistry", "Integer"),
    ("Mathematics", "MCQ"),
    ("Mathematics", "Integer"),
]

# Minimum questions expected per (subject, section) call before retry
_MIN_QUESTIONS = {
    ("Physics", "MCQ"): 5,
    ("Physics", "Integer"): 3,
    ("Chemistry", "MCQ"): 5,
    ("Chemistry", "Integer"): 3,
    ("Mathematics", "MCQ"): 5,
    ("Mathematics", "Integer"): 3,
}

# Default pause between consecutive Gemini calls (seconds).
# Prevents back-to-back 429 rate limiting on gemini-3.1-pro-preview.
# Override via --inter-call-delay CLI arg.
INTER_CALL_DELAY_SECONDS: int = 60


def extract_questions(
    pdf_path: Path,
    *,
    gemini_client: Any,
    model_config: Any,
    system_prompt: str,
    paper: Dict[str, Any],
    db_writer: Any,
    inter_call_delay: int = INTER_CALL_DELAY_SECONDS,
) -> List[Dict[str, Any]]:
    """Extract questions from a JEE paper PDF using Gemini Pro.

    Splits extraction into 6 calls (per subject × per section) of ~10–20 questions
    each to stay within the model's effective output token limit, then merges and
    deduplicates results. The PDF is cached once and reused across all 6 calls to
    reduce input token costs. An inter-call pause prevents 429 rate limiting.

    Args:
        pdf_path:           Local path to the downloaded question paper PDF.
        gemini_client:      GeminiClient instance (shared MultiStep module).
        model_config:       GeminiModelConfig for extraction (Pro model, JSON output).
        system_prompt:      Loaded text of question_extraction_system.txt.
        paper:              Row dict from exam_papers (id, year, dateofexam, shift, …).
        db_writer:          JEEExtractionDBWriter for answer key lookup.
        inter_call_delay:   Seconds to wait between Gemini calls (default 60).

    Returns:
        List of question dicts ready for db_writer.bulk_insert_questions().
    """
    LOGGER.info(
        "Extracting questions from paper id=%s year=%s dateofexam=%s shift=%s",
        paper["id"],
        paper.get("year"),
        paper.get("dateofexam"),
        paper.get("shift"),
    )

    # Cache the PDF once — all 6 subject/section calls reuse it.
    # generate_with_cache falls back to direct upload if caching fails.
    cached_doc = gemini_client.cache_document(
        pdf_path,
        model_id=model_config.model_id,
        ttl_seconds=3600,
        display_name=f"jee_paper_{paper['id']}",
    )

    all_raw: List[Dict[str, Any]] = []
    for subject, section in _SUBJECT_SECTION_CALLS:
        # Pause between calls to avoid back-to-back 429 rate limiting
        if all_raw:
            LOGGER.info("  Waiting %ds before next call...", inter_call_delay)
            time.sleep(inter_call_delay)

        LOGGER.info("  Extracting %s %s (paper id=%s)", subject, section, paper["id"])
        min_expected = _MIN_QUESTIONS.get((subject, section), 3)
        raw_questions: List[Dict[str, Any]] = []
        for attempt in range(3):
            raw_text = _call_gemini(
                pdf_path,
                gemini_client=gemini_client,
                model_config=model_config,
                system_prompt=system_prompt,
                subject_filter=subject,
                section_filter=section,
                cached_doc=cached_doc,
            )
            raw_questions = _parse_questions_json(raw_text)
            if len(raw_questions) >= min_expected:
                break
            LOGGER.warning(
                "  %s %s returned only %d questions on attempt %d/3 — retrying in 60s",
                subject, section, len(raw_questions), attempt + 1,
            )
            time.sleep(60)

        LOGGER.info("  Gemini returned %d %s %s entries", len(raw_questions), subject, section)
        all_raw.extend(raw_questions)

    LOGGER.info("Gemini returned %d raw question entries total", len(all_raw))

    questions = _normalize_and_enrich(all_raw, paper=paper, db_writer=db_writer)
    LOGGER.info(
        "Normalized to %d questions (paper id=%s)", len(questions), paper["id"]
    )
    return questions


def _call_gemini(
    pdf_path: Path,
    *,
    gemini_client: Any,
    model_config: Any,
    system_prompt: str,
    subject_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
    cached_doc: Optional[Any] = None,
) -> str:
    """Send the PDF to Gemini and return the raw text response.

    Uses cached_doc if provided (avoids re-uploading the PDF on each call).
    Falls back to direct upload if the cache is expired or unavailable.
    """
    if subject_filter and section_filter:
        section_label = (
            "Section A multiple choice (MCQ)" if section_filter == "MCQ"
            else "Section B integer/numerical type"
        )
        prompt = (
            f"Extract ONLY the {subject_filter} {section_label} questions from this JEE Main question paper "
            f"following the system instructions exactly. "
            f"Skip all questions that are NOT {subject_filter} AND NOT {section_filter} type. "
            "Return valid JSON only — a JSON array of question objects."
        )
    elif subject_filter:
        prompt = (
            f"Extract ONLY the {subject_filter} questions from this JEE Main question paper "
            f"following the system instructions exactly. "
            f"Skip all Physics, Chemistry, and Mathematics questions that are NOT {subject_filter}. "
            "Return valid JSON only — a JSON array of question objects."
        )
    else:
        prompt = (
            "Extract all questions from this JEE Main question paper "
            "following the system instructions exactly. "
            "Return valid JSON only."
        )

    if cached_doc is not None:
        result = gemini_client.generate_with_cache(
            model_config=model_config,
            prompt=prompt,
            cached_doc=cached_doc,
            system_instruction=system_prompt,
        )
    else:
        result = gemini_client.generate(
            model_config=model_config,
            prompt=prompt,
            document_path=pdf_path,
            system_instruction=system_prompt,
        )
    return result.text


def _parse_questions_json(raw_text: str) -> List[Dict[str, Any]]:
    """Parse Gemini's JSON response into a list of raw question dicts."""
    cleaned = raw_text.strip()
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        LOGGER.warning("JSON decode failed (%s); attempting partial extraction", exc)
        data = _extract_partial_json(cleaned)

    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]

    if not isinstance(data, list):
        LOGGER.error("Unexpected Gemini response structure: %r", type(data))
        return []

    return data


def _extract_partial_json(text: str) -> List[Dict[str, Any]]:
    """Best-effort: recover complete question objects from a truncated JSON array."""
    start = text.find("[")
    if start == -1:
        return []

    fragment = text[start:]

    # First try the full fragment as-is (handles minor whitespace issues)
    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        pass

    # Truncated array: find the last complete object boundary ("}," or "}\n")
    # and close the array there to recover all complete questions
    for marker in ("}\n  }", "},\n", "}, ", "},"):
        pos = fragment.rfind(marker)
        if pos != -1:
            repaired = fragment[: pos + 1] + "\n]"
            try:
                result = json.loads(repaired)
                if isinstance(result, list) and result:
                    LOGGER.info(
                        "Partial extraction recovered %d question(s) from truncated response",
                        len(result),
                    )
                    return result
            except json.JSONDecodeError:
                continue

    return []


def _normalize_and_enrich(
    raw_questions: List[Dict[str, Any]],
    *,
    paper: Dict[str, Any],
    db_writer: Any,
) -> List[Dict[str, Any]]:
    """Validate, normalise, and look up answer keys for each raw question."""
    # Normalise first pass — collect all NTA IDs for bulk AK lookup
    normalized: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for idx, raw in enumerate(raw_questions):
        try:
            q = _normalize_one(raw, idx=idx)
        except ValueError as exc:
            LOGGER.warning("Skipping question %d: %s", idx + 1, exc)
            continue

        nta_id = q["question_content"].get("nta_question_id")

        # Dedup by NTA ID
        if nta_id and nta_id in seen_ids:
            LOGGER.debug("Duplicate nta_question_id %s — skipping", nta_id)
            continue
        if nta_id:
            seen_ids.add(nta_id)

        normalized.append(q)

    # Single bulk DB round-trip for all answer keys
    all_nta_ids = [q["question_content"]["nta_question_id"] for q in normalized if q["question_content"].get("nta_question_id")]
    ak_map = db_writer.lookup_answer_keys_bulk(all_nta_ids)
    LOGGER.info("Bulk AK lookup: %d/%d IDs matched", len(ak_map), len(all_nta_ids))

    results: List[Dict[str, Any]] = []
    for q in normalized:
        nta_id = q["question_content"].get("nta_question_id")
        answer_key: Optional[str] = None
        if nta_id:
            raw_ak = ak_map.get(nta_id)
            if raw_ak:
                answer_key = _resolve_answer_key(
                    raw_ak, q["question_content"].get("options", [])
                )
            else:
                LOGGER.debug("No answer key found for Q ID %s", nta_id)
        q["answer_key"] = answer_key
        results.append(q)

    return results


def _normalize_one(raw: Dict[str, Any], *, idx: int) -> Dict[str, Any]:
    """Convert a raw Gemini question dict into the canonical M1b format."""
    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict, got {type(raw)}")

    # Subject
    subject = str(raw.get("subject", "")).strip()
    if subject not in _VALID_SUBJECTS:
        # Accept "Maths" / "Mathematics" as aliases
        if subject.lower() in {"maths", "mathematics"}:
            subject = "Mathematics"
        else:
            subject = subject or "Unknown"

    # Section
    section = str(raw.get("section", raw.get("type", "MCQ"))).strip()
    if section.lower() in {"integer", "numerical", "integer type", "numerical value"}:
        section = "Integer"
    else:
        section = "MCQ"

    # Options — store NTA option IDs; array position encodes A/B/C/D (index 0=A)
    raw_options = raw.get("options", [])
    if isinstance(raw_options, list):
        options = [
            {
                "nta_option_id": str(o.get("nta_option_id", "")).strip() or None,
                "text": str(o.get("text", "")),
            }
            for o in raw_options
            if isinstance(o, dict)
        ]
    else:
        options = []

    # Figure handling
    has_figure = bool(raw.get("has_figure", False))
    figure_description = raw.get("figure_description") or raw.get("figure_desc")

    question_content = {
        "nta_question_id": str(raw.get("nta_question_id", "")).strip() or None,
        "question_number": int(raw.get("question_number", idx + 1)),
        "raw_text": str(raw.get("raw_text", raw.get("text", ""))).strip(),
        "options": options if section == "MCQ" else [],
        "has_figure": has_figure,
        "figure_description": str(figure_description).strip() if figure_description else None,
        "figure_blob_url": None,  # populated later (Phase 2 figure crops)
    }

    return {
        "nta_question_id": question_content["nta_question_id"],
        "subject": subject,
        "section": section,
        "question_content": question_content,
        "answer_key": None,  # filled by caller after AK lookup
    }


_POSITION_LABELS = ["A", "B", "C", "D"]


def _resolve_answer_key(correct_option_id: str, options: List[Dict[str, Any]]) -> str:
    """Convert a raw AK correct_option_id to a usable answer key string.

    For MCQ: match correct_option_id against option nta_option_id values.
    Returns "A"/"B"/"C"/"D" based on the matching option's position (index).

    For Integer (Section B): the correct_option_id is a short integer string
    (e.g. "25", "1613") that does not match any NTA option ID.
    Return it as-is — it is the numeric answer.
    """
    # Try to match against option NTA IDs (MCQ case)
    for idx, opt in enumerate(options):
        if opt.get("nta_option_id") == correct_option_id:
            if idx < len(_POSITION_LABELS):
                return _POSITION_LABELS[idx]
            return str(idx + 1)  # safety fallback for >4 options

    # No match found — treat as integer answer (Section B)
    return correct_option_id


def validate_extraction(
    questions: List[Dict[str, Any]],
    *,
    expected_min: int = 70,
) -> tuple[bool, str]:
    """Validate that the extraction looks reasonable.

    Returns (ok, message).
    """
    count = len(questions)
    if count < expected_min:
        return False, f"Only {count} questions extracted (expected >= {expected_min})"

    # Check answer key coverage
    with_ak = sum(1 for q in questions if q.get("answer_key"))
    ak_pct = 100 * with_ak / count if count else 0
    if ak_pct < 80:
        return False, (
            f"Answer key coverage {ak_pct:.0f}% ({with_ak}/{count}) is below 80% — "
            "check that AKs were extracted first"
        )

    # Warn if count looks low for a standard paper (90 or 75) but don't fail
    expected_note = ""
    if count < 75:
        expected_note = " (expected 75 or 90 — check for missed questions)"
    return True, f"OK — {count} questions{expected_note}, {ak_pct:.0f}% have answer keys"
