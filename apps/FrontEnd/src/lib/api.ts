import axios from 'axios';
import type { Evaluation, EvaluationSummaryItem, SubmitEvaluationRequest } from '../types/evaluation';

// Create Axios Instance
const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:7071/api',
    headers: {
        'Content-Type': 'application/json',
    },
});

export default api;

// API Helper Functions

// AUTH
export const loginUser = async () => {
    const response = await api.post('/auth/login', {});
    return response.data;
};

// RESUME
export const fetchResumeData = async () => {
    const response = await api.get('/user/resume');
    return response.data;
};

// PRACTICE DASHBOARD
export interface DashboardData {
    supportedClasses: string[];
    supportedSubjects: string[];
    activeClass: string;
    activeSubject: string;
    activeBoard: string;
    chapters: {
        id: number;
        title: string;
        chapterNumber: string;
        pdfUrl: string | null
    }[];
}

export const fetchDashboardData = async (activeClass?: string, activeSubject?: string, activeBoard?: string): Promise<DashboardData> => {
    const params: any = {};
    if (activeClass) params.class = activeClass;
    if (activeSubject) params.subject = activeSubject;
    if (activeBoard) params.board = activeBoard;

    const response = await api.get('/practice/dashboard', { params });
    return response.data;
};

// PRACTICE SESSION
export interface QuestionResponse {
    questionId: number;
    questionRef?: string; // Added questionRef
    exerciseId: number;
    exerciseTitle?: string;
    chapterTitle?: string;
    subject?: string;
    content: any;
    solution: any;
    nextQuestionId: number | null;
    prevQuestionId: number | null;
}

export interface PracticeExerciseSummary {
    exerciseId: number;
    exerciseTitle: string;
    questionCount: number;
    firstQuestionId: number | null;
}

export interface PracticeChapterMapResponse {
    chapterId: number;
    chapterTitle: string;
    chapterNumber: string;
    subject: string;
    exercises: PracticeExerciseSummary[];
}

export interface PracticeExerciseQuestionSummary {
    questionId: number;
    questionRef: string;
    questionText?: string;
    hasSolution: boolean;
}

export interface PracticeExerciseQuestionsResponse {
    exerciseId: number;
    exerciseTitle: string;
    chapterId: number;
    questions: PracticeExerciseQuestionSummary[];
}

export const fetchQuestion = async (
    chapterId: string,
    mode: 'start' | 'resume' = 'start',
    questionId?: number,
    exerciseId?: number
): Promise<QuestionResponse> => {
    const params: any = { mode };
    if (questionId) params.questionId = questionId;
    if (exerciseId) params.exerciseId = exerciseId;

    const response = await api.get('/practice/question', { params: { ...params, chapterId } });
    return response.data;
};

export const fetchPracticeChapterMap = async (chapterId: string): Promise<PracticeChapterMapResponse> => {
    const response = await api.get('/practice/chapter-map', { params: { chapterId } });
    return response.data;
};

export const fetchExerciseQuestions = async (exerciseId: number): Promise<PracticeExerciseQuestionsResponse> => {
    const response = await api.get('/practice/exercise-questions', { params: { exerciseId } });
    return response.data;
};

export const saveProgress = async (chapterId: number, exerciseId: number, questionId: number) => {
    await api.post('/practice/progress', { chapterId, exerciseId, questionId });
};

// JEE ASCENT

export interface AccentChapterSummary {
    chapterId: number;
    questionCount: number;
    attempted: number;
    correct: number;
}

export interface AccentChapterMapResponse {
    chapters: AccentChapterSummary[];
}

export interface AccentQuestionSummary {
    id: number;
    subject: string;
    section: string;
    difficulty: string | null;
    hasFigure: boolean;
    attempted: boolean;
    wasCorrect: boolean | null;
}

export interface AccentSessionResponse {
    chapterId: number;
    questions: AccentQuestionSummary[];
    stats: { total: number; attempted: number; correct: number };
}

export interface AccentQuestionContent {
    raw_text: string;
    options: { nta_option_id: string; text: string }[];
    has_figure: boolean;
    figure_description: string | null;
    figure_blob_url: string | null;
}

export interface AccentQuestionResponse {
    id: number;
    subject: string;
    section: string;
    difficulty: string | null;
    patternLabel: string | null;
    answerKey: string | null;
    questionContent: AccentQuestionContent;
    solution: any;
}

export const fetchAccentChapterMap = async (): Promise<AccentChapterMapResponse> => {
    const response = await api.get('/accent/chapter-map');
    return response.data;
};

export const fetchAccentSession = async (chapterId: number): Promise<AccentSessionResponse> => {
    const response = await api.get('/accent/session', { params: { chapterId } });
    return response.data;
};

export const fetchAccentQuestion = async (id: number): Promise<AccentQuestionResponse> => {
    const response = await api.get(`/accent/question/${id}`);
    return response.data;
};

export const recordAccentProgress = async (payload: {
    questionId: number;
    chapterId: number;
    wasCorrect: boolean | null;
    wasSkipped: boolean;
    timeSpentSeconds: number;
}): Promise<void> => {
    await api.post('/accent/progress', payload);
};

// EVALUATIONS

/**
 * Submit a new solution for evaluation.
 * Sends multipart/form-data with image files.
 * Returns the job ID (UUID) for polling.
 */
export const submitEvaluation = async (data: SubmitEvaluationRequest): Promise<string> => {
    const formData = new FormData();
    formData.append('subject', data.subject);
    formData.append('problemTextRef', data.problemTextRef);
    if (data.userClass) formData.append('class', data.userClass);
    if (data.board) formData.append('board', data.board);

    data.solutionImages.forEach(file => {
        formData.append('solutionImages', file);
    });
    if (data.problemImages) {
        data.problemImages.forEach(file => {
            formData.append('problemImages', file);
        });
    }

    const response = await api.post('/evaluations', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data.jobId;
};

/**
 * Get all COMPLETED evaluations for a user (lightweight list).
 */
export const fetchCompletedEvaluations = async (userId: number): Promise<EvaluationSummaryItem[]> => {
    const response = await api.get('/evaluations/completed', { params: { userId } });
    return response.data.evaluations;
};

/**
 * Get the most recently created evaluation for a user (any status).
 */
export const fetchLastEvaluation = async (userId: number): Promise<Evaluation | null> => {
    const response = await api.get('/evaluations/last', { params: { userId } });
    return response.data.evaluation;
};

/**
 * Get a specific evaluation by ID. Used for polling and viewing previous solutions.
 */
export const fetchEvaluationById = async (id: string): Promise<Evaluation> => {
    const response = await api.get(`/evaluations/detail/${id}`);
    return response.data.evaluation;
};
