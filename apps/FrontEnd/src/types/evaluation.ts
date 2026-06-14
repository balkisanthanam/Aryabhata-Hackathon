/**
 * TypeScript types for the Solution Evaluation feature.
 * Maps to the real feedback_json shape produced by the Python Durable Function pipeline.
 */

// --- API Response Types ---

export type EvaluationStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

/** Lightweight evaluation item for the Previous Solutions dropdown */
export interface EvaluationSummaryItem {
    id: string;
    subject: string;
    problemTextRef: string | null;
    createdAt: string;
}

/** Full evaluation record from the server */
export interface Evaluation {
    id: string;
    status: EvaluationStatus;
    subject: string;
    problemTextRef: string | null;
    feedbackJson: FeedbackJson | null;
    createdAt: string;
    /** SAS-signed URLs of uploaded student handwritten work pages */
    studentWorkUrls?: string[];
    /** SAS-signed URLs of uploaded problem statement images */
    problemImageUrls?: string[];
}

// --- feedback_json shape (produced by Python pipeline) ---

export interface FeedbackJson {
    summary: EvaluationSummaryStats;
    evaluations: ProblemEvaluation[];
}

export interface EvaluationSummaryStats {
    total_problems: number;
    correct: number;
    acceptable: number;
    incorrect: number;
    errors: number;
}

/** Per-problem evaluation entry */
export interface ProblemEvaluation {
    problem_id: string;
    evaluation: ProblemEvaluationDetail;
    _meta?: {
        model?: string;
        usage_metadata?: any;
    };
}

/** The Gemini-produced evaluation for a single problem */
export interface ProblemEvaluationDetail {
    evaluation_status: string; // "Answer is Correct", "Answer is Acceptable", "Answer is Incorrect", "Error"
    error_pinpoint?: {
        divergence_step: string;
        student_wrote: string;
        expected: string;
        error_type: string; // conceptual_misconception | wrong_formula | sign_error | unit_error | algebraic_error | arithmetic_error | incomplete_solution | misread_problem
        severity: 'fundamental' | 'minor';
    };
    evaluation_details?: {
        conceptual_understanding: string;
        calculation_errors: string;
        presentation_and_steps: string;
    };
    feedback_for_student?: {
        tip: string;
    };
    full_solution?: {
        title: string;
        steps: SolutionStep[];
    };
    error?: string; // Present when evaluation_status is "Error"
}

export interface SolutionStep {
    step_number: number;
    description: string;
    calculation: string;
}

// --- Submission Types ---

export interface SubmitEvaluationRequest {
    subject: string;
    problemTextRef: string;
    userClass?: string;
    board?: string;
    solutionImages: File[];
    problemImages?: File[];
}
