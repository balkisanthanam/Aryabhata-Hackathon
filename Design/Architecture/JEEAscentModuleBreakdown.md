> ⛔ SUPERSEDED (status only) — live status in GitHub Projects (project 2 / view 11).
> The module *design* prose below is still useful reference; the **status fields are stale**
> (e.g. M4 "In Progress" — since shipped) and predate the M3 pipeline integration.

# JEE Ascent — Module Breakdown

> Generated: 2026-03-21 · Last updated: 2026-04-21
> Source of truth: `JEEAccentArchitecture.md` + `pipelines/DataCollection/CLAUDE.md`

---

## MVP Status (2026-04-21)

**2024-only MVP merged to master and deployed.** E2E validation complete across all three subjects (Chemistry Bonding, Physics Kinetic Theory, Maths Complex Numbers). Three fixes landed this cycle: Section B (Integer) input control, markdown pipe-table rendering, and a LaTeX-escape data repair (7 rows). Remaining gaps (189 figure-blob rows, 1 bilingual Hindi row, 10 image+text residuals) are parked as Known Issues and do not block demo. 2023 corpus is parked wholesale pending re-extraction post-MVP (KI-2: hallucinated NTA IDs).

**Commits of record:** `aa8011c` (MVP E2E fixes) + `55386fc` (QA rounds 1–5 tooling + dedup) on `feature/jeeascent` → merged to `master`.

**Active work:** M4 Solution Generator is running in a **parallel CLI session** (2026-04-21+). All other modules idle; come back here post-M4 to close the remaining parked items.

---

## Module Status Summary

| Module | Name | Status | Complexity |
|--------|------|--------|------------|
| M0 | Data Discovery & Audit | **Done** | Simple |
| M1a | JEE Papers — Download | **Done** (gaps remain) | Medium |
| M1b | JEE Papers — Extraction | **2024 done (1,504 post-dedup, E2E-validated); 2023/2021/2022/2025 parked post-MVP** | Complex |
| M1c | Step-up Problems — Sourcing | **Deferred — Phase 2** | Complex |
| M1d | DB Tables (JEE Ascent) | **Done** | Simple |
| M2 | NCERT Concept Index | **Done** ✓ (M2 Patch complete 2026-04-01) | Complex |
| M3 | Question Tagger | **2024 fully tagged (1,504 rows); 2023 parked post-MVP (KI-2)** | Complex |
| M4 | Solution Generator | **In Progress — parallel CLI session (2026-04-21)** | Medium |
| M5 | Question Generator | **Deferred — Phase 2** | Complex |
| M6 | Progression Engine | **Done (light)** — logic embedded in M7 endpoints | Medium |
| M7 | API Layer | **Done** — 4 endpoints live (`accentSession`, `accentQuestion`, `accentProgress`, `accentChapterMap`) | Medium |
| M8 | Frontend UX | **Done + Demo-ready** — `AccentSession.tsx` implemented + deployed | Medium |

---

## Detailed Module Breakdown

---

### Module 0: Data Discovery & Audit

**What it does:** Locates and normalises all existing JEE Main data across local disk, Azure Blob (`kalidasa`, `stevaluationstorage`), spreadsheets, and JSON. Classifies each artifact, maps to M1 schema, documents gaps by year/session/subject.

**Inputs:** Local disk, Azure Blob containers, DB `exam_papers` table
**Outputs:** `Data/JEEAudit.md` — inventory with status per source
**Dependencies:** None
**Complexity:** Simple
**Status:** **Done** — covered by `audit_answer_keys.py` output + DataCollection CLAUDE.md gap analysis

---

### Module 1a: JEE Papers — Download

**What it does:** Downloads JEE Main B.Tech question paper PDFs and answer key PDFs from the NTA website. Uploads to Azure Blob at `jeedata/{year}/{filename}` and `jeedata/answer_keys/{year}/{filename}`. Records metadata in `exam_papers` and `exam_answer_keys`.

**Inputs:** NTA website (`jeemain.nta.nic.in`), NTA Notice Board, CDN links
**Outputs:**
- `exam_papers` rows (2021–2025) with `blob_url` set
- `exam_answer_keys` rows with `blob_url` set

**Dependencies:** None (standalone)
**Complexity:** Medium
**Status:** **Done with known gaps**

Known remaining gaps (do before starting M1b on these sessions):

| Gap | Root Cause | Action |
|-----|-----------|--------|
| 2022 S1 AK | FINAL AK on NIC CDN, not NTA Notice Board | Manually retrieve CDN URL from jeemain.nta.nic.in archive; add to `known_cdn_urls` in `download_answer_keys_google.py`; re-run live |
| 2022 S2 AK | Same — confirmed PDF exists (`2022080776.pdf`) | Same approach |
| 2025 S2 AK | NTA has not published FINAL B.Tech AK as of Mar 2026 (Provisional is image-based) | Monitor NTA; re-run after publication |
| 2023 S1 papers | Zero papers downloaded — root cause unknown | Investigate separately before starting M1b for 2023 S1 |

**Scripts:** `download_exam_papers.py`, `download_answer_keys.py`, `download_answer_keys_google.py`, `audit_answer_keys.py`

---

### Module 1b: JEE Papers — Extraction

**What it does:** Parses downloaded PDFs to populate the JEE question bank.

