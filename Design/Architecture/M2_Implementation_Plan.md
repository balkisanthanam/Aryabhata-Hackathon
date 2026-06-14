# Module M2 Implementation Plan - NCERT Concept Index Pipeline

## 1. Module overview and goals

Module M2 builds the offline NCERT Concept Index that powers later JEE-to-NCERT matching. The pipeline will read NCERT chapter PDFs already referenced in `chapterdata`, extract a hierarchical concept tree for each chapter, generate plain-language semantic text for each concept, create embeddings, and persist both hierarchy rows and vector rows into the live JEE Ascent schema.

This plan is anchored to the current database contract in:

- `apps/functions/prisma/schema.prisma`
- `Scripts/JEEAscent_DB_Migration.sql`

Two important planning notes:

1. The live schema is the source of truth for writes. Older architecture sections that describe `topic_id`, `concept_ref`, or `text-embedding-005` are useful context, but the M2 implementation must target the current tables `ncert_concept_hierarchy` and `ncert_concept_embeddings`.
2. For embeddings, this plan intentionally uses:
   - model: `gemini-embedding-2-preview`
   - `output_dimensionality=768`
   - `task_type=RETRIEVAL_DOCUMENT` for indexing
   - `task_type=RETRIEVAL_QUERY` later for search consumers

Primary goals:

- Build a resumable per-chapter pipeline under `pipelines/ConceptIndex/`
- Populate `ncert_concept_hierarchy` with valid parent/child relationships and `ltree` paths
- Populate `ncert_concept_embeddings` with one 768-dim vector per concept row
- Preserve NCERT semantics in both UI-friendly and embedding-friendly forms
- Avoid duplicate high-cost embedding calls during resume
- Keep the design compatible with later M3/M4 hybrid retrieval

### Initial rollout strategy

The pipeline should support parameterized chapter-level runs from day one so we can test, iterate, and expand gradually instead of jumping directly to a full-corpus run.

Priority order for initial runs:

1. Phase 1: 2-3 handpicked chapters, ideally one from each subject
2. Phase 2: Review output quality and iterate on the Gemini prompt
3. Phase 3: Full subject run, starting with Physics
4. Phase 4: Full corpus

## 2. Input/output specification

### Inputs

Primary DB input:

- `chapterdata.chapterid`
- `chapterdata.class`
- `chapterdata.subject`
- `chapterdata.chapternumber`
- `chapterdata.chaptertitle`
- `chapterdata.pdffileurl`

Runtime/config inputs:

- Google Vertex/Gemini credentials already used by `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py`
- Database connection settings used by the pipeline
- Optional Azure Blob configuration if concept figures are uploaded

Reusable modules to import directly:

- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py`
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/blob_client.py`

### Outputs

Database outputs:

1. `ncert_concept_hierarchy`
   - `chapter_id`
   - `parent_id`
   - `concept_title`
   - `description`
   - `key_formulas`
   - `embedding_text`
   - `ncert_solved_example`
   - `content_type`
   - `path`
   - `figure_url`
   - `chunk_text`
   - `chunk_index`
   - `class`
   - `subject`
   - `tsv_content` - DO NOT write from the pipeline; it is auto-populated by `trg_ncert_concept_tsv` from `chunk_text`

2. `ncert_concept_embeddings`
   - `concept_id`
   - `embedding`

File outputs:

- Per-chapter checkpoint JSON files
- Pipeline run logs
- Prompt template text files
- README for usage and operator guidance

### Non-goals for M2

- No API work
- No search endpoint implementation
- No JEE question tagging
- No frontend changes

## 3. Step-by-step pipeline stages with pseudocode

The reliability design uses stable hierarchy paths as the primary identity for resumability. The schema critic review highlighted that row IDs are unsafe as resume anchors; the plan therefore uses `(chapter_id, path)` as the logical key for hierarchy rows and `concept_id` for embedding rows.

### Stage 0 - Bootstrap and configuration

Responsibilities:

- Load environment/config
- Initialize logger
- Initialize database client
- Import and initialize existing Gemini and Blob helpers
- Create local folders if missing
- Load chapter selection arguments

Pseudocode:

