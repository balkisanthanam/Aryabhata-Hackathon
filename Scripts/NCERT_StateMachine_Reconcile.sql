-- NCERT State Machine — Reconciliation (W0)
-- ------------------------------------------------------------------
-- Verified live DB state 2026-05-21 (verify_db_state.py):
--   questiondata already has review_status (DEFAULT 'LEGACY'), is_generated,
--   retry_count, answer_key. The 'Retrofit' migration is the one applied;
--   the conflicting 'UNVERIFIED'-default migration was NOT applied.
--   Row distribution is valid (LEGACY/MATH_PASSED/REJECTED/MATH_REGENERATED).
--   => No column adds and NO backfill required.
--
-- The only gap: no CHECK constraint on review_status, so a typo'd status
-- string would silently create a dead state. This script adds that guard.
-- Idempotent — safe to re-run.
-- ------------------------------------------------------------------

-- Defensive column ensures (no-ops on the current DB; documents the contract).
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS review_status VARCHAR(50) DEFAULT 'LEGACY';
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS is_generated  BOOLEAN     DEFAULT FALSE;
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS retry_count   INT         DEFAULT 0;
ALTER TABLE questiondata ADD COLUMN IF NOT EXISTS answer_key    TEXT;

-- Enumerate the valid state-machine statuses. NULL is permitted (CHECK passes
-- on NULL); the column default 'LEGACY' means new rows are never NULL anyway.
ALTER TABLE questiondata DROP CONSTRAINT IF EXISTS chk_questiondata_review_status;
ALTER TABLE questiondata ADD CONSTRAINT chk_questiondata_review_status
    CHECK (review_status IN (
        'LEGACY',
        'MATH_PASSED',
        'REJECTED',
        'MATH_REGENERATED',
        'PEDAGOGY_ADDED',
        'APPROVED',
        'APPROVED_GOLD',
        'NEEDS_HUMAN_REVIEW',
        'GENERATION_FAILED'
    ));