Two-step extraction order (AKs first, then papers):

1. **Step 1 — Extract answer keys:** Parse each `exam_answer_keys` PDF → populate `jee_answer_mappings (nta_question_id PK, correct_option_id, source_key_id FK)`. Mark `exam_answer_keys.extraction_status = 'EXTRACTED'`.
2. **Step 2 — Extract questions:** Parse each `exam_papers` PDF → write to `jee_question_bank`. Mark `exam_papers.extraction_status = 'EXTRACTED'`.

**Inputs:**
- `exam_answer_keys` rows with non-NULL `blob_url` and `extraction_status = 'PENDING'`
- `exam_papers` rows with non-NULL `blob_url` and `extraction_status = 'PENDING'`

**Outputs:**
- `jee_answer_mappings` table populated
- `jee_question_bank` populated with per-question JSON (NTA IDs, answer key, subject, section, tier=3)
- Figure image crops uploaded to Azure Blob

**Dependencies:** M1a (papers + AKs downloaded), M1d (DB tables created)
**Complexity:** Complex

---

#### Two Extraction Pipelines

Both live in `pipelines/JEEAscentPipeline/`. They are independent — no shared state, separate checkpoint prefixes.

| Pipeline | Entry point | How it works | Speed | Use when |
|----------|------------|--------------|-------|----------|
| **Crop pipeline** | `jee_crop_pipeline.py` | Scans PDF text layer for NTA IDs → crops per-question image → Gemini Flash transcribes each crop (4 concurrent workers) | ~7 min/paper | Standard case: PDF has a text layer (2021+). Default choice. |
| **Pro pipeline** | `jee_extraction_pipeline.py` | Sends full PDF to Gemini Pro → parses 90-question JSON in one call | ~10–15 min/paper | Image-only PDFs (no text layer); or as fallback when crop pipeline fails |

**Decision rule:** Run `python jee_crop_pipeline.py --paper-ids <id> --render-only` first. If it reports `0 NTA IDs found`, the PDF is image-only → use the Pro pipeline instead.

Key implementation notes:
- AK PDFs: multi-column table, 3 pairs of `QUESTION ID | CORRECT OPTION ID` per page; text-selectable (PyMuPDF, no OCR)
- Q ID format varies by year (10-digit 2021/2023/2025, 11-digit 2022/2024, 6-digit sequential also seen in 2022)
- NTA ID filter: span must contain the keyword "Question" — required to exclude option IDs which also appear in the text layer (especially 2023 papers)
- 2023 S1: skip entirely — both papers and AK are missing
- Data anomalies: one 2024 paper filed under `year=2025` and vice versa; two 2025 rows with wrong paper names — skip/flag
- Figure crop + blob upload deferred to Phase 2; Phase 1 sets `has_figure=true` + text description only

**Reuses:** `gemini_client.py`, `blob_client.py`, `config.py` from `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/`

---

#### Current Status (parked 2026-04-05)

**Status: Parked** — sufficient data in DB to validate the full E2E feature (M3→M8). Will resume after E2E is working and architecture is confirmed.

**What is done:**
- Crop pipeline written, tested, and cross-year validated (2021/2023/2024/2025 formats all confirmed working)
- Pro pipeline written and tested
- Answer keys extracted for all available sessions (2021 S1/S2, 2023 S2, 2024 S1/S2, 2025 S1)
- **2024: 34 of 38 papers EXTRACTED** → ~3,060 questions in `jee_question_bank` (enough for M3–M8 validation)

**What is parked:**

| Remaining work | Reason parked | Resume action |
|----------------|--------------|---------------|
| 4 image-only 2024 papers (IDs 6, 7, 8, 9 — dates 2024-04-04/05) | PDF has no text layer; crop pipeline returns 0 IDs | Use Pro pipeline: `python jee_extraction_pipeline.py --paper-ids 6,7,8,9` |
| 2021 full run | Render validated (paper 208 = 90 crops ✓); not yet run | `python jee_crop_pipeline.py --year 2021` |
| 2022 full run | No matching AKs in DB (AK source_key_id range mismatch) | Fix M1a gaps for 2022 AKs first, then run |
| 2023 full run | AKs downloaded but NTA ID ranges don't match 2023 papers; need correct AK files | Fix M1a 2023 AK download, then run |
| 2025 full run | Render validated (paper 165 = 75 crops ✓); not yet run | `python jee_crop_pipeline.py --year 2025` |

**Known data quality issues (found 2026-04-06):**

| Issue | Scope | Impact | Fix |
|-------|-------|--------|-----|
| **Subject rotation** — crop pipeline assigns subjects by question-number position (1–30=Physics, 31–60=Chemistry, 61–90=Mathematics) but most NTA PDFs order subjects as Maths→Physics→Chemistry | 12 of 13 extracted 2024 papers + 1 of 2025 papers affected (only 2024-04-08 shift 2 was correct) | All 90 questions per paper get wrong subject labels | Fixed via `subject_auditor.py` — LLM-verified + cyclic UPDATE applied. Root cause: `assign_subject_section()` in `jee_crop_pipeline.py:406` assumes fixed ordering. Must be fixed before extracting remaining years. |
| **LLM reasoning leaked into `raw_text`** — Gemini Flash "thinks out loud" during crop transcription, injecting phrases like "Wait, let me look at the second option again" into question text | 47 of 1,160 questions (~4.4%) — evenly spread across subjects (Physics 17, Chemistry 16, Mathematics 14) | Polluted question text; does not block concept tagging but makes questions unreadable in UI | Low priority — cosmetic. Consider post-processing cleanup or re-extraction with stricter prompt when resuming M1b. |

