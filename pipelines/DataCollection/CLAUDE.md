# DataCollection Pipeline — Facts & Decisions

## What This Folder Does

Downloads JEE Main question papers and answer key PDFs from the NTA website, uploads them to Azure Blob Storage, and records metadata in PostgreSQL.

---

## Scripts

### `download_exam_papers.py`
- Downloads JEE Main B.Tech (Paper 1) question papers from `https://jeemain.nta.nic.in/`
- Uses Selenium to navigate the NTA site (year + search interaction)
- Downloads PDFs via direct link click (browser download event), not `requests`
- Uploads each PDF to Azure Blob Storage at path: `jeedata/{year}/{filename}`
- Inserts a record into `exam_papers` after each successful upload
- Controlled by `YEARS_TO_DOWNLOAD` env var (comma-separated years); omit to process all available years

### `download_answer_keys.py`
- Downloads JEE Main answer key PDFs from `https://jeemain.nta.nic.in/document-category/archive/`
- The archive page uses a category `<select>` dropdown — there is no free-text filter. Do NOT attempt to type "answer key" into an input; just navigate and paginate.
- Scrapes all pages; `classify_title()` handles filtering per-row (must contain "answer key", must not be B.Arch/Planning, must contain a 4-digit year)
- Downloads PDFs via `requests.get(url, stream=True)` — CDN links are direct, no browser download event needed
- Uploads each PDF to Azure Blob Storage at path: `jeedata/answer_keys/{year}/{filename}`
- Inserts a record into `exam_answer_keys` after each successful upload
- Controlled by `YEARS_TO_DOWNLOAD` env var; omit to process all years found

---

## Database Tables

### `exam_papers`
Stores metadata for downloaded question paper PDFs.

**Unique constraint**: `(ExamName, Year, DateOfExam, Shift)` — NOT `(ExamName, PaperName)`.
- The old `(ExamName, PaperName)` constraint was wrong: pre-2023 NTA papers reuse generic names like "BTech" across all sessions within a year, causing all but the first insert to silently fail.
- Migration: `DROP CONSTRAINT IF EXISTS uq_exam_paper` then `ADD CONSTRAINT uq_exam_paper UNIQUE (ExamName, Year, DateOfExam, Shift)`

**`ON CONFLICT` upsert pattern**:
```sql
ON CONFLICT (ExamName, Year, DateOfExam, Shift) DO UPDATE
    SET blob_url = EXCLUDED.blob_url, filename = EXCLUDED.filename
    WHERE exam_papers.blob_url IS NULL
```
This means re-running is safe — it only updates rows that previously had a NULL blob_url.

### `exam_answer_keys`
Stores metadata for downloaded answer key PDFs.

Columns: `id`, `title`, `year`, `session`, `key_type` (`FINAL` or `PROVISIONAL`), `blob_url`, `filename`, `extraction_status` (default `PENDING`)

**Unique constraint**: `(year, session, key_type)`

**`ON CONFLICT` upsert pattern**:
```sql
ON CONFLICT (year, session, key_type) DO UPDATE
    SET blob_url = EXCLUDED.blob_url, filename = EXCLUDED.filename
    WHERE exam_answer_keys.blob_url IS NULL
```

---

## Paper Filtering Rules (`download_exam_papers.py`)

Papers are skipped if they match any of these:
- Contains `arch` or `planning` in the name → B.Arch / Planning paper
- Contains a regional language name (hindi, assamese, bengali, gujarati, kannada, malayalam, marathi, odiya, odia, punjabi, tamil, telugu, urdu) → non-English paper
- Matches `\bE[A-Z]{1,3}\b` (e.g., "BTech EA", "BTech ETE") → 2021-era bilingual code
- Ends with ` h` → standalone Hindi abbreviation

**Exception**: if the paper name contains `english`, it is always kept regardless of other matches.

Papers with no language suffix (e.g., "BTech") are kept — these are English papers.

---

## Answer Key Classification Rules (`download_answer_keys.py`)

