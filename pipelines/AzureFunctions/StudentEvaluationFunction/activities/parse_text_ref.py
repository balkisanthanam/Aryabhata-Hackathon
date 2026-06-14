"""
Activity: Parse student's free-form text reference into structured problem numbers.
Uses Gemini MODEL_TEXT_PARSE + Text_ParsingPrompt.
"""
import logging
from utils.gemini_client import call_gemini, MODEL_TEXT_PARSE
from utils.prompt_loader import load_prompt, fill_template
from utils.db import get_chapter_titles


def parse_text_ref_activity(input_data: dict) -> dict:
    """
    Parse free-form text like "13.8, 13.9, 13.10" into structured problem references.
    
    Args:
        input_data: {
            "problem_text_ref": str,
            "class": str,
            "board": str,
            "subject": str,
            "chapter_title": str (optional)
        }
    
    Returns:
        Parsed result: {
            "metadata": {"subject": ..., "chapter_number": ..., "chapter_title": ...},
            "exercises": [{"exercise_label": str|null, "problem_numbers": [...]}]
        }
    """
    text_ref = input_data["problem_text_ref"]
    logging.info(f"Activity parse_text_ref: text='{text_ref}'")

    # Fetch valid chapter titles for grounding (cheap DB query ~5ms)
    subject = input_data.get("subject")
    class_val = input_data.get("class")
    if subject:
        titles = get_chapter_titles(subject, class_val)
        valid_chapters = ", ".join(titles) if titles else "(not available)"
    else:
        valid_chapters = "(not available — subject unknown)"

    # Load and fill the text parsing prompt
    prompt_template = load_prompt("Text_ParsingPrompt.md")
    filled_prompt = fill_template(
        prompt_template,
        user_input=text_ref,
        valid_chapters=valid_chapters,
    )

    # Call Gemini for structured parsing
    gemini_response = call_gemini(
        model_id=MODEL_TEXT_PARSE,
        content_parts=[filled_prompt],
        response_json=True,
        temperature=0.1,
    )

    result = gemini_response["parsed_result"]

    # Merge any metadata extracted by Gemini with what we already know
    metadata = result.get("metadata", {})

    # Canonical subjects — anything Gemini puts in "subject" that isn't one of
    # these is likely a chapter title (e.g. "Organic Chemistry", "Thermodynamics")
    _CANONICAL_SUBJECTS = {"physics", "chemistry", "maths", "mathematics", "biology"}

    gemini_subject = (metadata.get("subject") or "").strip()
    if gemini_subject and gemini_subject.lower() not in _CANONICAL_SUBJECTS:
        # Gemini misclassified a chapter name as subject — reclassify
        if not metadata.get("chapter_title"):
            metadata["chapter_title"] = gemini_subject
            logging.info(f"Reclassified Gemini subject '{gemini_subject}' as chapter_title")
        metadata.pop("subject", None)

    # Enrich metadata from DB record context (don't overwrite Gemini extractions)
    if not metadata.get("subject") and input_data.get("subject"):
        metadata["subject"] = input_data["subject"]
    if not metadata.get("chapter_title") and input_data.get("chapter_title"):
        metadata["chapter_title"] = input_data["chapter_title"]
    
    result["metadata"] = metadata

    exercises = result.get("exercises", [])
    total_problems = sum(len(ex.get("problem_numbers", [])) for ex in exercises)
    logging.info(f"Parsed {total_problems} problem(s) across {len(exercises)} exercise(s)")

    # ── Subject mismatch detection ──
    # If the chapter title extracted by Gemini clearly belongs to a different subject,
    # add a warning. This is informational only — evaluation still proceeds.
    subject_mismatch_warning = None
    _SUBJECT_CHAPTER_HINTS = {
        "physics": {"motion", "force", "energy", "waves", "optics", "thermodynamics",
                     "gravitation", "oscillations", "magnetism", "electrostatics",
                     "current electricity", "electromagnetic", "nuclear", "semiconductor",
                     "mechanical properties", "thermal properties", "kinetic theory",
                     "laws of motion", "work energy power", "ray optics", "wave optics"},
        "chemistry": {"organic", "inorganic", "chemical bonding", "equilibrium",
                       "solutions", "electrochemistry", "coordination", "hydrocarbons",
                       "polymers", "biomolecules", "aldehydes", "ketones", "alcohols",
                       "haloalkanes", "amines", "redox", "p-block", "d-block", "s-block",
                       "solid state", "surface chemistry", "chemical kinetics",
                       "general principles", "hydrogen", "classification of elements"},
        "maths": {"algebra", "calculus", "trigonometry", "geometry", "vectors",
                  "matrices", "determinants", "probability", "statistics", "integration",
                  "differentiation", "conic", "permutation", "combination", "binomial",
                  "sequence", "series", "complex numbers", "linear programming",
                  "three dimensional", "3d geometry", "continuity", "differentiability",
                  "relations and functions", "inverse trigonometric"},
    }
    
    extracted_title = (metadata.get("chapter_title") or "").lower()
    user_subject = (input_data.get("subject") or "").lower()
    if extracted_title and user_subject:
        # Check if the extracted title matches a DIFFERENT subject's keywords
        for subj, keywords in _SUBJECT_CHAPTER_HINTS.items():
            if subj == user_subject:
                continue
            for kw in keywords:
                if kw in extracted_title:
                    subject_mismatch_warning = (
                        f"You selected '{input_data.get('subject')}', but the problems "
                        f"appear to be from '{subj.title()}' (detected topic: '{metadata.get('chapter_title')}'). "
                        f"Results may be less accurate if the subject is incorrect."
                    )
                    logging.warning(f"Subject mismatch: user={user_subject}, detected={subj}, title='{extracted_title}'")
                    break
            if subject_mismatch_warning:
                break

    meta = {
        "model": gemini_response["model"],
        "prompt_version": "Text_ParsingPrompt.md",
        "usage_metadata": gemini_response.get("usage_metadata"),
        "total_problems": total_problems,
        "exercises_count": len(exercises),
    }
    if subject_mismatch_warning:
        meta["subject_mismatch_warning"] = subject_mismatch_warning

    return {
        "parsed": result,
        "_meta": meta,
    }
