# JEE Ascent — Architecture & Design Document

## Context
The JEE Ascent feature elevates a student from NCERT chapter exercises to JEE Main-level problems through a graduated, structured progression. The problem it solves: students who complete NCERT practice have no guided, difficulty-aware path to exam-level problems. JEE Ascent creates that bridge through 4 tiers: NCERT exercises → Step-up problems → JEE Main questions → More JEE practice. All core modules are async and offline in nature; UX is the final layer.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector store | pgvector in existing PostgreSQL | ~6-8K vectors total; no new infra needed |
| Concept index structure | Hybrid: relational hierarchy + pgvector | Relational for browsing/filtering; vectors for semantic matching |
| Embedding model | Gemini `text-embedding-005` (768 dims) | Cheapest; best STEM coverage; native to existing Gemini usage |
| Embedding input | Plain-text `embedding_text` (not raw LaTeX) | Embedding models cannot interpret raw LaTeX symbols semantically |
| Search strategy | Hybrid: pgvector ANN + PostgreSQL full-text (BM25) | Vectors for semantic; BM25 for exact formula/symbol matching |
| Step-up problem source | Scrape first + LLM-generate to fill gaps | Authenticity + coverage |
| JEE data download | Extend existing `download_exam_papers.py` + new extraction pipeline | Reuse Selenium downloader; extraction is a separate concern |
| NTA ID handling | Preserve NTA Question IDs and Option IDs; cross-reference with official answer key | Enables deterministic correct-answer linkage |
| Solution grounding | Focused vector context (top-3 concept chunks) instead of full PDF | ~95% fewer tokens; same or better relevance |
| Progression trigger | System nudges, user confirms | Confidence heuristic + explicit user gate |
| Pattern tagging | Phase 1 — LLM-assigned during ingestion | Enables grouping without ML clustering overhead |
| Difficulty classification | LLM few-shot (Gemini 3.1 Pro) | ~80-85% accuracy; no training data needed |
| Question generation | RAG + few-shot (Phase 1); fine-tune when ≥500 verified examples | Fast to implement; fine-tuning reserved until student data exists |
| Question evaluation | 3-layer: automated rubric → human review queue → student performance | Progressive quality assurance |
| Cloud posture | GCP-ready design (Azure for now) | Easy swap to Cloud Run/GCS/Pub-Sub later |
| Entry point (UX) | Existing PracticeDashboard "JEE Ascent" button per chapter card | No separate dashboard needed; already present in UI |
| Lateral jump indicator | JEE icon on exercise navigator question chips (not just sidebar chip) | Visible at a glance without disrupting the reading flow |

---

## 1. Feature Overview

### 4-Tier Progression
```
Tier 1: NCERT Exercise Problems      (already in DB — bridge, not built new)
         ↓  "Step up?" nudge
Tier 2: Step-up Problems             (intermediate: harder NCERT-adjacent problems)
         ↓  "Ready for JEE?" nudge
Tier 3: JEE Main Past Questions      (actual past exam questions, sourced)
         ↓  "Practice more?" nudge
Tier 4: More JEE Practice Problems   (generated + curated, high volume)
```

**Entry points:**
1. **Transition** — "JEE Ascent" button on each chapter card in the existing PracticeDashboard (already visible in UI). No separate Ascent dashboard page is needed.
2. **Post-chapter nudge** — After completing a chapter's NCERT exercises, a nudge appears: "Ready to step up?"
3. **Lateral jump** — While in NCERT exercise, question chips in the exercise navigator show a small JEE indicator icon if the question has high JEE similarity. Tapping opens a non-disruptive overlay.

---

## 2. Module Architecture

8 independent modules, all async/offline except API and Frontend. Build and test in this order.

```
Module 0: Data Discovery & Audit        (one-time)
Module 1: Question Bank Ingestion       (offline pipeline)
Module 2: NCERT Concept Index           (offline pipeline)
Module 3: Question Tagger               (offline pipeline, after M1+M2)
Module 4: Solution Generator            (offline pipeline, after M1)
Module 5: Question Generator            (offline pipeline, after M1+M2+M3)
Module 6: Progression Engine            (online, query-time logic)
Module 7: API Layer                     (online, Azure Functions v4)
Module 8: Frontend UX                   (React, built last)
```

---

## Module 0: Data Discovery & Audit

**Goal:** Locate and normalize all existing JEE Main data before building pipelines.

**Steps:**
1. Audit all known locations: local disk, Azure Blob (`kalidasa` + `stevaluationstorage`), spreadsheets/JSON
2. Classify each artifact: raw PDF / structured JSON / spreadsheet / already-in-DB
3. Map to Module 1 standard schema
4. Document gaps: which years, sessions, subjects are missing

**Output:** `Data/JEEAudit.md` — inventory with status per source

---

## Module 1: Question Bank Ingestion

**Goal:** Populate `jee_question_bank` with questions from all sources, normalized with source metadata and NTA IDs.

### 1a. JEE Main Past Papers — Download

**Existing infrastructure:** `pipelines/DataCollection/download_exam_papers.py`
- Selenium-based; navigates NTA site year dropdown; downloads question PDFs and answer key PDFs
- Stores metadata to PostgreSQL `exam_papers` table (`ExamName`, `PaperName`, `Year`, `DateOfExam`, `Shift`, `FileName`)
- Has triple-click fallback, stale element recovery, pagination support

**Enhancements needed to downloader:**
1. **Azure Blob upload** — after downloading each PDF, upload to `kalidasa` container at path `jeedata/{year}/{paper_id}/{filename}.pdf`; store blob URL in `exam_papers.blob_url`
2. **Exponential backoff** — replace current retry logic with exponential backoff (initial: 2s, max: 60s, jitter: ±20%) on network errors and Selenium timeouts
3. **Year-format detection** — NTA paper structure has varied slightly across years (section naming, question counts, ID formats); add a `detect_paper_format(year)` helper that maps years to known format variants

### 1b. JEE Main Past Papers — Extraction

**Separate pipeline:** `jee_extraction_pipeline.py` (new, in `pipelines/JEEAccentPipeline/`)

