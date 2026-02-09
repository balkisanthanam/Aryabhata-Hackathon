--TRUNCATE TABLE exam_papers;

--CREATE TABLE exam_papers_back AS SELECT * FROM exam_papers;

--SELECT * FROM exam_papers LIMIT 100;
SELECT * FROM exam_papers WHERE LOWER(papername) LIKE '%english%';