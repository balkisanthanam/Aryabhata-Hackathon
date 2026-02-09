import axios from 'axios';

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

export const saveProgress = async (chapterId: number, exerciseId: number, questionId: number) => {
    await api.post('/practice/progress', { chapterId, exerciseId, questionId });
};