Download and extraction are deliberately separated — the downloader runs on a schedule; extraction runs on-demand after audit.

**NTA paper structure to handle:**
- 75 questions per paper: 25 Physics + 25 Chemistry + 25 Maths
- Section A: 20 MCQ per subject (all compulsory)
- Section B: 10 numerical per subject (attempt any 5)
- Each question has a **NTA Question ID** (e.g., `NQ_12345`)
- Each option has a **NTA Option ID** (e.g., `NO_23456A`, `NO_23456B`, `NO_23456C`, `NO_23456D`)
- Answer key PDFs map: `NTA Question ID → Correct NTA Option ID`

**Year-structure variations to handle:**
- Pre-2021: Single-column layout, no explicit section headers in some papers
- 2021+: Two-column layout; explicit Section A / Section B headers
- Some papers omit set code on cover page; infer from filename
- Format detection: send page 1 to Gemini with a format-detection prompt before running main extraction

**Extraction pipeline steps:**
1. Fetch PDF blob URL from `exam_papers` → download to temp
2. **Format detection pass** — Gemini (Flash): identify paper year, structure variant, subject boundaries
3. **Question extraction pass** — Gemini (3.1 Pro, sliding window): extract all questions preserving NTA Question IDs and Option IDs; same sliding-window approach as `extraction_engine.py`; LaTeX for all math; `$\ce{...}$` for chemistry
4. **Answer key cross-reference** — Parse answer key PDF (separate file); map `NTA Question ID → Correct Option ID → answer text`; JOIN into extracted questions
5. **Figure extraction** — Gemini (Flash): detect figures with bounding boxes; crop from PDF; upload crops to Azure Blob; replace with URLs in JSON
6. INSERT/UPSERT into `jee_question_bank`

**Per-question output:**
```json
{
  "question_id": "JEE_MAIN_2024_JAN_S1_NQ12345",
  "paper_id": "JEE_MAIN_2024_JAN_S1_SHIFT1",
  "nta_question_id": "NQ_12345",
  "nta_option_ids": {
    "A": "NO_23456A",
    "B": "NO_23456B",
    "C": "NO_23456C",
    "D": "NO_23456D"
  },
  "question_text": "A particle moves...$v = v_0 + at$...",
  "question_type": "MCQ",
  "options": [{"key": "A", "text": "2 m/s"}, {"key": "B", "text": "4 m/s"}],
  "answer_key": "C",
  "subject": "Physics",
  "section": "A",
  "visual_required": false,
  "visual_data": null,
  "source": "JEE_MAIN",
  "tier": 3
}
```

**Sources (priority order):**
1. Existing data found in Module 0 audit (already in `kalidasa` blob / `jeedata/*.json`)
2. NTA official downloads via enhanced downloader (3-5 years of papers)
3. Open GitHub datasets archiving past JEE papers
4. Coaching institute open question banks (Resonance, Allen)

### 1c. Step-up Problems (Tier 2)

**Sources:**
1. Coaching institute open question banks (scrape where permitted)
2. LLM-generated variants (Module 5) to fill gaps
3. Hand-curated problems with known NCERT proximity

### 1d. New DB Tables

```sql
-- Enhance existing exam_papers table (from DataCollection pipeline)
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS blob_url VARCHAR(500);
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS paper_format VARCHAR(50);  -- e.g., 'PRE_2021', '2021_PLUS'
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'PENDING';

-- Question papers (JEE Ascent specific — links to exam_papers)
CREATE TABLE jee_question_papers (
  paper_id        VARCHAR(100) PRIMARY KEY,
  exam_paper_id   INT REFERENCES exam_papers(id),  -- FK to existing table
  source          VARCHAR(50),       -- 'JEE_MAIN', 'STEP_UP', 'GENERATED'
  exam_date       DATE,
  session         VARCHAR(50),       -- 'January', 'April'
  shift           VARCHAR(20),
  set_code        CHAR(1),
  total_questions INT,
  official_url    VARCHAR(500),
  blob_url        VARCHAR(500),      -- PDF stored in Azure Blob
  metadata        JSONB,
  created_at      TIMESTAMP DEFAULT NOW()
);

-- Question bank (all non-NCERT questions)
CREATE TABLE jee_question_bank (
  question_id           VARCHAR(150) PRIMARY KEY,
  paper_id              VARCHAR(100) REFERENCES jee_question_papers(paper_id),
  nta_question_id       VARCHAR(50),   -- NTA's own question ID (preserved for answer key correlation)
  nta_option_ids        JSONB,         -- {"A": "NO_...", "B": "NO_...", ...}
  subject               VARCHAR(50) NOT NULL,
  class                 VARCHAR(10),
  question_text         TEXT NOT NULL,
  question_type         VARCHAR(20),             -- 'MCQ', 'NUMERICAL'
  options               JSONB,
  answer_key            VARCHAR(100),
  section               VARCHAR(10),             -- 'A' (MCQ) or 'B' (Numerical)
  tier                  SMALLINT NOT NULL,       -- 2=StepUp, 3=JEEMain, 4=MoreJEE
  source                VARCHAR(50) NOT NULL,    -- 'JEE_MAIN', 'STEP_UP_SCRAPED', 'GENERATED'
  is_generated          BOOLEAN DEFAULT FALSE,
  difficulty            VARCHAR(20),             -- 'Easy', 'Medium', 'Hard', 'JEE'
  difficulty_confidence FLOAT,
  pattern_label         VARCHAR(100),            -- e.g., 'projectile + friction'
  visual_data           JSONB,
  content               JSONB,                   -- same shape as questiondata.content
  solution              JSONB,                   -- same shape as questiondata.solution
  generation_quality_score FLOAT,               -- rubric score (Module 5, generated only)
  review_status         VARCHAR(20) DEFAULT 'AUTO_ACCEPTED',  -- 'AUTO_ACCEPTED', 'PENDING_REVIEW', 'APPROVED', 'REJECTED'
  created_at            TIMESTAMP DEFAULT NOW(),
  updated_at            TIMESTAMP DEFAULT NOW()
);
```

