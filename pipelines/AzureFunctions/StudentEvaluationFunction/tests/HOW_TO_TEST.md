# How to Test & Debug the Student Evaluation Pipeline

## Quick Reference

| What to test | Command | Gemini cost |
|---|---|---|
| Student HW splitting | `split-hw` | ~1 call (bounding box, supports multi-page) |
| Text ref parsing | `parse-ref` | ~1 call (lightweight flash-lite) |
| Textbook page splitting | `split-tb` | ~1 call (bounding box, supports multi-page) |
| Multi-problem unified evaluation | `evaluate` | ~1 call per batch (full student pages + optional textbook pages) |
| Custom prompt | `raw-gemini` | ~1 call |
| **Full pipeline (local)** | `test_durable_e2e.py` | **~5–8 calls** |
| **Full pipeline (deployed)** | `test_durable_e2e.py --target deployed` | **~5–8 calls** |

---

## 1. Prerequisites

### Environment

```powershell
# Activate the conda environment
conda activate AzureFunc

# Ensure you are in the project directory
cd C:\Bala\Coding\AryaBhatta\pipelines\AzureFunctions\StudentEvaluationFunction
```

### Azure Login (required for Key Vault + Blob access)

```powershell
az login
```

The test script auto-loads `local.settings.json` so all env vars
(KEY_VAULT_URL, BLOB_STORAGE_URL, DB_*, etc.) are available automatically.

---

## 2. Isolated Activity Testing  (`test_activities.py`)

These tests call Gemini **directly** — no `func start`, no queue, no database.
Every run saves all inputs/outputs to `tests/output/<timestamp>_<command>/`.

### 2a. Student Handwriting Splitting  (`split-hw`)

Detects individual problem bounding boxes in a student's handwritten solution image
and crops them using PIL.

```powershell
# Single page
python tests/test_activities.py split-hw --image "G:\My Drive\Karma\AryaBhatta\Samples\HandWritten\11_NCERT_Phy_Oscillations\Phy_13_9.jpeg"

# Multi-page (student work spans multiple photos)
python tests/test_activities.py split-hw --image page1.jpg page2.jpg page3.jpg

# Skip PIL cropping (just get the bounding-box JSON)
python tests/test_activities.py split-hw --image "path\to\image.jpg" --skip-crop

# Override model
python tests/test_activities.py split-hw --image "path\to\image.jpg" --model gemini-2.5-flash-lite
```

**Output files:**
```
tests/output/20260219_143022_split_hw/
  ├── prompt.md             # The prompt sent to Gemini
  ├── input_image_0.jpeg    # Copy of page 1
  ├── input_image_1.jpeg    # Copy of page 2 (if multi-page)
  ├── raw_response.txt      # Gemini's raw text response
  ├── parsed_result.json    # Parsed bounding box JSON
  ├── meta.json             # Model, tokens, duration
  ├── crop_Q1.jpg           # Cropped problem images (if not --skip-crop)
  ├── crop_Q2.jpg
  └── ...
```

**What to look for:**
- Are all problems detected? Check `parsed_result.json` → `solutions[]`
- Are bounding boxes reasonable? Check `box_2d` values (0–1000 scale)
- Are crops correct? Open `crop_Q*.jpg` files visually

---

### 2b. Text Reference Parsing  (`parse-ref`)

Parses free-form text like `"13.8, 13.9"` or `"Exercise 13.1 Q4 Q5"` into
structured `{ metadata, exercises[{exercise_label, problem_numbers}] }`.

```powershell
# Simple problem numbers
python tests/test_activities.py parse-ref --text-ref "13.9"

# Multiple problems
python tests/test_activities.py parse-ref --text-ref "13.8, 13.9, 13.10"

# With exercise label
python tests/test_activities.py parse-ref --text-ref "Exercise 13.1 Q4 Q5" --subject Physics --chapter "Oscillations"

# Chemistry chapter
python tests/test_activities.py parse-ref --text-ref "5.1, 5.2" --subject Chemistry --chapter "States of Matter"
```

**What to look for:**
- Does `exercises[].problem_numbers` match what the student typed?
- Is the chapter number extracted correctly in `metadata`?
- Does it handle edge cases? (e.g. `"Q4-Q8"` ranges, `"all"`, `"13.1 to 13.5"`)

---

### 2c. Textbook Problem Splitting  (`split-tb`)  — Legacy

> **Note:** In the v4 unified flow, textbook images are sent as full pages
> (via `--textbook-image` in the `evaluate` command) instead of being
> split into individual problems. This command is retained for debugging
> bounding-box detection but is **not used in the main pipeline**.

Splits a photo of a textbook page into individual problem bounding boxes.

```powershell
# Single page
python tests/test_activities.py split-tb --image "path\to\textbook_page.jpg"

# Multi-page (problems span across pages)
python tests/test_activities.py split-tb --image textbook_p1.jpg textbook_p2.jpg

# Skip cropping
python tests/test_activities.py split-tb --image "path\to\textbook_page.jpg" --skip-crop
```