**Resume condition:** After the E2E feature (M3 → M8) is working end-to-end and architecture is confirmed. No M3–M8 design decisions depend on having all years extracted.

---

### Module 1c: Step-up Problems — Sourcing (Tier 2)

**What it does:** Populates `jee_question_bank` with Tier 2 (Step-up) problems — intermediate difficulty problems bridging NCERT exercises and JEE Main. Sources include coaching institute open question banks (scrape where permitted), hand-curated problems, and LLM-generated variants from Module 5 to fill gaps.

**Inputs:** External sources (Resonance, Allen open banks), Module 5 output
**Outputs:** `jee_question_bank` rows with `tier=2`, `source='STEP_UP_SCRAPED'` or `'GENERATED'`
**Dependencies:** M1d (DB tables), M5 (for generated fill-ins)
**Complexity:** Complex (scraping + curation + integration)
**Status:** Not started

Note: This is lower priority than M1b. Start M1b first (Tier 3 JEE Main questions), then M1c.

---

### Module 1d: DB Tables (JEE Ascent)

**What it does:** Creates or migrates all new database tables required for JEE Ascent. Also enhances existing tables.

**New tables (8 total):**
- `jee_question_papers` — paper metadata (links to `exam_papers`)
- `jee_question_bank` — all non-NCERT questions (Tier 2/3/4)
- `jee_answer_mappings` — NTA question ID → correct option ID (extraction join key)
- `jee_question_tags` — question ↔ NCERT concept (many-to-many)
- `jee_question_embeddings` — 768-dim vectors for lateral jump + RAG
- `ncert_concept_hierarchy` — relational concept tree with `embedding_text`
- `ncert_concept_embeddings` — 768-dim vectors per concept (HNSW index)
- `user_accent_progress` — per-user per-chapter tier + confidence state
- `user_accent_attempts` — individual attempt records (time, skip)

**Existing table modifications:**
- `exam_papers`: add `blob_url`, `paper_format`, `extraction_status`
- `questiondata`: add `jee_similar_question_id`, `jee_similarity_score`
- Enable `pgvector` extension on PostgreSQL

**Inputs:** None
**Outputs:** Tables live in PostgreSQL; DDL in `Scripts/DB_Master.sql` + `apps/functions/prisma/schema.prisma`
**Dependencies:** None (prerequisite for all other modules)
**Complexity:** Simple
**Status:** **Done** — all 9 new tables created, pgvector + ltree extensions active, Prisma schema updated and generating clean.

**Design note:** `questiondata.jee_similar_question_id` / `jee_similarity_score` columns (per original exit criteria) were replaced by the `ncert_jee_similarity` join table. Same data, better normalisation. M3 writes to `ncert_jee_similarity` instead.

---

### Module 2: NCERT Concept Index

**What it does:** Builds a hierarchical + vector-searchable index of NCERT concepts. Each concept gets two representations: raw LaTeX (`key_formulas`) for UI rendering, and `embedding_text` (plain-language description) for embedding. Vectors stored with HNSW index in `ncert_concept_embeddings`.

**Why `embedding_text` is mandatory:** Embedding models tokenise LaTeX as raw characters — `\frac{a}{b}` and a verbal description produce near-zero cosine similarity. Every concept must be described in plain English for the vector to be meaningful.

**Pipeline steps (`concept_index_pipeline.py`):**
1. Iterate `chapterdata` rows (~74 chapters)
2. Fetch PDF from blob → cache with Gemini → extract concept hierarchy (with `embedding_text` + `ncert_solved_example`)
3. UPSERT into `ncert_concept_hierarchy`
4. Construct `embed_text = concept_title + embedding_text + ncert_solved_example`; call `text-embedding-005`
5. UPSERT into `ncert_concept_embeddings`
6. Checkpoint per chapter (resumable)

**Search strategy:** Hybrid — pgvector ANN (top-20 candidates) + BM25 re-rank on `embedding_text`. Final score: `0.7 × (1 − vec_dist) + 0.3 × bm25_score`.

**Inputs:** NCERT PDF blob URLs from `chapterdata.pdffileurl`
**Outputs:**
- `ncert_concept_hierarchy` (~2,200 rows across 74 chapters)
- `ncert_concept_embeddings` (~2,200 vectors, 768-dim, HNSW-indexed)

**Dependencies:** M1d (tables created), `pgvector` extension enabled
**Complexity:** Complex
**Status:** **Done** — M2 Patch complete 2026-04-01. 2,432 nodes + 46 `data_table` nodes across 13 chapters. All three design-review gaps resolved.

**Completed:**
- Full run for all 74 chapters (Class 11 + Class 12, Physics / Chemistry / Maths)
- `ncert_concept_hierarchy` (2,432 nodes) + `ncert_concept_embeddings` fully populated
- HNSW index + BM25 GIN index built

