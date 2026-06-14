# Google-Driven Answer Key Download — Implementation Plan

**Date:** 2026-03-20
**Branch:** feature/jeeascent
**Scope:** Download NTA answer key PDFs for 6 high-priority year+session combinations using Google search, validate Q IDs, upload to blob, upsert to DB.

---

## Context

`download_answer_keys.py` scrapes the NTA archive page and uses `classify_title()` to filter rows. This produced bad data for 2022 (provisional notices, not AK PDFs) and missed 2024/2025 entirely. The Google-driven approach (Approach 8, see `SITE_EVALUATION.md`) can surface NTA AK PDFs directly for known sessions and is used here as a targeted gap-filler.

---

## Target Sessions (High Priority Only)

| # | Year | Session | Dates covered | Existing DB row | Action |
|---|------|---------|--------------|-----------------|--------|
| 1 | 2022 | Session 1 (Jun) | Jun 24–30 | id=4, PROVISIONAL, bad title | INSERT FINAL; null-clear id=4 blob_url |
| 2 | 2022 | Session 2 (Jul) | Jul 25–30 | id=3, PROVISIONAL, unverified | INSERT FINAL; null-clear id=3 blob_url |
| 3 | 2024 | Session 1 (Jan-Feb) | Jan 27–Feb 1 | none | INSERT |
| 4 | 2024 | Session 2 (Apr) | Apr 4–9 | none | INSERT |
| 5 | 2025 | Session 1 (Jan) | Jan 22–28 | none | INSERT |
| 6 | 2025 | Session 2 (Apr) | Apr 2–8 | none | INSERT |

---

## Deferred / Out of Scope

| Sessions | Reason |
|----------|--------|
| 2020 Session 1 & 2 | Low priority — predates NTA Q ID system used in Module 1b |
| 2021 Session 3 (Jul) | Medium priority — add to TARGET_SESSIONS after high priority done |
| 2021 Session 4 (Aug–Sep) | Medium priority — same |
| 2021 Aug 3–4 | Investigate first — not a standard NTA session date |
| 2023 Session 1 | Double gap: zero papers AND bad AK row — needs separate investigation (download papers first, then AK) |

---

## Search String Strategy

Search string format depends on year (see `SITE_EVALUATION.md` Approach 8):

| Year | Format | Rationale |
|------|--------|-----------|
| 2022 | `jee main [month] [year] session [N] btech answer key filetype:pdf` | 2022 AKs are on NIC CDN; plain query returns only coaching articles; `filetype:pdf` surfaces CDN direct links |
| 2024 | `jee main [DD month YYYY] shift [N] answer key from nta site` | 2024 AKs on `nta.ac.in/Download/Notice/`; plain date query returns NTA PDF as result #1 |
| 2025 | `jee main [DD month YYYY] shift [N] answer key from nta site` | Likely same as 2024 (confirmed Jan 2025) |

**Per-session search strings (try in order; stop at first valid PDF found):**

```python
TARGET_SESSIONS = [
    {
        "year": 2022, "session": "Session 1", "key_type_expected": "FINAL",
        "search_strings": [
            "jee main june 2022 session 1 btech answer key filetype:pdf",
            "jee main 2022 session 1 btech final answer key filetype:pdf",
        ],
        "replace_row_ids": [4],
    },
    {
        "year": 2022, "session": "Session 2", "key_type_expected": "FINAL",
        "search_strings": [
            "jee main july 2022 session 2 btech answer key filetype:pdf",
            "jee main 2022 session 2 btech final answer key filetype:pdf",
        ],
        "replace_row_ids": [3],
    },
    {
        "year": 2024, "session": "Session 1", "key_type_expected": "FINAL",
        "search_strings": [
            "jee main 31st jan 2024 shift 1 answer key from nta site",
            "jee main 31st jan 2024 shift 2 SET16 answer key from nta site",
            "jee main 2024 session 1 btech answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
    {
        "year": 2024, "session": "Session 2", "key_type_expected": "FINAL",
        "search_strings": [
            "jee main 9th april 2024 shift 1 answer key from nta site",
            "jee main 2024 session 2 btech answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
    {
        "year": 2025, "session": "Session 1", "key_type_expected": "FINAL",
        "search_strings": [
            "jee main 23rd jan 2025 shift 2 answer key from nta site",
            "jee main 2025 session 1 btech answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
    {
        "year": 2025, "session": "Session 2", "key_type_expected": "FINAL",
        "search_strings": [
            "jee main 3rd april 2025 shift 1 answer key from nta site",
            "jee main 2025 session 2 btech answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
]
```

---

## NTA URL Detection Logic

Two sources are scanned per search result page:

### A. AI Overview text
- Google AI Overview sometimes embeds the direct NTA PDF URL in its summary text
- Extract all URLs matching:
  - `https://nta\.ac\.in/Download/Notice/Notice_\d+\.pdf`
  - `https://cdnbbsr\.s3waas\.gov\.in/.+\.pdf`

### B. Top 5 organic results
- Scan result links and their snippets
- Accept a result if **all** of:
  - Domain is `nta.ac.in` OR `cdnbbsr.s3waas.gov.in`
  - URL ends in `.pdf`
  - Snippet or title contains "answer key" (case-insensitive) AND target year