**What to look for:**
- Same as `split-hw` but for textbook formatting
- Are sub-parts (a, b, c) grouped correctly under the same problem?

---

### 2d. Unified Multi-Problem Evaluation  (`evaluate`)  — v4

Sends full student page images + a list of problem numbers to Gemini in one call.
Gemini locates the relevant work on the student's pages and evaluates each problem.
Supports multiple student images (multi-page), multiple problems, and optional
textbook page images as additional visual context.

```powershell
# Single problem, single page, with chapter PDF from blob
python tests/test_activities.py evaluate `
  --student-image "G:\My Drive\...\Phy_13_9.jpeg" `
  --problem-number "13.9" `
  --subject Physics `
  --class-val 11 `
  --chapter "Oscillations" `
  --pdf-url "<BLOB_STORAGE_URL>/feedback/11/Physics/keph213.pdf"

# Multiple problems, multiple student pages
python tests/test_activities.py evaluate `
  --student-image "page1.jpg" "page2.jpg" `
  --problem-number "13.8" "13.9" "13.10" `
  --subject Physics `
  --exercise-label "Exercise 13.1" `
  --pdf-file "path\to\chapter.pdf"

# With textbook page image(s) as additional context
python tests/test_activities.py evaluate `
  --student-image "page1.jpg" `
  --textbook-image "textbook_page.jpg" `
  --problem-number "13.8" "13.9" `
  --subject Physics `
  --class-val 11 `
  --chapter "Oscillations" `
  --pdf-url "<BLOB_STORAGE_URL>/feedback/11/Physics/keph213.pdf"

# Without PDF (Gemini uses training knowledge only)
python tests/test_activities.py evaluate `
  --student-image "page1.jpg" `
  --problem-number "4.1" "4.2" `
  --subject Chemistry
```

**What to look for:**
- Response format: `{"evaluations": [{problem_id, found_in_student_work, evaluation_status, ...}]}`
- `found_in_student_work` — did Gemini correctly identify which problems are on the pages?
- `evaluation_status` — Correct / Partially Correct / Incorrect / Not Found / Error
- `feedback_for_student` — is it helpful and specific?
- Compare runs with and without `--pdf-file` to see PDF impact
- Compare runs with and without `--textbook-image` to see textbook context impact
- Try with problems NOT on the student's pages to test the "Not Found" case

> **Batch size note**: In production, the orchestrator batches by `EVAL_BATCH_SIZE` (default 3).
> The test CLI sends all requested problems in a single Gemini call.

---

### 2e. Raw Gemini Call  (`raw-gemini`)

Free-form Gemini testing with any prompt or input combination.

```powershell
# Text-only prompt
python tests/test_activities.py raw-gemini --prompt-file "my_prompt.txt"

# Image + prompt
python tests/test_activities.py raw-gemini --prompt-file "my_prompt.txt" --image "img.jpg"

# PDF + prompt + JSON mode
python tests/test_activities.py raw-gemini --prompt-file "my_prompt.txt" --pdf "doc.pdf" --json-mode

# Override temperature
python tests/test_activities.py raw-gemini --prompt-file "my_prompt.txt" --temperature 0.3
```

---

## 3. Full Pipeline E2E Testing  (`test_durable_e2e.py`)

Tests the **entire** pipeline: queue → orchestrator → all activities → DB update.
Requires `func start` to be running.

### Start the Function Host

```powershell
# Terminal 1 — start the function host
.\start-func.ps1
```

### Run E2E test

```powershell
# Terminal 2 — text reference only (most common)
python tests/test_durable_e2e.py `
  --student-work "G:\My Drive\...\Phy_13_9.jpeg" `
  --text-ref "13.9" `
  --subject Physics `
  --class 11 `
  --chapter "Oscillations" `
  --chapter-num 13

# Multi-page student work (4 scanned pages) + text-ref-driven chapter resolution
python tests/test_durable_e2e.py `
  --student-work page1.jpg page2.jpg page3.jpg page4.jpg `
  --text-ref "Organic chemistry problems 1 to 4, 6 to 8, 11 to 16" `
  --subject Chemistry `
  --class 11

# Text reference + textbook image (optional extra context)
python tests/test_durable_e2e.py `
  --student-work "student.jpg" `
  --text-ref "13.8, 13.9" `
  --problem-image "textbook_page.jpg" `
  --subject Physics `
  --class 11 `
  --chapter "Oscillations" `
  --chapter-num 13

# Check status / cleanup
python tests/test_durable_e2e.py --status <job_id>
python tests/test_durable_e2e.py --cleanup <job_id>
```

> **v4 Note:** `--text-ref` is always required. `--problem-image` is optional —
> if provided, the textbook page image is fetched and sent to Gemini as
> additional visual context alongside student pages.
> `--chapter` and `--chapter-num` are optional — if omitted, the pipeline
> resolves them from the text ref via Gemini + DB grounding.

---

## 3b. Testing the Deployed Function  (`--target deployed`)

