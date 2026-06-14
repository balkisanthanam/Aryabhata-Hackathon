# E2E Pipeline CLI Reference

Command-line reference for `main.py` - the extraction and solution generation pipeline.

**Last Updated:** January 25, 2026

---

## Quick Examples

```bash
# Extract questions from a PDF (Stage 1)
python main.py --stage 1 --pdf "Input/keph203.pdf" --class 11 --subject Physics

# Generate solutions for specific questions (Stage 2)
python main.py --stage 2 --pdf "Input/keph203.pdf" --questions "10.1,10.5,10.10" --subject Physics

# Full E2E pipeline: extract, solve, and upload to DB (Stage 3)
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics

# Cleanup chapter data from database + local files
python main.py --cleanup --pdf "Input/keph203.pdf" --chapter-id 24 --dry-run
```

---

## Stage Selection

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--stage` | `1`, `2`, or `3` | Auto | Pipeline stage to run |

**Stage Descriptions:**
- **Stage 1 (Extraction):** Extract questions from PDF → saves to `Output/<pdf>_extraction.json`
- **Stage 2 (Solver):** Generate step-by-step solutions → saves to `Output/<pdf>_solutions.json`
- **Stage 3 (E2E Pipeline):** Full pipeline: Extract → Solve → Upload to Azure DB/Blob

**Auto-detection:** If `--stage` is not provided:
- If `--questions` is provided → Stage 2
- Otherwise → Stage 1

---

## Common Arguments

These arguments apply to all stages:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--pdf` | string | `Input/keph205.pdf` | Path to the chapter PDF file |
| `--subject` | string | `Physics` | Subject name |
| `--class` | string | `11th` | Class level (e.g., `11th`, `12`) |
| `--board` | string | `CBSE` | Education board |
| `--chapter` | string | None | Chapter name (optional metadata) |
| `--output` | string | `Output/` | Output directory path |
| `--prompt` | string | None | Path to custom prompt template |

---

## Stage 1: Extraction

Extract questions and exercises from a PDF chapter.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--pages` | string | None | Page range to extract (e.g., `20-25`). Omit for auto-detect. |
| `--two-pass` | flag | False | Use two-pass extraction (better for complex content like Chemistry) |

**Examples:**

```bash
# Auto-detect exercise pages
python main.py --stage 1 --pdf "Input/keph203.pdf" --subject Physics

# Extract specific pages only
python main.py --stage 1 --pdf "Input/keph203.pdf" --pages "180-195"

# Two-pass extraction for Chemistry (more reliable)
python main.py --stage 1 --pdf "Input/kech104.pdf" --subject Chemistry --two-pass
```

**Output:** `Output/<pdf_stem>_extraction.json`

---

## Stage 2: Solver

Generate step-by-step solutions for questions.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--questions` | string | None | Comma-separated question IDs (e.g., `12.4,12.7`) or `all` |
| `--from-extraction` | string | None | Path to extraction JSON to get questions from |
| `--batch-size` | int | `5` | Questions per batch. Set to `0` to disable batching. |
| `--no-cache` | flag | False | Disable Gemini content caching |
| `--use-smart-context` | flag | False | Use localized vector context & critique loop instead of Full PDF |

**Examples:**

```bash
# Solve specific questions
python main.py --stage 2 --pdf "Input/keph203.pdf" --questions "10.1,10.5,10.10"

# Solve all questions from an extraction file
python main.py --stage 2 --pdf "Input/keph203.pdf" --from-extraction "Output/keph203_extraction.json" --questions all

# Solve with smaller batches (for stability)
python main.py --stage 2 --pdf "Input/keph203.pdf" --questions "10.1,10.2,10.3" --batch-size 2

# Disable batching (one API call for all questions)
python main.py --stage 2 --pdf "Input/keph203.pdf" --questions "10.1,10.2" --batch-size 0

# Solve using Smart Context + Golden Generator instead of the entire PDF
python main.py --stage 2 --pdf "Input/keph203.pdf" --questions "10.1,10.2" --use-smart-context
```

**Output:** `Output/<pdf_stem>_solutions.json`

---

## Stage 3: E2E Pipeline

