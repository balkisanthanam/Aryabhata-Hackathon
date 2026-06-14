import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Navbar } from '../components/layout/Navbar';
import { QuestionView } from '../components/practice/QuestionView';
import { SolutionView } from '../components/practice/SolutionView';
import { PracticeNavigatorPanel } from '../components/practice/PracticeNavigatorPanel';
import SriChakramLoader from '../components/common/SriChakramLoader';
import { UnderConstruction } from '../components/common/UnderConstruction';
import {
    fetchExerciseQuestions,
    fetchPracticeChapterMap,
    fetchQuestion,
    saveProgress,
    PracticeChapterMapResponse,
    PracticeExerciseQuestionSummary,
    QuestionResponse,
} from '../lib/api';

export const PracticeSession = () => {
    const { chapterId } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();

    const [questionData, setQuestionData] = useState<QuestionResponse | null>(null);
    const [chapterMap, setChapterMap] = useState<PracticeChapterMapResponse | null>(null);
    const [exerciseQuestionsById, setExerciseQuestionsById] = useState<Record<number, PracticeExerciseQuestionSummary[]>>({});
    const [loading, setLoading] = useState(true);
    const [chapterMapLoading, setChapterMapLoading] = useState(false);
    const [navigatorOpen, setNavigatorOpen] = useState(false);
    const [selectedExerciseId, setSelectedExerciseId] = useState<number | null>(null);
    const [loadingExerciseQuestionsFor, setLoadingExerciseQuestionsFor] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showSimilarPopup, setShowSimilarPopup] = useState(false);

    const getCurrentQuestionLabel = () => {
        if (!questionData) return '';

        const exerciseQuestions = exerciseQuestionsById[questionData.exerciseId] || [];
        const questionIndex = exerciseQuestions.findIndex(q => q.questionId === questionData.questionId);
        const refMatch = questionData.questionRef?.match(/Q(\d+)$/i);
        const fallbackNumber = refMatch ? parseInt(refMatch[1], 10) : questionData.questionId;
        const questionNumber = questionIndex >= 0 ? questionIndex + 1 : fallbackNumber;

        return `Question ${questionNumber}`;
    };

    // Current State from URL or Data
    const mode = (searchParams.get('mode') as 'start' | 'resume') || 'start';
    const paramQuestionId = searchParams.get('questionId') ? parseInt(searchParams.get('questionId')!) : undefined;
    const paramExerciseId = searchParams.get('exerciseId') ? parseInt(searchParams.get('exerciseId')!) : undefined;

    useEffect(() => {
        setChapterMap(null);
        setExerciseQuestionsById({});
        setSelectedExerciseId(null);
        setNavigatorOpen(false);
    }, [chapterId]);

    useEffect(() => {
        const loadChapterMap = async () => {
            if (!chapterId) return;

            setChapterMapLoading(true);
            try {
                const data = await fetchPracticeChapterMap(chapterId);
                setChapterMap(data);
            } catch (err) {
                console.error('Failed to load chapter map:', err);
            } finally {
                setChapterMapLoading(false);
            }
        };

        loadChapterMap();
    }, [chapterId]);

    useEffect(() => {
        const loadQuestion = async () => {
            if (!chapterId) return;

            setLoading(true);
            setError(null);
            try {
                const data = await fetchQuestion(chapterId, mode, paramQuestionId, paramExerciseId);
                setQuestionData(data);
                setSelectedExerciseId(data.exerciseId);

                // If URL doesn't have the questionId, update it to reflect loaded question
                // But avoid loop if paramQuestionId matches data.questionId
                if (!paramQuestionId || paramQuestionId !== data.questionId) {
                    // Updating params might re-trigger effect if we dependent on paramQuestionId
                    // Better to just rely on internal state or use 'replace' navigation
                }

            } catch (err: any) {
                console.error('Failed to load question:', err);
                setError(err.response?.data?.error || 'Failed to load question. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        loadQuestion();
    }, [chapterId, mode, paramQuestionId, paramExerciseId]);

    useEffect(() => {
        const loadExerciseQuestions = async () => {
            if (!selectedExerciseId || exerciseQuestionsById[selectedExerciseId]) return;

            setLoadingExerciseQuestionsFor(selectedExerciseId);
            try {
                const data = await fetchExerciseQuestions(selectedExerciseId);
                setExerciseQuestionsById(prev => ({
                    ...prev,
                    [selectedExerciseId]: data.questions,
                }));
            } catch (err) {
                console.error('Failed to load exercise questions:', err);
            } finally {
                setLoadingExerciseQuestionsFor(null);
            }
        };

        if (navigatorOpen || questionData?.exerciseId === selectedExerciseId) {
            loadExerciseQuestions();
        }
    }, [navigatorOpen, questionData?.exerciseId, selectedExerciseId, exerciseQuestionsById]);


    const handleNavigation = async (nextQId: number | null) => {
        if (!nextQId || !questionData || !chapterId) return;

        // Set loading true immediately for instant feedback
        setLoading(true);

        // Save Progress before moving
        try {
            await saveProgress(parseInt(chapterId), questionData.exerciseId, questionData.questionId);
        } catch (e) {
            console.error("Failed to save progress", e);
        }

        // Navigate to new question (this triggers re-fetch via useEffect)
        setSearchParams({ questionId: nextQId.toString(), mode: 'start' });
    };

    const handleSelectExercise = (exerciseId: number) => {
        setSelectedExerciseId(exerciseId);
    };

    const handleStartExercise = (exerciseId: number) => {
        setNavigatorOpen(false);
        setSearchParams({ exerciseId: exerciseId.toString(), mode: 'start' });
    };

    const handleJumpToQuestion = (exerciseId: number, questionId: number) => {
        setNavigatorOpen(false);
        setSearchParams({ questionId: questionId.toString(), exerciseId: exerciseId.toString(), mode: 'start' });
    };

    // Initial Loading State (Full Screen)
    if (loading && !questionData) {
        return (
            <div className="bg-background-light dark:bg-background-dark min-h-screen flex flex-col items-center">
                <Navbar />
                <div className="flex-1 flex flex-col items-center justify-center">
                    <SriChakramLoader className="w-48 h-48" />
                    <p className="mt-8 font-serif text-xl text-primary dark:text-indigo-300 animate-pulse font-medium">
                        Preparing your next challenge...
                    </p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-background-light dark:bg-background-dark min-h-screen flex flex-col items-center">
                <Navbar />
                <div className="flex-1 flex flex-col items-center justify-center gap-4">
                    <div className="text-red-500 font-bold text-lg">{error}</div>
                    <Link to="/practice" className="text-primary hover:underline">Return to Dashboard</Link>
                </div>
            </div>
        );
    }

    if (!questionData) return null;

    return (
        <div className="bg-background-light dark:bg-background-dark text-text-main-light dark:text-text-main-dark min-h-screen font-sans flex flex-col items-center">
            <Navbar />
            <main className="w-full max-w-6xl space-y-6 py-4 lg:py-8 px-4 sm:px-6 lg:px-8 relative">
                {/* Loading Overlay: Subtly transparent background with blur */}
                {loading && questionData && (
                    <div className="absolute inset-0 bg-white/90 dark:bg-slate-900/90 backdrop-blur-sm z-50 flex flex-col items-center justify-center rounded-xl transition-all duration-300">
                        <SriChakramLoader className="w-48 h-48" />
                        <h3 className="text-xl font-serif text-primary/80 dark:text-indigo-300 animate-pulse">
                            Preparing your next challenge...
                        </h3>
                    </div>
                )}
                {/* Back Button */}
                <div className="flex items-center justify-start">
                    <Link to="/practice" className="flex items-center gap-2 text-text-muted-light dark:text-indigo-300 hover:text-primary dark:hover:text-white transition-colors font-medium text-sm">
                        <span className="material-symbols-outlined text-lg">arrow_back</span>
                        Back to Practice Topics
                    </Link>
                </div>

                {/* Filters Row (Shifted to Clean White Card) */}
                <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-indigo-900/50 p-4">
                    <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto">
                        <div className="relative group">
                            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <span className="material-symbols-outlined text-gray-400 text-lg">science</span>
                            </span>
                            <div className="pl-10 pr-4 py-2 w-full sm:w-40 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white font-medium flex items-center">
                                {questionData.subject || 'Subject'}
                            </div>
                        </div>
                        <div className="relative group">
                            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <span className="material-symbols-outlined text-gray-400 text-lg">menu_book</span>
                            </span>
                            <div className="pl-10 pr-4 py-2 w-full sm:w-auto min-w-[16rem] rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white font-medium flex items-center">
                                {questionData.chapterTitle ? `${questionData.chapterTitle} - ${questionData.exerciseTitle}` : (questionData.exerciseTitle || 'Chapter Questions')}
                            </div>
                        </div>
                        <div className="relative group">
                            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <span className="material-symbols-outlined text-gray-400 text-lg">tag</span>
                            </span>
                            <div className="pl-10 pr-4 py-2 w-full sm:w-44 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white font-medium flex items-center">
                                {getCurrentQuestionLabel()}
                            </div>
                        </div>
                    </div>

                    <button
                        onClick={() => setNavigatorOpen(true)}
                        className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/40 text-primary dark:text-indigo-200 hover:bg-primary hover:text-white transition-all text-sm font-semibold border border-indigo-100 dark:border-indigo-800 w-full lg:w-auto"
                    >
                        <span className="material-symbols-outlined text-lg">format_list_bulleted</span>
                        Jump to Exercise & Question
                    </button>
                </div>

                {/* Main Content Card - Single Column Stack */}
                <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-gray-200 dark:border-indigo-900/50 overflow-hidden">
                    {/* 1. Question View (Text + Image) */}
                    <div className="bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-800/50 border-b border-gray-200 dark:border-indigo-900/50">
                        <QuestionView question={{
                            question_id: getCurrentQuestionLabel(),
                            question_text: questionData.content.question_text || "No Question Text",
                            figure: questionData.content.figure_info?.[0] ? {
                                url: questionData.content.figure_info[0].url,
                                caption: questionData.content.figure_info[0].description
                            } : undefined
                        }} />
                    </div>

                    {/* 2. Solution View (Includes Key Concept inside) */}
                    <div className="pt-6">
                        <SolutionView solution={questionData.solution} />
                    </div>
                </div>

                {/* Navigation Footer */}
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-6 border-t border-gray-200 dark:border-indigo-900/50 mt-4">
                    <button
                        onClick={() => handleNavigation(questionData.prevQuestionId)}
                        disabled={!questionData.prevQuestionId}
                        className={`group flex items-center gap-3 transition-colors ${!questionData.prevQuestionId ? 'opacity-50 cursor-not-allowed' : 'text-text-muted-light dark:text-indigo-300 hover:text-primary dark:hover:text-white'}`}
                    >
                        <div className="w-10 h-10 rounded-full bg-surface-light dark:bg-surface-dark shadow-sm border border-gray-200 dark:border-indigo-900 flex items-center justify-center group-hover:border-primary group-hover:bg-primary group-hover:text-white transition-all">
                            <span className="material-symbols-outlined">arrow_back</span>
                        </div>
                        <span className="font-medium font-serif">Prev Problem</span>
                    </button>

                    <button
                        onClick={() => setShowSimilarPopup(true)}
                        className="bg-primary/5 dark:bg-indigo-900/40 hover:bg-primary/10 dark:hover:bg-indigo-900/60 text-primary dark:text-indigo-200 px-8 py-3 rounded-xl font-semibold shadow-sm transition-colors w-full sm:w-auto text-center border border-primary/20 flex items-center justify-center gap-2 cursor-pointer"
                    >
                        <span className="material-symbols-outlined">dataset</span>
                        Show Similar Problems
                    </button>

                    <button
                        onClick={() => handleNavigation(questionData.nextQuestionId)}
                        disabled={!questionData.nextQuestionId}
                        className={`group flex items-center gap-3 transition-colors ${!questionData.nextQuestionId ? 'opacity-50 cursor-not-allowed' : 'text-text-muted-light dark:text-indigo-300 hover:text-primary dark:hover:text-white'}`}
                    >
                        <span className="font-medium font-serif">Next Problem</span>
                        <div className="w-10 h-10 rounded-full bg-surface-light dark:bg-surface-dark shadow-sm border border-gray-200 dark:border-indigo-900 flex items-center justify-center group-hover:border-primary group-hover:bg-primary group-hover:text-white transition-all">
                            <span className="material-symbols-outlined">arrow_forward</span>
                        </div>
                    </button>
                </div>

            </main>

            {/* Similar Problems Modal */}
            {
                showSimilarPopup && (
                    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
                        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full mx-4 overflow-hidden relative animate-in zoom-in-95 duration-200 border border-gray-200 dark:border-gray-800">
                            <UnderConstruction
                                title="Similar Problems"
                                variant="embedded"
                                onBack={() => setShowSimilarPopup(false)}
                            />
                        </div>
                    </div>
                )
            }

            <PracticeNavigatorPanel
                open={navigatorOpen}
                chapterTitle={questionData.chapterTitle || chapterMap?.chapterTitle}
                exercises={chapterMap?.exercises || []}
                selectedExerciseId={selectedExerciseId}
                currentQuestionId={questionData.questionId}
                isLoadingExercises={chapterMapLoading}
                isLoadingQuestions={loadingExerciseQuestionsFor === selectedExerciseId}
                questions={selectedExerciseId ? (exerciseQuestionsById[selectedExerciseId] || []) : []}
                onClose={() => setNavigatorOpen(false)}
                onSelectExercise={(exercise) => handleSelectExercise(exercise.exerciseId)}
                onStartExercise={(exercise) => handleStartExercise(exercise.exerciseId)}
                onJumpToQuestion={handleJumpToQuestion}
            />
        </div >
    );
};
