-- Table creation script for ChapterData
CREATE TABLE ChapterData (
    ChapterId SERIAL PRIMARY KEY,
    Class VARCHAR(100) NOT NULL,
    Subject VARCHAR(255) NOT NULL,
    ChapterNumber INT NOT NULL,
    ChapterTitle VARCHAR(255) NOT NULL,
    PDFFileURL VARCHAR(500),
    UNIQUE (Class, Subject, ChapterNumber)
);

-- Optional: Create indexes for better query performance
CREATE INDEX IX_ChapterData_ChapterNumber ON ChapterData(Class, Subject, ChapterNumber);

-- Add unique constraint to existing ChapterData table (run this if table already exists)
ALTER TABLE ChapterData ADD CONSTRAINT UQ_ChapterData_Class_Subject_ChapterNumber UNIQUE (Class, Subject, ChapterNumber);

-- Add BOARD column to ChapterData table
ALTER TABLE ChapterData ADD COLUMN Board VARCHAR(100) NULL;

ALTER TABLE ChapterData ALTER COLUMN ChapterNumber TYPE VARCHAR(50);


-- Table creation script for ExerciseData
CREATE TABLE ExerciseData (
    ExerciseId SERIAL PRIMARY KEY,
    ChapterId INT NOT NULL REFERENCES ChapterData(ChapterId),
    Exercise VARCHAR(255) NOT NULL,
    totalQuestions INT,
    OtherData JSONB
);

ALTER TABLE ExerciseData ADD CONSTRAINT UQ_ExerciseData_Chapter_Exercise 
    UNIQUE (ChapterId, Exercise);

-- Optional: Create indexes for better query performance
CREATE INDEX IX_ExerciseData_Exercise ON ExerciseData(Exercise);

CREATE TABLE QuestionData (
    QuestionId SERIAL PRIMARY KEY,
    ExerciseId INT NOT NULL REFERENCES ExerciseData(ExerciseId),
    Question_Ref VARCHAR(255) NOT NULL,
    Content JSONB NOT NULL
);

CREATE INDEX IX_QuestionData_QuestionRef ON QuestionData(Question_Ref);

ALTER TABLE QuestionData ADD COLUMN Solution JSONB NULL;

-- 3. Add unique constraint for QuestionData UPSERT
ALTER TABLE QuestionData ADD CONSTRAINT UQ_QuestionData_Exercise_Ref 
    UNIQUE (ExerciseId, Question_Ref);
    

-- Insert statements for ChapterData
-- Class 11 - Maths
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 1, 'Sets', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh101.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 2, 'Relations and Functions', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh102.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 3, 'Trigonometric Functions', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh103.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 4, 'Complex Numbers and Quadratic Equations', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh104.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 5, 'Linear Inequalities', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh105.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 6, 'Permutations and Combinations', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh106.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 7, 'Binomial Theorem', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh107.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 8, 'Sequences and Series', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh108.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 9, 'Straight Lines', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh109.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 10, 'Conic Sections', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh110.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 11, 'Introduction to Three Dimensional Geometry', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh111.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 12, 'Limits and Derivatives', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh112.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 13, 'Statistics', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh113.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Maths', 14, 'Probability', 'https://kalidasa.blob.core.windows.net/feedback/11/Maths/kemh114.pdf','CBSE');

-- Class 11 - Physics
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 1, 'Units and Measurement', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph101.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 2, 'Motion in a Straight Line', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph102.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 3, 'Motion in a Plane', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph103.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 4, 'Laws of Motion', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph104.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 5, 'Work, Energy and Power', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph105.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 6, 'Systems of Particles and Rotational Motion', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph106.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 7, 'Gravitation', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph107.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 8, 'Mechanical Properties of Solids', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph201.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 9, 'Mechanical Properties of Fluids', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph202.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('11', 'Physics', 10, 'Thermal Properties of Matter', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph203.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Physics', 11, 'Thermodynamics', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph204.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Physics', 12, 'Kinetic Theory', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph205.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Physics', 13, 'Oscillations', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph206.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Physics', 14, 'Waves', 'https://kalidasa.blob.core.windows.net/feedback/11/Physics/keph207.pdf');

