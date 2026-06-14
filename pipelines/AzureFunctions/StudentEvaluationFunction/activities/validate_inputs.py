"""
Activity: Validate that all required inputs are resolved before evaluation.
Checks class, board, subject, chapter, and problem references.

v4 — Unified flow: always requires parsed_ref (text reference).
     Textbook images are optional context, not a separate validation path.
"""
import logging
from utils.db import lookup_chapter

# Canonical subject names as stored in ClassSubjectData / ChapterData.
# Keys must be lowercase. Value = exact DB spelling.
_SUBJECT_ALIASES: dict[str, str] = {
    "mathematics": "Maths",
    "math": "Maths",
    "maths": "Maths",
    "physics": "Physics",
    "phy": "Physics",
    "chemistry": "Chemistry",
    "chem": "Chemistry",
    "biology": "Biology",
    "bio": "Biology",
}


def _normalize_subject(raw: str | None) -> str | None:
    """Map common subject synonyms/abbreviations to canonical DB value."""
    if not raw:
        return raw
    canonical = _SUBJECT_ALIASES.get(raw.strip().lower())
    if canonical and canonical.lower() != raw.strip().lower():
        logging.info(f"Subject normalized: '{raw}' → '{canonical}'")
    return canonical or raw.strip()


def validate_inputs_activity(input_data: dict) -> dict:
    """
    Validate and resolve all inputs needed for evaluation.
    
    Args:
        input_data: {
            "record": dict — the solution_evaluations DB record,
            "parsed_ref": dict — output of parse_text_ref (always required)
        }
    
    Returns:
        {
            "valid": bool,
            "error": str (if invalid),
            "resolved": {
                "class": str,
                "board": str,
                "subject": str,
                "chapter_id": int,
                "chapter_title": str,
                "chapter_number": str,
                "problems": list — flat list of problem numbers/ids
            }
        }
    """
    record = input_data["record"]
    parsed_ref = input_data.get("parsed_ref")

    logging.info(f"Activity validate_inputs: job_id={record.get('id')}")

    # --- Resolve class, board, subject ---
    class_val = record.get("class")
    board = record.get("board")
    subject = record.get("subject")

    # Enrich from parsed text reference metadata if available
    if parsed_ref:
        metadata = parsed_ref.get("metadata", {})
        if not class_val and metadata.get("class"):
            class_val = metadata["class"]
        if not board and metadata.get("board"):
            board = metadata["board"]
        if not subject and metadata.get("subject"):
            subject = metadata["subject"]

    # Normalize subject to canonical DB value
    subject = _normalize_subject(subject)

    # Validate required fields
    errors = []
    if not subject:
        errors.append("subject is missing")
    if not class_val:
        errors.append("class is missing")

    # --- Resolve chapter ---
    chapter_id = record.get("chapter_id")
    chapter_title = record.get("chapter_title")
    chapter_number = record.get("chapter_number")

    # Try enriching from parsed text reference
    if parsed_ref:
        metadata = parsed_ref.get("metadata", {})
        if not chapter_title and metadata.get("chapter_title"):
            chapter_title = metadata["chapter_title"]
        if not chapter_number and metadata.get("chapter_number"):
            chapter_number = metadata["chapter_number"]

    # Attempt chapter lookup from DB
    chapter_data = None
    if chapter_id or (class_val and subject and (chapter_number or chapter_title)):
        chapter_data = lookup_chapter(
            class_val=class_val,
            board=board,
            subject=subject,
            chapter_id=chapter_id,
            chapter_number=str(chapter_number) if chapter_number else None,
            chapter_title=chapter_title,
        )

    if chapter_data:
        chapter_id = chapter_data["ChapterId"]
        chapter_title = chapter_data["ChapterTitle"]
        chapter_number = chapter_data["ChapterNumber"]
        logging.info(f"Chapter resolved: {chapter_title} (ID={chapter_id})")
    else:
        # Chapter not found — this is a warning, not necessarily fatal
        # We can still evaluate if we have enough context
        if not chapter_title:
            errors.append("chapter could not be resolved — no chapter_id, chapter_number, or chapter_title provided")

    # --- Collect problem list ---
    problems = []
    if parsed_ref:
        for ex in parsed_ref.get("exercises", []):
            exercise_label = ex.get("exercise_label")
            for pn in ex.get("problem_numbers", []):
                problems.append({
                    "problem_number": pn,
                    "exercise_label": exercise_label,
                })

    if not problems:
        errors.append("no problems resolved from input")

    if errors:
        error_msg = "; ".join(errors)
        logging.error(f"Validation failed: {error_msg}")
        return {"valid": False, "error": error_msg}

    resolved = {
        "class": class_val,
        "board": board,
        "subject": subject,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "chapter_number": chapter_number,
        "problems": problems,
    }

    logging.info(f"Validation passed: {len(problems)} problem(s), chapter='{chapter_title}'")
    return {"valid": True, "resolved": resolved}