**Checkpointing:** `Output/{paper_id}_extraction_state.json` — same pattern as existing pipeline.

---

## Module 2: NCERT Concept Index

**Goal:** Hierarchical + vector-searchable index of NCERT concepts — the semantic backbone linking JEE questions to NCERT chapters.

### 2a. pgvector Suitability for NCERT Content

**Decision: pgvector IS appropriate**, with mandatory semantic preprocessing. Here is the full analysis:

#### Why pgvector Works
- **Scale:** ~74 chapters × ~30 concepts/chapter = ~2,200 concept vectors. pgvector handles millions of vectors efficiently; 2,200 is trivial.
- **HNSW index:** Near-O(log n) query time; recall >95% at this scale; no training required (unlike IVFFlat).
- **Colocation with relational data:** Concept-to-chapter joins happen in a single SQL query — no round-trip to a separate vector DB.
- **Operational simplicity:** No new infrastructure, no new deployment, no new credentials.

#### The Problem: Raw LaTeX is Not Semantically Embeddable
NCERT content is dense with LaTeX:
- **Chemistry:** 100% of chemical equations in `$\ce{H_2SO_4}$`, `$\ce{2H_2 + O_2 -> 2H_2O}$`
- **Math:** 100% of formulas in `$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$`
- **Physics:** Mixed prose + formula (e.g., `$F = ma$`, `$v^2 = u^2 + 2as$`)

**Embedding models tokenize LaTeX as raw characters** — `\frac{a}{b}` and `\dfrac{a}{b}` produce near-zero cosine similarity despite being identical mathematically. A concept chunk containing only formulas generates a near-random vector.

#### Fix: Semantic Preprocessing (`embedding_text`)
Every concept chunk is stored with TWO representations:
1. **`key_formulas` (JSONB):** Raw LaTeX — rendered in UI via KaTeX
2. **`embedding_text` (TEXT):** Plain-language description — used for embedding

```python
# Example transformation
raw_formula = "$\\ce{H_2SO_4 + 2NaOH -> Na_2SO_4 + 2H_2O}$"
embedding_text = "sulfuric acid reacts with sodium hydroxide to form sodium sulfate and water (neutralization reaction)"

raw_formula = "$v^2 = u^2 + 2as$"
embedding_text = "final velocity squared equals initial velocity squared plus 2 times acceleration times displacement (kinematic equation)"
```

The pipeline asks Gemini to generate `embedding_text` alongside each concept during extraction (one extra field in the extraction prompt — zero extra API calls).

#### Include Solved Examples in Concept Chunks
A solved example is the strongest embedding signal — it contains concept + formula + application context in natural language.

```python
embed_text = f"""
Concept: {concept_title}
Description: {description}
Plain-text formulas: {embedding_text_for_formulas}
Example: {ncert_example_text}  # prose description of worked example
"""
```

Estimated token count per concept chunk: ~1,000–1,500 tokens. Embedding input limit for `text-embedding-005` is 2,048 tokens — well within range.

#### Hybrid Search: pgvector + BM25
Neither ANN search nor keyword search alone is sufficient:
- **ANN (pgvector):** Finds semantically similar concepts ("inertia" matches "resistance to change") — misses exact matches
- **BM25 (full-text):** Finds exact keyword/formula name matches — misses paraphrases

**Implementation:**
```sql
-- pgvector ANN search
SELECT concept_id, embedding <=> $query_embedding AS vec_dist
FROM ncert_concept_embeddings
WHERE subject = $subject
ORDER BY vec_dist ASC LIMIT 20;

-- BM25 keyword re-rank on the top-20
SELECT concept_id,
       ts_rank_cd(to_tsvector('english', embed_text), plainto_tsquery($query_keywords)) AS bm25_score
FROM ncert_concept_hierarchy
WHERE concept_id = ANY($top_20_ids)
ORDER BY bm25_score DESC LIMIT 3;
```

Final score: `final = 0.7 × (1 - vec_dist) + 0.3 × bm25_score` (tunable).

#### Limitations to Monitor
| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Embedding model has no math reasoning | Semantically similar formulas may rank poorly | embedding_text preprocessing |
| Concept chunks are coarse (chapter-level) | Fine-grained sub-topic matching may miss | Add ncert_section as a filter field |
| 2,200 vectors — small corpus | Recall is high but precision may be noisy at boundary | Hybrid BM25 re-ranking |
| No cross-subject disambiguation | "Energy" in Physics ≠ Chemistry | Always filter by subject before ANN search |

### 2b. Concept Extraction

**Input:** NCERT chapter PDFs (blob URLs from `chapterdata.pdffileurl`)
**Model:** `gemini-3.1-pro-preview` with context caching (reuse `GeminiClient.create_cache()`)

**Output per chapter:**
```json
{
  "topics": [{
    "topic_id": "T1",
    "topic_title": "Newton's First Law",
    "concepts": [{
      "concept_id": "C1",
      "concept_title": "Inertia and Mass",
      "description": "Inertia is the resistance of an object to any change in its state of motion...",
      "key_formulas": ["$F = ma$", "$p = mv$"],
      "embedding_text": "Force equals mass times acceleration. Momentum equals mass times velocity. A body at rest stays at rest unless acted on by an external force.",
      "key_examples": ["Book resting on table stays at rest until pushed"],
      "ncert_solved_example": "A truck of mass 2000 kg accelerates from rest to 20 m/s in 10s. Find the force. (Answer: F = 2000 × 2 = 4000 N)",
      "ncert_section": "5.2"
    }]
  }]
}
```

### 2c. New DB Tables