```python
def bootstrap():
    config = load_config()
    logger = configure_logging(config.log_dir)
    db = create_db_connection(config)
    gemini = GeminiClient(config.gemini_pipeline_config)  # imported, not copied
    blob = get_blob_client(use_managed_identity=True)     # imported, not copied
    ensure_dirs([
        "pipelines/ConceptIndex/checkpoints",
        "pipelines/ConceptIndex/logs",
        "pipelines/ConceptIndex/prompts",
    ])
    return config, logger, db, gemini, blob
```

### Stage 1 - Discover target chapters

Responsibilities:

- Query `chapterdata`
- Select chapters with non-null `pdffileurl`
- Optionally filter by class, subject, and explicit chapter IDs
- Support dry-run execution without DB writes

CLI arguments to add to `concept_index_pipeline.py`:

- `--chapter-ids 5,12,23` - run only these specific chapter IDs
- `--subject physics` - run only one subject
- `--class 11` - run only one class
- `--dry-run` - extract and validate but do not write to DB

Pseudocode:

```python
def get_target_chapters(db, filters):
    rows = db.fetch_all("""
        SELECT chapterid, class, subject, chapternumber, chaptertitle, pdffileurl
        FROM chapterdata
        WHERE pdffileurl IS NOT NULL
        ORDER BY class, subject, chapternumber
    """)
    return apply_filters(rows, filters)
```

Filtering notes:

- `--chapter-ids` should be parsed as a comma-separated list of integers
- If `--chapter-ids` is present, it should narrow the result set after the base DB query
- `--subject` and `--class` should act as additional filters
- `--dry-run` should execute extraction and validation stages but skip hierarchy and embedding writes

### Stage 2 - Load or initialize chapter checkpoint

Responsibilities:

- Read `checkpoints/chapter_<chapterid>.json` if present
- Skip fully completed chapters
- Resume partially completed chapters from the last durable state

Pseudocode:

```python
def load_checkpoint(chapter):
    path = checkpoint_path(chapter.chapterid)
    if not path.exists():
        return new_checkpoint(chapter)
    return read_json(path)
```

### Stage 3 - Acquire chapter PDF

Responsibilities:

- Download the NCERT PDF referenced by `chapterdata.pdffileurl`
- Store a local temp copy for Gemini cache use
- Record source URL and local file metadata in the checkpoint

Note on reuse:

- `blob_client.py` is upload-oriented, so it should be reused for blob-related helpers and any figure uploads.
- The chapter PDF itself can be downloaded directly from `chapterdata.pdffileurl`; no copy of blob logic should be created.

Pseudocode:

```python
def acquire_pdf(chapter, checkpoint):
    if checkpoint["stages"]["pdf_acquired"] and file_exists(checkpoint["pdf"]["local_path"]):
        return checkpoint["pdf"]["local_path"]

    local_pdf = download_file(chapter.pdffileurl, temp_pdf_path(chapter))
    checkpoint["pdf"] = build_pdf_metadata(local_pdf, chapter.pdffileurl)
    checkpoint["stages"]["pdf_acquired"] = True
    save_checkpoint(checkpoint)
    return local_pdf
```

### Stage 4 - Create/reuse Gemini cache for the chapter PDF

Responsibilities:

- Use the imported `GeminiClient.cache_document(...)`
- Cache once per chapter/model
- Persist cache metadata in the checkpoint

Pseudocode:

```python
def ensure_pdf_cache(gemini, pdf_path, checkpoint, extraction_model):
    if checkpoint["cache"].get("valid"):
        return checkpoint["cache"]

    cached_doc = gemini.cache_document(
        document_path=pdf_path,
        model_id=extraction_model,
        display_name=f"concept_index_chapter_{checkpoint['chapter']['chapter_id']}"
    )
    checkpoint["cache"] = serialize_cached_doc(cached_doc)
    checkpoint["stages"]["pdf_cached"] = True
    save_checkpoint(checkpoint)
    return checkpoint["cache"]
```

### Stage 5 - Extract raw concept hierarchy JSON with Gemini

Responsibilities:

- Send the cached PDF and extraction prompt to Gemini
- Ask for strict JSON only
- Produce nodes with stable `node_key` values that also map cleanly to `ltree`

Key design choice:

- The prompt must emit path-safe keys such as `C1`, `C1.S1`, `C1.S1.M1`
- These path labels become the canonical identity for checkpointing and DB upsert targeting

Pseudocode:

