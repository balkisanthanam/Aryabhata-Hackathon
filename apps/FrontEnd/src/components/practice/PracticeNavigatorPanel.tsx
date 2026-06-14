import { AnimatePresence, motion } from 'framer-motion';
import type { PracticeExerciseQuestionSummary, PracticeExerciseSummary } from '../../lib/api';

interface PracticeNavigatorPanelProps {
    open: boolean;
    chapterTitle?: string;
    exercises: PracticeExerciseSummary[];
    selectedExerciseId: number | null;
    currentQuestionId?: number;
    isLoadingExercises: boolean;
    isLoadingQuestions: boolean;
    questions: PracticeExerciseQuestionSummary[];
    onClose: () => void;
    onSelectExercise: (exercise: PracticeExerciseSummary) => void;
    onStartExercise: (exercise: PracticeExerciseSummary) => void;
    onJumpToQuestion: (exerciseId: number, questionId: number) => void;
}

export const PracticeNavigatorPanel = ({
    open,
    chapterTitle,
    exercises,
    selectedExerciseId,
    currentQuestionId,
    isLoadingExercises,
    isLoadingQuestions,
    questions,
    onClose,
    onSelectExercise,
    onStartExercise,
    onJumpToQuestion,
}: PracticeNavigatorPanelProps) => {
    const getQuestionLabel = (_question: PracticeExerciseQuestionSummary, index: number) => `Question ${index + 1}`;

    const selectedExercise = exercises.find(exercise => exercise.exerciseId === selectedExerciseId) ?? null;

    return (
        <AnimatePresence>
            {open && (
                <>
                    <motion.div
                        className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                    />

                    <motion.div
                        className="fixed right-0 top-0 h-full w-full sm:w-[420px] lg:w-[520px] bg-surface-light dark:bg-surface-dark shadow-2xl z-50 flex flex-col border-l border-gray-200 dark:border-indigo-900/50"
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
                    >
                        <div className="flex items-start justify-between p-5 border-b border-gray-200 dark:border-gray-700/50">
                            <div className="flex-1 pr-4">
                                <p className="text-xs text-text-muted-light dark:text-gray-400 uppercase tracking-wider font-semibold mb-2">
                                    Exercise Navigator
                                </p>
                                <h3 className="text-lg font-bold text-gray-900 dark:text-white leading-tight">
                                    {chapterTitle || 'Chapter Questions'}
                                </h3>
                                <p className="text-sm text-text-muted-light dark:text-gray-400 mt-2">
                                    Start from an exercise or jump directly to a specific question.
                                </p>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex-shrink-0"
                            >
                                <span className="material-symbols-outlined text-xl text-gray-500">close</span>
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 space-y-5">
                            <div>
                                <p className="text-xs text-text-muted-light dark:text-gray-500 uppercase tracking-wide font-semibold mb-3">
                                    Exercises
                                </p>
                                {isLoadingExercises ? (
                                    <div className="rounded-xl border border-gray-200 dark:border-gray-700/50 p-4 text-sm text-text-muted-light dark:text-gray-400">
                                        Loading exercises...
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        {exercises.map(exercise => {
                                            const isSelected = exercise.exerciseId === selectedExerciseId;
                                            return (
                                                <div
                                                    key={exercise.exerciseId}
                                                    className={`rounded-xl border p-4 transition-all ${isSelected
                                                        ? 'border-primary/40 bg-primary/5 dark:bg-indigo-900/20 shadow-soft'
                                                        : 'border-gray-200 dark:border-gray-700/50 bg-white dark:bg-slate-900/40'
                                                        }`}
                                                >
                                                    <button
                                                        onClick={() => onSelectExercise(exercise)}
                                                        className="w-full text-left"
                                                    >
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div>
                                                                <h4 className="text-sm font-bold text-gray-900 dark:text-white leading-snug">
                                                                    {exercise.exerciseTitle}
                                                                </h4>
                                                                <p className="mt-1 text-xs text-text-muted-light dark:text-gray-400 uppercase tracking-wide">
                                                                    {exercise.questionCount} questions
                                                                </p>
                                                            </div>
                                                            {isSelected && (
                                                                <span className="material-symbols-outlined text-primary">check_circle</span>
                                                            )}
                                                        </div>
                                                    </button>

                                                    {isSelected && (
                                                        <div className="mt-3 pt-3 border-t border-primary/15 dark:border-indigo-800/50">
                                                            <button
                                                                onClick={() => onStartExercise(exercise)}
                                                                className="w-full rounded-xl bg-primary/10 hover:bg-primary/20 text-primary dark:text-indigo-200 text-sm font-semibold py-2.5 px-4 transition-colors"
                                                            >
                                                                Start From First Question
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>

                            <div>
                                <div className="flex items-center justify-between mb-3 gap-3">
                                    <p className="text-xs text-text-muted-light dark:text-gray-500 uppercase tracking-wide font-semibold">
                                        {selectedExercise ? `Questions · ${selectedExercise.exerciseTitle}` : 'Questions'}
                                    </p>
                                    {isLoadingQuestions && (
                                        <span className="text-xs text-text-muted-light dark:text-gray-400">Loading...</span>
                                    )}
                                </div>

                                {!selectedExercise ? (
                                    <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 p-4 text-sm text-text-muted-light dark:text-gray-400">
                                        Select an exercise to see its questions.
                                    </div>
                                ) : questions.length === 0 && !isLoadingQuestions ? (
                                    <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 p-4 text-sm text-text-muted-light dark:text-gray-400">
                                        No questions found for this exercise.
                                    </div>
                                ) : (
                                    <div className="flex flex-wrap gap-2">
                                        {questions.map((question, index) => {
                                            const isCurrent = question.questionId === currentQuestionId;
                                            return (
                                                <button
                                                    key={question.questionId}
                                                    onClick={() => onJumpToQuestion(selectedExercise.exerciseId, question.questionId)}
                                                    className={`px-3 py-2 rounded-lg border text-sm font-semibold transition-all text-left ${isCurrent
                                                        ? 'bg-primary text-white border-primary shadow-lg shadow-primary/20'
                                                        : 'bg-white dark:bg-slate-900/40 border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary text-gray-700 dark:text-gray-200'
                                                        }`}
                                                >
                                                    {getQuestionLabel(question, index)}
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="p-4 border-t border-gray-200 dark:border-gray-700/50">
                            <button
                                onClick={onClose}
                                className="w-full py-2.5 px-4 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary text-sm font-medium transition-colors"
                            >
                                Close Navigator
                            </button>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
};