```sql
-- Enable pgvector (once per DB)
CREATE EXTENSION IF NOT EXISTS vector;

-- Relational concept hierarchy
CREATE TABLE ncert_concept_hierarchy (
  concept_id    SERIAL PRIMARY KEY,
  chapter_id    INT REFERENCES chapterdata(chapterid),
  topic_id      VARCHAR(20),
  topic_title   VARCHAR(255),
  concept_ref   VARCHAR(20),
  concept_title VARCHAR(255) NOT NULL,
  description   TEXT,
  key_formulas  JSONB,                   -- raw LaTeX (for UI rendering)
  embedding_text TEXT,                   -- plain-language text (for embedding)
  key_examples  JSONB,
  ncert_solved_example TEXT,             -- worked example text (improves embedding quality)
  ncert_section VARCHAR(20),
  created_at    TIMESTAMP DEFAULT NOW(),
  UNIQUE (chapter_id, topic_id, concept_ref)
);

-- BM25 full-text index on embedding_text
CREATE INDEX ON ncert_concept_hierarchy USING gin(to_tsvector('english', embedding_text));

-- Vector embeddings (embed_text = embedding_text + solved example + concept_title)
CREATE TABLE ncert_concept_embeddings (
  concept_id    INT PRIMARY KEY REFERENCES ncert_concept_hierarchy(concept_id),
  embedding     vector(768) NOT NULL,
  embed_text    TEXT,                    -- exact text that was embedded (for debugging/refresh)
  model_version VARCHAR(50),            -- e.g., 'text-embedding-005'
  created_at    TIMESTAMP DEFAULT NOW()
);
-- HNSW index for approximate nearest-neighbour search
CREATE INDEX ON ncert_concept_embeddings USING hnsw (embedding vector_cosine_ops);
```

**Scale:** 74 chapters × ~30 concepts = ~2,200 vectors

### 2d. Pipeline

`concept_index_pipeline.py`:
1. Iterate `chapterdata` rows
2. Fetch PDF from blob → cache with Gemini → extract concept hierarchy (with `embedding_text` and `ncert_solved_example`)
3. UPSERT into `ncert_concept_hierarchy`
4. For each concept: construct `embed_text = concept_title + embedding_text + ncert_solved_example`; call `text-embedding-005`
5. UPSERT into `ncert_concept_embeddings`
6. Checkpoint per chapter (resumable)

---

## Module 3: Question Tagger

**Goal:** Assign NCERT concept links, difficulty level, and pattern label to every question in `jee_question_bank`. Also detect JEE-proximity for existing NCERT questions (powers lateral jump).

### 3a. Existing Infrastructure to Reuse

- **`pipelines/ExtractionPipeline/JSONBasedExtraction/run_question_tagging.py`** — batches 5 JEE questions per API call, supports vision (figure images), outputs Topic/SubTopic/Difficulty
- **`JEEMainQuestionPaper_NTA_Tagging.txt`** — existing tagging prompt to extend

Module 3 **extends** this pipeline; new additions: NCERT concept linking (vector search), pattern label, and `embedding_text` preprocessing for JEE question embedding.

### 3b. Tagging Strategy

**Step 1 — Embed JEE question:**
```python
# Generate plain-text version of question before embedding
jee_embed_text = gemini_client.generate(
    f"Describe this {subject} question in plain English, replacing all formulas with their verbal description: {question_text}"
)
q_embedding = gemini_client.embed_text(jee_embed_text)
```

**Step 2 — NCERT Concept Linking (hybrid search):**
```sql
-- ANN: get top-20 candidates
WITH vec_candidates AS (
  SELECT c.concept_id, c.embed_text,
         e.embedding <=> $q_embedding AS vec_dist
  FROM ncert_concept_embeddings e
  JOIN ncert_concept_hierarchy c ON e.concept_id = c.concept_id
  JOIN chapterdata ch ON c.chapter_id = ch.chapterid
  WHERE ch.subject = $subject
  ORDER BY vec_dist ASC LIMIT 20
)
-- BM25 re-rank
SELECT concept_id,
       0.7 * (1 - vec_dist) + 0.3 * ts_rank_cd(
         to_tsvector('english', embed_text),
         plainto_tsquery($keyword_query)
       ) AS final_score
FROM vec_candidates
ORDER BY final_score DESC LIMIT 3;
```

**Step 3 — Difficulty + Pattern (LLM, single batch call):**
- Show 3 examples each of Easy / Medium / Hard / JEE level, then classify
- In same call: "Identify solving pattern in ≤5 words"
- Output: `{ "difficulty": "Hard", "confidence": 0.91, "pattern": "projectile + friction" }`

### 3c. New DB Tables

```sql
-- Many-to-many: question ↔ NCERT concept
CREATE TABLE jee_question_tags (
  tag_id           SERIAL PRIMARY KEY,
  question_id      VARCHAR(150) REFERENCES jee_question_bank(question_id),
  concept_id       INT REFERENCES ncert_concept_hierarchy(concept_id),
  similarity_score FLOAT,
  is_primary       BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP DEFAULT NOW(),
  UNIQUE (question_id, concept_id)
);

-- Question embeddings (for lateral jump detection + generation RAG)
CREATE TABLE jee_question_embeddings (
  question_id   VARCHAR(150) PRIMARY KEY REFERENCES jee_question_bank(question_id),
  embedding     vector(768) NOT NULL,
  embed_text    TEXT,                    -- plain-text used for embedding
  model_version VARCHAR(50),
  created_at    TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON jee_question_embeddings USING hnsw (embedding vector_cosine_ops);

-- Proximity flag on existing NCERT questions (powers lateral jump)
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS jee_similar_question_id VARCHAR(150);
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS jee_similarity_score FLOAT;
```

### 3d. Lateral Jump: Indicator on Exercise Navigator

After tagging, run NCERT proximity detection:
```python
# For each NCERT question in questiondata:
ncert_embed = embed(plain_text_version_of_ncert_question)
# Search jee_question_embeddings
top_jee = vector_search(ncert_embed, limit=1, threshold=0.85)
if top_jee.score >= 0.85:
    UPDATE questiondata SET jee_similar_question_id = top_jee.id,
                            jee_similarity_score = top_jee.score
    WHERE questionid = ncert_question_id
```

**Frontend indicator (in existing `PracticeSession.tsx` exercise navigator):**
- The exercise navigator right panel shows question chips (Q1, Q2, ... Q7 per exercise)
- For any question chip where `jee_similar_question_id IS NOT NULL`, render a small JEE badge icon (e.g., a flame or ★ icon) directly on the chip
- Tapping the chip opens the question as normal; the JEE overlay is shown as a dismissible banner within the question card: "This concept appears in JEE Main! [See example →]"
- This approach is visible at a glance across the full question list — no sidebar chip needed

