# JEE Ascent Pipeline (M1b + M3)

## What This Does

Extracts structured question data from NTA JEE Main PDFs (2021–2025) and writes it to the database.

**Two phases:**
1. **Phase 1 — Answer Key extraction**: Parse AK PDFs with PyMuPDF (no Gemini, text-selectable) → write to `jee_answer_mappings`
2. **Phase 2 — Question paper extraction**: Parse question paper PDFs with Gemini Pro → write to `jee_question_bank`, with answer keys joined inline

**Why this order?** NTA Question IDs are the join key. AKs must be in DB before papers are extracted so answer keys can be attached to each question during extraction.

---

## File Map

| File | Purpose |
|------|---------|
| `jee_extraction_pipeline.py` | Main entry point — orchestrates Phase 1 + Phase 2, CLI, checkpoints |
| `jee_ak_extractor.py` | AK PDF → list of `{nta_question_id, correct_option_id}` pairs (PyMuPDF + regex) |
| `jee_format_detector.py` | Renders page 1 of paper PDF as image → Gemini Flash classifies format |
| `jee_paper_extractor.py` | Sends full PDF to Gemini Pro → parses JSON → normalizes → AK lookup |
| `db_writer.py` | All DB reads/writes: fetch pending rows, bulk insert, mark extracted/failed |
| `settings_loader.py` | Loads `local.settings.local.json` into `os.environ` (same pattern as ConceptIndex) |
| `prompts/format_detection_prompt.txt` | Gemini Flash prompt: classify `PRE_2021` vs `2021_PLUS` vs `UNKNOWN` |
| `prompts/question_extraction_system.txt` | Gemini Pro system prompt: extract all 90 questions as JSON array with LaTeX |

**M3 files (question tagger):**

| File | Purpose |
|------|---------|
| `question_tagger.py` | Main entry point — loads vocab, calls Gemini Flash, embeds, writes DB |
| `prompts/question_tagger_system.txt` | LLM system prompt — tagging rules, difficulty/pattern/embed_text schema |
| `prompts/question_tagger_user.txt` | Per-batch user prompt template — vocabulary block + questions block |

**Shared libs (NOT in this folder — loaded via sys.path):**
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py`
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/config.py`
- `pipelines/ConceptIndex/gemini_extractor.py` — `embed_texts_batch()` used by M3 for question embeddings

---

## Prerequisites

### 1. Settings file
Create `pipelines/JEEAscentPipeline/local.settings.local.json`:
```json
{
  "IsEncrypted": false,
  "Values": {
    "DB_HOST": "<DB_HOST>",
    "DB_PORT": "5432",
    "DB_NAME": "<DB_NAME>",
    "DB_USER": "<DB_USER>"
  }
}
```
No `DB_PASSWORD` needed — the pipeline uses `DefaultAzureCredential` (Entra ID token) as fallback.

### 2. Python packages
```bash
pip install pymupdf psycopg2-binary azure-identity azure-storage-blob
```
(Gemini/MultiStep deps should already be installed from M2.)

### 3. Azure login
```bash
az login
```
Required for both blob downloads (PDFs from your configured blob container) and DB auth (Entra ID token).

---

## CLI Reference

```
python jee_extraction_pipeline.py [options]

--dry-run          Extract + validate but skip all DB writes
--ak-only          Run Phase 1 only (AK extraction, no Gemini)
--format-only      Run format detection only (Gemini Flash, no extraction)
--year 2024        Filter to a specific year
--session "S1"     Filter by session name
--paper-ids 12,34  Run only specific exam_papers IDs
```

---

## Recommended Run Order

### Step 1 — Validate AK extraction (no Gemini, cheap)
```bash
cd pipelines/JEEAscentPipeline
python jee_extraction_pipeline.py --dry-run --ak-only --year 2024
```
**Success:** `checkpoints/ak_<id>.json` shows `"mappings_count": 440+` and `"completed": true`

### Step 2 — Validate format detection (Gemini Flash, fast)
```bash
python jee_extraction_pipeline.py --dry-run --format-only --year 2024
```
**Success:** Logs show `format=2021_PLUS` for all 2024 papers

### Step 3 — Single paper e2e dry-run (Gemini Pro, uses tokens)
First find a 2024 paper ID:
```sql
SELECT id, year, shift, filename FROM exam_papers WHERE year = 2024 LIMIT 5;
```
Then:
```bash
python jee_extraction_pipeline.py --dry-run --paper-ids <id>
```
**Success:** Log shows `OK — 30 questions, 90%+ have answer keys`

