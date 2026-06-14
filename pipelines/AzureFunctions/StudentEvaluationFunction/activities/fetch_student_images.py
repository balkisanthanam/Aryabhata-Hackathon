"""
Activity: Fetch student work images from blob storage.

Simple download activity — no Gemini call, no image processing.
Returns raw image bytes (base64-encoded) for all student pages.
"""
import logging
import base64
from utils.blob_storage import fetch_image_from_url


def fetch_student_images_activity(input_data: dict) -> dict:
    """
    Fetch student work image(s) from URL(s) and return as base64.

    Args:
        input_data: {
            "student_work_url": str | list[str]  — URL(s) to student's uploaded work
        }

    Returns:
        {
            "pages": [
                {"page_index": 0, "image_b64": "..."},
                {"page_index": 1, "image_b64": "..."},
            ],
            "page_count": int,
        }
    """
    raw_url = input_data["student_work_url"]
    # Handle list (from code), comma-separated string (from DB TEXT column), or single URL
    if isinstance(raw_url, list):
        urls = raw_url
    elif "," in raw_url:
        urls = [u.strip() for u in raw_url.split(",") if u.strip()]
    else:
        urls = [raw_url]
    logging.info(f"Activity fetch_student_images: {len(urls)} page(s)")

    pages = []
    for idx, url in enumerate(urls):
        image_bytes = fetch_image_from_url(url)
        pages.append({
            "page_index": idx,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        })
        logging.info(f"  Page {idx}: {len(image_bytes)} bytes fetched")

    return {
        "pages": pages,
        "page_count": len(pages),
    }
