-- Working SQL scratchpad for JEE / NCERT data maintenance.
--
-- Organization rules:
-- 1. Keep representative queries near the top.
-- 2. Group by concept/table family.
-- 3. Move likely-removable or superseded variants to the archive section.
-- 4. Edit the hardcoded IDs / dates / years inline before running.

-- region System / Schema Inspection

SELECT *
FROM pg_available_extensions
WHERE name = 'ltree';

SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'jee_question_bank'
ORDER BY table_name, ordinal_position;

SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'jee_question_bank'
ORDER BY ordinal_position;

-- endregion


-- region NCERT Concept Hierarchy / Embeddings

-- Chapter-level hierarchy + embedding counts.
-- Replace chapter_id as needed.
SELECT COUNT(*)
FROM ncert_concept_hierarchy
WHERE chapter_id = 1;

SELECT COUNT(*)
FROM ncert_concept_embeddings e
JOIN ncert_concept_hierarchy h ON h.id = e.concept_id
WHERE h.chapter_id = 1;

-- Delete a chapter's hierarchy before reloading.
-- Replace chapter_id as needed.
DELETE FROM ncert_concept_hierarchy
WHERE chapter_id = 1;

-- Fix missing parent_id values for one chapter.
-- Replace chapter_id as needed.
UPDATE ncert_concept_hierarchy child
SET parent_id = parent.id
FROM ncert_concept_hierarchy parent
WHERE child.chapter_id = 42
  AND child.parent_id IS NULL
  AND child.path::text LIKE '%.%'
  AND parent.chapter_id = 42
  AND parent.path = subpath(child.path, 0, nlevel(child.path) - 1);

-- Verify that only true roots have parent_id = NULL.
SELECT COUNT(*)
FROM ncert_concept_hierarchy
WHERE chapter_id = 42
  AND parent_id IS NULL
  AND path::text LIKE '%.%';

-- Inspect orphaned nodes and their expected parent path.
SELECT
    child.path::text AS orphan_path,
    subpath(child.path, 0, nlevel(child.path) - 1)::text AS expected_parent_path,
    parent.id AS parent_exists
FROM ncert_concept_hierarchy child
LEFT JOIN ncert_concept_hierarchy parent
    ON parent.chapter_id = 42
   AND parent.path = subpath(child.path, 0, nlevel(child.path) - 1)
WHERE child.chapter_id = 42
  AND child.parent_id IS NULL
  AND child.path::text LIKE '%.%';

-- Coverage summary by subject/class.
SELECT subject, class, COUNT(*) AS chapters, SUM(node_count) AS nodes
FROM (
    SELECT subject, class, chapter_id, COUNT(*) AS node_count
    FROM ncert_concept_hierarchy
    GROUP BY subject, class, chapter_id
) t
GROUP BY subject, class
ORDER BY subject, class;

-- endregion


-- region Exam Papers / Answer Keys / Mappings

-- Quick extraction-status summary by year.
SELECT year, extraction_status, COUNT(1) AS papercount
FROM exam_papers
GROUP BY year, extraction_status
ORDER BY year, extraction_status;

-- List papers for one year.
-- Replace year as needed.
SELECT id, year, shift, filename, extraction_status
FROM exam_papers
WHERE year = 2023
ORDER BY dateofexam, shift;

-- Per-paper question counts for one year.
-- Replace year as needed.
SELECT
    ep.id,
    ep.year,
    ep.shift,
    ep.dateofexam,
    ep.extraction_status,
    COUNT(qb.id) AS num_questions
FROM exam_papers ep
LEFT JOIN jee_question_bank qb ON ep.id = qb.exam_paper_id
WHERE ep.year = 2024
GROUP BY ep.id, ep.year, ep.shift, ep.dateofexam, ep.extraction_status
ORDER BY ep.year, ep.dateofexam, ep.shift;

-- Reset one paper for re-extraction.
-- Replace exam_paper_id as needed.
DELETE FROM jee_question_bank
WHERE exam_paper_id = 220;

UPDATE exam_papers
SET extraction_status = 'PENDING'
WHERE id = 13;

-- Bulk reset a set of papers for re-extraction.
-- Replace ids as needed.
UPDATE exam_papers
SET extraction_status = 'PENDING'
WHERE id IN (2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16, 17);

SELECT id, extraction_status
FROM exam_papers
WHERE id IN (2,3,5,10,12,13,14,15,16);
--WHERE id IN (2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16, 17);

-- Answer-key extraction status by year.
-- Replace year as needed.
SELECT id, year, session, key_type, extraction_status, blob_url IS NOT NULL AS has_blob
FROM exam_answer_keys
WHERE year = 2023
ORDER BY session;