-- Class 11 - Chemistry
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 1, 'Some Basic Concepts of Chemistry', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech101.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 2, 'Structure of Atom', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech102.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 3, 'Classification of Elements and Periodicity in Properties', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech103.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 4, 'Chemical Bonding and Molecular Structure', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech104.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 5, 'Thermodynamics', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech105.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 6, 'Equilibrium', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech106.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 7, 'Redox Reactions', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech201.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 8, 'Organic Chemistry - Some Basic Principles and Techniques', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech202.pdf');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL) VALUES ('11', 'Chemistry', 9, 'Hydrocarbons', 'https://kalidasa.blob.core.windows.net/feedback/11/Chemistry/kech203.pdf');

-- Class 12 Maths
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '1', 'Relations and Functions', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh101.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '2', 'Inverse Trigonometric Functions', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh102.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '3', 'Matrices', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh103.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '4', 'Determinants', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh104.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '5', 'Continuity and Differentiability', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh105.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '6', 'Application of Derivatives', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh106.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '7', 'Integrals', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh201.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '8', 'Application of Integrals', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh202.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '9', 'Differential Equations', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh203.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '10', 'Vector Algebra', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh204.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '11', 'Three Dimensional Geometry', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh205.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '12', 'Linear Programming', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh206.pdf', 'CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Maths', '13', 'Probability', 'https://kalidasa.blob.core.windows.net/feedback/12/Maths/lemh207.pdf', 'CBSE');

--Class 12 Chemistry
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '1', 'Solutions', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech101.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '2', 'Electrochemistry', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech102.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '3', 'Chemical Kinetics', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech103.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '4', 'The d- and f-Block Elements', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech104.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '5', 'Coordination Compounds', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech105.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '6', 'Haloalkanes and Haloarenes', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech201.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '7', 'Alcohols, Phenols and Ethers', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech202.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '8', 'Aldehydes, Ketones and Carboxylic Acids', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech203.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '9', 'Amines', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech204.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Chemistry', '10', 'Biomolecules', 'https://kalidasa.blob.core.windows.net/feedback/12/Chemistry/lech205.pdf','CBSE');

--Class 12 Physics
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '1', 'ELECTRIC CHARGES AND FIELDS', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '2', 'ELECTROSTATIC POTENTIAL AND CAPACITANCE', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '3', 'CURRENT ELECTRICITY', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '4', 'MOVING CHARGES AND MAGNETISM', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '5', 'MAGNETISM AND MATTER', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '6', 'ELECTROMAGNETIC INDUCTION', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '7', 'ALTERNATING CURRENT', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '8', 'ELECTROMAGNETIC WAVES', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph2ps.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '9', 'RAY OPTICS AND OPTICAL INSTRUMENTS', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph201.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '10', 'WAVE OPTICS', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph202.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '11', 'DUAL NATURE OF RADIATION AND MATTER', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph203.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '12', 'ATOMS', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph204.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '13', 'NUCLEI', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph205.pdf','CBSE');
INSERT INTO ChapterData (Class, Subject, ChapterNumber, ChapterTitle, PDFFileURL, board) VALUES ('12', 'Physics', '14', 'SEMICONDUCTOR ELECTRONICS: MATERIALS, DEVICES AND SIMPLE CIRCUITS', 'https://kalidasa.blob.core.windows.net/feedback/12/Physics/leph206.pdf','CBSE');


-- Update existing ChapterData records to set Board = 'CBSE'
 UPDATE ChapterData SET Board = 'CBSE' WHERE Board IS NULL;

CREATE TABLE UserProfileData (
    UserId SERIAL PRIMARY KEY,
    UserName VARCHAR(500) NOT NULL,
    Class VARCHAR(100) NOT NULL,
    Board VARCHAR(100) NOT NULL,
    Goal VARCHAR(1000),
    email VARCHAR(500)
);

CREATE INDEX IX_UserProfileData_UserName ON UserProfileData(UserName);
CREATE INDEX IX_UserProfileData_Email ON UserProfileData(email);

