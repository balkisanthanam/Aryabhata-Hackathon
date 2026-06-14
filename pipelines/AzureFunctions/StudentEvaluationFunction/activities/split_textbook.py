"""
Activity: Split a textbook problem image into individual problem crops.
Uses Gemini MODEL_BOUNDING_BOX + SplitTextBookProblems prompt.
(Path B — student uploaded a photo of the textbook page)
"""
import logging
from utils.gemini_client import call_gemini, MODEL_BOUNDING_BOX
from utils.blob_storage import fetch_image_from_url
from utils.image_processing import group_and_stitch, image_bytes_to_base64
from utils.prompt_loader import load_prompt


def split_textbook_activity(input_data: dict) -> list:
    """
    Split textbook page image(s) into individual problem bounding boxes and crop.
    
    Args:
        input_data: {
            "problem_image_url": str | list[str] — URL(s) to textbook page image(s)
        }
    
    Returns:
        Dict: {
            "problems": [{ "problem_id": str, "image_b64": str, "confidence": float }],
            "_meta": { ... }
        }
    """
    raw_url = input_data["problem_image_url"]
    # Accept single URL (str) or list of URLs for multi-page
    urls = raw_url if isinstance(raw_url, list) else [raw_url]
    logging.info(f"Activity split_textbook: {len(urls)} page(s)")

    # Fetch all page images
    image_bytes_list = [fetch_image_from_url(u) for u in urls]
    logging.info(f"Fetched {len(image_bytes_list)} image(s)")

    # Load the textbook splitting prompt (TBD #1)
    prompt = load_prompt("SplitTextBookProblems.txt")

    # Build content parts: all images first, then prompt
    content_parts = []
    for img_bytes in image_bytes_list:
        content_parts.append({
            "mime_type": "image/jpeg",
            "data": img_bytes,
        })
    content_parts.append(prompt)

    # Call Gemini for bounding box detection on textbook
    logging.info("Calling Gemini for textbook problem splitting...")
    gemini_response = call_gemini(
        model_id=MODEL_BOUNDING_BOX,
        content_parts=content_parts,
        response_json=True,
        temperature=0.1,
    )

    result = gemini_response["parsed_result"]
    solutions = result.get("solutions", [])
    logging.info(f"Detected {len(solutions)} textbook problem regions")

    if not solutions:
        logging.warning("No problems detected in textbook image")
        return []

    # Crop using PIL
    cropped = group_and_stitch(solutions, image_bytes_list)
    logging.info(f"Cropped {len(cropped)} textbook problems")

    # Convert to base64 for serialization
    output = []
    for item in cropped:
        output.append({
            "problem_id": item["problem_id"],
            "image_b64": image_bytes_to_base64(item["image_bytes"]),
            "confidence": item["confidence"],
        })

    return {
        "problems": output,
        "_meta": {
            "model": gemini_response["model"],
            "prompt_version": "SplitTextBookProblems.txt",
            "usage_metadata": gemini_response.get("usage_metadata"),
            "problems_detected": len(output),
        },
    }