UPDATE exam_answer_keys
SET extraction_status = 'PENDING'
WHERE id IN (7, 10);

-- Mapping counts by answer-key year.
SELECT year, COUNT(*) AS mapping_count
FROM jee_answer_mappings m
JOIN exam_answer_keys e ON e.id = m.source_key_id
GROUP BY year
ORDER BY year;

-- Mapping count for one source key.
SELECT COUNT(*)
FROM jee_answer_mappings
WHERE source_key_id = 1;

-- endregion


-- region JEE Question Bank / Tags / Embeddings

-- Question counts for a small set of papers.
-- Replace paper ids as needed.
SELECT
    ep.id,
    ep.year,
    ep.extraction_status,
    COUNT(jqb.id) AS questions
FROM exam_papers ep
LEFT JOIN jee_question_bank jqb ON jqb.exam_paper_id = ep.id
WHERE ep.year = 2024
  AND ep.id IN (7, 8, 9)
GROUP BY ep.id, ep.year, ep.extraction_status
ORDER BY ep.id;

-- Tagging coverage by subject.
SELECT
    q.year,
    q.subject,
    COUNT(*) AS total_questions,
    COUNT(DISTINCT t.question_id) AS tagged_questions,
    COUNT(*) - COUNT(DISTINCT t.question_id) AS untagged_questions
FROM jee_question_bank q
LEFT JOIN jee_question_tags t ON t.question_id = q.id
WHERE q.year = 2024
GROUP BY q.year, q.subject
ORDER BY q.year, q.subject;

-- Tagging coverage for one subject by year.
-- Replace subject as needed.
SELECT
    q.year,
    q.subject,
    COUNT(q.*) AS total_questions,
    COUNT(DISTINCT t.question_id) AS tagged_questions,
    COUNT(t.*) AS total_tags
FROM jee_question_bank q
LEFT JOIN jee_question_tags t ON q.id = t.question_id
WHERE q.subject = 'Mathematics'
GROUP BY q.year, q.subject
ORDER BY q.year, q.subject;

--if the untagged questions are structurally untaggable (no text = embedding is useless = retrieval fails = hallucination)
  SELECT                                                                                               
    subject,
    COUNT(*) total_untagged,
    SUM(CASE WHEN (question_content->>'has_figure')::boolean = true THEN 1 ELSE 0 END) has_figure,
    SUM(CASE WHEN TRIM(COALESCE(question_content->>'raw_text', '')) = '' THEN 1 ELSE 0 END) no_text
  FROM jee_question_bank q
  WHERE year = 2024
    AND NOT EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
  GROUP BY subject ORDER BY subject;

  -- Which papers are most untagged?
  SELECT --dateofexam, shift, 
    q.year, q.subject,
    COUNT(*) total,
    COUNT(t.question_id) tagged,
    COUNT(*) - COUNT(t.question_id) untagged
  FROM jee_question_bank q
  LEFT JOIN jee_question_tags t ON t.question_id = q.id
  --WHERE q.year = 2024
  GROUP BY --dateofexam, shift, 
  q.year, q.subject
  ORDER BY untagged DESC;

  SELECT COUNT(*) untagged
  FROM jee_question_bank q
  WHERE q.year = 2024 AND q.subject = 'Mathematics'
  AND NOT EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id);

  SELECT dateofexam, shift, subject, COUNT(*)
  FROM jee_question_bank
  WHERE year = 2024
  GROUP BY dateofexam, shift, subject
  ORDER BY dateofexam, shift, subject;

-- Spot-check concept tags for one question.
-- Replace question_id as needed.
SELECT nch.concept_title, nch.subject, nch.content_type, t.similarity_score
FROM jee_question_tags t
JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
WHERE t.question_id = 39
ORDER BY t.similarity_score DESC;

-- Inspect difficulty and pattern classification for one question.
SELECT id, subject, section, difficulty, difficulty_confidence, pattern_label
FROM jee_question_bank
WHERE id = 39;

SELECT id, dateofexam, shift, COUNT(*) 
FROM jee_question_bank WHERE exam_paper_id
   IN (6,7,8,9) GROUP BY id, dateofexam, shift;

SELECT COUNT(*), year FROM jee_question_bank WHERE year = 2023 GROUP BY year;

-- Inspect tags for one subject/date/shift slice.
-- Replace subject, date, shift as needed.
SELECT q.id, q.nta_question_id, t.concept_id, nch.concept_title, t.similarity_score
FROM jee_question_tags t
JOIN jee_question_bank q ON q.id = t.question_id
JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
WHERE q.subject = 'Mathematics'
  AND q.dateofexam = '2024-01-27'
  AND q.shift = '1'