`classify_title(title)` returns `{year, session, key_type}` or `None`:
- Must contain "answer key" (case-insensitive)
- Must NOT contain: `paper-2`, `paper 2`, `b.arch`, `b.planning`, `architecture`, `planning`
- Must contain a 4-digit year matching `\b(20\d{2})\b`
- `key_type`: `PROVISIONAL` if "provisional" in title, else `FINAL`
- `session`: extracted from "Session N" pattern; falls back to 3-letter month abbreviation (FEB, AUG, etc.); defaults to `All`

**Deduplication**: for each `(year, session)` group, if a FINAL exists, all PROVISIONAL entries for that group are dropped.

---

## Answer Key PDF Format (NTA)

- Multi-column table layout: 3 pairs of `QUESTION ID | CORRECT OPTION ID` columns per page
- Rows grouped by subject: Physics, Chemistry, Maths
- MCQ rows: numeric Question ID → numeric Option ID (e.g., 1, 2, 3, 4)
- Integer type rows: numeric Question ID → numeric answer value
- **All years 2021+:** one PDF per session covering all dates × shifts (not one per date)
- NTA Question IDs are the same across all language variants — any language's answer key gives the correct mapping
- Text-selectable (not image-based) — PyMuPDF extraction works without OCR

### Question ID Digit Count by Year

| Year | Question ID digits | Correct Option ID (MCQ) digits |
|------|--------------------|-------------------------------|
| 2021 | 10-digit | 11-digit |
| 2022 | 11-digit | 12-digit |
| 2023 | 10-digit | 11-digit |
| 2024 | 11-digit | 12-digit |

Integer-type answers are always raw numbers (e.g., `18`, `420`) regardless of year.

### AK PDF Hosting by Year

| Year | Host | Notes |
|------|------|-------|
| 2021 | `nta.ac.in/Download/Notice/` | Predictable `Notice_YYYYMMDDHHMMSS.pdf` filenames |
| 2022 | NIC CDN (`cdnbbsr.s3waas.gov.in`) | Unpredictable path; requires `filetype:pdf` Google search |
| 2023 | NIC CDN (`cdnbbsr.s3waas.gov.in`) | Unpredictable path; requires `filetype:pdf` Google search |
| 2024 | `nta.ac.in/Download/Notice/` | Predictable `Notice_YYYYMMDDHHMMSS.pdf` filenames |
| 2025 | `nta.ac.in/Download/Notice/` | Likely same as 2024 (not yet fully tested) |

---

## Extraction Architecture (Sub-Module 1c — not yet implemented)

**Step 1 — Extract answers first:**
- Parse each `exam_answer_keys` PDF
- Store results in `jee_answer_mappings (nta_question_id PK, correct_option_id, source_key_id FK)`
- Mark `exam_answer_keys.extraction_status = 'EXTRACTED'`

**Step 2 — Extract questions second:**
- Parse each `exam_papers` PDF
- For each question: look up `nta_question_id` in `jee_answer_mappings` → set `answer_key` immediately
- Write complete record to `jee_question_bank`
- Mark `exam_papers.extraction_status = 'EXTRACTED'`

**Linking mechanism**: No DB-level FK between `exam_papers` and `exam_answer_keys`. The NTA Question ID is the sole join key, resolved at extraction time. Questions with no matching answer key entry get `answer_key = NULL` and can be reprocessed later.

---

## Authentication

- Azure Blob Storage: `DefaultAzureCredential()` (requires `az login`)
- PostgreSQL: Entra ID token fetched via `DefaultAzureCredential()` when `DB_PASSWORD` is not set
- No passwords or connection strings are stored — run `az login` before executing any script

---

## Blob Storage Paths

| Content | Path |
|---------|------|
| Question papers | `jeedata/{year}/{filename}` |
| Answer keys | `jeedata/answer_keys/{year}/{filename}` |

Storage account: `kalidasa` (dev/current). Container: `jeedata`.

---

## Environment Variables (`.env`)