**M2 Patch (2026-04-01) — all gaps closed:**
1. **`data_table` content type** — Added to CHECK constraint, `VALID_CONTENT_TYPES`, and system prompt. 13 chapters re-extracted; 46 `data_table` nodes live (electrode potentials, bond enthalpies, ionic radii, physical constants, solubility tables, etc.).
2. **BM25 enriched** — `fn_ncert_concept_tsv()` now concatenates `concept_title + chunk_text + description + embedding_text`. All 2,432 rows backfilled via trigger. GIN index rebuilt automatically.
3. **`embed_text` audit column** — Added to `ncert_concept_embeddings`. Column exists in DB; pipeline population is P2 (not yet wired in `concept_index_pipeline.py`).

**Pipeline resilience fix (2026-04-01):**
- `gemini_client.py` `generate_with_cache`: catches server-side cache expiry (400) and request timeouts → evicts stale local cache entry → re-ingests PDF → retries once automatically.
- Default per-attempt timeout reduced from 1800s → 600s (`CONCEPT_INDEX_API_TIMEOUT_SECONDS`).

**Known P2 items (non-blocking for M3):**
- `embed_text` column not yet populated by pipeline
- ~4 chapters originally targeted for re-extraction (Surface Chemistry, p-Block, Polymers, Nuclear Chemistry) not found in `chapterdata` — verify chapter IDs if coverage needs to extend

**M2 Patch work:**
- Part A (DB migration): `data_table` in CHECK constraint; enriched trigger + backfill; `embed_text` column — `Scripts/JEEAscent_DB_Migration.sql` + `pipelines/ConceptIndex/m2_patch_live_db.sql`
- Part B (pipeline): `data_table` in `VALID_CONTENT_TYPES` (`gemini_extractor.py`); prompt updated; 13 chapters re-extracted

**Reuses:** `gemini_client.py`, `blob_client.py`
**New files:** `pipelines/ConceptIndex/concept_index_pipeline.py`, `gemini_extractor.py`, `db_writer.py`

---

### Module 3: Question Tagger

**What it does:** Assigns NCERT concept links, difficulty level, and pattern label to every question in `jee_question_bank`. Also detects JEE-proximity for existing NCERT questions in `questiondata` (powers the lateral-jump indicator in `PracticeSession`).

**Steps per question:**
1. Generate plain-text `embed_text` for the JEE question (Gemini: "describe this question verbally")
2. Embed with `text-embedding-005`
3. Hybrid vector + BM25 search → top-3 NCERT concept matches → populate `jee_question_tags`
4. LLM batch call (difficulty + pattern label combined) → update `jee_question_bank`
5. NCERT proximity detection: embed each NCERT question, search `jee_question_embeddings`, flag `questiondata.jee_similar_question_id` where score ≥ 0.85

**Inputs:**
- `jee_question_bank` (all questions, post-M1b)
- `ncert_concept_hierarchy` + `ncert_concept_embeddings` (post-M2)
- `questiondata` (existing NCERT questions)

**Outputs:**
- `jee_question_tags` (concept links per question)
- `jee_question_embeddings` (vectors per JEE question)
- `jee_question_bank.difficulty`, `.difficulty_confidence`, `.pattern_label` updated
- `questiondata.jee_similar_question_id`, `.jee_similarity_score` populated for matching NCERT questions

**Dependencies:** M1b (questions in bank), M1d (tables), M2 (concept index ready)
**Complexity:** Complex
**Status:** **2024 fully tagged** (2026-04-14); 2023 not started

**Corpus tagged:**
- 2024 Mathematics: 2,290 / 2,290 ✓
- 2024 Chemistry:   2,088 / 2,088 ✓
- 2024 Physics:     2,045 / 2,045 ✓
- 2023 Mathematics: 0 / 360
- 2023 Chemistry:   0 / 360
- 2023 Physics:     0 / 360

**Validation state (from earlier spot-check):**
- Partial manual review: 33 of 63 tag pairs on 1 Maths paper (2024-01-27 shift 1) → 84.8% accuracy
- High-score tags (≥0.9): 100% reliable in sample
- Low-score tags (0.5–0.7): noisier; NCERT "example" content_type nodes produced most false positives
- No missed primary concepts observed

**Open validation items (non-blocking for E2E):**
- Systematic spot-check across Physics + Chemistry
- Decide whether to raise `similarity_score` threshold from 0.5 → 0.6
- Decide whether to filter `content_type = 'example'` nodes from vocabulary

**Approach (as implemented):**
- Hybrid mode (default): pgvector top-K retrieval per batch → Gemini Flash tags against reduced candidate set
- Full mode fallback (`--mode full --batch-size 1`): sends entire subject vocabulary; used for ~10–15% of questions that persistently hallucinate sequential IDs in hybrid mode
- `text-embedding-004` (768-dim) for question vectors via `embed_texts_batch()`
- 4 concurrent workers (`ThreadPoolExecutor`) + `ThreadedConnectionPool` for DB

**Performance notes (2026-04-14):**
- `ThreadedConnectionPool` replaces per-call `psycopg2.connect()` — eliminates Entra auth overhead
- `max_output_tokens` reduced 32768 → 8192 — eliminates Flash latency from oversized ceiling
- Full mode with batch-size 1 is the proven fix for persistent hybrid failures (0 failed batches)

