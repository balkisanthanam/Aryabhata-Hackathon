
# Project Context: Offline Education Solver Pipeline

## Overview
This project is an offline data processing pipeline designed to extract exercise questions from textbook PDFs (CBSE Class 11), generate pedagogical step-by-step solutions, and verify them against answer keys. The output drives a mobile app experience that "nudges" students through problems one step at a time.
Here is a high level overview
1) Extract the Questions along with images and page nos - Questions with Gemini 3 and images with PyMuPDF - Question.json
2) For a batch of Questions, ask Gemini 3 to create step by step solution. Loop through batches and generate solutions - Solution.json
3) Extract Answers - answer.json
I will store the above in Azure Storage, with metadata i Azure PostgreSQL.
This will help me with creating experiences (like showing students step by step for a question on any exercise etc.)

## Architecture: The "Tri-Stage" Pipeline

### Stage 1: The Extraction Engine (Updated)

**Goal:** Convert raw PDF pages into structured, machine-readable data (`Question.json`).

* **Model:** `gemini-2.5-pro` (Strong vision capability and JSON formatting).
* **Input Strategy:** **Sliding Window of Page Images (Current Page + Next Page)**.
    * *Reason:* Sending two consecutive page images in the same prompt provides the necessary context for the model to **"look ahead"** and capture diagrams or text that spill over to the subsequent page, while the single-page image ensures **strict, simple 1000x1000 coordinate precision** for the crop.

***

* **Data Handling Strategy:**

    1.  **Text:** Extracted verbatim.
    2.  **Formulas:** Converted to **Standard LaTeX** strings (including math and physics).
    3.  **Chemical Equations:** Converted to **LaTeX** using `mhchem` syntax (e.g., `\ce{H2 + O2 -> H2O}`).
    4.  **Data Tables:** **Must be transcribed** into the question text using standard **Markdown table format**; do *not* capture them as an image crop.

    5.  **Visuals (Classification & Cropping Router):**
        * *Chemical Structures:* Extract **SMILES** strings (e.g., `c1ccccc1`) for SVG rendering.
        * *Complex Diagrams (Graphs, Free-body diagrams):* Extract **Bounding Boxes** `[y_min, x_min, y_max, x_max]` (on a 0-1000 scale).
            * **Crucial Update for Spill-Over:** The bounding box must be accompanied by a `source_page` flag:
                * `"source": "current_page"` (if the diagram is on the first image).
                * `"source": "next_page"` (if the question starts on the first image but refers to a diagram on the second image).

* **Output:** `Question.json` containing question metadata, LaTeX text, and visual metadata with page source flags.
### Stage 2: The Solver Engine
**Goal:** Generate high-quality, step-by-step tutorial solutions (`Solution.json`).
* **Model:** `gemini-3-pro-image-preview` (Required for interleaved text/image generation).
* **Input Strategy:** **Full PDF Chapter** (via Context Caching).
    * *Reason:* Passing the full PDF allows the model to "flip back" to reference tables, constants, and solved examples, ensuring the solution style matches the curriculum.
* **Processing Pattern:**
    * **Context Caching:** Upload the PDF once with a TTL (e.g., 60 mins) to reduce latency and cost.
    * **Interleaved Generation:** The model generates text steps *and* explanatory diagrams (if needed) in a single API stream.
* **Output Schema:** A strict JSON structure supporting the "Nudge" UI:
    * `step_type`: (Conceptual / Calculation / Visual)
    * `nudge_hint`: A clue to show before the full step.
    * `explanation`: The full step content.
    * `visual_asset`: References an inline generated image or SMILES string.

### Stage 3: The Answer Verifications Engine
**Goal:** Automated Quality Assurance (`Answer.json`).
* **Model:** `gemini-3-pro-preview`.
* **Input:** PDF of the Answer page.
* **Process:**
    1.  Locate.
    2.  Compare the official short answer vs. the Model's generated final result.
    3.  Flag for manual review if they disagree (fuzzy matching allowed for units/rounding).

## Data Standards & Formats

| Content Type | Format / Storage | Rendering Engine (App Side) |
| :--- | :--- | :--- |
| **Math Formulas** | LaTeX String | KaTeX or MathJax |
| **Chemical Rxns** | LaTeX String (mhchem) | KaTeX (w/ mhchem extension) |
| **Chemical Structures** | SMILES String | SmilesDrawer (Client-side SVG) |
| **Physics Diagrams** | Raster Image (PNG/JPG) | Standard `<img>` tag |
| **Generated Graphs** | Raster Image (PNG) | Standard `<img>` tag |

## Technical Implementation Notes
* **Library:** Use `google-genai` (V2 SDK) for Gemini 3 compatibility.
* **PDF Processing:** Use `PyMuPDF` for cropping Stage 1 visuals based on bounding boxes.
* **Context Management:** Use `caching.CachedContent` for Stage 2 to handle large textbook chapters efficiently.
* **Safety:** Ensure `temperature` is low (e.g., `0.4`) in Stage 2 to prevent hallucination of mathematical constants.
