"""
Activity: Retrieve chapter PDF from ChapterData table or blob storage.
"""
import logging
from utils.db import lookup_chapter
from utils.blob_storage import fetch_blob_content


def get_chapter_pdf_activity(input_data: dict) -> dict:
    """
    Get the chapter PDF for use as reference material during evaluation.
    
    Args:
        input_data: {
            "class": str,
            "board": str,
            "subject": str,
            "chapter_id": int (optional),
            "chapter_number": str (optional),
            "chapter_title": str (optional)
        }
    
    Returns:
        {
            "pdf_url": str,
            "pdf_size": int (byte count — proves the PDF is accessible),
            "chapter_title": str
        }
        or {"pdf_url": None, "pdf_size": 0} if not found
    """
    logging.info(f"Activity get_chapter_pdf: chapter_id={input_data.get('chapter_id')}, "
                 f"title={input_data.get('chapter_title')}")

    # Look up chapter to get PDF URL
    chapter = lookup_chapter(
        class_val=input_data.get("class"),
        board=input_data.get("board"),
        subject=input_data.get("subject"),
        chapter_id=input_data.get("chapter_id"),
        chapter_number=input_data.get("chapter_number"),
        chapter_title=input_data.get("chapter_title"),
    )

    if not chapter or not chapter.get("PDFFileURL"):
        logging.warning("Chapter PDF not available")
        return {
            "pdf_url": None,
            "pdf_size": 0,
            "chapter_title": input_data.get("chapter_title", "Unknown"),
        }

    pdf_url = chapter["PDFFileURL"]
    # Azure blob container names are always lowercase; fix legacy URLs with "Feedback" → "feedback"
    pdf_url = pdf_url.replace("/Feedback/", "/feedback/")
    chapter_title = chapter["ChapterTitle"]
    logging.info(f"Fetching PDF from: {pdf_url}")

    try:
        pdf_bytes = fetch_blob_content(pdf_url, as_text=False)
        logging.info(f"PDF verified: {len(pdf_bytes)} bytes for '{chapter_title}'")
        return {
            "pdf_url": pdf_url,
            "pdf_size": len(pdf_bytes),
            "chapter_title": chapter_title,
        }
    except Exception as e:
        logging.error(f"Failed to verify chapter PDF: {e}")
        return {
            "pdf_url": pdf_url,
            "pdf_size": 0,
            "chapter_title": chapter_title,
        }