**Reuses:** `gemini_client.py`, `gemini_extractor.embed_texts_batch()`, `db_writer.py` (extended)
**New files:** `pipelines/JEEAscentPipeline/question_tagger.py`, `prompts/question_tagger_system.txt`, `prompts/question_tagger_user.txt`

**To run:**
```bash
cd pipelines/JEEAscentPipeline
# Step 1 — Standard hybrid run (handles ~85-90%)
python question_tagger.py --year 2023

# Step 2 — Fallback for persistent hybrid failures (hallucinated IDs 1,2,3...)
python question_tagger.py --subject Mathematics --year 2023 --mode full --batch-size 1
python question_tagger.py --subject Chemistry --year 2023 --mode full --batch-size 1
python question_tagger.py --subject Physics --year 2023 --mode full --batch-size 1
```

---

### Module 4: Solution Generator

**What it does:** Pre-generates step-by-step solutions for all `jee_question_bank` questions. Uses focused vector context (top-3 NCERT concept chunks, ~4,500 tokens) instead of full chapter PDFs, achieving ~95% token reduction and ~20× cost saving.

**Context construction per question:**
1. Retrieve top-3 concept chunks via `jee_question_tags` + `ncert_concept_hierarchy`
2. Build context string: `concept_title + description + key_formulas_plain_text + ncert_solved_example` × 3
3. Prompt `SolverEngine.generate()` with focused context + question + answer key

**Solution JSON schema** (must match `questiondata.solution` for frontend compatibility):
```json
{
  "steps": [{ "step_number", "step_type", "hint", "explanation", "formula" }],
  "final_answer": "...",
  "visual_needed": { "required", "type", "description", "smiles" }
}
```

Field names `hint` and `formula` are exact — do not rename.

**Inputs:**
- `jee_question_bank` rows without solutions
- `jee_question_tags` + `ncert_concept_hierarchy` (concept context)

**Outputs:** `jee_question_bank.solution` JSONB updated for all questions

**Dependencies:** M1b (questions exist), M2 (concept index), M3 (tags link questions to concepts)
**Complexity:** Medium
**Status:** **In Progress** — running in a parallel CLI session (started 2026-04-21 after 2024-only MVP shipped). This session (feature/jeeascent E2E validator) is paused; resume here for M4 close-out + remaining parked items once the parallel session lands solutions for 2024.

**Reuses:** `solver_engine.py`, `tutor_prompt.md`, `gemini_client.py`
**New file:** `pipelines/JEEAccentPipeline/jee_solution_pipeline.py`

---

### Module 5: Question Generator

**What it does:** Generates additional questions to fill concept × difficulty × tier coverage gaps (< 5 questions for a given combination). Uses RAG + few-shot with Gemini Pro (Phase 1). Applies a 3-layer quality gate.

**Pipeline steps:**
1. Coverage gap analysis: `SELECT concept_id, difficulty, tier, COUNT(*) FROM jee_question_tags GROUP BY ...`
2. For each gap: retrieve top-3 similar existing questions via `jee_question_embeddings` (RAG examples)
3. Prompt Gemini: generate new question with concept context + RAG examples
4. Quality rubric (Layer 1 — automated): novelty check (cosine < 0.85), correctness re-solve, difficulty re-classify, ambiguity check, clarity score
5. Score ≥ 0.90 → auto-accept; 0.75–0.90 → `PENDING_REVIEW` for human queue; < 0.75 → discard
6. INSERT with `is_generated=true`; run M3 tagging on newly generated questions

**Layer 2 — Human review queue:** Admin-only Azure Functions endpoint + minimal React table view. Actions: Approve / Reject / Edit-then-Approve.

**Layer 3 — Student performance signal (post-Phase 3):** Weekly job flags questions with `skip_rate > 0.6` or `avg_time < 30s` for re-review.

**Phase 2 fine-tuning trigger:** ≥ 500 verified examples + measurable failure mode. Not before.

**Inputs:**
- `jee_question_bank` + `jee_question_embeddings` (existing questions for RAG)
- `ncert_concept_hierarchy` (concept context + formulas)
- Coverage gap query results

**Outputs:**
- New rows in `jee_question_bank` (`is_generated=true`, `review_status` set)
- Admin review queue populated

**Dependencies:** M1b (existing questions for RAG), M2 (concept context), M3 (tags + embeddings for gap analysis and novelty check)
**Complexity:** Complex
**Status:** Not started

**Reuses:** `gemini_client.py`, pgvector hybrid search
**New file:** `pipelines/JEEAccentPipeline/jee_qgen_pipeline.py`

---

### Module 6: Progression Engine

**What it does:** Tracks per-user, per-chapter tier progress. Computes confidence score from attempt data. Triggers tier-advance nudge when `confidence ≥ 0.70 AND attempts ≥ 5`.

**Confidence heuristic:**
```
confidence = 0.5 × (questions_attempted / questions_in_tier)
           + 0.3 × (1 − skip_rate)
           + 0.2 × avg_time_factor
```

**Logic location:** Query-time computation inside `GET /api/accent/status`. Reads from `user_accent_attempts`, writes to `user_accent_progress`.

**Lateral jump logic (query-time):** When student is on a NCERT question in `PracticeSession` and `questiondata.jee_similar_question_id IS NOT NULL`, the API response includes the JEE question reference. Frontend shows a JEE badge on the exercise navigator chip and a dismissible banner within the question card.

