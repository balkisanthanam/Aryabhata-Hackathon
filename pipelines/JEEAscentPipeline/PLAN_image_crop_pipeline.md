# M1b Phase 2 — Per-Question Image Crop Pipeline

## Problem

The current Gemini Pro approach (6 calls × full 100-page PDF) is:
- **~90 min per paper** (60s inter-call delay × rate limiting)
- **~$30 for 40 papers** (Pro model + cache hits still expensive)
- Unreliable: Math Integer questions consistently fail (truncation)

Root cause: JEE paper PDFs have a **split structure**:
- Text layer = metadata only (NTA IDs, question numbers, section headers) — extractable by PyMuPDF
- Question content (formulas, options, figures) = embedded DeviceRGB image objects — NOT extractable as text

Sending the full PDF to Gemini Pro for text already in the text layer is wasteful.

---

## New Architecture: Text Layer + Per-Question Image Crops

### Core Idea

1. **PyMuPDF extracts the text layer** — NTA Question IDs, Option IDs, question numbers, section/subject headers
2. **PyMuPDF renders page-region crops** — one PNG per question (page region from marker N to marker N+1)
3. **Gemini Flash reads each crop** — transcribes LaTeX, formula text, option text
4. **Merge** — text layer metadata + Flash LaTeX → full question record
5. **Azure Blob** — crop PNGs uploaded; URL stored in `figure_blob_url` field

Expected: **~3 min per paper** vs 90 min (30× speedup), **~$0.75 per paper** vs $0.75 (Flash is 10–20× cheaper than Pro).

---

## How Page-Region Cropping Works

JEE papers have consistent text-layer markers:
```
Q.1  87827056058          ← NTA Question ID at same y-position as question number
Q.2  87827056059
```

Approach:
1. Walk all text blocks on each page, sorted by (page_num, y0)
2. Find question markers: patterns like `Q.1`, `Q. 1`, `1.`, etc. + associated NTA ID
3. Each marker defines a **crop start** at that y-position
4. Next marker (same page) or top of next page = **crop end**
5. Render the page strip between y_start and y_end as PNG at ~200 DPI

This correctly handles:
- Multiple questions per page
- Questions spanning 2 pages (split into two crops, labelled part A and part B)
- Questions with multiple embedded images (all captured in the region crop)

---

## Step-by-Step Plan

### Step 1 — Prototype & Validate (this step)
**Goal:** Prove the approach on paper_1 (2024) before building the full pipeline.

Tasks:
- [ ] Write `jee_text_layer_parser.py` — extract NTA IDs + question boundaries from text layer
- [ ] Write `jee_crop_renderer.py` — render page-region crops as PNGs using PyMuPDF
- [ ] Upload 5 sample crops to Azure Blob and send to Gemini Flash
- [ ] Compare Flash output against the 80 questions already in DB for paper_1 (benchmark)
- [ ] Validate: does Flash correctly transcribe formulas/LaTeX from crops?

### Step 2 — Build Full Pipeline
**Goal:** Replace the Gemini Pro pipeline with the new crop-based approach.

New files:
- `jee_crop_pipeline.py` — orchestrator (replaces `jee_paper_extractor.py` for the new flow)
- `jee_text_layer_parser.py` — text layer → question boundaries + NTA IDs
- `jee_crop_renderer.py` — page-region crop renderer + Azure Blob uploader

Updated files:
- `jee_extraction_pipeline.py` — add `--crop-mode` flag to switch between Pro and Flash/crop
- `db_writer.py` — add `update_figure_blob_url()` for storing crop URLs

### Step 3 — Full Run
**Goal:** Extract all ~40 papers (2021–2025) using the new pipeline.

- Run crop pipeline on all PENDING papers
- Validate: ≥70 questions per paper, ≥80% answer key coverage
- Keep Gemini Pro pipeline as fallback for any papers where text layer is too sparse

---

## Data Flow (per question)

```
PDF (paper_1.pdf)
  │
  ├─ PyMuPDF text layer ──► NTA Question ID, Option IDs, question number, section/subject
  │
  └─ PyMuPDF page render ──► PNG crop (question region, ~200 DPI)
                                  │
                                  ├─ Azure Blob upload ──► blob_url (stored in figure_blob_url)
                                  │
                                  └─ Gemini Flash ──► raw_text (LaTeX), option texts
                                                           │
                                                           └─ Merge with text-layer metadata
                                                                    │
                                                                    └─ jee_question_bank row
```

---

## DB Impact

No schema changes needed. Existing fields map cleanly:

| Field | Source |
|-------|--------|
| `nta_question_id` | PyMuPDF text layer |
| `subject` | PyMuPDF section header text |
| `section` | PyMuPDF section header ("Section A" / "Section B") |
| `question_content.raw_text` | Gemini Flash transcription of crop |
| `question_content.options[].nta_option_id` | PyMuPDF text layer |
| `question_content.options[].text` | Gemini Flash transcription of crop |
| `question_content.has_figure` | Flash detects diagrams in crop |
| `question_content.figure_blob_url` | Azure Blob URL of the crop PNG |
| `answer_key` | `jee_answer_mappings` (existing, unchanged) |

---

## Fallback Strategy

Keep Gemini Pro pipeline (`jee_paper_extractor.py`) intact.

- Pre-2021 papers (if any) where text layer has no NTA IDs → fall back to Pro
- Any paper where crop pipeline extracts < 70 questions → flag for Pro re-run
- CLI: `--crop-mode` (new, default) vs `--pro-mode` (existing behavior)

---

## Current Status

- [x] PDF structure confirmed: all 2020–2025 papers text-selectable, question content as image objects
- [x] 660 embedded images confirmed in paper_1 (sample crops extracted in `analyze_pdf_images.py`)
- [x] Architecture designed and questions answered (full question text, NTA IDs from text layer, crops in Blob)
- [ ] **Next: write prototype (`jee_text_layer_parser.py`) and test on paper_1**