### Step 4 — Single paper real write (when dry-run passes)
```bash
python jee_extraction_pipeline.py --paper-ids <id>
```
Check DB: `SELECT COUNT(*) FROM jee_question_bank WHERE exam_paper_id = <id>;`

### Step 5 — Full run (all years)
```bash
python jee_extraction_pipeline.py
```
2023 S1 and "JEE Main 2018" rows are automatically skipped by the DB queries.

---

## Checkpoint Files

Location: `checkpoints/ak_<id>.json` and `checkpoints/paper_<id>.json`

Each checkpoint tracks stages: `downloaded`, `parsed`/`format_detected`/`questions_extracted`, `db_written`, `completed`.

**The pipeline is fully resumable** — restarting picks up from the last completed stage. To force a retry from scratch, delete the checkpoint file.

Logs go to `logs/jee_extraction_<timestamp>.log`.

---

## DB Tables Written

| Table | Phase | What's written |
|-------|-------|---------------|
| `jee_answer_mappings` | Phase 1 | `nta_question_id` → `correct_option_id`, `source_key_id` |
| `exam_answer_keys.extraction_status` | Phase 1 | `'EXTRACTED'` or `'FAILED'` |
| `jee_question_bank` | Phase 2 | Full question record: `nta_question_id`, `subject`, `section`, `question_content` (JSONB), `answer_key`, `tier=3`, `source='NTA_EXTRACTED'` |
| `exam_papers.extraction_status` | Phase 2 | `'EXTRACTED'` or `'FAILED'` |
| `exam_papers.paper_format` | Phase 2 | `'PRE_2021'`, `'2021_PLUS'`, or `'UNKNOWN'` |

---

## `question_content` JSONB Schema

```json
{
  "nta_question_id": "87827056058",
  "question_number": 1,
  "raw_text": "A particle moves in a circle of radius $r$...",
  "options": [
    {"nta_option_id": "878270220131", "text": "$\\frac{v^2}{r}$"},
    {"nta_option_id": "878270220132", "text": "$\\frac{v}{r^2}$"},
    {"nta_option_id": "878270220133", "text": "$vr$"},
    {"nta_option_id": "878270220134", "text": "$\\frac{r}{v^2}$"}
  ],
  "has_figure": false,
  "figure_description": null,
  "figure_blob_url": null
}
```
Options use NTA Option IDs as identifiers. Array position encodes the letter: index 0 = A, 1 = B, 2 = C, 3 = D.
`answer_key` in `jee_question_bank` stores "A"/"B"/"C"/"D" for MCQ, or a plain integer string (e.g. "25") for Section B.
`figure_blob_url` is always `null` in Phase 1 — figure image crops are a Phase 2 enhancement.

---

## Known Data Anomalies (handled automatically)

| Anomaly | How handled |
|---------|-------------|
| 2022 papers have mixed 6-digit + 11-digit NTA Q IDs | Regex `\b\d{6,}\b` captures all; dedup by first occurrence |
| 2023 S1 — no papers, bad AK row | Filtered out in all DB fetch queries |
| Two 2025 rows named "JEE Main 2018" | Filtered out in `fetch_pending_papers()` SQL |
| One 2024 paper filed under year=2025 | Uses actual `dateofexam` date, not year column |

---

## NTA Question ID Digit Counts by Year

| Year | Q ID Format | Min digits in regex |
|------|-------------|---------------------|
| 2021 | 10-digit | 8 |
| 2022 | 6-digit sequential OR 11-digit mixed | 6 |
| 2023 | 10-digit | 8 |
| 2024 | 11-digit | 8 |
| 2025 | 10-digit | 8 |

---

## Gemini Models Used

| Task | Model | Config |
|------|-------|--------|
| Format detection | `gemini-3-flash-preview` | temp=0.1, JSON output |
| Question extraction | `gemini-3.1-pro-preview` | temp=0.2, JSON output, max_tokens=32768 |

---

## Validation Thresholds

| Check | Threshold |
|-------|-----------|
| AK pairs extracted per AK file | ≥ 400 (expected ~448 for 2024) |
| Questions extracted per paper | ≥ 70 (expected 90) |
| Answer key coverage | ≥ 80% of questions must have `answer_key` set |

