-- ============================================================
-- JEE Ascent — M1d Database Migration v2
-- Target:  <DB_HOST>
-- Safe to re-run: all statements use IF NOT EXISTS guards.
--
-- Changes from v1:
--   - Removed CHECK constraints on class/subject (extensibility)
--   - Added ltree extension + path column (efficient subtree queries)
--   - Added figure_url to ncert_concept_hierarchy
--   - Replaced ALTER TABLE questiondata (jee_similar_question_id/score)
--     with ncert_jee_similarity junction table (many-to-many)
--   - Added ncert_jee_similarity indexes
-- ============================================================
--
-- HYBRID SEARCH QUERY PATTERN (reference):
--
--   SELECT nch.chunk_text,
--     0.7 * (1 - (nce.embedding <=> query_vec::vector)) +
--     0.3 * ts_rank(nch.tsv_content, plainto_tsquery('english', 'query'))
--     AS combined_score
--   FROM ncert_concept_hierarchy nch
--   JOIN ncert_concept_embeddings nce ON nce.concept_id = nch.id
--   WHERE nch.class = 11 AND nch.subject = 'physics'
--     AND nch.chapter_id = X
--   ORDER BY combined_score DESC LIMIT 5;
--
-- LTREE SUBTREE QUERY PATTERN (reference):
--
--   -- Get a concept and all its children:
--   SELECT * FROM ncert_concept_hierarchy
--   WHERE path <@ 'C1.S2';
--
--   -- Get direct children only:
--   SELECT * FROM ncert_concept_hierarchy
--   WHERE path ~ 'C1.S2.*{1}';
-- ============================================================


-- ============================================================
-- 0. Extensions
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector: VECTOR type + HNSW index
CREATE EXTENSION IF NOT EXISTS ltree;    -- ltree: hierarchical path queries


-- ============================================================
-- 1. Alter existing tables
-- ============================================================

-- exam_papers — already migrated in JEEMainDownloadScripts.sql;
-- IF NOT EXISTS guards make this idempotent on a live DB.
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS blob_url           VARCHAR(500);
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS paper_format       VARCHAR(50);   -- 'PRE_2021', '2021_PLUS', 'UNKNOWN'
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS extraction_status  VARCHAR(20) DEFAULT 'PENDING';
                                                                                   -- 'PENDING', 'EXTRACTED', 'FAILED'

-- NOTE: jee_similar_question_id / jee_similarity_score have been
-- replaced by the ncert_jee_similarity junction table (§2j below).
-- Do NOT add scalar FK columns to questiondata.


-- ============================================================
-- 2. New tables
-- Creation order respects FK dependencies.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- 2a. ncert_concept_hierarchy
--     Relational concept tree extracted from NCERT chapter PDFs (M2).
--
--     Column purposes:
--       concept_title        — name of the node (e.g. "Lorentz Force")
--       description          — main prose explanation of the concept
--       key_formulas         — LaTeX string for frontend rendering (e.g. $F=qv\times B$)
--       embedding_text       — plain-English translation of the concept/formula
--                             MANDATORY: raw LaTeX produces near-zero cosine
--                             similarity with verbal query vectors. Every row
--                             must have embedding_text populated.
--       ncert_solved_example — step-by-step text of the NCERT worked example
--       chunk_text           — 200-400 token retrieval unit (used for RAG)
--       figure_url           — blob URL for associated diagram/figure image
--       path                 — ltree path for hierarchy (e.g. 'C1', 'C1.S1', 'C1.S1.M1')
--                             Level 1: root concepts (C1, C2, ...)
--                             Level 2: sub-concepts (C1.S1, C1.S2, ...)
--                             Level 3: specific mechanisms/formulas (C1.S1.M1, ...)
--       content_type         — controls which content columns are populated:
--                             'definition'    → description
--                             'theorem'       → description + key_formulas
--                             'formula'       → key_formulas + embedding_text
--                             'worked_example'→ ncert_solved_example
--                             'concept'       → description
--       class, subject       — no CHECK constraints; validated by application
--                             logic against classsubjectdata master table.
--                             Allows future extension to Biology, Class 10, etc.
--       tsv_content          — auto-updated via trigger for hybrid BM25 search
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ncert_concept_hierarchy (
    id                   SERIAL PRIMARY KEY,
    chapter_id           INT          REFERENCES chapterdata(chapterid) ON DELETE CASCADE,
    parent_id            INT          REFERENCES ncert_concept_hierarchy(id),
    path                 ltree,                              -- e.g. 'C1.S1.M1'
    concept_title        TEXT         NOT NULL,
    description          TEXT,
    key_formulas         TEXT,                               -- LaTeX for UI rendering
    embedding_text       TEXT,                               -- plain-English for embedding (MANDATORY)
    ncert_solved_example TEXT,                               -- worked example text
    content_type         TEXT         CHECK (content_type IN
                                         ('definition', 'theorem', 'formula',
                                          'worked_example', 'concept', 'data_table')),
    chunk_text           TEXT,                               -- 200-400 token retrieval chunk
    chunk_index          INT,                                -- ordinal position within chapter
    figure_url           TEXT,                               -- blob URL for diagram/figure
    class                INT,                                -- 11 or 12 (no CHECK — extensible)
    subject              TEXT,                               -- physics/chemistry/maths/etc (no CHECK)
    tsv_content          TSVECTOR,                           -- auto-updated via trigger
    created_at           TIMESTAMPTZ  DEFAULT NOW()
);

