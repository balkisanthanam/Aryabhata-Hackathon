-- ============================================================
-- M2 Patch — Live DB Migration
-- Target:  <DB_HOST>
-- Safe to re-run: uses IF NOT EXISTS / OR REPLACE / IF EXISTS guards.
--
-- What this patch does:
--   1. Extends the content_type CHECK constraint on ncert_concept_hierarchy
--      to allow the new 'data_table' type.
--   2. Updates fn_ncert_concept_tsv() to index all 4 text fields for BM25
--      (was: chunk_text only; now: concept_title + chunk_text + description
--       + embedding_text).
--   3. Recreates the trigger to fire on updates to any of the 4 indexed fields
--      (was: UPDATE OF chunk_text only).
--   4. Backfills tsv_content for all 2,432 existing rows using the new function.
--   5. Adds an embed_text TEXT column to ncert_concept_embeddings for
--      audit and re-embedding without re-extraction.
--
-- Run order matters — execute top to bottom.
-- After this patch, re-extract the ~15 chapters that have reference data tables
-- (Electrochemistry, Thermodynamics, Periodicity, Chemical Bonding, etc.)
-- using: python batch_run.py --chapter-ids 25,31,32,33,51,52,54,55,60,62,66,68,74
-- ============================================================


-- ============================================================
-- Step 1: Extend content_type CHECK constraint to include 'data_table'
-- ============================================================
-- PostgreSQL names inline CHECK constraints as <table>_<column>_check.
ALTER TABLE ncert_concept_hierarchy
    DROP CONSTRAINT IF EXISTS ncert_concept_hierarchy_content_type_check;

ALTER TABLE ncert_concept_hierarchy
    ADD CONSTRAINT ncert_concept_hierarchy_content_type_check
    CHECK (content_type IN (
        'definition', 'theorem', 'formula', 'worked_example', 'concept', 'data_table'
    ));


-- ============================================================
-- Step 2: Update trigger function to index all 4 text fields
-- ============================================================
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


-- ============================================================
-- Step 3: Recreate trigger with updated firing columns
-- ============================================================
DROP TRIGGER IF EXISTS trg_ncert_concept_tsv ON ncert_concept_hierarchy;
CREATE TRIGGER trg_ncert_concept_tsv
    BEFORE INSERT OR UPDATE OF concept_title, chunk_text, description, embedding_text
    ON ncert_concept_hierarchy
    FOR EACH ROW EXECUTE FUNCTION fn_ncert_concept_tsv();


-- ============================================================
-- Step 4: Backfill tsv_content for all existing rows (~2,432 rows)
-- Touching chunk_text fires the trigger for every row, rebuilding tsv_content
-- using the new 4-field concatenation.
-- ============================================================
UPDATE ncert_concept_hierarchy SET chunk_text = chunk_text;


-- ============================================================
-- Step 5: Add embed_text column to ncert_concept_embeddings
-- ============================================================
ALTER TABLE ncert_concept_embeddings ADD COLUMN IF NOT EXISTS embed_text TEXT;
