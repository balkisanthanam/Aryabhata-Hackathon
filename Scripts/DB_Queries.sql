
-- ============================================
-- CHAPTERDATA QUERIES
-- ============================================

SELECT * 
FROM chapterdata 
WHERE chapterid IN (64);

SELECT subject, class, COUNT(*) 
FROM chapterdata 
WHERE pdffileurl IS NOT NULL 
GROUP BY subject, class 
ORDER BY class, subject;

SELECT * 
FROM chapterdata 
WHERE class = '11' AND subject = 'Maths';

UPDATE chapterdata AS t
SET pdffileurl = v.new_url
FROM (VALUES 
    (61, '12', 'Physics', 'ELECTRIC CHARGES AND FIELDS', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph101.pdf'),
    (62, '12', 'Physics', 'ELECTROSTATIC POTENTIAL AND CAPACITANCE', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph102.pdf'),
    (63, '12', 'Physics', 'CURRENT ELECTRICITY', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph103.pdf'),
    (64, '12', 'Physics', 'MOVING CHARGES AND MAGNETISM', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph104.pdf'),
    (65, '12', 'Physics', 'MAGNETISM AND MATTER', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph105.pdf'),
    (66, '12', 'Physics', 'ELECTROMAGNETIC INDUCTION', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph106.pdf'),
    (67, '12', 'Physics', 'ALTERNATING CURRENT', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph107.pdf'),
    (68, '12', 'Physics', 'ELECTROMAGNETIC WAVES', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph108.pdf')
) AS v(chapterid, class, subject, title, new_url)
WHERE t.chapterid = v.chapterid
  AND t.class = v.class
  AND t.subject = v.subject
  AND t.chaptertitle = v.title;


-- ============================================
-- QUESTIONDATA QUERIES
-- ============================================

SELECT * 
FROM questiondata 
WHERE exerciseid = '38';

SELECT review_status, COUNT(*)
FROM questiondata 
group by review_status;

select questionid,review_status 
from questiondata 
where questionid in ('181','182','183','184','185','186','187','188','219','220');


SELECT count(1) 
from questiondata
where solution is not null;


-- ============================================
-- EXERCISEDATA QUERIES
-- ============================================

select * from exercisedata limit 2;

-- ============================================
-- USERPROFILEDATA QUERIES
-- ============================================

INSERT INTO UserProfileData (UserName, Class, Board, Goal, email)
VALUES ('Viswanathan', '11', 'CBSE', 'JEE Advanced', 'abcd@xyz.com');

SELECT * FROM UserProfileData;


-- ============================================
-- CLASSSUBJECTDATA QUERIES
-- ============================================

SELECT * FROM ClassSubjectData;


-- ============================================
-- SOLUTION_EVALUATIONS QUERIES
-- ============================================

SELECT * 
FROM solution_evaluations;

DELETE FROM solution_evaluations;

DELETE FROM solution_evaluations 
WHERE id = '91a8a4c4-5660-453d-b498-aac1c4307ce9';

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'solution_evaluations'
ORDER BY ordinal_position;

CREATE TABLE solution_evaluation_backup AS 
SELECT * FROM solution_evaluations 
WHERE id = '91a8a4c4-5660-453d-b498-aac1c4307ce9';

INSERT INTO solution_evaluation_backup 
SELECT * FROM solution_evaluations;


-- ============================================
-- NCERT_CONCEPT_HIERARCHY QUERIES
-- ============================================

SELECT COUNT(1) 
FROM ncert_concept_hierarchy;

SELECT * 
FROM ncert_concept_hierarchy 
LIMIT 10;

SELECT * FROM ncert_concept_hierarchy 
WHERE id NOT IN (SELECT DISTINCT concept_id FROM ncert_concept_embeddings);


-- ============================================
-- NCERT_CONCEPT_EMBEDDINGS QUERIES
-- ============================================

SELECT COUNT(1) 
FROM ncert_concept_embeddings;

SELECT * 
FROM ncert_concept_embeddings 
LIMIT 10;


-- ============================================
-- EXAM_PAPERS QUERIES
-- ============================================

SELECT id, year, shift, filename, extraction_status
FROM exam_papers
WHERE year = 2023
ORDER BY dateofexam, shift;


-- ============================================
-- JEE_QUESTION_BANK QUERIES
-- ============================================

SELECT review_status, COUNT(*)
FROM jee_question_bank
GROUP BY review_status;

SELECT is_generated, review_status, COUNT(*)
FROM jee_question_bank
GROUP BY is_generated, review_status;

SELECT * FROM jee_question_bank LIMIT 2;

SELECT 
    subject, 
    review_status, 
    COUNT(*) as solution_count
FROM jee_question_bank
WHERE is_generated = TRUE 
GROUP BY subject, review_status
ORDER BY subject, review_status;

UPDATE jee_question_bank 
SET solution = NULL, 
    is_generated = FALSE, 
    review_status = 'PENDING', 
    retry_count = 0 
WHERE is_generated = TRUE 
  AND review_status IN ('UNVERIFIED', 'NEEDS_REWRITE', 'GENERATION_FAILED');

UPDATE jee_question_bank
SET review_status = 'PENDING'
WHERE is_generated = FALSE AND solution IS NULL AND review_status = 'APPROVED';

UPDATE jee_question_bank
SET review_status = 'APPROVED_GOLD'
WHERE is_generated = TRUE AND review_status = 'APPROVED';


-- ============================================
-- MULTI-TABLE QUERIES
-- ============================================

-- Detailed list of questions for a specific class/subject/chapter
SELECT chapterdata.chapterid, chapterdata.class, chapterdata.subject, chapterdata.chapternumber, chapterdata.chaptertitle,
exercisedata.exerciseid, exercisedata.exercise, 
questiondata.questionid, questiondata.question_ref, questiondata.solution
FROM questiondata
INNER JOIN exercisedata ON questiondata.exerciseid = exercisedata.exerciseid
INNER JOIN chapterdata ON exercisedata.chapterid = chapterdata.chapterid
WHERE chapterdata.class = '12' AND chapterdata.subject = 'Physics' AND chapterdata.chapternumber IN ('3')
    AND questiondata.question_ref LIKE '%3.7%'
ORDER BY chapterdata.chapternumber, exercisedata.exerciseid, questiondata.questionid;

-- Distinct chapters and exercises
SELECT DISTINCT chapterdata.subject, chapterdata.chapternumber, chapterdata.chaptertitle, 
       substring(chapterdata.pdffileurl,'[^/]*$') AS pdffilename, exercisedata.exerciseid, chapterdata.chapterid
FROM exercisedata
INNER JOIN chapterdata ON exercisedata.chapterid = chapterdata.chapterid
ORDER BY chapterdata.subject, chapterdata.chapternumber;

-- Exercises for specific IDs
SELECT c.chapternumber, c.chaptertitle, substring(c.pdffileurl,'[^/]*$') AS pdffilename, e.exerciseid, e.exercise
FROM exercisedata e 
INNER JOIN chapterdata c ON e.chapterid = c.chapterid
WHERE e.exerciseid IN ('36','37');

-- 1. Overall summary by chapter
SELECT 
    c.subject,
    c.chapternumber,
    c.chaptertitle,
    e.exerciseid,
    e.exercise,
    substring(c.pdffileurl,'[^/]*$') AS pdffilename,
    COUNT(q.questionid) AS total_questions,
    COUNT(q.solution) AS solved_questions,
    COUNT(q.questionid) - COUNT(q.solution) AS missing_solutions,
    CASE 
        WHEN COUNT(q.questionid) = COUNT(q.solution) THEN '✅ COMPLETE'
        WHEN COUNT(q.solution) = 0 THEN '❌ NO SOLUTIONS'
        ELSE '⚠️ PARTIAL (' || COUNT(q.solution) || '/' || COUNT(q.questionid) || ')'
    END AS status
FROM chapterdata c
INNER JOIN exercisedata e ON c.chapterid = e.chapterid
INNER JOIN questiondata q ON e.exerciseid = q.exerciseid
WHERE c.subject = 'Physics' AND c.class = '12'
GROUP BY c.subject, c.chapternumber, c.chaptertitle, e.exerciseid, e.exercise, pdffilename
ORDER BY c.subject, c.chapternumber::int;

-- 2. Find questions with missing solutions
SELECT 
    c.subject,
    c.chapternumber,
    e.exercise,
    q.question_ref,
    q.questionid,
    CASE WHEN q.solution IS NULL THEN '❌ MISSING' ELSE '✅' END AS solution_status
FROM questiondata q
INNER JOIN exercisedata e ON q.exerciseid = e.exerciseid
INNER JOIN chapterdata c ON e.chapterid = c.chapterid
WHERE q.solution IS NULL
ORDER BY c.subject, c.chapternumber::int, q.question_ref;

-- 3. Find questions with figures (to verify blob upload)
SELECT 
    c.subject,
    c.chapternumber,
    q.question_ref,
    q.questionid,
    q.content::json->>'has_figure' AS has_figure,
    q.content::json->'figure_info'->0->>'url' AS figure_url
FROM questiondata q
INNER JOIN exercisedata e ON q.exerciseid = e.exerciseid
INNER JOIN chapterdata c ON e.chapterid = c.chapterid
WHERE q.content::json->>'has_figure' = 'true'
ORDER BY c.subject, c.chapternumber::int, q.question_ref;

select c.subject, count(1) AS  questions_with_figures
FROM questiondata q
INNER JOIN exercisedata e ON q.exerciseid = e.exerciseid
INNER JOIN chapterdata c ON e.chapterid = c.chapterid
WHERE q.content::json->>'has_figure' = 'true'
GROUP BY c.subject
ORDER BY c.subject;

SELECT c.class, c.subject, (q.solution IS NULL) AS solution_is_null, q.is_generated, COUNT(*)
FROM questiondata q
INNER JOIN exercisedata e ON q.exerciseid = e.exerciseid
INNER JOIN chapterdata c ON e.chapterid = c.chapterid
WHERE c.class IN ('11','12') 
  --AND c.subject ILIKE '%Maths%' 
  AND q.solution IS NULL
GROUP BY c.class, c.subject, (q.solution IS NULL), q.is_generated
ORDER BY c.class, c.subject, solution_is_null, is_generated;


-- 4. Quick status count
SELECT 
    c.class,
    c.subject,
    COUNT(DISTINCT c.chapterid) AS chapters,
    COUNT(DISTINCT e.exerciseid) AS exercises,
    COUNT(q.questionid) AS total_questions,
    COUNT(q.solution) AS with_solutions,
    COUNT(q.questionid) - COUNT(q.solution) AS missing_solutions
FROM chapterdata c
LEFT JOIN exercisedata e ON c.chapterid = e.chapterid
LEFT JOIN questiondata q ON e.exerciseid = q.exerciseid
GROUP BY c.class, c.subject
ORDER BY c.class, c.subject;

-- Questions for specific physics chapter
SELECT c.chaptertitle, c.chapternumber, e.exerciseid, e.exercise, q.*
FROM questiondata q
INNER JOIN exercisedata e ON q.exerciseid = e.exerciseid
INNER JOIN chapterdata c ON e.chapterid = c.chapterid
WHERE c.class = '12' AND c.subject = 'Maths' AND substring(c.pdffileurl,'[^/]*$') = 'lemh204.pdf'
and q.solution IS NOT NULL;

SELECT c.chaptertitle,
         substring(c.pdffileurl,'[^/]*$') AS pdf,
         q.review_status, count(*) AS n
  FROM questiondata q
  JOIN exercisedata e ON q.exerciseid = e.exerciseid
  JOIN chapterdata  c ON e.chapterid  = c.chapterid
  WHERE c.class='12' AND c.subject='Chemistry'
    AND q.is_generated = TRUE
  GROUP BY 1,2,3
  ORDER BY 1,3;

  SELECT q.questionid,
         substring(c.pdffileurl,'[^/]*$') AS pdf,
         (q.solution::text LIKE '%\ce{%') AS has_mhchem,
         q.content
  FROM questiondata q
  JOIN exercisedata e ON q.exerciseid = e.exerciseid
  JOIN chapterdata  c ON e.chapterid  = c.chapterid
  WHERE c.class='12' AND c.subject='Chemistry' AND q.is_generated = TRUE;


-- Miscellaneous questions for Maths chapter 4
SELECT chapterdata.chapterid, chapterdata.class, chapterdata.subject, chapterdata.chapternumber, chapterdata.chaptertitle,
exercisedata.exerciseid, exercisedata.exercise, 
questiondata.questionid, questiondata.question_ref,
substring(chapterdata.pdffileurl,'[^/]*$') AS pdffilename
FROM questiondata
INNER JOIN exercisedata ON questiondata.exerciseid = exercisedata.exerciseid
INNER JOIN chapterdata ON exercisedata.chapterid = chapterdata.chapterid
WHERE questiondata.question_ref ILIKE 'Misc%' AND chapterdata.subject = 'Maths' 
AND chapterdata.chapternumber = '4'
ORDER BY chapterdata.chapternumber, exercisedata.exerciseid, questiondata.questionid;

-- How much is ingested and how much is pending
SELECT 
    c.class, 
    c.subject, 
    c.chaptertitle,
    COUNT(DISTINCT e.exerciseid) as exercise_count,
    COUNT(DISTINCT q.questionid) as question_count,
    COUNT(q.questionid) FILTER (WHERE q.solution IS NOT NULL) as solution_count
FROM chapterdata c 
LEFT JOIN exercisedata e ON c.chapterid = e.chapterid
LEFT JOIN questiondata q ON e.exerciseid = q.exerciseid
GROUP BY c.class, c.subject, c.chaptertitle
ORDER BY c.class, c.subject, c.chaptertitle;

-- Chapters with missing concept embeddings
SELECT * 
FROM chapterdata 
WHERE class='12' 
AND chapterid NOT IN (SELECT DISTINCT chapter_id FROM ncert_concept_hierarchy);

-- 5. Chapters with no exercises or questions extracted
SELECT 
    c.chapterid,
    c.class,
    c.subject,
    c.chapternumber,
    c.chaptertitle,
    substring(c.pdffileurl,'[^/]*$') AS pdffilename
FROM chapterdata c
LEFT JOIN exercisedata e ON c.chapterid = e.chapterid
LEFT JOIN questiondata q ON e.exerciseid = q.exerciseid
WHERE e.exerciseid IS NULL AND q.questionid IS NULL
GROUP BY c.chapterid, c.class, c.subject, c.chapternumber, c.chaptertitle
ORDER BY c.class, c.subject, c.chapternumber;


SELECT dateofexam, shift, COUNT(*) AS unsolved_with_figure
  FROM jee_question_bank
  WHERE year = 2024 AND solution IS NULL
    AND (question_content->>'has_figure')::boolean = TRUE
  GROUP BY dateofexam, shift
  ORDER BY unsolved_with_figure DESC
  LIMIT 5;


  SELECT review_status, COUNT(*)
  FROM jee_question_bank
  WHERE year = 2024 AND is_generated = TRUE AND solution IS NOT NULL
  AND dateofexam = '2024-01-30' AND shift = '1'
  GROUP BY review_status;

-- Get column names and types
SELECT 
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'jee_question_bank'
ORDER BY ordinal_position;

SELECT id, review_status, (question_content->>'has_figure')::boolean AS has_figure
  FROM jee_question_bank
  WHERE year = 2024 AND dateofexam = '2024-01-30' AND shift = '1'
    AND review_status IN ('FIGURE_UNVERIFIED', 'GATE_FAILED')
  ORDER BY review_status;
  