Full end-to-end pipeline: Extract → Solve → Upload to Azure.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--local-only` | flag | False | Skip DB/Blob operations (save to local JSON only) |
| `--force-rerun` | flag | False | Re-process even if data exists (uses UPSERT) |
| `--skip-solutions` | flag | False | Skip solution generation (extraction only) |
| `--no-managed-identity` | flag | False | Use connection strings instead of Azure Managed Identity |
| `--batch-size` | int | `5` | Questions per batch for solution generation |
| `--use-smart-context` | flag | False | Use localized vector context & critique loop instead of Full PDF |

**Examples:**

```bash
# Full pipeline with Azure upload
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics

# Local only (no Azure)
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics --local-only

# Re-run extraction and update DB (force rerun)
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics --force-rerun

# Extract only, skip solution generation
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics --skip-solutions

# Full pipeline using the highly optimized Smart Context
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics --use-smart-context
```

**Output:**
- `Output/<pdf_stem>_extraction.json`
- `Output/<pdf_stem>_solutions.json`
- `Output/<pdf_stem>_pipeline_state.json`
- Database tables: `ExerciseData`, `QuestionData`
- Blob storage: Figure images uploaded to Azure

---

## Cleanup Mode

Delete ExerciseData and QuestionData for a chapter, plus local state/output files. **ChapterData is NOT touched.**

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--cleanup` | flag | - | Enable cleanup mode |
| `--pdf` | string | **Required** | Path to PDF (used to identify local files to delete) |
| `--chapter-id` | int | None | ChapterId from database (for DB cleanup) |
| `--chapter-number` | string | None | Chapter number from book (requires `--class` and `--subject`) |
| `--dry-run` | flag | False | Preview what would be deleted without deleting |
| `--no-managed-identity` | flag | False | Use connection strings instead of Azure Managed Identity |

**Note:** 
- `--pdf` is always required
- If `--chapter-id` or `--chapter-number` is provided → cleans DB + local files
- If neither is provided → cleans only local files (useful for aborted Stage 1)

**Examples:**

```bash
# Full cleanup (DB + local files) by chapter ID
python main.py --cleanup --pdf "Input/keph203.pdf" --chapter-id 24

# Full cleanup using class/subject/chapter-number
python main.py --cleanup --pdf "Input/keph203.pdf" --class 11 --subject Physics --chapter-number 10

# Local files only (no DB) - for aborted Stage 1
python main.py --cleanup --pdf "Input/kech102.pdf"

# Preview cleanup (recommended first step)
python main.py --cleanup --pdf "Input/keph203.pdf" --chapter-id 24 --dry-run
```

**What gets deleted:**

*With chapter info (--chapter-id or --chapter-number):*
- ✅ All `QuestionData` rows for exercises in that chapter
- ✅ All `ExerciseData` rows for that chapter
- ✅ Local state file: `Output/<pdf_stem>_pipeline_state.json`
- ✅ Local extraction JSON: `Output/<pdf_stem>_extraction.json`
- ✅ Local solutions JSON: `Output/<pdf_stem>_solutions.json`
- ❌ `ChapterData` is NOT touched (preserved)
- ❌ Blob storage images are NOT touched (preserved)

*Without chapter info (local only):*
- ✅ Local state file: `Output/<pdf_stem>_pipeline_state.json`
- ✅ Local extraction JSON: `Output/<pdf_stem>_extraction.json`
- ✅ Local solutions JSON: `Output/<pdf_stem>_solutions.json`
- ❌ Database is NOT touched

---

## Environment Variables

The pipeline can be configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Gemini API key (for non-Vertex AI) | - |
| `GOOGLE_PROJECT_ID` | GCP project ID (for Vertex AI) | - |
| `GOOGLE_LOCATION` | GCP region (for Vertex AI) | `global` |
| `AZURE_PG_HOST` | PostgreSQL host | `<DB_HOST>` |
| `AZURE_PG_DATABASE` | Database name | `<DB_NAME>` |
| `AZURE_PG_USER` | Entra user (UPN format) | - |
| `AZURE_STORAGE_ACCOUNT` | Blob storage account | `stevaluationstorage` |
| `AZURE_BLOB_CONTAINER` | Blob container name | `onlineresources` |

---

## Typical Workflows

### First-time chapter processing
```bash
# 1. Run full E2E pipeline
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics
```

### Re-run with fixes (after code changes)
```bash
# 1. Clean up existing data (DB + local files)
python main.py --cleanup --pdf "Input/keph203.pdf" --chapter-id 24

# 2. Re-run full pipeline (fresh start)
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics
```

