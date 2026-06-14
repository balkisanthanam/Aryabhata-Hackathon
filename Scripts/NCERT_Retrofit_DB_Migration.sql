-- NCERT Retrofit DB Migration 
-- Adds state machine tracking and answer keys to the legacy questiondata table.

ALTER TABLE questiondata
ADD COLUMN review_status VARCHAR(50) DEFAULT 'LEGACY',
ADD COLUMN is_generated BOOLEAN DEFAULT FALSE,
ADD COLUMN retry_count INT DEFAULT 0,
ADD COLUMN answer_key TEXT;

-- Create an index to speed up the fetching of rows per status
CREATE INDEX ix_questiondata_review_status ON questiondata(review_status);
