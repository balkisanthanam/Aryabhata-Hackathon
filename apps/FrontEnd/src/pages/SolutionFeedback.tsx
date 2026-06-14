import { useEffect, useState, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/layout/Navbar';
import { ImageUploadZone } from '../components/feedback/ImageUploadZone';
import { EvaluationSummaryCard } from '../components/feedback/EvaluationSummaryCard';
import { EvaluationCard } from '../components/feedback/EvaluationCard';
import { ProcessingIndicator } from '../components/feedback/ProcessingIndicator';
import { StudentWorkViewer } from '../components/feedback/StudentWorkViewer';
import { useFeedbackStore, getFilteredIndices } from '../store/useFeedbackStore';
import { useUserStore } from '../store/useUserStore';
import type { FeedbackJson, ProblemEvaluation } from '../types/evaluation';
import clsx from 'clsx';

const SUBJECTS = ['Physics', 'Chemistry', 'Maths'];
const PLACEHOLDER_EXAMPLES: Record<string, string> = {
    Physics: 'e.g. 13.4, 13.8-13.10 in thermal props of matter',
    Chemistry: 'e.g. Organic Chemistry 10.1 and 10.5',
    Maths: 'e.g. 8 to 13 miscellaneous exercise in 3d geometry',
};

export const SolutionFeedback = () => {
    const userId = useUserStore(s => s.userId) || 1;
    const userClass = useUserStore(s => s.userClass);
    const board = useUserStore(s => s.board);

    const {
        completedEvaluations,
        lastEvaluation,
        selectedEvaluation,
        isSubmitting,
        isPolling,
        isLoadingInitial,
        isLoadingSelected,
        submitError,
        notification,
        fetchInitialData,
        submitEvaluation,
        selectEvaluation,
        stopPolling,
        clearNotification,
        // Navigation
        currentProblemIndex,
        statusFilter,
        setCurrentProblemIndex,
        setStatusFilter,
        nextProblem,
        prevProblem,
    } = useFeedbackStore();

    // Form state
    const [subject, setSubject] = useState('Physics');
    const [problemTextRef, setProblemTextRef] = useState('');
    const [solutionImages, setSolutionImages] = useState<File[]>([]);
    const [problemImages, setProblemImages] = useState<File[]>([]);

    // Fetch initial data on mount and when navigating back
    useEffect(() => {
        fetchInitialData(userId);
        return () => stopPolling();
    }, [userId]);

    const isSubmissionDisabled = isSubmitting || isPolling;

    const handleSubmit = useCallback(async () => {
        if (!problemTextRef.trim() || solutionImages.length === 0) return;
        await submitEvaluation(
            {
                subject,
                problemTextRef: problemTextRef.trim(),
                userClass: userClass || undefined,
                board: board || undefined,
                solutionImages,
                problemImages: problemImages.length > 0 ? problemImages : undefined,
            },
            userId
        );
        // Clear form
        setProblemTextRef('');
        setSolutionImages([]);
        setProblemImages([]);
    }, [subject, problemTextRef, solutionImages, problemImages, userClass, board, userId, submitEvaluation]);

    const handleSelectPrevious = (id: string) => {
        selectEvaluation(id);
    };

    // Parse the feedback_json
    const feedbackJson: FeedbackJson | null =
        selectedEvaluation?.status === 'COMPLETED' && selectedEvaluation.feedbackJson
            ? (selectedEvaluation.feedbackJson as FeedbackJson)
            : null;

    const isProcessing =
        lastEvaluation &&
        (lastEvaluation.status === 'PENDING' || lastEvaluation.status === 'PROCESSING');

    const isFailed = selectedEvaluation?.status === 'FAILED';

    return (
        <div className="bg-gray-50 dark:bg-background-dark text-slate-900 dark:text-white min-h-screen font-sans flex flex-col items-center relative overflow-x-hidden">
            {/* Mesh Gradient Background */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
                <div className="absolute top-[20%] left-[10%] w-[500px] h-[500px] bg-primary/5 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-normal dark:bg-primary/10 animate-blob"></div>
                <div className="absolute top-[30%] right-[10%] w-[400px] h-[400px] bg-indigo-200/20 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-normal dark:bg-indigo-900/20 animate-blob animation-delay-2000"></div>
                <div className="absolute -bottom-[10%] left-[20%] w-[600px] h-[600px] bg-amber-100/40 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-normal dark:bg-amber-900/10 animate-blob animation-delay-4000"></div>
            </div>

            <div className="relative z-10 w-full flex flex-col items-center">
                <Navbar />

                <main className="w-full max-w-[1200px] flex-1 flex flex-col items-center py-6 sm:py-8 px-3 sm:px-4 md:px-8 lg:px-12 xl:px-20 mx-auto">
                    {/* Back Link */}
                    <div className="w-full mb-4 sm:mb-6">
                        <Link to="/practice" className="flex items-center gap-2 text-indigo-800 dark:text-indigo-300 hover:text-indigo-600 text-sm font-medium transition-colors group">
                            <span className="material-symbols-outlined text-lg group-hover:-translate-x-0.5 transition-transform">arrow_back</span>
                            Back to Practice Topics
                        </Link>
                    </div>

                    {/* Notification Toast */}
                    {notification && (
                        <div className={`w-full mb-4 p-4 rounded-xl border flex items-start gap-3 animate-in fade-in slide-in-from-top-2 duration-300 ${
                            notification.type === 'success'
                                ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800/50'
                                : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800/50'
                        }`}>
                            <span className={`material-symbols-outlined mt-0.5 ${
                                notification.type === 'success' ? 'text-green-600' : 'text-red-600'
                            }`}>
                                {notification.type === 'success' ? 'check_circle' : 'error'}
                            </span>
                            <p className={`text-sm flex-1 ${
                                notification.type === 'success'
                                    ? 'text-green-800 dark:text-green-300'
                                    : 'text-red-800 dark:text-red-300'
                            }`}>
                                {notification.message}
                            </p>
                            <button onClick={clearNotification} className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded">
                                <span className="material-symbols-outlined text-sm text-gray-500">close</span>
                            </button>
                        </div>
                    )}

                    {isLoadingInitial ? (
                        <div className="flex items-center justify-center py-20 w-full">
                            <div className="w-10 h-10 border-4 border-gray-200 dark:border-gray-700 border-t-primary rounded-full animate-spin"></div>
                        </div>
                    ) : (
                        <div className="flex flex-col w-full gap-6">
                            {/* ══════════════════════════════════════════════
                                ZONE 1: ACTION AREA — Submission Form
                            ══════════════════════════════════════════════ */}
                            <section className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-4 sm:p-6 md:p-8 border border-gray-200 dark:border-indigo-900/50 shadow-sm w-full relative z-20 flex flex-col gap-6">
                                <h2 className="text-slate-900 dark:text-white font-bold text-lg flex items-center gap-2">
                                    <span className="material-symbols-outlined text-primary">auto_awesome</span>
                                    Get AI Feedback on Your Solution
                                </h2>

                                {/* Subject + Problem Description Row */}
                                <div className="flex flex-col sm:flex-row gap-4">
                                    {/* Subject Selector */}
                                    <div className="flex flex-col gap-1.5 sm:w-40 shrink-0">
                                        <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                            Subject
                                        </label>
                                        <select
                                            aria-label="Select subject"
                                            value={subject}
                                            onChange={e => setSubject(e.target.value)}
                                            disabled={isSubmissionDisabled}
                                            className="rounded-lg border-gray-300 dark:border-gray-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm focus:border-primary focus:ring focus:ring-primary/20 text-sm h-11 px-3 disabled:opacity-50"
                                        >
                                            {SUBJECTS.map(s => (
                                                <option key={s} value={s}>{s}</option>
                                            ))}
                                        </select>
                                    </div>

                                    {/* Problem Description */}
                                    <div className="flex flex-col gap-1.5 flex-1">
                                        <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                            Problem Reference <span className="text-red-500">*</span>
                                        </label>
                                        <input
                                            value={problemTextRef}
                                            onChange={e => setProblemTextRef(e.target.value)}
                                            disabled={isSubmissionDisabled}
                                            placeholder={PLACEHOLDER_EXAMPLES[subject] || 'Describe the problems you solved...'}
                                            className="w-full rounded-lg border-gray-300 dark:border-gray-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm focus:border-primary focus:ring focus:ring-primary/20 text-sm h-11 px-3 disabled:opacity-50"
                                            type="text"
                                        />
                                    </div>
                                </div>

                                {/* Image Upload Zones */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <ImageUploadZone
                                        label="Your Solution Pages"
                                        description="Drop your handwritten solution pages here"
                                        files={solutionImages}
                                        onFilesChange={setSolutionImages}
                                        maxFiles={5}
                                        required
                                    />
                                    <ImageUploadZone
                                        label="Problem Images (Optional)"
                                        description="Upload if the problem is not from NCERT"
                                        files={problemImages}
                                        onFilesChange={setProblemImages}
                                        maxFiles={5}
                                    />
                                </div>

                                {/* Submit Error */}
                                {submitError && (
                                    <p className="text-red-500 dark:text-red-400 text-sm flex items-center gap-1">
                                        <span className="material-symbols-outlined text-sm">error</span>
                                        {submitError}
                                    </p>
                                )}

                                {/* Submit Button */}
                                <button
                                    onClick={handleSubmit}
                                    disabled={isSubmissionDisabled || !problemTextRef.trim() || solutionImages.length === 0}
                                    className="w-full bg-primary hover:bg-indigo-600 text-white font-bold text-base sm:text-lg py-3 sm:py-4 px-6 rounded-xl shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all transform hover:-translate-y-0.5 flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
                                >
                                    {isSubmitting ? (
                                        <>
                                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                            Submitting...
                                        </>
                                    ) : (
                                        <>
                                            <span className="material-symbols-outlined text-xl sm:text-2xl">auto_awesome</span>
                                            Submit for Evaluation
                                        </>
                                    )}
                                </button>

                                {isSubmissionDisabled && !isSubmitting && (
                                    <p className="text-amber-600 dark:text-amber-400 text-xs text-center flex items-center justify-center gap-1">
                                        <span className="material-symbols-outlined text-sm">info</span>
                                        A solution is being evaluated. New submissions will be enabled once it completes.
                                    </p>
                                )}
                            </section>

                            {/* ══════════════════════════════════════════════
                                ZONE 2: PREVIOUS SOLUTIONS DROPDOWN
                            ══════════════════════════════════════════════ */}
                            {completedEvaluations.length > 0 && (
                                <section className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-4 sm:p-5 border border-gray-200 dark:border-indigo-900/50 shadow-sm w-full">
                                    <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                                        <label className="text-sm font-bold text-slate-700 dark:text-slate-300 flex items-center gap-2 shrink-0">
                                            <span className="material-symbols-outlined text-lg text-primary">history</span>
                                            Previous Solutions
                                        </label>
                                        <select
                                            aria-label="Select previous evaluation"
                                            onChange={e => {
                                                if (e.target.value) handleSelectPrevious(e.target.value);
                                            }}
                                            value={selectedEvaluation?.id || ''}
                                            className="flex-1 rounded-lg border-gray-300 dark:border-gray-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm focus:border-primary focus:ring focus:ring-primary/20 text-sm h-10 px-3"
                                        >
                                            <option value="">Select a previous evaluation...</option>
                                            {completedEvaluations.map(e => (
                                                <option key={e.id} value={e.id}>
                                                    {e.subject} — {e.problemTextRef || 'Untitled'} ({new Date(e.createdAt).toLocaleDateString()})
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </section>
                            )}

                            {/* ══════════════════════════════════════════════
                                ZONE 3: SOLUTION VIEWING SPACE
                            ══════════════════════════════════════════════ */}
                            <div className="w-full flex flex-col gap-4">
                                {/* Processing state */}
                                {isProcessing && !selectedEvaluation && (
                                    <ProcessingIndicator
                                        subject={lastEvaluation.subject}
                                        problemTextRef={lastEvaluation.problemTextRef}
                                    />
                                )}

                                {/* Loading selected */}
                                {isLoadingSelected && (
                                    <div className="flex items-center justify-center py-12">
                                        <div className="w-8 h-8 border-4 border-gray-200 dark:border-gray-700 border-t-primary rounded-full animate-spin"></div>
                                    </div>
                                )}

                                {/* Failed state */}
                                {isFailed && selectedEvaluation && (
                                    <div className="bg-red-50 dark:bg-red-900/20 rounded-xl p-6 border border-red-200 dark:border-red-800/50 text-center">
                                        <span className="material-symbols-outlined text-red-500 text-4xl mb-3">error</span>
                                        <h3 className="text-red-700 dark:text-red-400 font-bold text-lg mb-2">
                                            Evaluation Failed
                                        </h3>
                                        <p className="text-red-600 dark:text-red-300 text-sm">
                                            Something went wrong while evaluating your solution. Please try submitting again.
                                        </p>
                                    </div>
                                )}

                                {/* Completed — show results */}
                                {feedbackJson && (
                                    <ProblemNavigator
                                        feedbackJson={feedbackJson}
                                        studentWorkUrls={selectedEvaluation?.studentWorkUrls || []}
                                        problemImageUrls={selectedEvaluation?.problemImageUrls || []}
                                        currentProblemIndex={currentProblemIndex}
                                        statusFilter={statusFilter}
                                        onFilterByStatus={setStatusFilter}
                                        onSetIndex={setCurrentProblemIndex}
                                        onNext={nextProblem}
                                        onPrev={prevProblem}
                                    />
                                )}

                                {/* Empty state — no selection and not processing */}
                                {!isProcessing && !selectedEvaluation && !isLoadingSelected && completedEvaluations.length === 0 && (
                                    <div className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-8 sm:p-12 border border-gray-200 dark:border-indigo-900/50 shadow-sm text-center flex flex-col items-center gap-3">
                                        <span className="material-symbols-outlined text-5xl text-slate-300 dark:text-slate-600">rate_review</span>
                                        <h3 className="text-slate-700 dark:text-slate-300 font-semibold text-lg">
                                            No Evaluations Yet
                                        </h3>
                                        <p className="text-slate-400 dark:text-slate-500 text-sm max-w-md">
                                            Upload your handwritten solution above and get detailed AI feedback with step-by-step corrections.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
};
// ═══════════════════════════════════════════════════════════════════
// ProblemNavigator — one-problem-at-a-time view with pill strip
// ═══════════════════════════════════════════════════════════════════

interface ProblemNavigatorProps {
    feedbackJson: FeedbackJson;
    studentWorkUrls: string[];
    problemImageUrls: string[];
    currentProblemIndex: number;
    statusFilter: string | null;
    onFilterByStatus: (status: string | null) => void;
    onSetIndex: (index: number) => void;
    onNext: () => void;
    onPrev: () => void;
}

/** Map evaluation_status string → colour token */
function statusColor(ev: ProblemEvaluation): string {
    const s = ev.evaluation?.evaluation_status || '';
    if (s.includes('Correct') && !s.includes('Incorrect')) return 'green';
    if (s.includes('Acceptable')) return 'amber';
    if (s.includes('Incorrect')) return 'red';
    return 'slate'; // Error / Not Found / Unknown
}

const PILL_BG: Record<string, string> = {
    green: 'bg-green-500',
    amber: 'bg-amber-500',
    red: 'bg-red-500',
    slate: 'bg-slate-400',
};
const PILL_RING: Record<string, string> = {
    green: 'ring-green-400',
    amber: 'ring-amber-400',
    red: 'ring-red-400',
    slate: 'ring-slate-400',
};

const ProblemNavigator = ({
    feedbackJson,
    studentWorkUrls,
    problemImageUrls,
    currentProblemIndex,
    statusFilter,
    onFilterByStatus,
    onSetIndex,
    onNext,
    onPrev,
}: ProblemNavigatorProps) => {
    const evaluations = feedbackJson.evaluations;
    const filteredIndices = useMemo(
        () => getFilteredIndices(evaluations, statusFilter),
        [evaluations, statusFilter]
    );

    // Clamp the current index to valid evaluation range
    const safeIndex = Math.max(0, Math.min(currentProblemIndex, evaluations.length - 1));
    const currentEval = evaluations[safeIndex];

    // Position in the filtered list for "X of Y" label
    const posInFiltered = filteredIndices.indexOf(safeIndex);
    const isFirst = posInFiltered <= 0;
    const isLast = posInFiltered >= filteredIndices.length - 1;

    return (
        <div className="flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Summary Card — clickable tiles */}
            <EvaluationSummaryCard
                summary={feedbackJson.summary}
                activeFilter={statusFilter}
                onFilterByStatus={onFilterByStatus}
            />

            {/* ── Uploaded Work Viewer (collapsible) ── */}
            <StudentWorkViewer
                studentWorkUrls={studentWorkUrls}
                problemImageUrls={problemImageUrls}
            />

            {/* ── Navigation Bar ── */}
            <div className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-3 sm:p-4 border border-gray-200 dark:border-indigo-900/50 shadow-sm flex flex-col gap-3">
                {/* Prev / label / Next */}
                <div className="flex items-center justify-between">
                    <button
                        onClick={onPrev}
                        disabled={isFirst}
                        className="flex items-center gap-1 text-sm font-medium text-primary hover:text-indigo-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                        <span className="material-symbols-outlined text-lg">chevron_left</span>
                        <span className="hidden sm:inline">Previous</span>
                    </button>

                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                        Problem{' '}
                        <span className="text-primary">{posInFiltered >= 0 ? posInFiltered + 1 : '—'}</span>
                        {' '}of{' '}
                        <span className="text-primary">{filteredIndices.length}</span>
                        {statusFilter && (
                            <span className="ml-1 text-xs font-normal text-slate-400">
                                ({statusFilter})
                            </span>
                        )}
                    </span>

                    <button
                        onClick={onNext}
                        disabled={isLast}
                        className="flex items-center gap-1 text-sm font-medium text-primary hover:text-indigo-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                        <span className="hidden sm:inline">Next</span>
                        <span className="material-symbols-outlined text-lg">chevron_right</span>
                    </button>
                </div>

                {/* ── Color-coded pill strip ── */}
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
                    {evaluations.map((ev, idx) => {
                        const col = statusColor(ev);
                        const isCurrent = idx === safeIndex;
                        const isInFilter = filteredIndices.includes(idx);
                        return (
                            <button
                                key={idx}
                                onClick={() => onSetIndex(idx)}
                                aria-label={`Problem ${ev.problem_id || idx + 1}`}
                                title={`Problem ${ev.problem_id || idx + 1}`}
                                className={clsx(
                                    'shrink-0 rounded-full transition-all duration-200',
                                    PILL_BG[col],
                                    isCurrent
                                        ? `w-8 h-8 ring-2 ring-offset-2 dark:ring-offset-gray-900 ${PILL_RING[col]} scale-110`
                                        : 'w-5 h-5 hover:scale-110',
                                    !isInFilter && statusFilter ? 'opacity-25' : ''
                                )}
                            >
                                {isCurrent && (
                                    <span className="text-[10px] font-bold text-white leading-none flex items-center justify-center h-full">
                                        {ev.problem_id || idx + 1}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* ── Single Evaluation Card ── */}
            {currentEval && (
                <EvaluationCard
                    key={currentEval.problem_id || safeIndex}
                    evaluation={currentEval}
                    index={safeIndex}
                />
            )}
        </div>
    );
};