### Local testing (no Azure)
```bash
# Run locally without DB/Blob
python main.py --stage 3 --pdf "Input/keph203.pdf" --class 11 --subject Physics --local-only
```

### Regenerate solutions only
```bash
# If extraction is fine but solutions need re-generation:
python main.py --stage 2 --pdf "Input/keph203.pdf" --from-extraction "Output/keph203_extraction.json" --questions all
```

---

## Troubleshooting

### "Chapter not found"
- Ensure `ChapterData` table has the chapter entry
- Check class level format (`11` vs `11th`)
- Verify subject name matches exactly

### Solutions have "unknown" question_id
- Model returned malformed JSON (often with thinking text inserted mid-JSON)
- Check `solved_questions` in state file for "unknown" entries
- Fix: Remove "unknown" from state, reset `stage2_complete` and `db_ingestion_complete` to `false`, then re-run
- Prevention: Prompt updated with JSON validity rule (Jan 2026)

### Azure authentication fails
- Ensure you're logged in: `az login`
- Check Entra user format for PostgreSQL (needs `#EXT#` for external users)
- Verify managed identity is enabled on the resource

### "Skipping ingestion - no extraction result available"
- Occurs when pipeline resumes from completed Stage 2 but DB ingestion was skipped
- Solutions exist in JSON but weren't written to DB
- Fix: Use `fix_db_ingestion.py` utility (see below)

### DB ingestion failed (Azure auth expired, interrupted, etc.)
- State shows `stage2_complete: true` but `db_ingestion_complete: false`
- Use `fix_db_ingestion.py` to push solutions to DB without re-running the full pipeline

---

## Utility Scripts

### fix_db_ingestion.py

Push existing solutions from JSON file to database. Use when:
- Pipeline completed Stage 2 but DB ingestion was skipped or failed
- Azure auth expired mid-run
- `db_ingestion_complete: false` but solutions exist in JSON

**Usage:**
```bash
# First, login to Azure
az login

# Then run the fix script
python fix_db_ingestion.py <pdf_name>

# Examples:
python fix_db_ingestion.py kech106
python fix_db_ingestion.py keph203
```

**What it does:**
1. Loads `Output/<pdf_name>_pipeline_state.json`
2. Loads `Output/<pdf_name>_solutions.json`
3. Pushes all solutions to database (with sub-part consolidation)
4. Sets `db_ingestion_complete: true` in state file

---

## Fixing "unknown" in State Files

When Gemini inserts thinking text inside JSON output, parsing fails and "unknown" appears in `solved_questions`. To fix:

**1. Edit the state file:**
```json
// Before (broken):
"solved_questions": ["6.58", "6.59", "6.60", "unknown", "6.71", "6.72"]

// After (fixed):
"solved_questions": ["6.58", "6.59", "6.60", "6.71", "6.72"]
```

**2. Reset completion flags:**
```json
"stage2_complete": false,
"db_ingestion_complete": false,
```

**3. Re-run the pipeline:**
```bash
python main.py --stage 3 --pdf "Input/kech106.pdf" --class 11 --subject Chemistry
```

The pipeline will detect missing questions (6.61-6.70 in this example) and solve only those.

---

## Version History

| Date | Changes |
|------|---------|
| 2026-04-10 | Added `--use-smart-context` flag for PgVector chunk retrieval and GoldenGenerator critique loop |
| 2026-01-25 | Added `fix_db_ingestion.py` utility for pushing solutions to DB after auth failures |
| 2026-01-25 | Added troubleshooting for "unknown" in state files and DB ingestion skip issues |
| 2026-01-24 | Added JSON validity rule to prompt to prevent Gemini from inserting thinking text mid-JSON |
| 2026-01-24 | Added sub-part consolidation for multi-part questions (8.6.a, 8.6.b → 8.6) |
| 2026-01-24 | Added exponential backoff for 429 rate limit errors in gemini_client.py |
| 2025-12-16 | Cleanup now requires `--pdf` and deletes local state/output files |
| 2025-12-16 | Added cleanup mode (`--cleanup`, `--dry-run`, `--chapter-id`, `--chapter-number`) |
| 2025-12-16 | Added JSON escape sanitization for model output |
| 2025-12-16 | Fixed PostgreSQL lowercase table/column names |
