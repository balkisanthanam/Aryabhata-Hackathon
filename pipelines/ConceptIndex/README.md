# ConceptIndex Pipeline

This directory contains Module M2: the NCERT Concept Index pipeline.

## Purpose

The pipeline builds a hierarchical and vector-searchable NCERT concept index for later JEE-to-NCERT mapping.

It:

- reads chapter PDFs referenced from `chapterdata`
- extracts a concept hierarchy with Gemini
- normalizes nodes into `ncert_concept_hierarchy`
- writes one 768-dim embedding per concept into `ncert_concept_embeddings`
- supports resumable per-chapter execution with local checkpoints

## Files

- `concept_index_pipeline.py` — main orchestration and CLI
- `batch_run.py` — multi-chapter batch runner with pause + post-chapter verification
- `verifier.py` — post-chapter consistency checker (standalone CLI + importable)
- `gemini_extractor.py` — Gemini extraction, prompt loading, PDF download, embedding wrapper
- `db_writer.py` — chapter queries and psycopg2 upsert logic
- `settings_loader.py` — auto-loads `local.settings.local.json` into `os.environ`
- `prompts/` — prompt templates
- `checkpoints/` — runtime checkpoint files (gitignored)
- `logs/` — runtime logs (gitignored)

## Reuse

This pipeline reuses the existing MultiStep helpers by import:

- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py`
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/blob_client.py`

## Files

- `batch_run.py` — multi-chapter batch runner with pause + post-chapter verification
- `verifier.py` — post-chapter consistency checker (standalone CLI + importable)

## CLI Reference

### Prerequisites

```powershell
az login                  # required for Azure PostgreSQL token auth when DB_PASSWORD is unset
cd pipelines\ConceptIndex
```

---

### 1. Single-chapter run — `concept_index_pipeline.py`

The direct entrypoint. Processes one or more chapters in sequence with no pause, no post-run verification.

```powershell
python concept_index_pipeline.py [OPTIONS]
```

| Switch | Type | Description |
|--------|------|-------------|
| `--chapter-ids 29,42,66` | string | Comma-separated DB chapter IDs to process. Omit to process all chapters with a PDF URL. |
| `--subject physics` | string | Limit to one subject (case-insensitive). Combine with `--class` to narrow further. |
| `--class 11` | int | Limit to one class level (11 or 12). |
| `--dry-run` | flag | Extract concepts and validate structure, but **do not write** hierarchy rows or embeddings to the DB. Checkpoint is saved. |

**Examples:**

```powershell
# Dry-run a single chapter
python concept_index_pipeline.py --chapter-ids 66 --dry-run

# Live write for three specific chapters
python concept_index_pipeline.py --chapter-ids 29,42,66

# Live write all Class 12 Physics chapters
python concept_index_pipeline.py --subject physics --class 12
```

**Resumability:** Each chapter has a checkpoint file at `checkpoints/chapter_<id>.json`. If a run is interrupted, re-running the same command resumes from the last completed stage. A chapter with `stages.completed = true` is skipped entirely.

---

### 2. Batch run — `batch_run.py`

Wraps `concept_index_pipeline.py` for multi-chapter runs. Adds per-chapter pausing (to respect Gemini rate limits on PDF extraction) and automatic post-chapter verification.

```powershell
python batch_run.py [OPTIONS]
```

| Switch | Type | Default | Description |
|--------|------|---------|-------------|
| `--chapter-ids 29,42,66` | string | — | Comma-separated DB chapter IDs. Omit to use `--subject`/`--class` filters. |
| `--subject physics` | string | — | Filter by subject (case-insensitive). |
| `--class 12` | int | — | Filter by class level. |
| `--pause-seconds 45` | int | `45` | Seconds to wait **between chapters that need Gemini extraction**. Skipped chapters (already extracted) get a 5s pause instead. |
| `--on-failure stop` | choice | `stop` | What to do when a chapter errors or verification fails. `stop` halts immediately (safe for unattended runs). `continue` logs the failure and moves on. |
| `--no-verify` | flag | off | Skip the post-chapter verifier. Use when you want speed and will verify manually. |
| `--dry-run` | flag | off | Passed through to each chapter — extract only, no DB writes. Verifier is also skipped in dry-run mode. |

**Examples:**

```powershell
# Validate batch: 1 new chapter per subject (recommended before full corpus run)
python batch_run.py --chapter-ids 30,43,67

# Full corpus run for Class 12 Physics, 60s pause, continue on failure
python batch_run.py --subject physics --class 12 --pause-seconds 60 --on-failure continue

# Dry-run all Class 11 chapters to check extraction quality
python batch_run.py --class 11 --dry-run

# Re-run a known-complete batch (skips instantly, re-verifies DB state)
python batch_run.py --chapter-ids 29,42,66 --no-verify
```

**Smart pause:** The 45s pause is only applied before chapters that need a fresh Gemini PDF extraction call. If the next chapter already has `stages.concepts_extracted = true` in its checkpoint, the pause is reduced to 5s automatically.

**Summary table:** At the end of every batch run, a table is printed with per-chapter node count, verification check results, elapsed time, and final status.

---

### 3. Post-chapter verifier — `verifier.py`

Standalone consistency checker. Can be run manually after any write to confirm the DB state is clean.

```powershell
python verifier.py --chapter-id 66 [--skip-db]
```

| Switch | Type | Description |
|--------|------|-------------|
| `--chapter-id 66` | int | **Required.** The DB chapter ID to verify. |
| `--skip-db` | flag | Only run Tier 1 checks (checkpoint file only, no DB queries). Useful when DB is unavailable. |

**What it checks:**

| Tier | Check | Severity |
|------|-------|----------|
| 1 | All nodes have `hierarchy_written = true` | FAIL |
| 1 | All nodes have a non-null `concept_id` | FAIL |
| 1 | All nodes have `embedding_written = true` | FAIL |
| 1 | Node count ≥ 1 | FAIL |
| 2 | DB hierarchy row count == checkpoint node count | FAIL |
| 2 | DB embedding count == DB hierarchy count | FAIL |
| 2 | No `NULL` ltree paths | FAIL |
| 2 | No duplicate `(chapter_id, path)` rows | FAIL |
| 2 | No non-root nodes with `NULL parent_id` | FAIL |
| 2 | All `parent_id` values resolve to real rows | FAIL |
| 2 | All embedding vectors are 768-dimensional | FAIL |
| 2 | No empty `embedding_text` or `concept_title` | WARN |
| 2 | Node count in expected range 5–200 | WARN |

**Exit code:** `0` if all checks pass (warnings are OK), `1` if any FAIL.

---

### Local config loading

- The pipeline auto-loads `pipelines\ConceptIndex\local.settings.local.json` when present
- Existing environment variables always win over the local settings file
- For local runs, `az login` is required when `DB_PASSWORD` is not set (uses `DefaultAzureCredential`)

### Database auth

- If `DATABASE_URL` is set, it is used directly
- Otherwise reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`
- If `DB_PASSWORD` is not set, falls back to `DefaultAzureCredential` → `az login` covers this for local dev

## Current figure handling

Initial M2 behavior is text-only for figures:

- no figure upload
- no image embedding
- `figure_url` remains `None`
- figure meaning should be captured in `embedding_text`

## DB behavior

- hierarchy identity is treated as `(chapter_id, path)`
- embeddings are upserted by unique `concept_id`
- `tsv_content` is never written directly; the DB trigger populates it from `chunk_text`