| Variable | Purpose |
|----------|---------|
| `AZURE_STORAGE_ACCOUNT` | Storage account name |
| `AZURE_STORAGE_CONTAINER` | Blob container name |
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port (default 5432) |
| `DB_NAME` | Database name |
| `DB_USER` | Entra ID username for DB |
| `DOWNLOAD_DIR` | Local folder for downloaded PDFs (optional) |
| `YEARS_TO_DOWNLOAD` | Comma-separated years to process (omit for all) |

---

## Run Order

1. Run SQL from `JEEMainDownloadScripts.sql` to create/migrate tables
2. Run `download_exam_papers.py` for question papers
3. Run `download_answer_keys.py` for answer keys
4. Run extraction pipeline (Sub-Module 1c — not yet built)

---

## Sub-Module 1a — Completion Status (2026-03-21)

Sub-Module 1a covers all data collection: question paper downloads, answer key downloads,
and the infrastructure to make 1b (extraction) viable. **COMPLETE** — 3 AKs downloaded
this session to close all remaining gaps.

### Scripts delivered

| Script | Status | Notes |
|--------|--------|-------|
| `download_exam_papers.py` | DONE | Selenium + blob upload + exponential backoff |
| `download_answer_keys.py` | DONE (with caveat) | `classify_title()` has misclassification issue; produced bad 2022 rows |
| `download_answer_keys_google.py` | DONE | NTA Notice Board + DDG fallback; DRY_RUN=True default |
| `audit_answer_keys.py` | DONE | Read-only gap analysis script |

### exam_papers coverage

Papers in blob + DB for years: **2021, 2022, 2023, 2024, 2025**.
Known data anomalies (do not fix in 1a — note for 1b):
- One 2024 paper (Jan 29) filed under `year=2025`; one 2025 paper (Feb 1) filed under `year=2024`
- Two 2025 rows have "JEE Main 2018" paper names — wrong ingestion
- 2023 Session 1: **zero papers** — double gap (papers + AK both missing); investigate separately

### exam_answer_keys coverage

| Year | Session | blob_url | key_type | Notes |
|------|---------|---------|---------|-------|
| 2021 | Session 1 | present | FINAL | Existing row, not re-validated |
| 2021 | Session 2 | present | FINAL | Existing row, not re-validated |
| 2022 | Session 1 | **DONE** | FINAL | Downloaded this session — CDN URL resolved |
| 2022 | Session 2 | **DONE** | FINAL | Downloaded this session — CDN URL resolved |
| 2023 | Session 2 | present | FINAL | Existing row |
| 2024 | Session 1 | **DONE** | FINAL | `Notice_20240212120843.pdf` — 10 pages, 448 Q IDs |
| 2024 | Session 2 | **DONE** | FINAL | `Notice_20240424132602.pdf` — 10 pages, 451 Q IDs |
| 2025 | Session 1 | **DONE** | FINAL | `Notice_20250210115032.pdf` — 20 pages, 404 Q IDs |
| 2025 | Session 2 | **DONE** | FINAL | Downloaded this session |

### Remaining 1a work

None. All gaps resolved. 1a is complete.

> **Note on 2022 Q ID format:** 2022 AK PDFs use **6-digit sequential IDs** (e.g. `100001`) on most pages,
> not the 10-11 digit NTA format seen in 2024/2025. The validation regex `\b\d{6,}\b` handles both.
> Sub-Module 1b must account for this when building the `jee_answer_mappings` join key.

---

## What Sub-Module 1b Needs to Pick Up

1b is the extraction pipeline: parse AK PDFs → `jee_answer_mappings`; parse question papers → `jee_question_bank`.

### Starting state 1b will receive

- `exam_answer_keys` rows with non-NULL `blob_url` and `extraction_status = 'PENDING'`:
  - 2021 S1, 2021 S2, 2023 S2 (existing rows — not re-validated in 1a)
  - 2022 S1, 2022 S2, 2024 S1, 2024 S2, 2025 S1, 2025 S2 (all confirmed downloaded)