```python
def extract_concepts(gemini, cached_doc, prompt_text, checkpoint):
    if checkpoint["stages"]["concepts_extracted"]:
        return checkpoint["raw_extraction"]

    response = gemini.generate_with_cache(
        model_config=concept_extraction_model(),
        prompt=prompt_text,
        cached_doc=deserialize_cached_doc(cached_doc),
    )
    raw_json = parse_json_response(response.text)
    checkpoint["raw_extraction"] = raw_json
    checkpoint["stages"]["concepts_extracted"] = True
    save_checkpoint(checkpoint)
    return raw_json
```

### Stage 6 - Normalize and validate the extracted hierarchy

Responsibilities:

- Validate required fields
- Normalize strings
- Ensure every node has:
  - `node_key`
  - `parent_node_key` or null
  - `concept_title`
  - `embedding_text`
  - `content_type`
  - `chunk_index`
- Ensure `node_key` is valid for `ltree`
- Ensure parent nodes exist
- Detect cycles
- Sort nodes by depth so parents are written before children

Pseudocode:

```python
def normalize_hierarchy(raw_json, chapter):
    nodes = []
    for item in raw_json["nodes"]:
        node = {
            "chapter_id": chapter.chapterid,
            "path": normalize_ltree_key(item["node_key"]),
            "parent_path": normalize_nullable_ltree_key(item.get("parent_node_key")),
            "concept_title": clean_text(item["concept_title"]),
            "description": clean_optional(item.get("description")),
            "key_formulas": join_formulas(item.get("key_formulas", [])),
            "embedding_text": require_text(item["embedding_text"]),
            "ncert_solved_example": clean_optional(item.get("ncert_solved_example")),
            "content_type": validate_content_type(item["content_type"]),
            "chunk_text": build_chunk_text(item),
            "chunk_index": require_int(item["chunk_index"]),
            "has_figure": bool(item.get("has_figure", False)),
            "class": int(chapter.class),
            "subject": normalize_subject(chapter.subject),
        }
        nodes.append(node)

    assert_is_acyclic(nodes)
    assert_parent_paths_exist(nodes)
    return sort_by_path_depth(nodes)
```

### Stage 7 - Optional figure extraction/upload handling

Responsibilities:

- Do not attempt image embedding
- Do not upload concept figures in the first M2 implementation pass
- If Gemini indicates a node has a figure, preserve that signal in plain English inside `embedding_text`
- Store `figure_url = None` for now
- Record figure presence in checkpoint for future enhancement

Pseudocode:

```python
def resolve_figure_state(node, checkpoint):
    checkpoint["nodes"][node["path"]]["has_figure"] = node["has_figure"]
    checkpoint["nodes"][node["path"]]["figure_url"] = None
    save_checkpoint(checkpoint)
    return None
```

### Stage 8 - Upsert hierarchy rows

Responsibilities:

- Write `ncert_concept_hierarchy`
- Resolve `parent_id` from the already-written parent path
- Write nodes in topological order
- Capture DB IDs in checkpoint

Pseudocode:

```python
def write_hierarchy(db, nodes, checkpoint):
    path_to_id = load_existing_path_id_map(db, checkpoint["chapter"]["chapter_id"])

    for node in nodes:
        if checkpoint["nodes"].get(node["path"], {}).get("hierarchy_written"):
            path_to_id[node["path"]] = checkpoint["nodes"][node["path"]]["concept_id"]
            continue

        parent_id = None
        if node["parent_path"]:
            parent_id = path_to_id[node["parent_path"]]

        row = upsert_hierarchy_row(
            db=db,
            chapter_id=node["chapter_id"],
            path=node["path"],
            parent_id=parent_id,
            concept_title=node["concept_title"],
            description=node["description"],
            key_formulas=node["key_formulas"],
            embedding_text=node["embedding_text"],
            ncert_solved_example=node["ncert_solved_example"],
            content_type=node["content_type"],
            figure_url=node["figure_url"],
            chunk_text=node["chunk_text"],
            chunk_index=node["chunk_index"],
            class_value=node["class"],
            subject=node["subject"],
        )

        checkpoint["nodes"][node["path"]]["concept_id"] = row["id"]
        checkpoint["nodes"][node["path"]]["hierarchy_written"] = True
        path_to_id[node["path"]] = row["id"]
        save_checkpoint(checkpoint)
```

