# Answer Key Download — Run Report

**Date:** 2026-03-21
**Script:** `download_answer_keys_google.py`
**Branch:** `feature/jeeascent`

---

## Step 3 — Dry Run Results

**Mode:** `DRY_RUN = True` (no writes)
**Architecture:** NTA Notice Board Archive (primary) + DuckDuckGo HTML (2022/2023 fallback)

| Session | Status | PDF | Pages | First Q ID | Source |
|---------|--------|-----|-------|-----------|--------|
| 2022 Session 1 (Jun 24-30) | VALIDATION_FAILED | `Notice_20220703210359.pdf` | 2 | — | NTA notice board |
| 2022 Session 2 (Jul 25-30) | NOT_FOUND | — | — | — | — |
| 2024 Session 1 (Jan 27-Feb 1) | DRY_RUN_VALID | `Notice_20240212120843.pdf` | 10 | 5335431363 | NTA notice board |
| 2024 Session 2 (Apr 4-9) | DRY_RUN_VALID | `Notice_20240424132602.pdf` | 10 | 87827055428 | NTA notice board |
| 2025 Session 1 (Jan 22-28) | DRY_RUN_VALID | `Notice_20250210115032.pdf` | 20 | 6564451001 | NTA notice board |
| 2025 Session 2 (Apr 2-8) | NOT_FOUND | — | — | — | — |

### Dry Run Findings

**2022 S1 — VALIDATION_FAILED:**
The NTA Notice Board has two 2022 Session 1 entries but both are announcements
(extension of provisional AK display period), not AK tables. Page 1 text starts
with NTA letterhead in Hindi/English — no `QUESTION ID` header present.
The real 2022 AK is on NIC CDN (`cdnbbsr.s3waas.gov.in`). DDG surfaces CDN URLs
only when "cdnbbsr" is included in the query, and results are inconsistent.

**2022 S2 — NOT_FOUND:**
No matching entries on NTA Notice Board. DDG returned no CDN URLs.
During out-of-script testing, DDG did surface `2022080776.pdf` (11 pages,
confirmed B.Tech AK with 6-digit sequential Q IDs starting at 100001).
DDG inconsistency is a known issue; requires reliable CDN URL source.

**2025 S2 — NOT_FOUND:**
NTA Notice Board has only `Notice_20250412003547` (provisional B.Tech AK,
image-based, 2 pages, 0 extractable Q IDs). No FINAL B.Tech AK found
in archive as of March 2026. Awaiting NTA publication.

---

## Step 4 — Live Run Results

**Mode:** `DRY_RUN = False` (live writes enabled)
**Sessions processed:** 2024 S1, 2024 S2, 2025 S1 only
**Runner:** `_run_live_3sessions.py` (temp script, deleted after use)

| Session | DB status | Blob path | Pages | Q IDs (page 1) |
|---------|-----------|-----------|-------|----------------|
| 2024 Session 1 | INSERTED (1 row) | `jeedata/answer_keys/2024/Notice_20240212120843.pdf` | 10 | 448 |
| 2024 Session 2 | INSERTED (1 row) | `jeedata/answer_keys/2024/Notice_20240424132602.pdf` | 10 | 451 |
| 2025 Session 1 | INSERTED (1 row) | `jeedata/answer_keys/2025/Notice_20250210115032.pdf` | 20 | 404 |

**Sample Q IDs confirmed:**
- 2024 S1: `5335431363`, `5335431368`, `5335431370` (11-digit NTA format)
- 2024 S2: `87827055428`, `87827055429`, `87827055430` (11-digit NTA format)
- 2025 S1: `6564451001`, `6564451007`, `6564451009` (10-digit NTA format)

**Note:** 2025 S1 has a header-only page 1 (date header, no Q IDs). Q IDs begin
on page 2. The 3-page scan in `validate_ak_pdf()` handles this correctly.

**Post-run blob fix:** Initial upload used temp filenames (`tmprXXXX.pdf`).
Repair script re-uploaded with correct NTA filenames, updated DB blob_url,
and deleted the temp-named blobs. Final DB rows are clean.

---

## DB State After Step 4

`exam_answer_keys` rows with non-NULL blob_url:

| id | year | session | key_type | filename |
|----|------|---------|---------|---------|
| (new) | 2024 | Session 1 | FINAL | Notice_20240212120843.pdf |
| (new) | 2024 | Session 2 | FINAL | Notice_20240424132602.pdf |
| (new) | 2025 | Session 1 | FINAL | Notice_20250210115032.pdf |

Existing rows 3 and 4 (2022 PROVISIONAL bad rows) are **unchanged** —
`blob_url` will be nulled only when the 2022 FINAL CDN URLs are obtained
and inserted.

---

## Remaining Work

| Session | Issue | Required action |
|---------|-------|----------------|
| 2022 Session 1 | CDN URL not reliably found via DDG | Manually retrieve CDN URL from `jeemain.nta.nic.in` archive page or NIC CDN listing; hardcode as `known_urls` in script config |
| 2022 Session 2 | Same as above | Same approach |
| 2025 Session 2 | No FINAL B.Tech AK published by NTA | Re-run after NTA publishes; provisional notice exists but is image-based |

**Not in scope:**
- 2021 Sessions 3 & 4 (medium priority — extend `TARGET_SESSIONS` when ready)
- 2023 Session 1 (double gap — papers missing too; investigate separately)
- 2020 sessions (predates NTA Q ID system)
