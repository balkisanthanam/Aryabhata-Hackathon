-- Detailed list of questions for a specific class/subject/chapter
SELECT chapterdata.chapterid, chapterdata.class, chapterdata.subject, chapterdata.chapternumber, chapterdata.chaptertitle,
exercisedata.exerciseid, exercisedata.exercise, 
questiondata.questionid, questiondata.question_ref
FROM questiondata
inner join exercisedata ON questiondata.exerciseid = exercisedata.exerciseid
inner JOIN chapterdata ON exercisedata.chapterid = chapterdata.chapterid
WHERE chapterdata.class = '11' AND chapterdata.subject = 'Physics' AND chapterdata.chapternumber IN ('2')
--chapterdata.class = '11' AND chapterdata.subject = 'Chemistry' AND chapterdata.chapternumber = '5'
ORDER BY chapterdata.chapternumber, exercisedata.exerciseid, questiondata.questionid;

SELECT DISTINCT chapterdata.subject, chapterdata.chapternumber, chapterdata.chaptertitle, substring(chapterdata.pdffileurl,'[^/]*$') AS pdffilename, exercisedata.exerciseid, chapterdata.chapterid
FROM exercisedata
inner JOIN chapterdata ON exercisedata.chapterid = chapterdata.chapterid
--WHERE exercisedata.exerciseid IN ('17','19','20','21')
ORDER BY chapterdata.subject, chapterdata.chapternumber;

select * 
from chapterdata;

SELECT * from questiondata WHERE exerciseid = '38';

select distinct exerciseid from questiondata ORDER BY exerciseid;

SELECT c.chapternumber, c.chaptertitle, substring(c.pdffileurl,'[^/]*$') AS pdffilename, e.exerciseid, e.exercise
from exercisedata e inner join chapterdata c ON e.chapterid = c.chapterid
where exerciseid in ('36','37');


-- Sample Data
INSERT INTO UserProfileData (UserName, Class, Board, Goal, email)
VALUES ('Viswanathan', '11', 'CBSE', 'JEE Advanced', 'abcd@xyz.com');

SELECT * FROM ClassSubjectData;


SELECT * FROM UserProfileData;



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
GROUP BY c.subject, c.chapternumber, c.chaptertitle, e.exerciseid, e.exercise,pdffilename
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

-- 4. Quick status count
SELECT 
    c.subject,
    COUNT(DISTINCT c.chapterid) AS chapters,
    COUNT(DISTINCT e.exerciseid) AS exercises,
    COUNT(q.questionid) AS total_questions,
    COUNT(q.solution) AS with_solutions,
    COUNT(q.questionid) - COUNT(q.solution) AS missing_solutions
FROM chapterdata c
LEFT JOIN exercisedata e ON c.chapterid = e.chapterid
LEFT JOIN questiondata q ON e.exerciseid = q.exerciseid
GROUP BY c.subject
ORDER BY c.subject;


select * from solution_evaluations;

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'solution_evaluations'
ORDER BY ordinal_position;