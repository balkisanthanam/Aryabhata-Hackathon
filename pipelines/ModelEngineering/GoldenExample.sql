(SELECT 'Math_Golden' AS Result_Type, q.content, q.solution 
 FROM questiondata q 
 JOIN exercisedata e ON q.exerciseid = e.exerciseid 
 JOIN chapterdata c ON e.chapterid = c.chapterid 
 WHERE c.class = '11' AND c.subject ILIKE 'Math%' AND c.chaptertitle ILIKE '%Trigonometric%' AND e.exercise ILIKE '%3.1%' 
 LIMIT 1)
 
UNION ALL

(SELECT 'Physics_Pedagogy' AS Result_Type, q.content, q.solution 
 FROM questiondata q 
 JOIN exercisedata e ON q.exerciseid = e.exerciseid 
 JOIN chapterdata c ON e.chapterid = c.chapterid 
 WHERE c.class = '11' AND c.subject ILIKE 'Physics%' AND c.chaptertitle ILIKE '%THERMODYNAMICS%' AND (e.exercise ILIKE '%11.1%' OR q.question_ref ILIKE '%11.1%') 
 LIMIT 1)
 
UNION ALL

(SELECT 'Physics_Drift' AS Result_Type, q.content, q.solution 
 FROM questiondata q 
 JOIN exercisedata e ON q.exerciseid = e.exerciseid 
 JOIN chapterdata c ON e.chapterid = c.chapterid 
 WHERE c.class = '12' AND c.subject ILIKE 'Physics%' AND c.chaptertitle ILIKE '%CURRENT ELECTRICITY%' AND q.question_ref ILIKE '%7%' 
 LIMIT 1)
 
UNION ALL

(SELECT 'Chemistry_Hallucination' AS Result_Type, q.content, q.solution 
 FROM questiondata q 
 JOIN exercisedata e ON q.exerciseid = e.exerciseid 
 JOIN chapterdata c ON e.chapterid = c.chapterid 
 WHERE c.class = '11' AND c.subject ILIKE 'Chemistry%' AND c.chaptertitle ILIKE '%BONDING%' AND q.question_ref ILIKE '%14%' 
 LIMIT 1);