### 3e. Pipeline

`question_tagger_pipeline.py`:
1. Fetch untagged questions from `jee_question_bank`
2. Generate `embed_text` for each question (Gemini plain-text conversion)
3. Batch embed (5-10/batch, reuse `GeminiClient`)
4. Hybrid vector+BM25 search → populate `jee_question_tags`
5. LLM batch call (difficulty + pattern combined) → update `jee_question_bank`
6. Run NCERT proximity detection → flag `questiondata.jee_similar_question_id`
7. Checkpoint per batch

---

## Module 4: Solution Generator

**Goal:** Pre-generate step-by-step solutions for all `jee_question_bank` questions using focused vector context instead of full chapter PDFs.

### 4a. Focused Context Approach (vs. Full PDF)

**Old approach (NCERT pipeline):** Upload full chapter PDF (~150 pages, ~300K tokens) to Gemini context cache. Works for NCERT because every question comes from that exact chapter. Cost: ~$0.30/question at 2024 pricing.

**New approach (JEE Ascent):** Use top-3 concept chunks from `ncert_concept_hierarchy` + 2 solved examples per concept (~4,500 tokens total) as the grounding context.

| Metric | Full PDF | Focused Context | Improvement |
|--------|----------|-----------------|-------------|
| Input tokens/question | ~300K | ~4,500 | **~95% reduction** |
| Cost/question (estimate) | ~$0.30 | ~$0.015 | **~20× cheaper** |
| Context relevance | All chapter content | Top-3 matching concepts | More focused |
| Cache TTL dependency | 1-hour Gemini cache | No cache needed | More resilient |

**Why this works better:** A JEE question tests 1-2 specific concepts. Retrieving exactly those concept chunks (with formulas and solved examples) provides all necessary grounding for solution generation — the surrounding chapter text adds noise, not signal.

**Context construction per question:**
```python
# 1. Get top-3 concept chunks via vector search (Module 3 tags already available)
concept_chunks = get_top_concepts(question_id, limit=3)

# 2. Build focused context
context = f"""
Relevant NCERT concepts for this {subject} question:

{concept1_title}: {concept1_description}
Key formulas: {concept1_embedding_text}
Solved example: {concept1_ncert_solved_example}

{concept2_title}: ...
{concept3_title}: ...
"""

# 3. Prompt SolverEngine with focused context
solution = solver_engine.generate(question_text, answer_key, context=context)
```

### 4b. Solution JSON Schema (exact, from `tutor_prompt.md`)

```json
{
  "steps": [{
    "step_number": 1,
    "step_type": "conceptual | calculation | visual",
    "hint": "<short nudge hint>",
    "explanation": "<detailed explanation with LaTeX>",
    "formula": "<LaTeX formula or null>"
  }],
  "final_answer": "<concise answer with units>",
  "visual_needed": {
    "required": false,
    "type": "none | diagram | graph | chemical_structure",
    "description": "<what to show>",
    "smiles": "<SMILES string if chemical>"
  }
}
```

> **Note:** Field names are `hint` and `formula` (not `nudge_hint`/`latex_formula`). Must match exactly for frontend compatibility.

### 4c. Pipeline

`jee_solution_pipeline.py`:
1. Fetch questions without solutions from `jee_question_bank`
2. For each question: retrieve top-3 concept chunks from `jee_question_tags` + `ncert_concept_hierarchy`
3. Construct focused context string (~4,500 tokens)
4. Reuse `SolverEngine.generate()` with focused context (no full PDF needed)
5. UPDATE `jee_question_bank.solution` with JSON
6. Checkpoint per batch (5 questions/batch)

**Phase 2 note:** Standardize `tutor_prompt.md` across NCERT Practice Session, JEE Ascent, and Student Feedback surfaces (currently using different prompts).

---

## Module 5: Question Generator

**Goal:** Generate additional questions to fill concept × difficulty × tier coverage gaps.

### 5a. Model Choice: RAG + Gemini vs. Fine-tuning

**Phase 1 — RAG + few-shot with Gemini 3.1 Pro (current choice):**

| Dimension | Assessment |
|-----------|------------|
| Speed to implement | 1-2 weeks (reuses GeminiClient, pgvector retrieval) |
| Quality | Determined by example quality from RAG; 70-80% auto-accept rate expected |
| Cost | ~$0.01/question at 2024 pricing |
| Training data needed | None |
| Limitations | May reproduce patterns from few-shot examples; subject-specific quirks need prompt tuning |

**Phase 2+ — Fine-tuning trigger criteria:**
Fine-tuning is appropriate when:
1. ≥ 500 verified high-quality questions exist (auto-accepted by rubric + human-reviewed)
2. Student performance data shows consistent correctness patterns (questions students get right/wrong repeatedly)
3. A specific failure mode is measurable (e.g., "generated Chemistry questions have wrong stoichiometry 15% of the time")

**Why not fine-tune in Phase 1:**
- No labeled training data yet — the generated questions ARE the training data
- Fine-tuning Gemini requires Vertex AI tuning jobs; significant engineering overhead
- RAG quality at JEE Main level is sufficient when examples are curated past papers

**Phase 2 fine-tuning pipeline (future):**
```
Input: 500+ verified (question, answer, subject, difficulty) pairs
Fine-tune: Gemini Flash (cheaper inference post-fine-tune)
Validation: hold-out rubric scores; compare to RAG baseline
Trigger: rubric score improvement > 5% on validation set
```

### 5b. RAG-based Generation Pipeline

**Trigger:** After M1-M3, identify gaps: `concept × difficulty × tier` combinations with < 5 questions.

**Pipeline (`jee_qgen_pipeline.py`):**
1. Find coverage gaps: `SELECT concept_id, difficulty, tier, COUNT(*) FROM jee_question_tags GROUP BY ...`
2. For each gap: retrieve top-3 similar existing questions via `jee_question_embeddings` (RAG examples)
3. Prompt Gemini:
   ```
   Generate a NEW {difficulty} {subject} question testing concept: {concept_title}
   (NCERT {chapter_title}, section {ncert_section})

   Relevant formulas: {embedding_text}
   Solved example for reference: {ncert_solved_example}

   3 example questions at this difficulty:
   [RAG examples with answers]

   Requirements: exactly one answer, clear wording, different scenario from examples
   Output JSON: { question_text, question_type, options, answer_key }
   ```
