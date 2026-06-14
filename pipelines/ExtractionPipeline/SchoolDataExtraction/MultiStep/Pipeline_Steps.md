# Multi-Step Extraction Pipeline

This document explains the end-to-end multi-step extraction pipeline located in `pipelines\ExtractionPipeline\SchoolDataExtraction\MultiStep\`. The orchestrator for this pipeline is `e2e_pipeline.py`.

The pipeline extracts exercises and questions from NCERT PDF chapters, generates solutions using LLMs, and stores both the structured data and images into a PostgreSQL database and Azure Blob Storage.

## Pipeline Steps

### Stage 1: Question Extraction
The pipeline reads the chapter PDF and extracts questions across all exercises using a two-pass approach (`ExtractionEngine`):
- **Pass 1 (Text + Figure Flags)**: Uploads the PDF to the Gemini model to extract text, LaTeX formulas, and table structures. It also identifies where figure references occur and detects the `ExerciseSection` blocks.
- **Pass 2 (Figure Detection)**: For questions flagged in Pass 1 as having visual elements, it renders the corresponding pages as images and detects the bounding boxes of diagrams, graphs, and chemical structures.

**Output**: The extracted data is grouped by exercise and saved locally to: `Output/{pdf_name}_extraction.json`.

### Ingestion: Database and Blob Storage
After extraction, the pipeline uploads artifacts and inserts records into the database (`DatabaseClient`):
1. **Chapter Lookup**: Fetches the `ChapterId` based on class level, subject, and chapter number.
2. **Image Uploads**: Any images/figures cropped during Stage 1 are uploaded to Azure Blob Storage to generate public URLs.
3. **`exercisedata` Table Insertion**:
   - The pipeline iterates through all detected `ExerciseSection` objects.
   - It upserts each exercise into the **`exercisedata`** table to get the resulting `ExerciseId`.
4. **`questiondata` Table Insertion**:
   - Within each exercise, the pipeline iterates through all its questions.
   - It upserts each question into the **`questiondata`** table with the `ExerciseId` as a foreign key. 
   - The question text, figure references, and Azure Blob image URLs are saved into the `content` JSONB column.

### Stage 2: Solution Generation
Once questions are safely in the database, the pipeline begins solving them (`SolverEngine`):
- It chunks questions into batches and calls the Gemini model as a tutor to generate step-by-step solutions.
- The pipeline heavily relies on checkpointing to save state incrementally and allow resumption.
- **Output**: Solved questions are saved locally to: `Output/{pdf_name}_solutions.json`.

### Stage 2 Update: Updating the Database
After solutions are successfully generated:
- The pipeline updates the **`questiondata`** table for each question.
- It writes the generated solution steps and final answers directly into the `solution` JSONB column.

---

## Models Used

The pipeline leverages different Google Gemini models via Vertex AI for each specific task to balance capability, speed, and cost, as configured in `config.py`:

- **Stage 1.5 (Exercise Detection): `gemini-3-flash-preview`**
  - Used in Pass 1 to quickly read the PDF, detect the structural layout, and find the boundaries of the various `ExerciseSection` blocks. It's a faster model suited for layout and structure detection.

- **Stage 1 (Question Extraction): `gemini-3.1-pro-preview`**
  - Used for the heavy lifting of parsing complex NCERT question texts. It extracts mathematical notation, LaTeX formulas, chemical equations, and markdown tables. It runs with a low temperature (0.2) to ensure strict, consistent JSON extraction without hallucination. Note that `gemini-3-pro-image-preview` is also used under the hood by the shared `FigureExtraction` module (Pass 2) for precise bounding box detection around diagrams.

- **Stage 2 (Solution Generation): `gemini-3-pro-image-preview`**
  - Used as the core tutor/solver. This model handles reasoning and step-by-step logic. It takes the text questions and generates detailed explanations, step-by-step calculations, and can even output interleaved text/image responses if visual elements (SVGs, generated images) are required to explain the answer. 

*(A `gemini-2.0-flash` model is also configured as a Verification Engine for future validation logic.)*

---

## Multiple Exercises Support

**Yes, the pipeline fully supports multiple exercises per chapter.**
- During Pass 1, the LLM is prompted to group questions under their respective exercise titles (e.g., "EXERCISE 9.1", "ADDITIONAL EXERCISES").
- The extraction engine parses this into a list of `ExerciseSection` objects (`extraction_engine.py`).
- During the Ingestion phase (`e2e_pipeline.py::_run_ingestion`), it loops over `extraction_result.exercise_sections`, issuing an insert/upsert to the `exercisedata` table for *each* exercise section before iterating over the questions inside it.

---

## Sample Runs
You can view logs and serialized output of the pipeline in the `Output` subfolder. Example sample files include:
- `Output/kech101_extraction.json`: Contains the result of Stage 1 extraction before DB insertion.
- `Output/kech101_solutions.json`: Contains the generated solutions mapping to the extracted questions.
- `Output/kech101_pipeline_state.json`: The checkpoint file used by the application to pause and resume the process.