- Priority: `nta.ac.in` domain over NIC CDN (both valid); FINAL over PROVISIONAL

---

## PDF Validation (Lightweight)

After downloading to a temp file, run PyMuPDF (`fitz`) on page 1:

1. Extract text from page 1
2. Check **all** of:
   - `QUESTION ID` or `CORRECT OPTION ID` appears in text
   - At least one numeric string of 10–11 digits is present (`\b\d{10,11}\b`)
   - Text is not empty (rejects image-based PDFs)
3. If validation fails: log as rejected, skip upload and insert, try next candidate URL

This catches notices and non-AK PDFs that slip through domain/filename filtering.

---

## DB Upsert Strategy

### Standard insert (sessions with no existing row)
```sql
INSERT INTO exam_answer_keys (title, year, session, key_type, blob_url, filename)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (year, session, key_type) DO UPDATE
    SET blob_url = EXCLUDED.blob_url, filename = EXCLUDED.filename
    WHERE exam_answer_keys.blob_url IS NULL;
```

### Replace bad 2022 rows (ids 3 and 4)
Before inserting the new FINAL row, null out the bad PROVISIONAL row's blob_url so it is not used by the extraction pipeline:
```sql
UPDATE exam_answer_keys SET blob_url = NULL WHERE id = %s;
```
Then proceed with the standard upsert. The PROVISIONAL row remains in the table (with NULL blob_url) as a record that it existed; the new FINAL row is the authoritative AK for that session.

---

## Script Structure

**File:** `pipelines/DataCollection/download_answer_keys_google.py`

```
download_answer_keys_google.py
│
├── TARGET_SESSIONS  (list of session config dicts, see above)
│
├── get_connection()
│   └── reuse Entra ID token pattern from download_answer_keys.py
│
├── run_google_search(search_str) -> list[str]
│   ├── Playwright: navigate to google.com/search?q=...
│   ├── get_snapshot() — accessibility tree
│   ├── extract_nta_urls_from_ai_overview(snapshot) -> list[str]
│   └── extract_nta_urls_from_organic(snapshot, top_n=5) -> list[str]
│
├── validate_ak_pdf(url, year) -> (valid: bool, local_path: str, page_count: int)
│   ├── download to tempfile via requests.get(stream=True)
│   ├── fitz.open(local_path)
│   ├── page 1 text check:
│   │   ├── has "QUESTION ID" or "CORRECT OPTION ID"
│   │   └── has \b\d{10,11}\b
│   └── return result
│
├── upload_to_blob(local_path, year, filename) -> blob_url
│   └── reuse BlobServiceClient pattern from existing scripts
│
├── null_out_bad_row(conn, row_id)
│   └── UPDATE exam_answer_keys SET blob_url = NULL WHERE id = %s
│
├── upsert_answer_key(conn, title, year, session, key_type, blob_url, filename)
│   └── ON CONFLICT upsert (blob_url IS NULL guard)
│
└── main()
    ├── connect_to_database()
    ├── for each session in TARGET_SESSIONS:
    │   ├── for each search_str:
    │   │   ├── run_google_search(search_str) -> candidate_urls
    │   │   ├── for each url in candidate_urls:
    │   │   │   ├── validate_ak_pdf(url, year)
    │   │   │   ├── if valid: upload_to_blob, null_out_bad_rows, upsert → break
    │   │   │   └── else: log rejection reason
    │   │   └── if found: break to next session
    │   └── log: FOUND / NOT FOUND
    └── print final summary table
```

---

## Blob Storage Path

Consistent with existing convention:
```
jeedata/answer_keys/{year}/{filename}
```
where `filename` = last path segment of the NTA PDF URL (e.g. `Notice_20240212120843.pdf` or `2023042948.pdf`).

---

## Dependencies

All already available in the environment:
- `playwright` (Playwright MCP or `playwright` Python package for headless)
- `requests` (PDF download)
- `fitz` / `pymupdf` (PDF validation)
- `psycopg2` (DB)
- `azure-identity` (Entra ID token)
- `azure-storage-blob` (blob upload)

> **Note:** The search step uses Playwright in headless mode (not the Playwright MCP). This allows the script to run unattended without a GUI browser. Use `playwright install chromium` if not already installed.

---

## Logging / Output

Each session logs one of:
- `[OK] 2024 Session 1 — found Notice_20240212120843.pdf, 10 pages, uploaded, inserted`
- `[SKIP] 2024 Session 1 — already has blob_url, skipping`
- `[FAIL] 2025 Session 2 — no valid NTA PDF found across 2 search strings`
- `[REJECT] url X — page 1 failed validation (no Q IDs found)`

Final summary: table of year | session | result | blob_url.

---

## What This Script Does NOT Do

- Does not delete any existing `exam_answer_keys` rows (only nulls `blob_url` for ids 3 and 4)
- Does not touch `exam_papers`
- Does not run extraction (Sub-Module 1c is separate)
- Does not handle medium-priority 2021 sessions (extend `TARGET_SESSIONS` when ready)
- Does not handle 2023 Session 1 double gap (separate investigation needed)