4. Run quality rubric (§5c)
5. INSERT with `is_generated=true`, run M3 tagging

### 5c. Quality Rubric (automated — Layer 1)

| Dimension | Check | Pass threshold |
|-----------|-------|----------------|
| Novelty | Cosine similarity to nearest existing question | < 0.85 |
| Correctness | Re-solve via Gemini; answer consistent | Match |
| Difficulty match | Re-classify; confirm level | Same |
| Ambiguity | LLM: "Exactly one correct answer?" | Yes |
| Clarity | LLM fluency check | Score > 0.8 |

Scoring: each dimension = 0.2 weight. Composite score 0–1.

| Score | Action |
|-------|--------|
| < 0.75 | Auto-reject (discard) |
| 0.75–0.90 | Flag for human review queue |
| > 0.90 | Auto-accept |

Store score in `jee_question_bank.generation_quality_score`.

### 5d. Human Review Queue (Layer 2)

Questions with `review_status = 'PENDING_REVIEW'` appear in an admin review view:
- Read-only display: question text + options + answer + rubric breakdown
- Actions: Approve / Reject / Edit-then-Approve
- Approved → `review_status = 'APPROVED'`, immediately available in Ascent sessions
- Rejected → `review_status = 'REJECTED'`, excluded from serving; used as negative training signal

**Implementation:** Simple admin-only Azure Functions endpoint + basic React view. Not part of the student-facing app. Can be a minimal table-based interface.

### 5e. Student Performance Signal (Layer 3)

Once Ascent sessions are live, student attempt data in `user_accent_attempts` feeds back into quality assessment:

```python
# Weekly offline job
for each generated question:
    attempts = user_accent_attempts WHERE question_id = ... AND was_skipped = FALSE
    if attempts.count >= 10:
        skip_rate = attempts.filter(was_skipped).count / attempts.count
        avg_time = mean(attempts.time_spent_seconds)

        if skip_rate > 0.6:
            # Students consistently skip this question → too hard or unclear
            flag_for_review(question_id, reason="high_skip_rate")

        if avg_time < 30:
            # Too fast to be genuine attempt → too easy or trivial
            flag_for_review(question_id, reason="too_quick")
```

This performance signal also feeds into the fine-tuning dataset when Phase 2 trigger criteria are met.

---

## Module 6: Progression Engine

**Goal:** Track per-user, per-chapter tier progress and trigger nudges at confidence thresholds.

### 6a. Confidence Heuristic

```
confidence = 0.5 × (questions_attempted / questions_in_tier)
           + 0.3 × (1 - skip_rate)
           + 0.2 × avg_time_factor    # 1.0 if time in expected range

Nudge trigger: confidence ≥ 0.70 AND questions_attempted ≥ 5
```

Weights are configurable. After Phase 3, collect student data to validate and retune.

**Nudge UI:** Non-blocking modal — "Ready to try [next tier]?" → "Yes, let's go!" / "Not yet"

### 6b. Lateral Jump (see §3d for indicator design)

When student is on a NCERT question in `PracticeSession` and `jee_similar_question_id IS NOT NULL`:
- The question chip in the exercise navigator shows a JEE badge icon
- Within the question card: a dismissible banner appears: "This concept appears in JEE Main! [See example →]"
- Clicking "See example" opens a modal with the linked JEE question (read-only, with solution)
- Dismissing either the chip badge or the banner persists dismissal for that question for that session

### 6c. New DB Tables

```sql
CREATE TABLE user_accent_progress (
  progress_id      SERIAL PRIMARY KEY,
  user_id          INT REFERENCES userprofiledata(userid),
  chapter_id       INT REFERENCES chapterdata(chapterid),
  current_tier     SMALLINT NOT NULL DEFAULT 2,
  tier2_confidence FLOAT DEFAULT 0,
  tier3_confidence FLOAT DEFAULT 0,
  tier4_confidence FLOAT DEFAULT 0,
  tier2_unlocked   BOOLEAN DEFAULT TRUE,
  tier3_unlocked   BOOLEAN DEFAULT FALSE,
  tier4_unlocked   BOOLEAN DEFAULT FALSE,
  nudge_shown_at   TIMESTAMP,
  last_active_at   TIMESTAMP,
  created_at       TIMESTAMP DEFAULT NOW(),
  updated_at       TIMESTAMP DEFAULT NOW(),
  UNIQUE (user_id, chapter_id)
);

CREATE TABLE user_accent_attempts (
  attempt_id         SERIAL PRIMARY KEY,
  user_id            INT REFERENCES userprofiledata(userid),
  question_id        VARCHAR(150) REFERENCES jee_question_bank(question_id),
  chapter_id         INT REFERENCES chapterdata(chapterid),
  tier               SMALLINT,
  time_spent_seconds INT,
  was_skipped        BOOLEAN DEFAULT FALSE,
  created_at         TIMESTAMP DEFAULT NOW()
);
```

---

## Module 7: API Layer (Azure Functions v4)

**New endpoints** — follow all existing patterns (`cors.ts`, `prisma.ts`, `azure-storage.ts`, `session.config.ts`).

| Method | Endpoint | Purpose |
|--------|---------|---------|
| GET | `/api/accent/session` | Next N questions for user+chapter+tier; SAS-signed image URLs |
| GET | `/api/accent/question/{id}` | Single question with SAS-signed images |
| POST | `/api/accent/progress` | Record attempt (time_spent, was_skipped) |
| GET | `/api/accent/status` | Current tier + confidence + nudge eligibility for a chapter |
| POST | `/api/accent/advance-tier` | User confirms tier advancement |
| GET | `/api/accent/chapter-map` | Chapters with JEE Ascent content + user tier per chapter |

### Key Response Shapes