**Inputs:**
- `user_accent_attempts` (attempt records, time spent, skip flags)
- `user_accent_progress` (current tier per user/chapter)
- `jee_question_bank` (questions available per tier)

**Outputs:**
- `user_accent_progress` updated on tier advance
- Nudge flag in API response
- Tier-advance confirmation: `user_accent_progress.current_tier` incremented, next tier unlocked

**Dependencies:** M1d (tables), M7 (integrated into API layer — these are co-implemented)
**Complexity:** Medium
**Status:** Not started

---

### Module 7: API Layer (Azure Functions v4)

**What it does:** Exposes all JEE Ascent functionality as REST endpoints. Follows all existing Azure Functions patterns (`cors.ts`, `prisma.ts`, `azure-storage.ts`, `session.config.ts`). SAS tokens injected server-side on all image URLs.

**New endpoints (6):**

| Method | Endpoint | Purpose |
|--------|---------|---------|
| GET | `/api/accent/session` | Next N questions for user+chapter+tier; SAS-signed image URLs |
| GET | `/api/accent/question/{id}` | Single question with SAS-signed images |
| POST | `/api/accent/progress` | Record attempt (time_spent, was_skipped) |
| GET | `/api/accent/status` | Current tier + confidence + nudge eligibility |
| POST | `/api/accent/advance-tier` | User confirms tier advancement |
| GET | `/api/accent/chapter-map` | Chapters with JEE Ascent content + user tier per chapter |

**Inputs:** HTTP requests from frontend + DB (via Prisma)
**Outputs:** JSON responses (questions, progress, tier status)
**Dependencies:** M1b (questions in DB), M3 (tags, difficulty, pattern), M4 (solutions), M6 (progression logic), M1d (Prisma schema updated)
**Complexity:** Medium
**Status:** Not started

**New files:** `apps/functions/src/functions/accent*.ts` (one file per endpoint)

---

### Module 8: Frontend UX

**What it does:** Wires the student-facing JEE Ascent experience into the existing React app. No separate dashboard — entry is the existing "JEE Ascent" button on each chapter card in `PracticeDashboard`.

**New page — `AccentSession.tsx` (`/accent/:chapterId`):**
- Tier progress bar (colour-coded: emerald=Tier2, amber=Tier3, rose=Tier4)
- Single-question card (same layout as `PracticeSession`)
- Prev/next navigation within tier
- Solution accordion (reuse existing component — no new rendering code)
- Nudge modal (slides up at confidence threshold): "Ready to try JEE Main questions?" → Yes / Not yet
- Back button → `PracticeDashboard`

**Changes to existing `PracticeSession.tsx`:**
1. Check each question chip for `jee_similar_question_id IS NOT NULL`
2. Render a small JEE badge icon on matching chips in the exercise navigator
3. Show dismissible JEE proximity banner within question card
4. Lateral jump modal: fetch JEE question via `/api/accent/question/{id}`, display read-only with solution

**`PracticeDashboard.tsx`:** Chapter card shows tier badge ("Tier 2 — NCERT+") on the existing JEE Ascent button.

**Inputs:** API responses from M7 endpoints
**Outputs:** Rendered UI
**Dependencies:** M7 (all API endpoints live)
**Complexity:** Medium
**Status:** Not started (JEE Ascent button already visible in `PracticeDashboard` UI — entry point exists; session page not built)

---

## Parallel vs. Sequential Execution

```
M0  ──────────────────────────────────────────────────────► Done
M1d ──────────────────────────────────────────────────────► Prerequisite for everything below

        ┌── M1a (Download) ──► M1b (Extraction) ──► M3 ──┐
        │                                                  ├──► M4 ──┐
        │                                                  │         ├──► M6 ──► M7 ──► M8
        │                                                  ├──► M5 ──┘
        └── M2 (Concept Index) ────────────────────────────┘

        M1c (Step-up sourcing)  ──► M3 (for Tier 2 tagging)  [lower priority, runs after M1b]
```

**Can run in parallel:**
- M1a and M2 are independent — both can run simultaneously
- M3 and M4 both depend on M1b + M2, but M3 must finish before M4 starts (M4 needs tags)
- M5 depends on M3 completing (needs embeddings and tags for gap analysis + novelty check)
- M6 and M7 are co-implemented (M6 logic lives inside M7 endpoints)
- M1c can start independently once M1d tables exist; its outputs feed into M3/M4/M5 like any other question source

**Must be sequential:**
- M1d → everything else (tables must exist first)
- M1a → M1b (papers must be downloaded before extraction)
- M1b → M3 (questions must exist before tagging)
- M2 → M3 (concept index must exist for hybrid search)
- M3 → M4 (tags must exist for focused context retrieval)
- M3 → M5 (embeddings + tags needed for gap analysis and novelty check)
- M7 → M8 (API must be live before frontend can be wired)

**Recommended build order:**
1. M1d (DB tables — unblocks everything)
2. M1a gaps (finish downloads — unblocks M1b for gapped sessions)
3. M1b + M2 in parallel (extraction + concept index)
4. M3 (tagger — needs both M1b + M2)
5. M4 + M5 in parallel (solution gen + question gen — both need M3)
6. M6 + M7 (progression engine + API — co-implemented)
7. M1c (step-up sourcing — fills Tier 2 alongside or after M4/M5)
8. M8 (frontend — last, needs all API endpoints)

