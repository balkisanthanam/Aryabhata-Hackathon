"""
Image processing utilities — ported from validate_split.py.
Handles bounding box cropping (0–1000 scale) and multi-part vertical stitching.
"""
import logging
import io
import base64
from PIL import Image
from typing import Optional


def crop_from_bounding_box(image_bytes: bytes, box_2d: list) -> Optional[bytes]:
    """
    Crop a region from an image using normalized 0–1000 coordinates.
    
    Args:
        image_bytes: Raw image bytes
        box_2d: [ymin, xmin, ymax, xmax] on 0–1000 scale
    
    Returns:
        Cropped image as JPEG bytes, or None if invalid
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        ymin, xmin, ymax, xmax = box_2d

        left = (xmin / 1000) * width
        top = (ymin / 1000) * height
        right = (xmax / 1000) * width
        bottom = (ymax / 1000) * height

        # Validate crop dimensions
        if right <= left or bottom <= top:
            logging.warning(f"Invalid crop dimensions: box_2d={box_2d}, size={width}x{height}")
            return None

        crop = img.crop((left, top, right, bottom))

        # Convert to JPEG bytes
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logging.error(f"Error cropping image: {e}")
        return None


def group_and_stitch(solutions: list, image_bytes_list: list) -> list:
    """
    Group solutions by base problem_id, crop from source images,
    and vertically stitch multi-part solutions.
    
    Ported from validate_split.py stitch_and_crop().
    
    Args:
        solutions: List of solution dicts from Gemini with:
            - problem_id: str (e.g. "Q13" or "Q13_part1")
            - image_index: int
            - box_2d: [ymin, xmin, ymax, xmax]
        image_bytes_list: List of source image bytes (one per page)
    
    Returns:
        List of dicts with:
            - problem_id: str (base problem ID)
            - image_bytes: bytes (cropped/stitched JPEG)
            - confidence: float (avg confidence)
    """
    if not solutions:
        return []

    # Open source images
    source_images = []
    for img_data in image_bytes_list:
        source_images.append(Image.open(io.BytesIO(img_data)))

    # Group solutions by base problem_id
    solutions_map = {}
    for sol in solutions:
        problem_id_raw = sol.get("problem_id", "unknown")

        # Strip _part suffix to group multi-part solutions
        if "_part" in problem_id_raw:
            base_id = problem_id_raw.split("_part")[0]
            try:
                part_num = int(problem_id_raw.split("_part")[1])
            except ValueError:
                part_num = 0
        else:
            base_id = problem_id_raw
            part_num = 0

        if base_id not in solutions_map:
            solutions_map[base_id] = []

        solutions_map[base_id].append({"part_num": part_num, "data": sol})

    # Process each problem: crop + stitch
    results = []
    for base_id, parts in solutions_map.items():
        parts.sort(key=lambda x: x["part_num"])

        crops = []
        confidences = []

        for p in parts:
            sol = p["data"]
            img_idx = sol.get("image_index", 0)

            if img_idx >= len(source_images):
                logging.warning(f"Image index {img_idx} out of range for {base_id}")
                continue

            img = source_images[img_idx]
            width, height = img.size

            ymin, xmin, ymax, xmax = sol["box_2d"]

            left = (xmin / 1000) * width
            top = (ymin / 1000) * height
            right = (xmax / 1000) * width
            bottom = (ymax / 1000) * height

            if right <= left or bottom <= top:
                logging.warning(f"Invalid dimensions for {base_id} part")
                continue

            crop = img.crop((left, top, right, bottom))
            crops.append(crop)
            confidences.append(sol.get("confidence_score", 0.5))

        if not crops:
            continue

        # Stitch: single crop or vertical stitch
        if len(crops) == 1:
            final_img = crops[0]
        else:
            total_height = sum(c.height for c in crops)
            max_width = max(c.width for c in crops)
            final_img = Image.new("RGB", (max_width, total_height), (255, 255, 255))
            y_offset = 0
            for c in crops:
                final_img.paste(c, (0, y_offset))
                y_offset += c.height

        # Convert to JPEG bytes
        buf = io.BytesIO()
        final_img.save(buf, format="JPEG", quality=95)
        buf.seek(0)

        results.append({
            "problem_id": base_id,
            "image_bytes": buf.read(),
            "confidence": sum(confidences) / len(confidences) if confidences else 0.5,
        })

    # Clean up
    for img in source_images:
        img.close()

    return results


def image_bytes_to_base64(image_bytes: bytes) -> str:
    """Convert image bytes to base64 string."""
    return base64.b64encode(image_bytes).decode("utf-8")


def decode_base64_image(base64_string: str) -> bytes:
    """
    Decode base64 encoded image string to bytes.
    Handles data URL prefix (e.g. data:image/jpeg;base64,...).
    """
    try:
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        return base64.b64decode(base64_string)
    except Exception as e:
        logging.error(f"Error decoding base64 image: {e}")
        raise