The same `test_durable_e2e.py` script tests the **deployed** Azure Function App.
The script uses the same Azure resources (blob, DB, queue) — the only difference
is which function host picks up the queue message.

### Prerequisites

1. **Stop local func host** — both local and deployed compete for the same queue.
2. **Deploy latest code** — `func azure functionapp publish <FUNCTION_APP_NAME> --python`
3. **Azure CLI logged in** — `az login` (for DB auth, blob upload, and health check)

### Run against deployed function

```powershell
# Simple text-ref test
python tests/test_durable_e2e.py --target deployed `
  --student-work "G:\My Drive\...\1.jpeg" `
  --text-ref "13.9" `
  --subject Physics `
  --class 11

# Multi-page + problem images + text ref
python tests/test_durable_e2e.py --target deployed `
  --student-work hw1.jpg hw2.jpg hw3.jpg `
  --problem-image p1.jpg p2.jpg p3.jpg `
  --text-ref "Problems 10-13 in 3D geometry" `
  --subject Maths `
  --class 11

# Fire-and-forget (useful for long-running tests)
python tests/test_durable_e2e.py --target deployed `
  --student-work page1.jpg `
  --text-ref "Organic chemistry problems 1-4" `
  --subject Chemistry --class 11 `
  --no-poll --no-cleanup

# Check status later
python tests/test_durable_e2e.py --status <job_id>
```

### What `--target deployed` does differently

| Behavior | `--target local` (default) | `--target deployed` |
|---|---|---|
| Pre-flight check | Warns if port 7072 not listening | Warns if port 7072 IS listening (queue competition) |
| Health check | None | Runs `az functionapp show` to verify app is Running |
| Upload / Insert / Queue | Same (Azure resources) | Same (Azure resources) |
| Poll / Cleanup | Same (direct DB) | Same (direct DB) |

> **Tip:** Use `--no-poll --no-cleanup` to submit a job and check on it later.
> This is useful when testing the deployed function's cold-start or
> when you want to inspect logs in the Azure Portal.

---

## 5. Debugging Tips

### Comparing Gemini outputs

Every `test_activities.py` run saves to a timestamped output folder. To compare
two runs side-by-side:

```powershell
# List recent outputs
Get-ChildItem tests\output -Directory | Sort-Object Name -Descending | Select-Object -First 5

# Compare parsed results
diff (Get-Content tests\output\20260219_140000_split_hw\parsed_result.json) `
     (Get-Content tests\output\20260219_141500_split_hw\parsed_result.json)
```

### Model comparison

Run the same input with different models to compare quality:

```powershell
python tests/test_activities.py split-hw --image "img.jpg" --model gemini-3-pro-preview
python tests/test_activities.py split-hw --image "img.jpg" --model gemini-2.5-flash-lite
```

Then compare `parsed_result.json` and `meta.json` (token usage, duration).

### Prompt iteration

1. Save a copy of the prompt from the output folder
2. Edit it locally
3. Test with `raw-gemini`:

```powershell
python tests/test_activities.py raw-gemini --prompt-file "my_edited_prompt.txt" --image "img.jpg" --json-mode
```

### Check token costs

Every test run saves `meta.json` with:
```json
{
  "model": "gemini-3-pro-preview",
  "usage_metadata": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  },
  "duration_ms": 4523
}
```

### Database inspection

After an E2E run, check the evaluation row:

```sql
-- Full row
SELECT * FROM solution_evaluations WHERE evaluation_id = '<job_id>';

-- Checkpoint steps
SELECT evaluation_id, current_step, pipeline_steps
FROM solution_evaluations
WHERE status IN ('PROCESSING', 'COMPLETED', 'FAILED')
ORDER BY created_at DESC LIMIT 5;

-- Pretty-print pipeline steps
SELECT evaluation_id, jsonb_pretty(pipeline_steps) FROM solution_evaluations
WHERE evaluation_id = '<job_id>';
```

### Common errors

| Error | Cause | Fix |
|---|---|---|
| `Error retrieving API key from Key Vault` | Not logged in to Azure | `az login` |
| `429 / RESOURCE_EXHAUSTED` | Gemini rate limit | Wait, or use `--model gemini-2.5-flash-lite` |
| `Invalid JSON response from Gemini` | Model returned non-JSON | Check `raw_response.txt` in output folder |
| `Managed Identity auth failed` | Blob auth issue | Usually falls back to public access; check URL |
| `Image not found` | Wrong path | Use absolute path or check escaping |

---

## 6. File Reference

| File | Purpose |
|---|---|
| `tests/test_activities.py` | **Isolated activity testing** (this doc) |
| `tests/test_durable_e2e.py` | Full pipeline E2E test (local & deployed via `--target`) |
| `tests/test_prod.py` | Test deployed Azure Function (legacy) |
| `tests/test_helper.py` | Shared test utilities |
| `tests/output/` | All test outputs (git-ignored) |
| `start-func.ps1` | Start local function host |
| `local.settings.json` | Environment config (loaded automatically) |