If validation warns (not crashes) — check logs, inspect checkpoint, decide whether to proceed.

---

## DB Verification Queries

```sql
-- How many AKs extracted?
SELECT extraction_status, COUNT(*) FROM exam_answer_keys GROUP BY extraction_status;

-- Answer mappings by year
SELECT e.year, COUNT(*) FROM jee_answer_mappings m
JOIN exam_answer_keys e ON e.id = m.source_key_id
GROUP BY e.year ORDER BY e.year;

-- Questions extracted by year
SELECT year, COUNT(*) FROM jee_question_bank GROUP BY year ORDER BY year;

-- Coverage check
SELECT year,
  COUNT(*) total,
  SUM(CASE WHEN answer_key IS NOT NULL THEN 1 ELSE 0 END) with_ak,
  ROUND(100.0 * SUM(CASE WHEN answer_key IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) pct
FROM jee_question_bank GROUP BY year ORDER BY year;
```

Expected: ~750–900 questions per session-year across all papers.

---

---

## Crop Pipeline CLI (`jee_crop_pipeline.py`)

Crop-based alternative to the Pro pipeline. Faster (~3 min/paper) and cheaper.
**Does not touch any existing pipeline files.**

### Common commands

```bash
# Validate scan + render on one paper (no Gemini, no DB)
python jee_crop_pipeline.py --paper-ids 1 --render-only

# Full dry-run on one paper (Flash transcription, no DB writes)
python jee_crop_pipeline.py --paper-ids 1 --dry-run

# Full run on one paper (writes to DB)
python jee_crop_pipeline.py --paper-ids 1

# Full run filtered by year
python jee_crop_pipeline.py --year 2024

# Full run on multiple papers
python jee_crop_pipeline.py --paper-ids 1,208,222,165

# All pending papers (full run)
python jee_crop_pipeline.py
```

### Switches

| Switch | Effect |
|--------|--------|
| `--paper-ids 1,2,3` | Only process these exam_papers IDs |
| `--year 2024` | Only process papers for this year |
| `--session "Session 1"` | Filter papers by session name prefix |
| `--render-only` | Scan text layer + render crops; stop before Flash and DB |
| `--dry-run` | Run Flash transcription + validation; skip all DB writes |
| _(no flags)_ | Full run: scan, render, Flash, validate, write DB, mark extracted |

### Output locations

| Artifact | Location |
|----------|----------|
| Crop PNGs | `temp/crops/paper_{id}/q001_<nta_id>_p2.png` … |
| Checkpoints | `checkpoints/crop_paper_{id}.json` |
| Logs | `logs/jee_crop_<timestamp>.log` |

### Notes
- Crops are skipped if PNG already exists (resumable render step)
- Checkpoints use prefix `crop_paper_` to avoid collision with Pro pipeline's `paper_` checkpoints
- 2022 papers: skip (no matching answer keys in DB)
- Papers returning 0 NTA IDs are flagged and skipped (PRE_2021 format not supported)

---

## M3 — Question Tagger

Tags each `jee_question_bank` row with NCERT concept IDs, generates 768-dim question embeddings,
and writes `difficulty` / `pattern_label` metadata.

### How it works
- Loads the NCERT concept vocabulary once per subject (Physics 712 nodes / Chemistry 1,038 / Maths 958)
- Sends batches of 5 questions + vocabulary to Gemini Flash → returns concept IDs, relevance scores,
  difficulty, pattern label, and plain-English embed_text per question
- Embeds the embed_texts via `text-embedding-004` (768-dim, us-central1 regional endpoint)
- Writes to three tables: `jee_question_tags`, `jee_question_embeddings`, `jee_question_bank` (metadata cols)
- **Resumable by design** — re-runs skip already-tagged questions via NOT EXISTS on `jee_question_tags`

### Subject name mapping
`jee_question_bank.subject` uses 'Mathematics'; `ncert_concept_hierarchy.subject` uses 'Maths'.
The pipeline maps these automatically. Do not change the vocabulary query.

### M3 CLI Reference