ORDER BY q.id, t.similarity_score DESC;

-- Sample raw question text for one paper slice.
SELECT subject, LEFT(question_content->>'raw_text', 100) AS raw_text_preview
FROM jee_question_bank
WHERE dateofexam = '2024-04-06'
  AND shift = '1'
  AND subject = 'Physics'
ORDER BY id
LIMIT 3;

-- Similarity-score distribution for tags.
SELECT
    CASE
        WHEN similarity_score < 0.5 THEN '< 0.5'
        WHEN similarity_score < 0.6 THEN '[0.5, 0.6)'
        WHEN similarity_score < 0.7 THEN '[0.6, 0.7)'
        WHEN similarity_score < 0.8 THEN '[0.7, 0.8)'
        WHEN similarity_score < 0.9 THEN '[0.8, 0.9)'
        ELSE '[0.9, 1.0]'
    END AS score_bucket,
    COUNT(*) AS count
FROM jee_question_tags
GROUP BY score_bucket
ORDER BY score_bucket;

-- Lightweight content quality checks.
SELECT
    SUM(CASE WHEN qc->>'raw_text' ~* 'wait,|just checking|this matches|actually,|let me|matches option' THEN 1 ELSE 0 END) AS llm_leakage,
    SUM(CASE WHEN qc->>'raw_text' ~ '(\\\\frac|\\\\sin|\\\\cos|\\\\sqrt){[^$]' THEN 1 ELSE 0 END) AS bare_latex,
    COUNT(*) AS total
FROM jee_question_bank,
LATERAL (SELECT question_content) AS t(qc)
WHERE question_content IS NOT NULL;

-- Ranked sample of questions from selected papers.
WITH ranked_questions AS (
    SELECT
        id,
        subject,
        section,
        answer_key,
        question_content->>'raw_text' AS raw_text,
        jsonb_array_length(question_content->'options') AS option_count,
        ROW_NUMBER() OVER (PARTITION BY subject, section ORDER BY id) AS row_num
    FROM jee_question_bank
    WHERE exam_paper_id IN (6, 7, 8, 9)
)
SELECT id, subject, section, answer_key, raw_text, option_count, row_num
FROM ranked_questions
WHERE row_num <= 5;

-- endregion


-- region Targeted Cleanup / Repairs

-- Inspect known bad questions before deleting.
SELECT
    ep.id AS paper_id,
    ep.year,
    ep.dateofexam,
    ep.shift,
    COUNT(*) AS bad_questions,
    STRING_AGG(q.id::text, ',' ORDER BY q.id) AS question_ids,
    STRING_AGG(q.nta_question_id, ',' ORDER BY q.id) AS nta_ids
FROM jee_question_bank q
JOIN exam_papers ep ON ep.id = q.exam_paper_id
WHERE q.id IN (216, 367, 368, 432, 512, 544, 666, 713, 809, 819, 838, 863, 876, 927, 928, 956, 972, 1000, 1038, 1061, 1065, 1067, 1102, 1152, 1159)
GROUP BY ep.id, ep.year, ep.dateofexam, ep.shift
ORDER BY ep.dateofexam, ep.shift;

DELETE FROM jee_question_tags
WHERE question_id IN (216, 367, 368, 432, 512, 544, 666, 713, 809, 819, 838, 863, 876, 927, 928, 956, 972, 1000, 1038, 1061, 1065, 1067, 1102, 1152, 1159);

DELETE FROM jee_question_embeddings
WHERE question_id IN (216, 367, 368, 432, 512, 544, 666, 713, 809, 819, 838, 863, 876, 927, 928, 956, 972, 1000, 1038, 1061, 1065, 1067, 1102, 1152, 1159);

DELETE FROM jee_question_bank
WHERE id IN (216, 367, 368, 432, 512, 544, 666, 713, 809, 819, 838, 863, 876, 927, 928, 956, 972, 1000, 1038, 1061, 1065, 1067, 1102, 1152, 1159);

-- Remove stored figure blob URLs matching an old container pattern.
UPDATE jee_question_bank
SET question_content = jsonb_set(
    question_content,
    '{figure_blob_url}',
    'null'::jsonb
)
WHERE (question_content->>'figure_blob_url') LIKE '%kalidasa%';

-- Delete malformed question rows.
DELETE FROM jee_question_bank
WHERE (question_content->>'raw_text') LIKE '{%';

-- endregion



--Temp
select * from ncert_concept_hierarchy limit 10;
select * from ncert_concept_embeddings limit 10;