**GET `/api/accent/session`:**
```json
{
  "tier": 3,
  "chapterId": 5,
  "questions": [{
    "questionId": "JEE_MAIN_2024_JAN_NQ12345",
    "questionText": "A particle...",
    "questionType": "MCQ",
    "options": [{"key": "A", "text": "2 m/s"}, {"key": "B", "text": "4 m/s"}],
    "difficulty": "Hard",
    "patternLabel": "projectile + friction",
    "visualData": { "imageUrl": "https://...?sas=..." },
    "tier": 3
  }],
  "progress": {
    "currentTier": 3,
    "tierConfidence": 0.72,
    "showNudge": true,
    "nextTierName": "More JEE Practice"
  }
}
```

**GET `/api/accent/status`:**
```json
{
  "chapterId": 5,
  "currentTier": 2,
  "tiersUnlocked": [2],
  "tierProgress": {
    "2": { "confidence": 0.72, "attempted": 8, "total": 15 },
    "3": { "confidence": 0, "attempted": 0, "total": 24 }
  },
  "showNudge": true
}
```

---

## Module 8: Frontend UX (Phase 3 — built last)

### Entry Point (No Separate Dashboard)

The PracticeDashboard already shows a "JEE Ascent" button on each chapter card. That button navigates directly to `AccentSession` for that chapter. **No separate `AccentDashboard` page is needed.**

The chapter card button shows a tier badge (e.g., "Tier 2 — NCERT+") so the student sees their current status at a glance before entering.

### New Pages

**`AccentSession.tsx` (`/accent/:chapterId`):**
- Tier progress bar at top (colour-coded: emerald=Tier2 / amber=Tier3 / rose=Tier4)
- Single-question view — same card layout as `PracticeSession`
- Prev/next navigation within current tier
- Solution accordion — reuse existing component (zero new rendering code)
- Nudge modal — slides up from bottom when confidence threshold hit; "Yes, let's go!" / "Not yet"
- Back button → returns to PracticeDashboard chapter card

### Changes to Existing Pages

**`PracticeSession.tsx`:**
1. Check each question chip for `jee_similar_question_id IS NOT NULL`
2. If set: render a small JEE icon badge on the chip (e.g., a coloured dot or flame icon)
3. Within question card: show a dismissible JEE proximity banner
4. Lateral jump modal: on click, fetch JEE question via `/api/accent/question/{id}` and display read-only with solution

Minimal change. Non-disruptive to existing flow.

### Tier Labels & Colours

| Tier | Colour | Label |
|------|--------|-------|
| 2 (Step-Up) | Emerald green | NCERT+ |
| 3 (JEE Main) | Amber | JEE Main |
| 4 (More JEE) | Rose | JEE+ |

