# JEE Ascent Pipeline: DB CLI

This directory contains the Python script `jee_solution_pipeline.py` which pulls un-solved tier-3 questions from the `jee_question_bank` in PostgreSQL, uses Gemini 3.1 Pro to generate solutions based on the "Assembly Line Pattern" (Socratic Tutors & solvers), and synchronizes the results back to the database as Ground Truth data.

## Environment Preparation

You need the `Karma` conda environment (or equivalent python setup) running, as well as valid environment variables.

1. Activate Python:
   ```powershell
   conda activate Karma
   ```
2. Make sure you have your secrets configured via `.env` (or using `settings_loader.py` setup) which contains:
   * **Azure PostgreSQL Credentials** (DB_HOST, DB_USER, DB_PASSWORD, etc.)
   * **Google Cloud Project config** for Vertex AI Gemini API endpoint (if applicable) or your Gemini API Key.

## Running the Script
You can scope the execution of the pipeline using the built-in `argparse` options. If you provide these arguments, only matching questions (missing solutions, but containing an `answer_key`) will be picked up.

### Usage:
```powershell
python pipelines\JEEAscentPipeline\jee_solution_pipeline.py [--year YEAR] [--shift SHIFT] [--subject SUBJECT] [--exam-date EXAM_DATE] [--limit LIMIT] [--batch-size BATCH_SIZE] [--use-critique]
```

### CLI Arguments:
* `--year`: Target a specific year (e.g., 2024).
* `--shift`: Target a specific shift (e.g., 'Morning').
* `--subject`: Target a specific subject (e.g., 'Physics').
* `--exam-date`: Target an exact exam date (e.g., '2024-01-27').
* `--limit`: Total number of questions to process per execution (default: 100).
* `--batch-size`: Number of questions pulled from DB per batch (default: 10).
* `--use-critique`: Enables the 2-pass critique loop via `GoldenGenerator` to ensure absolute maximum quality outputs (useful for small batches). Omitting this runs faster, single-pass LLM prompts.

### Examples:
* **Run a Test Batch** (Process exactly 2 Physics questions with critique logic enabled):
  ```powershell
  python pipelines\JEEAscentPipeline\jee_solution_pipeline.py --subject "Physics" --limit 2 --batch-size 2 --use-critique
  ```

* **Run by Year & Subject**:
  ```powershell
  python pipelines\JEEAscentPipeline\jee_solution_pipeline.py --year 2024 --subject Physics
  ```

* **Run specifically for a targeted exact Date**:
  ```powershell
  python pipelines\JEEAscentPipeline\jee_solution_pipeline.py --exam-date "2024-01-27" --subject Chemistry
  ```

## Viewing and Testing Results (`review_generations.py`)
Because the script writes strictly JSON output into a PostgreSQL `JSONB` column, verifying generation output via SQL clients is annoying. 

Use the viewport script to quickly print the latest generated solutions directly into your terminal:
```powershell
python pipelines\JEEAscentPipeline\review_generations.py
```
This utility fetches the top 3 latest questions where `is_generated=TRUE` and `review_status='UNVERIFIED'` and pretty-prints the structured solution JSON for manual verification.

### What happens during execution:
1. The `jee_solution_pipeline.py` connects to Azure Database and retrieves questions with `solution IS NULL`, `question_content IS NOT NULL`, `is_generated = FALSE`, and **`answer_key IS NOT NULL`** (to anchor the generation to factual truth).
2. It hits the Gemini API using the updated pedagogical prompt design (`jee_solver_prompt.md`).
3. For each successfully parsed `JSON` result, it commits directly to the DB setting `is_generated = TRUE` and `review_status = 'UNVERIFIED'`.