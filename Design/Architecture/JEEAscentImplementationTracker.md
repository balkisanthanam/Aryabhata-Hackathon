> ⛔ SUPERSEDED — live status in GitHub Projects (project 2 / view 11). Kept for design/history only.
> This file predates the Gold Set, the M3 ship (untuned flash 3-stage; LoRA tuning abandoned), and the
> M3 pipeline integration. Its module statuses are stale — do not trust them.

Here's a clean summary you can paste into Claude CLI:

---

## AryaBhatta — JEE Ascent Feature Progress Summary

### What JEE Ascent Is
A new feature that bridges NCERT practice (Class 11-12) with JEE Main exam preparation. Students progress through tiers — NCERT exercises → step-up problems → JEE Main questions — with AI-generated solutions and concept tagging linking NCERT concepts to JEE questions.

---

### Module Status

| Module | Name | Status | Notes |
|--------|------|--------|-------|
| M0 | Data Discovery & Audit | ✅ Done | Gap analysis complete |
| M1a | JEE Papers — Download | ✅ Done (gaps remain) | 2024 S1, S2 + 2025 S1 answer keys downloaded. 2022 CDN gap, 2025 S2 pending NTA release |
| M1d | DB Tables | ✅ Done | All 9 tables created, pgvector + ltree enabled, Prisma schema updated and generating clean |
| M1b | JEE Papers — Extraction | 🔲 Not started | Next for Claude CLI |
| M1c | Step-up Problems | 🔲 Not started | Lower priority, after M1b |
| M2 | NCERT Concept Index | ✅ Done | M2 Patch complete 2026-04-01 — 2,432 nodes + 46 data_table nodes, BM25 enriched, all 74 chapters verified |
| M3 | Question Tagger | 🔲 Not started | Needs M1b + M2 complete |
| M4 | Solution Generator | 🔲 Not started | Needs M3 complete |
| M5 | Question Generator | ⏭️ Skipped for v1 | Post-MVP |
| M6 | Progression Engine | 🔲 Not started | Co-implemented with M7 |
| M7 | API Layer | 🔲 Not started | 6 new Azure Functions endpoints |
| M8 | Frontend UX | 🔲 Not started | Needs M7 complete |

---

### Critical Path to v1

```
M1d ✅ → M1b + M2 ✅ (parallel) → M3 → M4 → M6+M7 → M8
```

---

### M1a — Known Gaps

| Gap | Status | Action needed |
|-----|--------|---------------|
| 2022 S1 AK | Manual CDN URL retrieval needed | Add to known_cdn_urls in download script |
| 2022 S2 AK | Same as above | Same approach |
| 2025 S2 AK | NTA hasn't published final yet | Monitor NTA, re-run after release |
| 2023 S1 papers | Zero papers downloaded | Investigate separately |

---

### M1d — What Was Built

9 new tables created:
- `ncert_concept_hierarchy` — NCERT concept tree with ltree paths, tsvector for hybrid search
- `ncert_concept_embeddings` — 768-dim vectors (HNSW index)
- `jee_answer_mappings` — NTA question ID → correct option ID
- `jee_question_bank` — all JEE questions (tier 2/3/4)
- `jee_question_papers` — enriched paper metadata
- `jee_question_tags` — many-to-many question ↔ concept
- `jee_question_embeddings` — 768-dim vectors per JEE question
- `user_accent_progress` — per-user tier + confidence state
- `user_accent_attempts` — individual attempt records
- `ncert_jee_similarity` — many-to-many NCERT question ↔ JEE question

Extensions enabled: `pgvector`, `ltree`

Key design decisions:
- No CHECK constraints on class/subject — extensible to Biology, Class 10 etc.
- `ncert_jee_similarity` junction table (not scalar FK) — supports multiple JEE matches per NCERT question
- Hybrid search: `0.7 × pgvector cosine + 0.3 × tsvector ts_rank`
- `tsv_content` auto-populated by DB trigger — pipelines must NOT write this field

---

### M2 — Current State

**Done** — M2 Patch complete 2026-04-01. See `JEEAscentModuleBreakdown.md` for full record.

| What | Detail |
|------|--------|
| Nodes | 2,432 concept nodes + 46 `data_table` nodes across 13 chapters |
| BM25 | Trigger enriched: `concept_title + chunk_text + description + embedding_text`; all rows backfilled |
| `data_table` type | Live in CHECK constraint, pipeline, and prompt — electrode potentials, ionic radii, bond enthalpies, solubility tables, etc. |
| Resilience | `gemini_client.py` auto-recovers from server-side cache expiry and request timeouts (re-ingests cache, retries once) |
| P2 remaining | `embed_text` column in `ncert_concept_embeddings` exists but not yet populated by pipeline |

---

### M2 — Files Created

```
pipelines/ConceptIndex/
├── concept_index_pipeline.py   # main orchestration + CLI args
├── gemini_extractor.py         # Gemini extraction + embedding
├── db_writer.py                # DB upsert logic
├── checkpoints/                # gitignored
├── logs/                       # gitignored
├── prompts/
│   ├── concept_extraction_user.txt
│   ├── concept_extraction_system.txt
│   └── embedding_text_guidance.txt
└── README.md
```

CLI arguments supported:
- `--chapter-ids 5,12,23` — run specific chapters
- `--subject physics` — filter by subject
- `--class 11` — filter by class
- `--dry-run` — extract and validate without DB writes

Embedding model: `gemini-embedding-2-preview`, 768 dims, `task_type=RETRIEVAL_DOCUMENT`

---

### M1b — Not Started Yet

Next major task for Claude CLI. Key complexity:

- Answer key PDFs use different ID formats by year:
  - 2021: 10-digit NTA IDs
  - 2022: 11-digit NTA IDs
  - 2023: 10-digit NTA IDs
  - 2024: 11-digit NTA IDs
  - (NOT 6-digit sequential — those are provisional/anomalous)
- Two-step extraction: answer keys first, then questions
- Answer key PDFs are session-level (one PDF covers all dates/shifts in a session)
- Figure crops need blob upload
- Reuse `gemini_client.py` and `blob_client.py` patterns

---

### Key Architecture Decisions Made

- **No ParadeDB** — using native PostgreSQL tsvector + GIN for BM25-like keyword search
- **768 dimensions** — uses MRL truncation from gemini-embedding-2-preview default 3072
- **ltree for hierarchy** — efficient subtree queries without recursive joins
- **Vector index is shared infra** — serves M3 (tagging), NCERT solutions grounding, and student feedback evaluation
- **session-level answer key PDFs** — one PDF per session covers all shifts
- **Google approach for answer keys** — `filetype:pdf` operator unlocks NTA PDFs on NIC CDN
- **Phased rollout for M2** — handpicked chapters first, iterate prompt, then full corpus

---

### Reference Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` (root) | Global project context |
| `pipelines/DataCollection/CLAUDE.md` | M1a/M1b local context |
| `Design/Architecture/JEEAscentModuleBreakdown.md` | Full module breakdown with complexity + status |
| `Design/Architecture/M2_Implementation_Plan.md` | Detailed M2 implementation plan |
| `Design/Architecture/JEEAscentArchitecture.md` | End-to-end architecture |
| `Scripts/JEEAscent_DB_Migration_v2.sql` | DB migration (v2 — current) |
| `pipelines/DataCollection/SITE_EVALUATION.md` | Answer key source research |
| `pipelines/DataCollection/ANSWER_KEY_DOWNLOAD_PLAN.md` | Download strategy |
