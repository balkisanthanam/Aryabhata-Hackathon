-- Migration to introduce review_status for the NCERT Data Cleanse / Pipeline Gate.
ALTER TABLE questiondata
ADD COLUMN IF NOT EXISTS review_status VARCHAR(50) DEFAULT 'UNVERIFIED';

-- Backfill exiting rows if they are null
UPDATE questiondata
SET review_status = 'UNVERIFIED'
WHERE review_status IS NULL;