```
python question_tagger.py [options]

--subject Physics|Chemistry|Mathematics   Process only this subject (default: all three)
--year 2024                               Filter by exam year
--date 2024-04-08                         Filter to a single paper date (YYYY-MM-DD)
--shift 1                                 Filter to a single shift
--mode hybrid|full                        hybrid (default): pgvector top-K retrieval per batch
                                          full: sends entire subject vocabulary — use as fallback
--batch-size N                            Questions per LLM call (default: 15 hybrid, 5 full)
                                          Use --batch-size 1 with --mode full to avoid JSON truncation
--workers N                               Concurrent batch workers (default: 4)
--dry-run                                 Tag + embed but skip all DB writes; prints first-batch sample
--limit N                                 Max questions to process (useful for testing)
--skip-embeddings                         Tag only; skip jee_question_embeddings writes
```

### Recommended run sequence

```bash
cd pipelines/JEEAscentPipeline

# Standard run — hybrid mode, 4 workers (handles ~85-90% of questions)
python question_tagger.py --year 2024

# For questions that persistently fail hybrid (sequential hallucinated IDs 1,2,3…):
# Full mode with batch-size 1 eliminates both retrieval failures and JSON truncation
python question_tagger.py --subject Mathematics --year 2024 --mode full --batch-size 1

# Full corpus for a new year
python question_tagger.py --year 2023
```

### Failure modes and fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Hallucinated concept IDs 1,2,3… (whole batch) | pgvector retrieval returns poor candidates for sparse/equation-only questions | Switch to `--mode full --batch-size 1` |
| JSON parse error: Unterminated string | Response truncated — output too long for `max_output_tokens` | Reduce `--batch-size`; use `--batch-size 1` with full mode |
| ReadTimeout → retry | Gemini API timeout on large prompts | Normal; exponential backoff handles it |

### M3 DB Tables Written

| Table | What's written |
|-------|---------------|
| `jee_question_tags` | `(question_id, concept_id, similarity_score)` — 1–6 rows per question |
| `jee_question_embeddings` | `(question_id, embedding vector(768), embed_text)` — 1 row per question |
| `jee_question_bank` | `difficulty`, `difficulty_confidence`, `pattern_label` updated |

### M3 Verification Queries

```sql
-- Tagging progress per subject
SELECT q.subject,
       COUNT(*) total,
       COUNT(DISTINCT t.question_id) tagged,
       COUNT(*) - COUNT(DISTINCT t.question_id) untagged
FROM jee_question_bank q
LEFT JOIN jee_question_tags t ON t.question_id = q.id
GROUP BY q.subject ORDER BY q.subject;

-- Spot-check concept tags for one question
SELECT nch.concept_title, nch.content_type, t.similarity_score
FROM jee_question_tags t
JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
WHERE t.question_id = <id>
ORDER BY t.similarity_score DESC;

-- Difficulty distribution
SELECT difficulty, COUNT(*) FROM jee_question_bank
WHERE difficulty IS NOT NULL GROUP BY difficulty;
```

### M3 Gemini Model

| Task | Model | Config |
|------|-------|--------|
| Concept tagging + metadata | `gemini-3-flash-preview` | temp=0.1, JSON output, max_tokens=8192 |
| Question embedding | `text-embedding-004` | 768-dim, us-central1, RETRIEVAL_DOCUMENT |

Override tagging model via env var: `M3_TAGGER_MODEL=<model-id>`

---

## Status

**M1b:** In Progress — Pro pipeline complete; crop pipeline written and cross-year validated.

Crop pipeline validation status:
- 2021 (paper 208): render validated (90 crops)
- 2022: skipped (no AKs)
- 2023 (paper 222): render validated (90 crops, after option-ID filter fix)
- 2024 (paper 1): Flash validated 9/10 questions
- 2025 (paper 165): render validated (75 crops)

**M3:** 2024 fully tagged (2026-04-14).
- Mathematics: 2,290 / 2,290 tagged ✓
- Chemistry:   2,088 / 2,088 tagged ✓
- Physics:     2,045 / 2,045 tagged ✓
- 2023 tagging in progress (1,080 questions, all subjects)

Performance improvements applied (2026-04-14):
- `db_writer.py`: `ThreadedConnectionPool` replaces per-call `psycopg2.connect()` — eliminates Entra auth overhead on every query
- `question_tagger.py`: `ThreadPoolExecutor(max_workers=4)` — concurrent batch processing
- `max_output_tokens` reduced 32768 → 8192 — eliminates Flash latency from oversized output ceiling
- Proven fallback: `--mode full --batch-size 1` for questions that persistently hallucinate in hybrid mode

Next action: complete 2023 tagging, then E2E validation (M3 tags → M7 API → M8 frontend).