### Stage 9 - Build embedding payloads

Responsibilities:

- Construct the exact text that will be embedded
- Hash it so the resume logic can detect whether an existing embedding is still valid

Recommended embedding payload:

- `concept_title`
- `description` if present
- `embedding_text`
- `ncert_solved_example` if present
- optionally a short subject/chapter prefix for disambiguation

Pseudocode:

```python
def build_embed_text(node, chapter):
    return "\n".join(filter(None, [
        f"Subject: {chapter.subject}",
        f"Chapter: {chapter.chaptertitle}",
        f"Concept: {node['concept_title']}",
        f"Description: {node['description']}",
        f"Semantic description: {node['embedding_text']}",
        f"Solved example: {node['ncert_solved_example']}",
    ]))
```

### Stage 10 - Create embeddings and upsert vector rows

Responsibilities:

- Call `gemini-embedding-2-preview`
- Set `output_dimensionality=768`
- Use `task_type=RETRIEVAL_DOCUMENT`
- Upsert `ncert_concept_embeddings`
- Skip already-complete embeddings when the source hash matches

Pseudocode:

```python
def write_embeddings(db, gemini_embedder, nodes, checkpoint):
    for node in nodes:
        state = checkpoint["nodes"][node["path"]]
        embed_text = build_embed_text(node, checkpoint["chapter"])
        embed_hash = sha256(embed_text)

        if state.get("embedding_written") and state.get("embed_hash") == embed_hash:
            continue

        vector = gemini_embedder.embed_text(
            text=embed_text,
            model="gemini-embedding-2-preview",
            output_dimensionality=768,
            task_type="RETRIEVAL_DOCUMENT",
        )
        assert len(vector) == 768

        upsert_embedding_row(
            db=db,
            concept_id=state["concept_id"],
            embedding=vector,
        )

        state["embed_hash"] = embed_hash
        state["embedding_written"] = True
        save_checkpoint(checkpoint)
```

### Stage 11 - Mark chapter complete

Responsibilities:

- Only complete when:
  - hierarchy rows are written for all nodes
  - embedding rows are written for all nodes
- Persist summary counts and timestamps

Pseudocode:

```python
def finalize_chapter(checkpoint):
    assert all(node["hierarchy_written"] for node in checkpoint["nodes"].values())
    assert all(node["embedding_written"] for node in checkpoint["nodes"].values())
    checkpoint["stages"]["completed"] = True
    checkpoint["summary"] = summarize_checkpoint(checkpoint)
    save_checkpoint(checkpoint)
```

## 4. Gemini extraction prompt design

### Extraction objective

The extraction prompt must convert an NCERT chapter PDF into a clean, path-addressable hierarchy of concept nodes. The prompt should be optimized for:

- semantic indexing, not raw OCR transcription
- consistent hierarchy output
- plain-language `embedding_text`
- safe parent/child reconstruction
- optional solved examples and figure references

### What to ask Gemini

The prompt should instruct Gemini to:

1. Identify the major conceptual structure of the chapter
2. Emit nodes in a rooted hierarchy
3. Assign a stable `node_key` for each node using an `ltree`-safe format:
   - `C1`
   - `C1.S1`
   - `C1.S1.M1`
4. Include `parent_node_key` for non-root nodes
5. Preserve mathematical/chemical formulas in `key_formulas`
6. Translate formulas and symbolic statements into plain English in `embedding_text`
7. Include a concise worked example when present
8. Emit `content_type` using only the DB-supported values:
   - `definition`
   - `theorem`
   - `formula`
   - `worked_example`
   - `concept`
9. Return `has_figure` as a boolean for each node
10. If `has_figure=true`, include a plain-English description of the figure inside `embedding_text`
11. Produce a retrieval-friendly `chunk_text` target in the 200-400 token range
12. Return valid JSON only

### Prompt constraints

- Do not emit markdown
- Do not emit prose outside JSON
- Do not use raw LaTeX as the only content of `embedding_text`
- For chemistry, verbalize reactions and compounds in natural language
- For mathematics, verbalize equations in natural language
- For physics, explicitly state quantities, relationships, and conditions
- `node_key` must match regex `[A-Za-z0-9_]+` at the label level
- If a concept has a figure, describe the figure in words inside `embedding_text`
- Keep hierarchy depth to a practical maximum of 3 unless the chapter truly requires more
- Use source order so chunk indices remain stable across reruns

