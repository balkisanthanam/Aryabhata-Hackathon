import { create } from 'zustand';
import type {
    Evaluation,
    EvaluationSummaryItem,
    SubmitEvaluationRequest,
} from '../types/evaluation';
import {
    submitEvaluation as apiSubmitEvaluation,
    fetchCompletedEvaluations,
    fetchLastEvaluation,
    fetchEvaluationById,
} from '../lib/api';

const POLL_INTERVAL_MS = 10_000; // 10 seconds

interface FeedbackState {
    // Data
    completedEvaluations: EvaluationSummaryItem[];
    lastEvaluation: Evaluation | null;
    selectedEvaluation: Evaluation | null;

    // UI state
    activeJobId: string | null;
    isSubmitting: boolean;
    isPolling: boolean;
    isLoadingInitial: boolean;
    isLoadingSelected: boolean;
    submitError: string | null;
    notification: { type: 'success' | 'error'; message: string } | null;

    // Navigation state for problem-by-problem view
    currentProblemIndex: number;
    statusFilter: string | null; // null = all, 'Correct' / 'Acceptable' / 'Incorrect' / 'Error'

    // Actions
    fetchInitialData: (userId: number) => Promise<void>;
    submitEvaluation: (data: SubmitEvaluationRequest, userId: number) => Promise<void>;
    selectEvaluation: (id: string) => Promise<void>;
    startPolling: (jobId: string) => void;
    stopPolling: () => void;
    clearNotification: () => void;
    reset: () => void;