**Nudge modal copy:**
> "You've done well on [Chapter]. Want to try real JEE Main questions for this chapter?"
> → [Let's go!] [Not yet]

---

## 3. Complete Database Schema Additions

```sql
-- 1. Enable pgvector (once per DB)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Enhance existing DataCollection table
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS blob_url VARCHAR(500);
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS paper_format VARCHAR(50);
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'PENDING';

-- 3. New tables (dependency order)
--    jee_question_papers → jee_question_bank → jee_question_tags
--    ncert_concept_hierarchy → ncert_concept_embeddings → jee_question_embeddings
--    user_accent_progress → user_accent_attempts

-- 4. Alter existing NCERT question table
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS jee_similar_question_id VARCHAR(150);
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS jee_similarity_score FLOAT;
```

All DDL to be added to `Scripts/DB_Master.sql` and reflected in `apps/functions/prisma/schema.prisma`.

**Total new tables: 8** (`jee_question_papers`, `jee_question_bank`, `jee_question_tags`, `jee_question_embeddings`, `ncert_concept_hierarchy`, `ncert_concept_embeddings`, `user_accent_progress`, `user_accent_attempts`)

---

## 4. Pipelines Summary

| Pipeline | New file | Input | Reuses |
|----------|----------|-------|--------|
| JEE Downloader (enhanced) | `download_exam_papers.py` (modified) | NTA site | Selenium; adds blob upload + backoff |
| JEE Extraction | `jee_extraction_pipeline.py` | PDFs from blob | `GeminiClient`, Stage 1 prompts; NTA ID handling |
| Concept Index | `concept_index_pipeline.py` | NCERT PDFs (from `chapterdata`) | `GeminiClient`, `BlobClient` |
| Question Tagger | `question_tagger_pipeline.py` | `jee_question_bank` + concept index | `run_question_tagging.py`, `GeminiClient`, pgvector hybrid search |
| Solution Generator | `jee_solution_pipeline.py` | `jee_question_bank` (no solution) | `SolverEngine`, `tutor_prompt.md`; focused context instead of full PDF |
| Question Generator | `jee_qgen_pipeline.py` | Coverage gap analysis | `GeminiClient`, pgvector RAG, 3-layer quality evaluation |

All pipelines: checkpoint JSON in `Output/`, resumable, `--force-rerun` / `--dry-run` flags.

New folder: `pipelines/JEEAccentPipeline/`

---

## 5. Phase Roadmap

### Phase 1 — Core Data Infrastructure
Offline/async modules only. No UX.

| Step | Module | Deliverable |
|------|--------|-------------|
| 1 | M0 | `Data/JEEAudit.md` — inventory of existing JEE data |
| 2 | M1 | `jee_question_bank` populated (3-5 years of JEE Main); NTA IDs preserved; PDFs in blob |
| 3 | M2 | NCERT concept hierarchy + embeddings (all 74 chapters); `embedding_text` + solved examples |
| 4 | M3 | All questions tagged (concepts via hybrid search + difficulty + pattern) |
| 5 | M4 | Solutions pre-generated (focused vector context, ~20× cost saving vs. full PDF) |
| 6 | M5 | Generated questions fill coverage gaps; 3-layer evaluation running |

**Gate:** End-to-end tested on one subject (e.g., Physics) before expanding.

### Phase 2 — API + Progression Engine
API-testable without UI.

| Step | Deliverable |
|------|-------------|
| M6 | Progression engine implemented + unit tested |
| M7 | All 6 API endpoints live + Postman collection |
| — | Solution prompt standardized across all 3 surfaces (NCERT, Ascent, Student Feedback) |
| — | NCERT lateral jump flags populated; exercise navigator chip badges |
| — | Admin human review queue view for generated questions |

### Phase 3 — Frontend UX

| Step | Deliverable |
|------|-------------|
| M8 | `AccentSession` page wired from PracticeDashboard chapter card button |
| — | Tier progress bar + nudge modal |
| — | Lateral jump JEE icon badges on question chips in PracticeSession |
| — | Lateral jump modal (read-only JEE question + solution) |

### Phase 4 — Iteration & Quality

- Spot quizzes (timed mini-tests within a tier)
- Inline real-time feedback on JEE attempts (reuse Student Feedback pipeline)
- Student performance signals feed back into question quality flags (Layer 3)
- Fine-tune question generation model when ≥ 500 verified examples + measurable failure mode
- GCP migration: Azure Functions → Cloud Run; Azure Queue → Pub-Sub; Azure Blob → GCS

---

## 6. Technology Decisions

| Choice | Rationale |
|--------|-----------|
| pgvector on existing PostgreSQL | ~6-8K vectors; no new infra; SQL joins work naturally |
| `embedding_text` preprocessing for LaTeX | Embedding models cannot interpret raw LaTeX; plain-text conversion is mandatory |
| Hybrid search: pgvector + BM25 | Vectors for semantics; BM25 for exact formula/keyword matching — complement each other |
| HNSW index (`vector_cosine_ops`) | Better recall than IVFFlat at this scale; no training step |
| Gemini `text-embedding-005` (768 dims) | Cheapest; strong STEM performance; integrates with existing Gemini usage |
| Focused context for solution generation | ~95% token reduction vs. full PDF; 2-3 relevant concept chunks are sufficient |
| RAG + few-shot question generation (Phase 1) | No training data; weeks vs. months to implement; quality scales with example quality |
| Fine-tune reserved for Phase 2+ | Trigger: ≥500 verified examples + measurable failure mode; not before |
| 3-layer question evaluation | Automated rubric + human review queue + student performance → progressive quality |
| NTA ID preservation | Deterministic answer-key linkage; traceability to official source |
| Entry via existing PracticeDashboard button | No new dashboard page needed; JEE Ascent button already in UI |
| JEE icon on exercise navigator chips | Visible across full question list; non-disruptive to reading flow |
| Same solution JSON schema as NCERT | Zero new frontend rendering code |
| Standard Python + PostgreSQL + REST | Cloud-agnostic; easy swap Azure → GCP |

---

## 7. Verification Plan

| Module | Test |
|--------|------|
| M0 | Manual: `JEEAudit.md` covers all known data locations |
| M1 | Run enhanced downloader; verify PDF uploaded to blob; run extraction on 1 paper; verify ≥70 questions with correct NTA IDs and answer key cross-references |
| M2 | Run on 1 chapter; verify concept hierarchy in DB including `embedding_text` and `ncert_solved_example`; cosine similarity sanity check on 3 embeddings; verify BM25 index works |
| M3 | Tag 10 questions; manually verify top-1 concept links are semantically correct; check difficulty/pattern; verify at least 2 NCERT questions are flagged with JEE proximity |
| M4 | Generate solutions for 5 questions across subjects using focused context; verify JSON matches `questiondata.solution` schema; render in browser; confirm token count < 5K per question |
| M5 | Generate 5 questions for one gap; verify rubric scores; confirm novelty check rejects near-duplicates; verify PENDING_REVIEW questions appear in admin review view |
| M6 | Seed mock attempts; verify confidence score computation; verify nudge flag in API response |
| M7 | Postman collection: all 6 endpoints; verify SAS tokens on image URLs |
| M8 | E2E: PracticeDashboard "JEE Ascent" button → AccentSession → view question → solution accordion → tier nudge modal → advance tier; separately: NCERT question with JEE badge chip → lateral jump modal |

---

## 8. Critical Files Reference

| Purpose | Path |
|---------|------|
| **Reuse:** Gemini client (cache, batch, retry, images) | `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py` |
| **Reuse:** Stage 1 extraction engine (PDF parsing, sliding window) | `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/extraction_engine.py` |
| **Reuse:** Stage 2 solver engine (solution generation) | `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/solver_engine.py` |
| **Reuse:** Tutor prompt template (exact field names: `hint`, `formula`) | `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/tutor_prompt.md` |
| **Reuse:** E2E orchestrator pattern (checkpointing) | `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/e2e_pipeline.py` |
| **Reuse:** Existing JEE tagging pipeline | `pipelines/ExtractionPipeline/JSONBasedExtraction/run_question_tagging.py` |
| **Reuse:** Existing JEE tagging prompt | `pipelines/ExtractionPipeline/JSONBasedExtraction/JEEMainQuestionPaper_NTA_Tagging.txt` |
| **Modify:** JEE Main PDF downloader | `pipelines/DataCollection/download_exam_papers.py` |
| **Reuse:** Download pipeline README | `pipelines/DataCollection/EXAM_PAPER_DOWNLOAD_README.md` |
| **Reuse:** Azure Functions patterns | `apps/functions/src/functions/practiceQuestion.ts` |
| **Reuse:** SAS token generation | `apps/functions/src/utils/azure-storage.ts` |
| **Reuse + Modify:** Practice session (question card, accordion, navigator chips) | `apps/FrontEnd/src/pages/PracticeSession.tsx` |
| **Extend:** DB schema (SQL) | `Scripts/DB_Master.sql` |
| **Extend:** Prisma schema (ORM) | `apps/functions/prisma/schema.prisma` |
| **Extend:** Existing question table | `questiondata` — add `jee_similar_question_id`, `jee_similarity_score` |
| **New:** JEE pipelines folder | `pipelines/JEEAccentPipeline/` |
| **New:** Azure Functions | `apps/functions/src/functions/accent*.ts` |
| **New:** Frontend session page | `apps/FrontEnd/src/pages/AccentSession.tsx` |