### Concrete prompt file content

Planned file: `pipelines/ConceptIndex/prompts/concept_extraction_user.txt`

Suggested prompt text:

```text
Extract the complete concept hierarchy from this NCERT chapter.
Return ONLY valid JSON with no markdown fences.

For each concept node return:
{
  "node_key": "C1",
  "parent_node_key": null,
  "concept_title": "...",
  "content_type": "concept|definition|theorem|formula|worked_example",
  "description": "...",
  "key_formulas": "...",
  "embedding_text": "...",
  "ncert_solved_example": "...",
  "has_figure": true,
  "chunk_text": "...",
  "chunk_index": 1
}

Rules:
- Every node MUST have embedding_text in plain English.
- key_formulas may contain LaTeX but embedding_text must not be LaTeX.
- Each distinct formula is a separate node.
- Each distinct worked example is a separate node.
- node_key must match regex [A-Za-z0-9_]+.
- parent_node_key must be null for root nodes and otherwise reference an existing node_key.
- If has_figure is true, write a plain-English description of the figure into embedding_text.
- Do not output markdown, commentary, or explanatory text.
```

### Expected JSON shape

This is the planned extraction contract before DB writes:

```json
{
  "chapter": {
    "chapter_id": 12,
    "class": 11,
    "subject": "Physics",
    "chapter_number": "5",
    "chapter_title": "Laws of Motion"
  },
  "nodes": [
    {
      "node_key": "C1",
      "parent_node_key": null,
      "concept_title": "Force and Interaction",
      "description": "Force describes an interaction that can change the state of motion of a body.",
      "key_formulas": [
        "F = ma"
      ],
      "embedding_text": "Force equals mass times acceleration. A net external force changes motion.",
      "ncert_solved_example": "A 2 kg block accelerates at 3 m/s^2, so the net force is 6 N.",
      "has_figure": false,
      "content_type": "concept",
      "chunk_text": "Force and interaction ...",
      "chunk_index": 1
    },
    {
      "node_key": "C1.S1",
      "parent_node_key": "C1",
      "concept_title": "Newton's Second Law",
      "description": "Newton's second law relates net force to mass and acceleration.",
      "key_formulas": [
        "F = ma"
      ],
      "embedding_text": "The net force acting on a body equals its mass multiplied by its acceleration. The accompanying figure shows the direction of applied force and the resulting acceleration of the body.",
      "ncert_solved_example": "A 10 kg cart accelerating at 2 m/s^2 experiences a net force of 20 N.",
      "has_figure": true,
      "content_type": "theorem",
      "chunk_text": "Newton's second law ...",
      "chunk_index": 2
    }
  ]
}
```

## 5. Embedding strategy

### Required model parameters

For concept indexing:

- model: `gemini-embedding-2-preview`
- `output_dimensionality=768`
- `task_type=RETRIEVAL_DOCUMENT`

For later search/query usage:

- model: `gemini-embedding-2-preview`
- `output_dimensionality=768`
- `task_type=RETRIEVAL_QUERY`

### Why this split is correct

- `RETRIEVAL_DOCUMENT` optimizes stored corpus vectors
- `RETRIEVAL_QUERY` optimizes query vectors against those corpus vectors
- Keeping both at 768 dimensions matches the current `VECTOR(768)` schema and avoids dimension mismatch

### What gets embedded

Recommended canonical embedding text:

```text
Subject: <subject>
Chapter: <chapter_title>
Concept: <concept_title>
Description: <description>
Semantic description: <embedding_text>
Solved example: <ncert_solved_example>
```

Rules:

- `key_formulas` stays in the hierarchy row for UI and audit
- raw formulas are not the primary embedding signal
- if `ncert_solved_example` is absent, embed without it but record the omission explicitly in checkpoint/logs
- if `has_figure=true`, the figure must be represented only as plain-English text inside `embedding_text`
- do not attempt image embedding in M2
- keep `figure_url = None` in the initial implementation pass

Hashing rule:

- `embed_hash` must be computed from the exact full composite embedding payload
- do not hash only `embedding_text`
- the same full composite string must be used for both hashing and the actual embedding API call

### Integration note