    // Navigation actions
    setCurrentProblemIndex: (index: number) => void;
    setStatusFilter: (status: string | null) => void;
    nextProblem: () => void;
    prevProblem: () => void;
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

export const useFeedbackStore = create<FeedbackState>()((set, get) => ({
    // Initial state
    completedEvaluations: [],
    lastEvaluation: null,
    selectedEvaluation: null,
    activeJobId: null,
    isSubmitting: false,
    isPolling: false,
    isLoadingInitial: true,
    isLoadingSelected: false,
    submitError: null,
    notification: null,
    currentProblemIndex: 0,
    statusFilter: null,

    /**
     * Called on page load (and when navigating back).
     * Fetches completed list + last evaluation to determine initial UX state.
     */
    fetchInitialData: async (userId: number) => {
        set({ isLoadingInitial: true });

        // Use allSettled so one failure doesn't discard the other result
        const [completedResult, lastResult] = await Promise.allSettled([
            fetchCompletedEvaluations(userId),
            fetchLastEvaluation(userId),
        ]);

        const completedEvaluations =
            completedResult.status === 'fulfilled' ? completedResult.value : [];
        const lastEvaluation =
            lastResult.status === 'fulfilled' ? lastResult.value : null;

        if (completedResult.status === 'rejected') {
            console.error('[FeedbackStore] Error fetching completed evaluations:', completedResult.reason);
        }
        if (lastResult.status === 'rejected') {
            console.error('[FeedbackStore] Error fetching last evaluation:', lastResult.reason);
        }

        set({ completedEvaluations, lastEvaluation, isLoadingInitial: false });

        // If last evaluation is in-progress, resume polling
        if (
            lastEvaluation &&
            (lastEvaluation.status === 'PENDING' || lastEvaluation.status === 'PROCESSING')
        ) {
            get().startPolling(lastEvaluation.id);
        }

        // If last evaluation is completed, show it
        if (lastEvaluation && lastEvaluation.status === 'COMPLETED') {
            set({ selectedEvaluation: lastEvaluation });
        }
    },

    /**
     * Submit a new evaluation.
     * Uploads images, creates DB record, pushes to queue.
     */
    submitEvaluation: async (data: SubmitEvaluationRequest, _userId: number) => {
        set({ isSubmitting: true, submitError: null });
        try {
            const jobId = await apiSubmitEvaluation(data);
            set({
                isSubmitting: false,
                activeJobId: jobId,
                selectedEvaluation: null, // Clear current view - show processing state
                lastEvaluation: {
                    id: jobId,
                    status: 'PENDING',
                    subject: data.subject,
                    problemTextRef: data.problemTextRef,
                    feedbackJson: null,
                    createdAt: new Date().toISOString(),
                },
            });
            get().startPolling(jobId);
        } catch (error: any) {
            const message = error?.response?.data?.error || error.message || 'Submission failed';
            set({ isSubmitting: false, submitError: message });
        }
    },

    /**
     * Select a previous evaluation to view.
     * Fetches full record from server.
     */
    selectEvaluation: async (id: string) => {
        set({ isLoadingSelected: true });
        try {
            const evaluation = await fetchEvaluationById(id);
            set({ selectedEvaluation: evaluation, isLoadingSelected: false, currentProblemIndex: 0, statusFilter: null });
        } catch (error) {
            console.error('[FeedbackStore] Error fetching evaluation:', error);
            set({ isLoadingSelected: false });
        }
    },

    /**
     * Start polling for evaluation status updates.
     */
    startPolling: (jobId: string) => {
        // Clear any existing timer
        if (pollTimer) {
            clearInterval(pollTimer);
        }

        set({ isPolling: true, activeJobId: jobId });

        pollTimer = setInterval(async () => {
            try {
                const evaluation = await fetchEvaluationById(jobId);

                if (evaluation.status === 'COMPLETED' || evaluation.status === 'FAILED') {
                    // Stop polling
                    get().stopPolling();

                    const { selectedEvaluation } = get();
                    const isViewingAnother =
                        selectedEvaluation && selectedEvaluation.id !== jobId;

                    if (evaluation.status === 'COMPLETED') {
                        // Add to completed list
                        set((state) => ({
                            completedEvaluations: [
                                {
                                    id: evaluation.id,
                                    subject: evaluation.subject,
                                    problemTextRef: evaluation.problemTextRef,
                                    createdAt: evaluation.createdAt,
                                },
                                ...state.completedEvaluations,
                            ],
                            lastEvaluation: evaluation,
                        }));

                        if (isViewingAnother) {
                            // User is viewing a different solution → popup notification
                            set({
                                notification: {
                                    type: 'success',
                                    message:
                                        'Your evaluation is ready! Select it from the Previous Solutions dropdown to view.',
                                },
                            });
                        } else {
                            // User is waiting → show results directly
                            set({ selectedEvaluation: evaluation });
                        }
                    } else {
                        // FAILED
                        set({ lastEvaluation: evaluation });
                        if (isViewingAnother) {
                            set({
                                notification: {
                                    type: 'error',
                                    message:
                                        'Your evaluation failed. Please try submitting again.',
                                },
                            });
                        } else {
                            set({ selectedEvaluation: evaluation });
                        }
                    }
                }
            } catch (error) {
                console.error('[FeedbackStore] Polling error:', error);
            }
        }, POLL_INTERVAL_MS);
    },

    /**
     * Stop the polling timer.
     */
    stopPolling: () => {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
        set({ isPolling: false, activeJobId: null });
    },

    clearNotification: () => set({ notification: null }),

    reset: () => {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
        set({
            completedEvaluations: [],
            lastEvaluation: null,
            selectedEvaluation: null,
            activeJobId: null,
            isSubmitting: false,
            isPolling: false,
            isLoadingInitial: true,
            isLoadingSelected: false,
            submitError: null,
            notification: null,
            currentProblemIndex: 0,
            statusFilter: null,
        });
    },

    // ── Navigation actions ──

    setCurrentProblemIndex: (index: number) => set({ currentProblemIndex: index }),

    setStatusFilter: (status: string | null) => {
        set({ statusFilter: status, currentProblemIndex: 0 });
    },

    nextProblem: () => {
        const { currentProblemIndex, selectedEvaluation, statusFilter } = get();
        const evaluations = selectedEvaluation?.feedbackJson?.evaluations;
        if (!evaluations) return;
        const filtered = _getFilteredIndices(evaluations, statusFilter);
        const currentPos = filtered.indexOf(currentProblemIndex);
        if (currentPos < filtered.length - 1) {
            set({ currentProblemIndex: filtered[currentPos + 1] });
        }
    },

    prevProblem: () => {
        const { currentProblemIndex, selectedEvaluation, statusFilter } = get();
        const evaluations = selectedEvaluation?.feedbackJson?.evaluations;
        if (!evaluations) return;
        const filtered = _getFilteredIndices(evaluations, statusFilter);
        const currentPos = filtered.indexOf(currentProblemIndex);
        if (currentPos > 0) {
            set({ currentProblemIndex: filtered[currentPos - 1] });
        }
    },
}));

/**
 * Helper: get indices of evaluations matching the status filter.
 * Returns all indices if filter is null.
 */
function _getFilteredIndices(
    evaluations: import('../types/evaluation').ProblemEvaluation[],
    statusFilter: string | null
): number[] {
    if (!statusFilter) return evaluations.map((_, i) => i);
    return evaluations
        .map((ev, i) => ({ ev, i }))
        .filter(({ ev }) => {
            const s = ev.evaluation?.evaluation_status || '';
            if (statusFilter === 'Error') return s.includes('Error') || s.includes('Not Found') || s === 'Unknown';
            return s.includes(statusFilter);
        })
        .map(({ i }) => i);
}

/** Exported for use by components to compute filtered problem lists */
export { _getFilteredIndices as getFilteredIndices };
