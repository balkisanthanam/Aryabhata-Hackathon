"""
Activity: Split student handwriting into individual problem solutions.
Uses Gemini MODEL_BOUNDING_BOX + Student_HW_Split prompt + PIL cropping.
"""
import logging
from utils.gemini_client import call_gemini, MODEL_BOUNDING_BOX
from utils.blob_storage import fetch_image_from_url
from utils.image_processing import group_and_stitch, image_bytes_to_base64
from utils.prompt_loader import load_prompt


def split_student_hw_activity(input_data: dict) -> list:
    """
    Split student handwriting images into individual cropped solutions.
    
    Args:
        input_data: {
            "student_work_url": str | list[str]  — URL(s) to student's uploaded work
        }
    
    Returns:
        Dict: {
            "solutions": [{ "problem_id": str, "image_b64": str, "confidence": float }],
            "_meta": { ... }
        }
    """
    raw_url = input_data["student_work_url"]
    # Accept single URL (str) or list of URLs for multi-page
    urls = raw_url if isinstance(raw_url, list) else [raw_url]
    logging.info(f"Activity split_student_hw: {len(urls)} page(s)")

    # Fetch all page images
    image_bytes_list = [fetch_image_from_url(u) for u in urls]
    logging.info(f"Fetched {len(image_bytes_list)} image(s)")

    # Load the bounding box detection prompt
    prompt = load_prompt("Student_HW_Split.md")

    # Build content parts: images first, then prompt (matching validate_split.py pattern)
    content_parts = []
    for img_bytes in image_bytes_list:
        content_parts.append({
            "mime_type": "image/jpeg",
            "data": img_bytes,
        })
    content_parts.append(prompt)

    # Call Gemini for bounding box detection
    logging.info("Calling Gemini for student HW bounding box detection...")
    gemini_response = call_gemini(
        model_id=MODEL_BOUNDING_BOX,
        content_parts=content_parts,
        response_json=True,
        temperature=0.1,
    )

    result = gemini_response["parsed_result"]
    solutions = result.get("solutions", [])
    logging.info(f"Detected {len(solutions)} solution regions")

    if not solutions:
        logging.warning("No solutions detected in student work")
        return []

    # Crop and stitch using PIL
    cropped = group_and_stitch(solutions, image_bytes_list)
    logging.info(f"Cropped and stitched {len(cropped)} problems")

    # Convert to base64 for serialization across activity boundary
    output = []
    for item in cropped:
        output.append({
            "problem_id": item["problem_id"],
            "image_b64": image_bytes_to_base64(item["image_bytes"]),
            "confidence": item["confidence"],
        })

    return {
        "solutions": output,
        "_meta": {
            "model": gemini_response["model"],
            "prompt_version": "Student_HW_Split.md",
            "usage_metadata": gemini_response.get("usage_metadata"),
            "solutions_detected": len(output),
        },
    }
