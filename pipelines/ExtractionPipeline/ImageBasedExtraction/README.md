# Image-Based Question Extraction Pipeline

Extract entire questions as high-resolution images from PDF exercise pages, preserving all formatting, figures, and formulas intact.

## Overview

This pipeline extracts questions as complete images rather than mixed text/image, making them directly usable with any LLM without formatting loss.

## Pipeline Steps

### 1. Page Detection
Find pages containing exercises using:
- **Gemini 2.0 Flash** (Recommended): Single API call analyzes entire PDF, returns all exercise page ranges
- **Pattern matching** (Fast, free): Local keyword search for "Exercise", "Questions", etc.

### 2. Page to Image Conversion
Convert identified exercise pages to high-resolution images:
- **Recommended**: `pdf2image` library (uses Poppler for high-quality rendering)
- Alternative: PyMuPDF's `get_pixmap()` with high DPI

### 3. Bounding Box Detection
Use Gemini 2.5 Pro to identify question boundaries:
- Input: High-res page images
- Output: JSON with bounding boxes `[ymin, xmin, ymax, xmax]` for each question
- Includes question number, text, and all associated figures/diagrams

### 4. Image Cropping
Physically crop individual questions using detected coordinates:
- **Tool**: Pillow (PIL)
- Input: Page images + bounding box coordinates
- Output: Individual question images

## Files

- `step1_find_exercise_pages.py` - Detect pages with exercises
- `step2_convert_pages_to_images.py` - High-res PDF page conversion
- `step3_detect_question_boxes.py` - Get bounding boxes from Gemini
- `step4_crop_questions.py` - Extract individual question images
- `main_extraction_pipeline.py` - Orchestrates all steps
- `config.json` - Pipeline configuration
- `requirements.txt` - Additional dependencies

## Dependencies

```bash
pip install pdf2image Pillow google-generativeai PyMuPDF
```

Note: `pdf2image` requires Poppler. On Windows, download from https://github.com/oschwartz10612/poppler-windows/releases/

## Usage

```bash
python main_extraction_pipeline.py --input input/sample.pdf --output output/questions/
```

## Output Structure

```
output/
  └── book_name/
      ├── metadata.json          # Extraction metadata
      ├── page_images/           # Full page images
      │   ├── page_12.png
      │   └── page_13.png
      └── questions/             # Individual question images
          ├── q_12_1.png        # Page 12, Question 1
          ├── q_12_2.png
          └── q_13_1.png
```

## Advantages

- ✅ Preserves all formatting (formulas, figures, tables)
- ✅ No text extraction errors
- ✅ Works with any LLM that accepts images
- ✅ Maintains visual context
- ✅ Handles complex layouts (multi-column, wrapped figures)