The existing imported `gemini_client.py` already provides generation, cache support, and retry behavior for content generation. If it does not already expose an embedding helper, `pipelines/ConceptIndex/gemini_extractor.py` should compose around the imported Gemini client and underlying SDK usage instead of copying the client implementation.

## 6. DB write strategy

### Live schema targets

`ncert_concept_hierarchy`:

- `id`
- `chapter_id`
- `parent_id`
- `concept_title`
- `description`
- `key_formulas`
- `embedding_text`
- `ncert_solved_example`
- `content_type`
- `path`
- `figure_url`
- `chunk_text`
- `chunk_index`
- `class`
- `subject`
- `created_at`

`ncert_concept_embeddings`:

- `id`
- `concept_id`
- `embedding`
- `created_at`

### Exact write rules

1. `chapter_id`, `class`, and `subject` come from `chapterdata`, not from Gemini.
2. `path` is the stable hierarchy identity and must be populated explicitly by the pipeline.
3. `parent_id` is resolved from the parent path after parent rows are inserted.
4. `tsv_content` is not written directly; the DB trigger builds it from `chunk_text`.
5. `ncert_concept_embeddings` is written only after the hierarchy row exists and returns a concrete `concept_id`.

Explicit DB writer note:

- `tsv_content` must never be included in INSERT or UPDATE payloads from the pipeline
- it is auto-populated by the `trg_ncert_concept_tsv` trigger on `chunk_text`

### Upsert logic

#### Preferred hierarchy identity

Preferred logical key: `(chapter_id, path)`

Reason:

- `path` directly matches the schema's `ltree` hierarchy design
- `path` is stable across resume
- `path` is safer than `(chapter_id, concept_title)` because sibling titles can collide

#### Important schema note

The current schema exposes indexes for `chapter_id` and `(class, subject)` and a unique constraint only for `ncert_concept_embeddings.concept_id`. It does not currently show a unique constraint on hierarchy paths. Therefore the implementation plan should assume one of two modes:

1. Preferred mode: add a pre-M2 DB migration that makes `(chapter_id, path)` unique.
2. Fallback mode: implement manual lookup-then-update semantics inside a transaction using `(chapter_id, path)` as the application-level natural key.

Planned hierarchy upsert sequence:

1. Load existing rows for the chapter into a `path -> row` map.
2. For each normalized node in depth order:
   - resolve parent ID from `parent_path`
   - if row exists for `(chapter_id, path)`, update mutable fields
   - else insert a new row
3. Save returned `id` into checkpoint

Planned embedding upsert sequence:

1. Build vector from canonical embedding payload
2. Use unique `concept_id` in `ncert_concept_embeddings`
3. Update existing embedding if the source hash changed

### Parent/path assignment

Rules:

- Root node:
  - `parent_id = NULL`
  - `path = C<n>`
- Child node:
  - `parent_id = id(path parent)`
  - `path = <parent_path>.<segment>`

Example:

- `C1` -> root
- `C1.S1` -> child of `C1`
- `C1.S1.M1` -> child of `C1.S1`

The reliability pass specifically flagged path reconstruction as the main resumability risk. To address that, resume logic must always reconstruct hierarchy state from stored path values, never from assumed insertion order and never from raw serial IDs alone.

## 7. Checkpoint/resumability design

### Guiding principle

The checkpoint design must survive failures in:

- PDF download
- Gemini cache creation
- Gemini extraction
- JSON parsing/validation
- hierarchy DB writes
- figure uploads
- embedding API calls
- embedding DB writes

It must also prevent duplicate embedding charges.

### Checkpoint granularity

Primary unit: one checkpoint file per chapter

Path:

- `pipelines/ConceptIndex/checkpoints/chapter_<chapterid>.json`

### Checkpoint shape

```json
{
  "chapter": {
    "chapter_id": 12,
    "class": 11,
    "subject": "Physics",
    "chapter_number": "5",
    "chapter_title": "Laws of Motion"
  },
  "stages": {
    "pdf_acquired": true,
    "pdf_cached": true,
    "concepts_extracted": true,
    "concepts_normalized": true,
    "hierarchy_written": false,
    "embeddings_written": false,
    "completed": false
  },
  "pdf": {
    "source_url": "https://...",
    "local_path": "C:\\\\...\\\\chapter_12.pdf",
    "sha256": "..."
  },
  "cache": {
    "cache_name": "...",
    "display_name": "...",
    "file_uri": "...",
    "created_at": "...",
    "expires_at": "...",
    "valid": true
  },
  "nodes": {
    "C1": {
      "parent_path": null,
      "concept_id": 901,
      "hierarchy_written": true,
      "embedding_written": true,
      "has_figure": false,
      "embed_hash": "..."
    },
    "C1.S1": {
      "parent_path": "C1",
      "concept_id": 902,
      "hierarchy_written": true,
      "embedding_written": false,
      "has_figure": true,
      "embed_hash": null
    }
  },
  "errors": [],
  "summary": {}
}
```