**Phase gate:** Complete and validate on one subject (Physics) end-to-end before expanding to Chemistry and Maths.

---

## Critical Path Minimum (v1)

Critical path to a working v1 (students can practice JEE Main questions with solutions):

```
M1d → M1b → M2 → M3 → M4 → M6+M7 → M8
```

**Skipped for v1:**
- **M1c** (Step-up sourcing / Tier 2) — no scraped/curated step-up problems; Tier 2 stays empty; users enter directly at Tier 3
- **M5** (Question Generator) — no generated questions; bank is limited to real past-paper questions extracted in M1b

---

### M1d — DB Tables

**CLI sessions:** 1
**Entry criteria:** `az login` active; `DB_Master.sql` and `schema.prisma` open for editing
**Exit criteria:**
- All 8 new JEE Ascent tables exist in PostgreSQL (`jee_question_papers`, `jee_question_bank`, `jee_answer_mappings`, `jee_question_tags`, `jee_question_embeddings`, `ncert_concept_hierarchy`, `ncert_concept_embeddings`, `user_accent_progress`, `user_accent_attempts`)
- `exam_papers` has `blob_url`, `paper_format`, `extraction_status` columns
- `ncert_jee_similarity` join table created (replaces planned `questiondata` columns — better normalisation)
- `pgvector` extension enabled in PostgreSQL ✅
- DDL committed; Prisma schema updated and `prisma generate` passes ✅

**Status: DONE** — verified via DB schema dump 2026-03-25.

**Key risk:** `pgvector` extension may not be enabled on the Azure-managed PostgreSQL tier — confirm it's available before designing around it. If unavailable, the vector store design needs revisiting.

---

### M1b — JEE Papers Extraction

**CLI sessions:** 3–5 (done for 2024; ~3 more sessions needed for remaining years when resumed)

**Status: PARKED (2026-04-05)** — 2024 fully extracted (34/38 papers). Remaining years (2021, 2022, 2023, 2025) deferred until E2E feature is validated.

**Entry criteria (original):**
- M1d complete (tables exist) ✓
- At least one year's papers and AKs have non-NULL `blob_url` ✓
- Both `jee_crop_pipeline.py` and `jee_extraction_pipeline.py` written ✓

**Exit criteria (full — for when resumed):**
- `jee_answer_mappings` populated for all sessions with valid AK blobs (2021 S1/S2, 2023 S2, 2024 S1/S2, 2025 S1)
- `jee_question_bank` populated with ≥ 70 questions per paper, NTA IDs preserved, `answer_key` set
- Figure crops uploaded to blob; `visual_data` set where applicable
- `exam_papers.extraction_status = 'EXTRACTED'` for all processed rows

**Exit criteria (partial — sufficient for M3 validation):** ✓ MET
- 2024: 34 papers EXTRACTED, ~3,060 questions in `jee_question_bank` with `answer_key` set
- `jee_answer_mappings` populated for 2024 AKs

**Key risk (resolved):** NTA paper format varies significantly across years. Resolved by using a text-layer scan as the primary decision: if 0 NTA IDs found, route to Pro pipeline (full-PDF Gemini Pro). 4 image-only 2024 papers confirmed — use Pro pipeline when resuming.

---

### M2 — NCERT Concept Index

**CLI sessions:** 2–3
**Entry criteria:**
- M1d complete (`ncert_concept_hierarchy` and `ncert_concept_embeddings` tables exist, `pgvector` enabled)
- `chapterdata` rows have valid `pdffileurl` blob URLs
- `concept_index_pipeline.py` file created

**Exit criteria met (2026-04-01):**
- `ncert_concept_hierarchy` has rows for all 74 chapters (2,432 concept rows + 46 `data_table` rows)
- Every row has non-NULL `embedding_text` and `ncert_solved_example`
- `ncert_concept_embeddings` has a vector for every concept row
- HNSW index confirmed built
- BM25 GIN index confirmed present; tsvector now covers `concept_title + chunk_text + description + embedding_text`
- `data_table` content type live (electrode potentials, ionic radii, bond enthalpies, physical constants, solubility tables, etc.)
- Spot-check: cosine similarity on 3 known concepts returns semantically correct neighbours ✓

---

### M3 — Question Tagger

**CLI sessions:** 2–3
**Entry criteria:**
- M1b complete (questions in `jee_question_bank`)
- M2 fully complete ✓ (M2 Patch done 2026-04-01 — BM25 enriched, `data_table` nodes live, all 74 chapters verified)
- M1d complete (`jee_question_tags`, `jee_question_embeddings` tables exist)

**Architecture (updated 2026-03-30 — changed from original design):**
Original design assumed per-question vector search. Design review showed this is insufficient for multi-concept JEE problems. New approach:

**Primary: LLM-driven tagging with index as constrained vocabulary**
```
For each JEE question:
  1. Load concept vocabulary for relevant subject(s):
     (concept_id, concept_title, content_type, chapter_title, key_formulas)
     → ~15-22K tokens per subject — fits in Gemini's context window
  2. Single LLM call: "Which NCERT concepts does this question test? Return concept_ids."
     → LLM reasons about cross-chapter prerequisites naturally
     → Output is constrained to valid concept_ids from the DB
  3. Store tagged concept_ids + scores in jee_question_tags
```
**Optional: vector pre-filter** for large batches (retrieve top-30 candidates first, then LLM selects) — reduces cost but not required for correctness.

