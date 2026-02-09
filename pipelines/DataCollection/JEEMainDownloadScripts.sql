
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