### Resume rules

1. If `completed=true`, skip the chapter.
2. If extraction already succeeded, reuse the extracted JSON and do not call Gemini extraction again.
3. If a node's hierarchy row is already written and its `concept_id` is known, do not rewrite it unless the pipeline is explicitly run in refresh mode.
4. If a node's embedding is already written and the `embed_hash` of the full composite embed text matches, do not call the embedding API again.
5. If the checkpoint is missing but DB rows exist, rebuild a minimal in-memory state from `(chapter_id, path)` lookups before continuing.

### Critic-driven self-correction applied to the design

The reliability review identified a specific risk: the schema's hierarchy depends on both `parent_id` and `path`, and resumability breaks if child reconstruction assumes serial IDs or insertion order. This plan corrects for that by:

- making `path` the stable chapter-local identity
- sorting writes by path depth
- resolving `parent_id` from `parent_path -> concept_id`
- checkpointing each node by path
- never relying on prior `SERIAL` values as the source of truth for hierarchy structure

This is the required hierarchy-safe resume model for the current schema.

## 8. Error handling approach

### Principles

- Fail explicitly and record the failure location
- Retry transient network/model issues
- Avoid partial silent success
- Preserve enough state to resume without redoing expensive work

### Error classes and handling

#### PDF acquisition errors

- Causes:
  - broken `pdffileurl`
  - network timeout
  - permission issue
- Handling:
  - retry with bounded backoff
  - if still failing, mark chapter failed in checkpoint and stop chapter processing

#### Gemini cache/extraction errors

- Causes:
  - quota issues
  - 429/499/500/503 responses
  - invalid JSON
  - partial output
- Handling:
  - rely on imported Gemini retry logic where available
  - validate JSON shape before checkpointing extraction as complete
  - if extraction output is invalid, save raw response snippet to logs and mark stage failed

#### Hierarchy validation errors

- Causes:
  - duplicate node keys
  - missing parents
  - invalid `content_type`
  - cycle in hierarchy
- Handling:
  - fail chapter before DB writes
  - store validation errors in checkpoint
  - require operator review or rerun

#### Figure upload errors

- Causes:
  - future blob connectivity failure
  - future upload timeout
  - future invalid crop reference
- Handling:
  - for the initial M2 implementation, skip figure upload entirely
  - set `figure_url = null`
  - require the extractor to describe the figure in plain English inside `embedding_text`
  - do not pretend image upload or image embedding has happened

#### Embedding errors

- Causes:
  - quota/rate limit
  - dimension mismatch
  - malformed API response
- Handling:
  - retry transient failures
  - validate vector length equals 768
  - checkpoint after every successful node embedding write
  - skip previously completed nodes using `embed_hash`

#### DB write errors

- Causes:
  - parent FK failure
  - type mismatch
  - vector insert failure
  - duplicate row ambiguity when no unique key exists
- Handling:
  - use transactions around per-node write operations
  - fail fast on parent resolution issues
  - log the exact SQL operation phase

## 9. Test strategy

### Phase 1 - Single chapter dry run

Run one representative chapter first before any full corpus run.

Recommended dry run characteristics:

- one chapter with formulas
- one chapter with a likely solved example
- ideally one chapter with a figure

Expanded rollout plan:

- Phase 1: 2-3 handpicked chapters, one per subject
- Phase 2: Review output quality and iterate on the Gemini prompt
- Phase 3: Full subject run, Physics first
- Phase 4: Full corpus

Validation checklist:

