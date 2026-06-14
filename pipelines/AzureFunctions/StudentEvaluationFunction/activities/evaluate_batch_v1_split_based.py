"""
Activity: Batch evaluate student solutions against problems using Gemini.
Handles both text-ref (Path A) and image-ref (Path B) evaluation.
"""
import logging
import base64
from utils.gemini_client import call_gemini, MODEL_EVALUATION
from utils.prompt_loader import load_prompt, fill_template


def evaluate_batch_activity(input_data: dict) -> list:
    """
    Evaluate a batch of (student solution, problem) tuples using Gemini.
    Max 3 tuples per batch (one Gemini call per batch).
    
    Args:
        input_data: {
            "tuples": [
                {
                    "problem_id": str,
                    "student_image_b64": str,
                    "problem_number": str (Path A) | "problem_image_b64": str (Path B),
                    "exercise_label": str (optional, Path A)
                }
            ],
            "class": str,
            "subject": str,
            "chapter_title": str,
            "pdf_bytes_b64": str (optional — chapter PDF),
            "path": "text_ref" | "image_ref"
        }
    
    Returns:
        List of evaluation results: [{
            "problem_id": str,
            "evaluation": dict (Gemini output parsed as JSON)
        }]
    """
    tuples = input_data["tuples"]
    class_val = input_data["class"]
    subject = input_data["subject"]
    chapter_title = input_data.get("chapter_title", "")
    pdf_b64 = input_data.get("pdf_bytes_b64")
    path = input_data.get("path", "text_ref")

    logging.info(
        f"Activity evaluate_batch: {len(tuples)} problem(s), "
        f"path={path}, class={class_val}, subject={subject}"
    )

    results = []

    for t in tuples:
        problem_id = t["problem_id"]
        student_b64 = t["student_image_b64"]
        student_bytes = base64.b64decode(student_b64)

        try:
            if path == "text_ref":
                # Path A: problem is a text reference (number) — use evaluation prompt with PDF
                gemini_response = _evaluate_text_ref(
                    student_bytes=student_bytes,
                    problem_number=t.get("problem_number", problem_id),
                    exercise_label=t.get("exercise_label"),
                    class_val=class_val,
                    subject=subject,
                    chapter_title=chapter_title,
                    pdf_b64=pdf_b64,
                )
            else:
                # Path B: problem is an image — use evaluation prompt with problem image
                problem_bytes = base64.b64decode(t["problem_image_b64"]) if t.get("problem_image_b64") else None
                gemini_response = _evaluate_image_ref(
                    student_bytes=student_bytes,
                    problem_bytes=problem_bytes,
                    class_val=class_val,
                    subject=subject,
                    chapter_title=chapter_title,
                    pdf_b64=pdf_b64,
                )

            evaluation = gemini_response["parsed_result"]
            results.append({
                "problem_id": problem_id,
                "evaluation": evaluation,
                "_meta": {
                    "model": gemini_response["model"],
                    "usage_metadata": gemini_response.get("usage_metadata"),
                },
            })
            logging.info(f"  Problem {problem_id}: {evaluation.get('evaluation_status', 'N/A')}")

        except Exception as e:
            logging.error(f"  Problem {problem_id}: evaluation failed — {e}")
            results.append({
                "problem_id": problem_id,
                "evaluation": {
                    "evaluation_status": "Error",
                    "error": str(e),
                },
            })

    return {
        "evaluations": results,
        "_meta": {
            "model": MODEL_EVALUATION,
            "prompt_version": "Evaluation.txt",
            "problems_in_batch": len(tuples),
        },
    }


def _evaluate_text_ref(
    student_bytes: bytes,
    problem_number: str,
    exercise_label: str | None,
    class_val: str,
    subject: str,
    chapter_title: str,
    pdf_b64: str | None,
) -> dict:
    """Evaluate using text reference: problem number + PDF as reference."""
    
    # Build problem description
    problem_desc = f"Problem {problem_number}"
    if exercise_label:
        problem_desc = f"Exercise {exercise_label}, Problem {problem_number}"
    if chapter_title:
        problem_desc += f" from chapter '{chapter_title}'"

    # Load and fill the evaluation prompt
    prompt_template = load_prompt("Evaluation.txt")
    filled_prompt = fill_template(
        prompt_template,
        **{
            "class": class_val,
            "Subject": subject,
            "Problem": problem_desc,
            "RefAnswer": "Not provided — please refer to the chapter PDF for the problem and derive the correct answer.",
        }
    )

    # Build content parts
    content_parts = [filled_prompt]

    # Student answer image
    content_parts.append("\n[STUDENT'S ANSWER IMAGE]")
    content_parts.append({"mime_type": "image/jpeg", "data": student_bytes})

    # Reference PDF
    if pdf_b64:
        pdf_bytes = base64.b64decode(pdf_b64)
        content_parts.append("\n[REFERENCE MATERIAL PDF]")
        content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})

    return call_gemini(
        model_id=MODEL_EVALUATION,
        content_parts=content_parts,
        response_json=True,
    )


def _evaluate_image_ref(
    student_bytes: bytes,
    problem_bytes: bytes | None,
    class_val: str,
    subject: str,
    chapter_title: str,
    pdf_b64: str | None,
) -> dict:
    """Evaluate using image reference: problem image + student solution."""
    
    problem_desc = "[Problem provided as image — see attached image]"
    if chapter_title:
        problem_desc += f" from chapter '{chapter_title}'"

    # Load and fill the evaluation prompt
    prompt_template = load_prompt("Evaluation.txt")
    filled_prompt = fill_template(
        prompt_template,
        **{
            "class": class_val,
            "Subject": subject,
            "Problem": problem_desc,
            "RefAnswer": "Not provided — please derive from the problem image and reference PDF if available.",
        }
    )

    # Build content parts (matching prototype ordering: prompt → problem image → student → PDF)
    content_parts = [filled_prompt]

    # Problem image
    if problem_bytes:
        content_parts.append("\n[PROBLEM IMAGE]")
        content_parts.append({"mime_type": "image/jpeg", "data": problem_bytes})

    # Student answer image
    content_parts.append("\n[STUDENT'S ANSWER IMAGE]")
    content_parts.append({"mime_type": "image/jpeg", "data": student_bytes})

    # Reference PDF
    if pdf_b64:
        pdf_bytes = base64.b64decode(pdf_b64)
        content_parts.append("\n[REFERENCE MATERIAL PDF]")
        content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})

    return call_gemini(
        model_id=MODEL_EVALUATION,
        content_parts=content_parts,
        response_json=True,
    )
