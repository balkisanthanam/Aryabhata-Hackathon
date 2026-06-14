
CREATE TABLE exam_papers (
    id SERIAL PRIMARY KEY,
    ExamName VARCHAR(255),
    PaperName VARCHAR(500),
    Year INTEGER,
    DateOfExam DATE,
    Shift VARCHAR(50),
    FileName VARCHAR(500)
);

CREATE INDEX idx_examyear ON exam_papers(ExamName, Year);

-- JEE Ascent additions: blob storage, format detection, extraction pipeline state
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS blob_url VARCHAR(500);
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS paper_format VARCHAR(50);  -- 'PRE_2021', '2021_PLUS', 'UNKNOWN'
ALTER TABLE exam_papers ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'PENDING';
-- extraction_status values: 'PENDING', 'EXTRACTED', 'FAILED'

-- Unique constraint on (ExamName, Year, DateOfExam, Shift) — identifies one paper per exam/date/session.
-- Migration: drop old PaperName-based constraint if it exists, then add the correct one.
ALTER TABLE exam_papers DROP CONSTRAINT IF EXISTS uq_exam_paper;
ALTER TABLE exam_papers ADD CONSTRAINT uq_exam_paper UNIQUE (ExamName, Year, DateOfExam, Shift);

-- Answer key table: one row per downloaded answer key PDF from NTA archive
CREATE TABLE IF NOT EXISTS exam_answer_keys (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500),              -- original title from NTA archive page
    year INTEGER,
    session VARCHAR(50),             -- e.g. 'Session 1', 'FEB', 'AUG', 'All'
    key_type VARCHAR(20),            -- 'FINAL' or 'PROVISIONAL'
    blob_url VARCHAR(500),
    filename VARCHAR(500),
    extraction_status VARCHAR(20) DEFAULT 'PENDING'
    -- extraction_status values: 'PENDING', 'EXTRACTED', 'FAILED'
);
CREATE INDEX IF NOT EXISTS idx_answerkey_year ON exam_answer_keys(year, session);
ALTER TABLE exam_answer_keys
    ADD CONSTRAINT uq_answer_key UNIQUE (year, session, key_type);