**Why LLM-vocabulary over pure vector search:**
- Multi-concept JEE problems span 2–4 chapters; vector search cannot reason about prerequisite chains
- BM25 misses implicit prerequisites (a question about "equilibrium constant" doesn't contain the word "Gibbs")
- LLM sees full vocabulary → no silent retrieval misses

**`data_table` nodes in vocabulary (added 2026-04-01):**
Include `data_table` nodes in the concept vocabulary passed to the LLM. Reference tables (electrode potentials, solubility, ionic radii) are often the *direct* answer source for numerical JEE questions — tagging a question to the correct `data_table` node gives M4's solution generator the exact lookup table it needs as context.

**Exit criteria:**
- Every `jee_question_bank` row has `difficulty`, `difficulty_confidence`, `pattern_label` set
- `jee_question_tags` has ≥ 1 concept link per question
- `jee_question_embeddings` has a vector for every question
- Manual spot-check: concept links are semantically correct for 8/10 sampled questions (including multi-concept problems)

**Key risk:** Vocabulary list for all 3 subjects together (~55K tokens) may exceed a single Gemini call. Mitigation: tag per subject in separate calls, or use vector pre-filter to reduce vocabulary to top-50 candidates before LLM call.

---

### M4 — Solution Generator

**CLI sessions:** 2
**Entry criteria:**
- M1b complete (questions exist, `answer_key` set)
- M3 complete (`jee_question_tags` populated — needed to retrieve concept chunks)
- M2 complete (`ncert_concept_hierarchy` has `embedding_text` and `ncert_solved_example` for context)

**Exit criteria:**
- `jee_question_bank.solution` JSONB populated for all questions
- Solution JSON matches exact schema: `steps[].hint`, `steps[].formula` (not renamed variants)
- Token count per question confirmed < 5,000 (focused context working as expected)
- Solutions for 5 sample questions across Physics/Chemistry/Maths verified by hand

**Key risk:** `SolverEngine.generate()` currently expects a full PDF context cache handle. Adapting it to accept a plain-text focused context string instead must not break the existing NCERT pipeline. Isolate the change (pass `context=` kwarg, default to None for backward compatibility).

---

### M6 + M7 — Progression Engine + API Layer

**CLI sessions:** 3–4
**Entry criteria:**
- M1b complete (questions in DB)
- M3 complete (difficulty, pattern, tags set — needed for `/api/accent/session` filtering)
- M4 complete (solutions set — needed for `/api/accent/question/{id}` response)
- M1d complete (`user_accent_progress`, `user_accent_attempts` tables exist)
- Prisma schema updated and `prisma generate` clean

**Exit criteria:**
- All 6 endpoints return correct data (verified via Postman collection):
  - `/api/accent/session` — returns questions with SAS-signed image URLs
  - `/api/accent/question/{id}` — single question with solution
  - `POST /api/accent/progress` — records attempt, updates `user_accent_attempts`
  - `/api/accent/status` — correct confidence score + nudge flag
  - `POST /api/accent/advance-tier` — increments tier, unlocks next
  - `/api/accent/chapter-map` — chapters with JEE content + user tier
- SAS tokens present on all image URL fields (1-hour TTL)
- Confidence score computation verified with seeded mock attempts
- `UserId = 1` hardcoded (consistent with existing session pattern)

**Key risk:** Confidence score formula weights (0.5/0.3/0.2) are unvalidated guesses. They will not surface as a bug in v1 but will produce poor nudge timing. Accept this for v1; add a config constant so weights can be tuned without a code change.

---

### M8 — Frontend UX

**CLI sessions:** 3–4
**Entry criteria:**
- All M7 endpoints live and verified via Postman
- `AccentSession.tsx` page does not yet exist
- `PracticeSession.tsx` lateral jump changes are scoped and reviewed

**Exit criteria:**
- E2E flow works: `PracticeDashboard` "JEE Ascent" button → `AccentSession` → view question → solution accordion → nudge modal → advance tier
- Tier progress bar renders with correct colours (emerald/amber/rose)
- Solution accordion reuses existing component with no new rendering code
- `PracticeSession.tsx` change: JEE badge icons appear on correct question chips; lateral jump modal opens and shows read-only JEE question with solution
- No regressions in existing NCERT practice flow (test both `PracticeSession` and `SolutionFeedback`)

**Key risk:** `PracticeSession.tsx` is the most complex existing page. The lateral jump change (badge icons + dismissible banner + modal) touches the exercise navigator chip render logic — a high-traffic, state-heavy component. Write the change as an additive conditional block, not a refactor, to minimise regression surface.

---

## Naming Note

The DataCollection `CLAUDE.md` uses "Sub-Module 1c" to refer to the extraction pipeline. This corresponds to **Module 1b** in this document (following `JEEAccentArchitecture.md` numbering). The architecture doc's "Module 1c" is the Step-up Problems sourcing — a separate concern. Use the architecture numbering (M1a/M1b/M1c) as canonical.