1. chapter is selected correctly from `chapterdata`
2. PDF is downloaded once
3. Gemini cache is reused during the run
4. extracted JSON is valid
5. paths are valid `ltree` strings
6. parents are assigned correctly
7. `chunk_text` populates `tsv_content` through the DB trigger
8. every inserted embedding vector has length 768
9. `ncert_concept_embeddings` contains one row per hierarchy row written
10. rerunning the same chapter does not duplicate hierarchy or embedding work

### Phase 2 - Resume simulation

Simulate crashes at:

- after extraction
- after half the hierarchy rows
- after half the embedding rows

Expected result:

- rerun resumes cleanly
- already-complete embeddings are not recomputed
- child nodes still resolve correct parents

### Phase 3 - Cross-subject spot checks

Run one chapter each from:

- Physics
- Chemistry
- Mathematics

Goal:

- confirm prompt quality across symbolic domains
- confirm chemistry `embedding_text` verbalization is good enough for later query-time retrieval

## 10. File structure for the new pipeline

Planned location:

```text
pipelines/ConceptIndex/
├── concept_index_pipeline.py
├── gemini_extractor.py
├── db_writer.py
├── checkpoints/
├── logs/
├── prompts/
└── README.md
```

### File responsibilities

#### `concept_index_pipeline.py`

- main orchestration
- chapter selection
- checkpoint loading/saving
- stage sequencing
- dry-run/full-run CLI entry
- CLI filters for `--chapter-ids`, `--subject`, `--class`, and `--dry-run`

#### `gemini_extractor.py`

- imports and composes existing Gemini client utilities
- loads prompt templates
- chapter extraction call
- embedding helper wrapper for `gemini-embedding-2-preview`
- extraction response parsing/normalization helpers

#### `db_writer.py`

- DB read/write helpers
- hierarchy upsert logic
- parent/path resolution
- embedding upsert logic
- transaction boundaries

#### `checkpoints/`

- per-chapter checkpoint JSON files
- runtime-only artifacts, not committed

#### `logs/`

- run logs
- error traces
- optional saved raw Gemini response fragments for failed chapters

#### `prompts/`

Suggested prompt files:

- `concept_extraction_system.txt`
- `concept_extraction_user.txt`
- `embedding_text_guidance.txt`

#### `README.md`

- setup
- env vars
- usage examples
- dry-run workflow
- operational notes for resume/retry

## 11. Pipeline location

The new pipeline will be created under:

```text
pipelines/ConceptIndex/
```

This naming is correct because the pipeline indexes NCERT concepts, not chapters.

## 12. Reuse from existing pipelines

The new pipeline should reuse existing helpers by import, not copy/paste.

Direct reuse targets:

- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/blob_client.py`
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py`

Planned reuse pattern:

- import `GeminiClient` and existing cache/retry behavior from the current MultiStep pipeline
- import `BlobClient` / `get_blob_client` for any concept figure uploads or blob-related operations
- do not fork or duplicate those clients into `pipelines/ConceptIndex/`

## 13. Root `.gitignore` updates

Add:

```gitignore
pipelines/ConceptIndex/checkpoints/
pipelines/ConceptIndex/logs/
```

These directories are runtime artifacts and should stay untracked.

## 14. Recommended implementation sequence

1. Create `pipelines/ConceptIndex/` skeleton and prompt files.
2. Implement chapter discovery and checkpoint loading.
3. Wire Gemini PDF caching and extraction with strict JSON validation.
4. Implement normalization and hierarchy validation.
5. Implement hierarchy upsert logic keyed by `(chapter_id, path)`.
6. Implement embedding wrapper for `gemini-embedding-2-preview` with 768 dims and `RETRIEVAL_DOCUMENT`.
7. Implement embedding checkpoint/resume logic using per-node `embed_hash`.
8. Run a single chapter dry run.
9. Simulate resume from an interrupted run.
10. Expand to one chapter per subject before full corpus execution.

## 15. Final design summary

This M2 plan uses the current schema correctly by treating concept hierarchy paths as the durable identity for extraction, writes, and resume. That choice aligns with the `ltree` design in SQL, solves the critic's parent/child recovery concern, and gives the pipeline a reliable way to avoid duplicate embedding work even when the process fails mid-chapter.

The resulting pipeline will produce:

- a browsable NCERT concept tree in `ncert_concept_hierarchy`
- one 768-dim document vector per concept in `ncert_concept_embeddings`
- resumable per-chapter execution with explicit failure visibility
- retrieval-ready data for later M3/M4 modules