CREATE TABLE UserExerciseData (
    UserExerciseId SERIAL PRIMARY KEY,
    UserId INT NOT NULL REFERENCES UserProfileData(UserId),
    ChapterId INT NOT NULL REFERENCES ChapterData(ChapterId),
    ExerciseId INT NOT NULL REFERENCES ExerciseData(ExerciseId),
    QuestionId INT NOT NULL REFERENCES QuestionData(QuestionId),
    AttemptedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IX_UserExerciseData_UserId ON UserExerciseData(UserId);

CREATE TABLE ClassSubjectData (
    ClassSubjectId SERIAL PRIMARY KEY,
    Class VARCHAR(100) NOT NULL,
    Subject VARCHAR(255) NOT NULL,
    Board VARCHAR(100) NOT NULL,
    UNIQUE (Class, Subject, Board)
);
CREATE INDEX IX_ClassSubjectData_Class ON ClassSubjectData(Class);

INSERT INTO ClassSubjectData (Class, Subject, Board) VALUES ('11', 'Maths', 'CBSE');
INSERT INTO ClassSubjectData (Class, Subject, Board) VALUES ('11', 'Physics', 'CBSE');
INSERT INTO ClassSubjectData (Class, Subject, Board) VALUES ('11', 'Chemistry', 'CBSE');

INSERT INTO ClassSubjectData (Class, Subject, Board) VALUES ('12', 'Maths', 'CBSE');
INSERT INTO ClassSubjectData (Class, Subject, Board) VALUES ('12', 'Physics', 'CBSE');
INSERT INTO ClassSubjectData (Class, Subject, Board) VALUES ('12', 'Chemistry', 'CBSE');

-- Create ENUM type for status
CREATE TYPE solution_evaluation_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

-- Table creation script with Blueprint alignments
CREATE TABLE solution_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    userId INT NOT NULL REFERENCES UserProfileData(UserId),
    class VARCHAR(100),
    board VARCHAR(100),
    subject VARCHAR(50) NOT NULL, -- Physics, Chemistry, etc.
    chapter_id INT NULL REFERENCES ChapterData(ChapterId), -- Reference to NCERT chapter
    chapter_title VARCHAR(255) NULL,   -- Resolved by orchestrator when text_ref is used
    chapter_number VARCHAR(50) NULL,   -- Resolved by orchestrator when text_ref is used
    pdffileurl VARCHAR(500),
    status solution_evaluation_status NOT NULL DEFAULT 'PENDING',
    
    -- Inputs
    problem_text_ref VARCHAR(500) NULL,
    problem_image_url TEXT NULL,      -- Original problem image
    student_work_url TEXT NOT NULL,   -- Viswanathan's uploaded solution
    
    -- Outputs
    feedback_json JSONB NULL,         -- The detailed Guru Insight
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Text reference is always required; image reference is optional (textbook page photo for context)
    CONSTRAINT chk_problem_input CHECK (problem_text_ref IS NOT NULL)
);

-- Optimized Indexes
CREATE INDEX ix_evaluations_student_userid ON solution_evaluations(userid);
CREATE INDEX ix_evaluations_student_status ON solution_evaluations(status);
CREATE INDEX ix_evaluations_student_userid_status ON solution_evaluations(userid, status);

-- Trigger for UpdatedAt (Logic is correct, just updated naming)
CREATE OR REPLACE FUNCTION update_solution_evaluation_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_solution_evaluations_updated_at
    BEFORE UPDATE ON solution_evaluations
    FOR EACH ROW
    EXECUTE FUNCTION update_solution_evaluation_updated_at();

-- Align chapter_number type with ChapterData.ChapterNumber (VARCHAR(50))
ALTER TABLE solution_evaluations ALTER COLUMN chapter_number TYPE VARCHAR(50);

-- Pipeline micro-state checkpointing columns
ALTER TABLE solution_evaluations
    ADD COLUMN IF NOT EXISTS pipeline_steps JSONB NULL,
    ADD COLUMN IF NOT EXISTS current_step VARCHAR(100) NULL;

-- Optional indexes for pipeline observability (uncomment when needed)
-- CREATE INDEX ix_evaluations_current_step ON solution_evaluations(current_step) WHERE status = 'PROCESSING';
-- CREATE INDEX ix_evaluations_pipeline_steps ON solution_evaluations USING GIN (pipeline_steps);

-- v4: text_ref is always required; drop the old OR constraint, add the new one
ALTER TABLE solution_evaluations
  DROP CONSTRAINT IF EXISTS solution_evaluations_input_check;

ALTER TABLE solution_evaluations
  ADD CONSTRAINT solution_evaluations_input_check
  CHECK (problem_text_ref IS NOT NULL);

