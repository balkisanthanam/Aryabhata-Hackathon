-- Fix paper 2024-01-27 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-01-27' AND shift = '1';

-- Clean up M3 tags for 2024-01-27 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-27' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-27' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-01-27' AND shift = '1';

-- Fix paper 2024-01-30 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-01-30' AND shift = '1';

-- Clean up M3 tags for 2024-01-30 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-30' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-30' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-01-30' AND shift = '1';

-- Fix paper 2024-01-30 shift 2
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-01-30' AND shift = '2';

-- Clean up M3 tags for 2024-01-30 shift 2
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-30' AND shift = '2');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-30' AND shift = '2');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-01-30' AND shift = '2';

-- Fix paper 2024-01-31 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-01-31' AND shift = '1';

-- Clean up M3 tags for 2024-01-31 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-31' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-31' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-01-31' AND shift = '1';

-- Fix paper 2024-01-31 shift 2
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-01-31' AND shift = '2';

-- Clean up M3 tags for 2024-01-31 shift 2
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-31' AND shift = '2');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-01-31' AND shift = '2');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-01-31' AND shift = '2';

-- Fix paper 2024-02-01 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-02-01' AND shift = '1';

-- Clean up M3 tags for 2024-02-01 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-02-01' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-02-01' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-02-01' AND shift = '1';

-- Fix paper 2024-04-06 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-04-06' AND shift = '1';

-- Clean up M3 tags for 2024-04-06 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-06' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-06' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-04-06' AND shift = '1';

-- Fix paper 2024-04-06 shift 2
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-04-06' AND shift = '2';

-- Clean up M3 tags for 2024-04-06 shift 2
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-06' AND shift = '2');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-06' AND shift = '2');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-04-06' AND shift = '2';

-- Fix paper 2024-04-08 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-04-08' AND shift = '1';

-- Clean up M3 tags for 2024-04-08 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-08' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-08' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-04-08' AND shift = '1';

-- Fix paper 2024-04-09 shift 1
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-04-09' AND shift = '1';

-- Clean up M3 tags for 2024-04-09 shift 1
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-09' AND shift = '1');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-09' AND shift = '1');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-04-09' AND shift = '1';

-- Fix paper 2024-04-09 shift 2
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2024-04-09' AND shift = '2';

-- Clean up M3 tags for 2024-04-09 shift 2
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-09' AND shift = '2');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2024-04-09' AND shift = '2');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2024-04-09' AND shift = '2';

-- Fix paper 2025-02-01 shift 2
UPDATE jee_question_bank SET subject = CASE
    WHEN subject = 'Chemistry' THEN 'Physics'
    WHEN subject = 'Mathematics' THEN 'Chemistry'
    WHEN subject = 'Physics' THEN 'Mathematics'
    ELSE subject
END
WHERE dateofexam = '2025-02-01' AND shift = '2';

-- Clean up M3 tags for 2025-02-01 shift 2
DELETE FROM jee_question_tags WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2025-02-01' AND shift = '2');
DELETE FROM jee_question_embeddings WHERE question_id IN (SELECT id FROM jee_question_bank WHERE dateofexam = '2025-02-01' AND shift = '2');
UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL
WHERE dateofexam = '2025-02-01' AND shift = '2';