- `exam_papers` rows: years 2021–2025, most with blob_url set

### Key facts for 1b implementation

**AK PDF structure:**
- Multi-column table: 3 pairs of `QUESTION ID | CORRECT OPTION ID` per page
- One PDF per session covers all dates × shifts
- Text-selectable (PyMuPDF works without OCR)
- Page 1 may be header-only (Q IDs start on page 2) — scan all pages

**Q ID format by year** (critical for join key):

| Year | Q ID digits | Option ID digits (MCQ) | Notes |
|------|------------|----------------------|-------|
| 2021 | 10-digit | 11-digit | |
| 2022 | 6-digit sequential (most pages) OR 11-digit NTA (some pages) | varies | Mixed format — handle both |
| 2023 | 10-digit | 11-digit | |
| 2024 | 11-digit | 12-digit | |
| 2025 | 10-digit | 11-digit | |

Integer-type answers are raw numbers (e.g. `18`, `420`) regardless of year.

**Linking mechanism:** No FK between `exam_papers` and `exam_answer_keys`.
The NTA Question ID in the AK PDF is the sole join key to questions in paper PDFs.
Questions with no matching AK entry get `answer_key = NULL` and can be reprocessed.

**Extraction order:** AKs first (`jee_answer_mappings`), then papers (`jee_question_bank`).
This allows immediate answer injection during paper parsing.

**Data anomalies to handle in 1b:**
- Year field mismatches in `exam_papers` (Jan 29, 2024 row has `year=2025`; Feb 1, 2025 row has `year=2024`)
- Two 2025 rows with "JEE Main 2018" paper names — skip or flag
- 2023 Session 1: no papers and no valid AK — skip entirely until investigated

### Tables 1b will write to

```sql
jee_answer_mappings (
    nta_question_id   TEXT PRIMARY KEY,
    correct_option_id TEXT,
    source_key_id     INT REFERENCES exam_answer_keys(id)
)

jee_question_bank (
    id               SERIAL PRIMARY KEY,
    nta_question_id  TEXT,
    exam_paper_id    INT REFERENCES exam_papers(id),
    year             INT,
    dateofexam       DATE,
    shift            TEXT,
    subject          TEXT,
    question_content JSONB,
    answer_key       TEXT   -- NULL if no matching AK entry
)
```

On completion, mark:
- `exam_answer_keys.extraction_status = 'EXTRACTED'`
- `exam_papers.extraction_status = 'EXTRACTED'`

---

## Known Issues Carrying Into 1b

- `classify_title()` in `download_answer_keys.py` is imprecise — non-AK PDFs were inserted for 2022 (ids 3 and 4 are now tombstones with NULL blob_url). Fix the classifier to prevent recurrence when re-running 1a.
- 2023 Session 1: zero papers downloaded AND AK row is a bad notice. Full double gap — do not attempt 1b extraction for this session until both gaps are resolved.
- 2021 Session 3 (Jul) and Session 4 (Aug–Sep): medium-priority AK gaps. Add to `TARGET_SESSIONS` in `download_answer_keys_google.py` before running 1b on 2021 data.

---

## Next Session Plan (2026-03-21)

**M1a is complete.** Next two workstreams start in the next session and can run independently in parallel:

- **M1d — DB Tables** (start next session): Create all 8 new JEE Ascent tables + alter `exam_papers` and `questiondata`. Run DDL from `JEEMainDownloadScripts.sql`; update `apps/functions/prisma/schema.prisma`; confirm `pgvector` extension is available on the Azure PostgreSQL tier before proceeding. See `Design/Architecture/JEEAscentModuleBreakdown.md` for full entry/exit criteria.

- **M2 — NCERT Concept Index** (independent, can run in parallel with M1d): Build relational concept hierarchy + vector embeddings from NCERT chapter PDFs. No dependency on M1d. New pipeline file: `pipelines/JEEAccentPipeline/concept_index_pipeline.py`. Reuses `gemini_client.py` and `blob_client.py`.