-- Standard indexes
CREATE INDEX IF NOT EXISTS idx_ncert_concept_chapter
    ON ncert_concept_hierarchy (chapter_id);

CREATE INDEX IF NOT EXISTS idx_ncert_concept_class_subject
    ON ncert_concept_hierarchy (class, subject);

-- ltree index: efficient subtree and ancestor queries
CREATE INDEX IF NOT EXISTS idx_ncert_concept_path
    ON ncert_concept_hierarchy USING GIST (path);

-- GIN index: BM25 keyword-search component of hybrid search
CREATE INDEX IF NOT EXISTS idx_ncert_concept_tsv
    ON ncert_concept_hierarchy USING GIN (tsv_content);

-- Trigger function: auto-populate tsv_content from all indexed text fields
CREATE OR REPLACE FUNCTION fn_ncert_concept_tsv()
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_content := to_tsvector('english',
        COALESCE(NEW.concept_title, '')  || ' ' ||
        COALESCE(NEW.chunk_text, '')     || ' ' ||
        COALESCE(NEW.description, '')    || ' ' ||
        COALESCE(NEW.embedding_text, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ncert_concept_tsv ON ncert_concept_hierarchy;
CREATE TRIGGER trg_ncert_concept_tsv
    BEFORE INSERT OR UPDATE OF concept_title, chunk_text, description, embedding_text
    ON ncert_concept_hierarchy
    FOR EACH ROW EXECUTE FUNCTION fn_ncert_concept_tsv();


-- ────────────────────────────────────────────────────────────
-- 2b. ncert_concept_embeddings
--     768-dim vectors (text-embedding-005) for each concept row.
--     HNSW index: approximate nearest-neighbour search for M3 tagging
--     and M4 focused-context retrieval.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ncert_concept_embeddings (
    id         SERIAL PRIMARY KEY,
    concept_id INT UNIQUE    REFERENCES ncert_concept_hierarchy(id) ON DELETE CASCADE,
    embedding  VECTOR(768),
    embed_text TEXT,                                            -- composite text that was embedded (for audit/re-embed)
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

-- HNSW index: cosine distance — matches the hybrid query's (embedding <=> query_vec)
CREATE INDEX IF NOT EXISTS idx_ncert_concept_emb_hnsw
    ON ncert_concept_embeddings USING hnsw (embedding vector_cosine_ops);

-- M2 Patch: add embed_text column to existing installations
ALTER TABLE ncert_concept_embeddings ADD COLUMN IF NOT EXISTS embed_text TEXT;


-- ────────────────────────────────────────────────────────────
-- 2c. jee_answer_mappings
--     NTA question ID → correct option ID, extracted from answer
--     key PDFs in M1b Step 1. nta_question_id is the sole join
--     key to question papers — no DB-level FK between papers and
--     answer keys by design (see DataCollection/CLAUDE.md).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jee_answer_mappings (
    nta_question_id   TEXT PRIMARY KEY,
    correct_option_id TEXT,
    source_key_id     INT         REFERENCES exam_answer_keys(id),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);


-- ────────────────────────────────────────────────────────────
-- 2d. jee_question_bank
--     All non-NCERT questions:
--       tier 2 = Step-up (M1c / M5)
--       tier 3 = JEE Main extracted (M1b)
--       tier 4 = JEE Advanced (future)
--     answer_key is set at extraction time via jee_answer_mappings lookup.
--     solution schema must match questiondata.solution for frontend reuse:
--       { "steps": [{ step_number, step_type, hint, explanation, formula }],
--         "final_answer": "...",
--         "visual_needed": { required, type, description, smiles } }
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jee_question_bank (
    id                    SERIAL PRIMARY KEY,
    nta_question_id       TEXT,
    exam_paper_id         INT          REFERENCES exam_papers(id),
    year                  INT,
    dateofexam            DATE,
    shift                 TEXT,
    subject               TEXT,
    section               TEXT,                        -- 'MCQ' or 'Integer'
    tier                  INT          DEFAULT 3,       -- 2 / 3 / 4
    question_content      JSONB,
    answer_key            TEXT,                        -- NULL if no matching AK entry
    solution              JSONB,                       -- populated by M4
    difficulty            TEXT,                        -- 'EASY','MEDIUM','HARD' — M3
    difficulty_confidence FLOAT,                       -- 0.0–1.0 — M3
    pattern_label         TEXT,                        -- e.g. 'kinematics_projectile' — M3
    is_generated          BOOL         DEFAULT FALSE,   -- TRUE for M5-generated questions
    review_status         TEXT         DEFAULT 'APPROVED',
    source                TEXT         DEFAULT 'NTA_EXTRACTED',      evaluator_score       JSONB,                       -- AI evaluation JSON payload
      retry_count           INT          DEFAULT 0,      -- Generation retry count    created_at            TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jee_qbank_subject    ON jee_question_bank (subject);
CREATE INDEX IF NOT EXISTS idx_jee_qbank_year       ON jee_question_bank (year);
CREATE INDEX IF NOT EXISTS idx_jee_qbank_tier       ON jee_question_bank (tier);
CREATE INDEX IF NOT EXISTS idx_jee_qbank_nta_id     ON jee_question_bank (nta_question_id);
CREATE INDEX IF NOT EXISTS idx_jee_qbank_paper      ON jee_question_bank (exam_paper_id);

-- Idempotency guard: one row per (exam_paper_id, nta_question_id). Without this,
-- `ON CONFLICT DO NOTHING` in db_writer.bulk_insert_questions is a no-op and every
-- re-run of the crop pipeline creates a full set of duplicate rows.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_jee_qbank_paper_nta'
    ) THEN
        ALTER TABLE jee_question_bank
            ADD CONSTRAINT uq_jee_qbank_paper_nta
            UNIQUE (exam_paper_id, nta_question_id);
    END IF;
END $$;


-- ────────────────────────────────────────────────────────────
-- 2e. jee_question_papers
--     Enriched paper metadata populated after M1b extraction.
--     One row per successfully processed exam_papers row.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jee_question_papers (
    id              SERIAL PRIMARY KEY,
    exam_paper_id   INT UNIQUE   REFERENCES exam_papers(id),
    year            INT,
    session         TEXT,
    shift           TEXT,
    subject_counts  JSONB,
    total_questions INT,
    paper_format    TEXT,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);


-- ────────────────────────────────────────────────────────────
-- 2f. jee_question_tags
--     Many-to-many: jee_question_bank ↔ ncert_concept_hierarchy.
--     Populated by M3 via hybrid vector + BM25 search (top-3 per question).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jee_question_tags (
    id               SERIAL PRIMARY KEY,
    question_id      INT         REFERENCES jee_question_bank(id) ON DELETE CASCADE,
    concept_id       INT         REFERENCES ncert_concept_hierarchy(id) ON DELETE CASCADE,
    similarity_score FLOAT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (question_id, concept_id)
);

CREATE INDEX IF NOT EXISTS idx_jee_qtags_question ON jee_question_tags (question_id);
CREATE INDEX IF NOT EXISTS idx_jee_qtags_concept  ON jee_question_tags (concept_id);


-- ────────────────────────────────────────────────────────────
-- 2g. jee_question_embeddings
--     768-dim vectors per JEE question.
--     Used for: lateral jump detection (M3) + M5 novelty check.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jee_question_embeddings (
    id          SERIAL PRIMARY KEY,
    question_id INT UNIQUE    REFERENCES jee_question_bank(id) ON DELETE CASCADE,
    embedding   VECTOR(768),
    embed_text  TEXT,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jee_qemb_hnsw
    ON jee_question_embeddings USING hnsw (embedding vector_cosine_ops);


-- ────────────────────────────────────────────────────────────
-- 2h. user_accent_progress
--     Per-user, per-chapter tier state and confidence score.
--     Confidence heuristic (M6):
--       0.5 × (questions_attempted / questions_available_in_tier)
--       + 0.3 × (1 − skip_rate)
--       + 0.2 × avg_time_factor
--     Tier-advance nudge fires when confidence ≥ 0.70 AND attempts ≥ 5.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_accent_progress (
    id                  SERIAL PRIMARY KEY,
    user_id             INT         REFERENCES userprofiledata(userid) ON DELETE CASCADE,
    chapter_id          INT         REFERENCES chapterdata(chapterid),
    current_tier        INT         DEFAULT 2,
    confidence          FLOAT       DEFAULT 0.0,
    questions_attempted INT         DEFAULT 0,
    skip_rate           FLOAT       DEFAULT 0.0,
    avg_time_factor     FLOAT       DEFAULT 0.0,
    tier_unlocked_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, chapter_id)
);

CREATE INDEX IF NOT EXISTS idx_user_accent_progress_user
    ON user_accent_progress (user_id);

CREATE OR REPLACE FUNCTION fn_user_accent_progress_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_accent_progress_updated_at ON user_accent_progress;
CREATE TRIGGER trg_user_accent_progress_updated_at
    BEFORE UPDATE ON user_accent_progress
    FOR EACH ROW EXECUTE FUNCTION fn_user_accent_progress_updated_at();


-- ────────────────────────────────────────────────────────────
-- 2i. user_accent_attempts
--     Individual attempt records. Feeds confidence computation
--     in GET /api/accent/status.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_accent_attempts (
    id                 SERIAL PRIMARY KEY,
    user_id            INT         REFERENCES userprofiledata(userid) ON DELETE CASCADE,
    question_id        INT         REFERENCES jee_question_bank(id),
    chapter_id         INT         REFERENCES chapterdata(chapterid),
    tier               INT,
    time_spent_seconds INT,
    was_skipped        BOOL        DEFAULT FALSE,
    attempted_at       TIMESTAMPTZ DEFAULT NOW(),
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_accent_attempts_user
    ON user_accent_attempts (user_id);

CREATE INDEX IF NOT EXISTS idx_user_accent_attempts_question
    ON user_accent_attempts (question_id);

ALTER TABLE user_accent_attempts ADD COLUMN IF NOT EXISTS was_correct BOOLEAN;

-- ────────────────────────────────────────────────────────────
-- 2j. ncert_jee_similarity
--     Many-to-many: questiondata (NCERT) ↔ jee_question_bank.
--     Replaces the scalar jee_similar_question_id/jee_similarity_score
--     columns on questiondata. Allows multiple JEE matches per NCERT
--     question, ranked by similarity_score.
--
--     Frontend lateral jump: query top-3 by similarity_score DESC
--     for a given ncert_question_id to show JEE proximity badges.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ncert_jee_similarity (
    id                SERIAL PRIMARY KEY,
    ncert_question_id INT         REFERENCES questiondata(questionid) ON DELETE CASCADE,
    jee_question_id   INT         REFERENCES jee_question_bank(id) ON DELETE CASCADE,
    similarity_score  FLOAT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ncert_question_id, jee_question_id)
);

CREATE INDEX IF NOT EXISTS idx_ncert_jee_sim_ncert
    ON ncert_jee_similarity (ncert_question_id);

CREATE INDEX IF NOT EXISTS idx_ncert_jee_sim_jee
    ON ncert_jee_similarity (jee_question_id);
