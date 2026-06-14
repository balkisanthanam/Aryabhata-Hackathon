import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Navbar } from '../components/layout/Navbar';
import { SolutionView } from '../components/practice/SolutionView';
import { LatexRenderer } from '../components/common/LatexRenderer';
import { QuestionContent } from '../components/common/QuestionContent';
import SriChakramLoader from '../components/common/SriChakramLoader';
import {
    fetchAccentSession,
    fetchAccentQuestion,
    recordAccentProgress,
    type AccentQuestionSummary,
    type AccentQuestionResponse,
} from '../lib/api';

// ─── helpers ─────────────────────────────────────────────────────────────────

function difficultyBadge(d: string | null) {
    if (d === 'EASY') return { label: 'EASY', cls: 'text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20' };
    if (d === 'HARD') return { label: 'HARD', cls: 'text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20' };
    return { label: d ?? 'MEDIUM', cls: 'text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20' };
}

function optionLabel(index: number) {
    return String.fromCharCode(65 + index); // A B C D
}

// ─── Question chip in navigator ───────────────────────────────────────────────

function QuestionChip({
    q,
    index,
    active,
    onClick,
}: {
    q: AccentQuestionSummary;
    index: number;
    active: boolean;
    onClick: () => void;
}) {
    const diff = difficultyBadge(q.difficulty);
    let statusIcon = 'radio_button_unchecked';
    let statusCls = 'text-slate-400 dark:text-slate-500';
    if (q.attempted && q.wasCorrect === true) { statusIcon = 'check_circle'; statusCls = 'text-emerald-500'; }
    else if (q.attempted && q.wasCorrect === false) { statusIcon = 'cancel'; statusCls = 'text-rose-500'; }
    else if (q.attempted) { statusIcon = 'check_circle'; statusCls = 'text-slate-400'; }

    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-all
                ${active
                    ? 'bg-indigo-50 dark:bg-indigo-900/40 text-primary dark:text-indigo-200 font-semibold border border-indigo-200 dark:border-indigo-800'
                    : 'hover:bg-gray-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 border border-transparent'
                }`}
        >
            <span className={`material-symbols-outlined text-base shrink-0 ${statusCls}`}>{statusIcon}</span>
            <span className="flex-1 font-sans">Q{index + 1}</span>
            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${diff.cls}`}>{diff.label}</span>
        </button>
    );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function AccentSession() {
    const { chapterId } = useParams<{ chapterId: string }>();
    const chapterIdNum = parseInt(chapterId ?? '0');

    const [questions, setQuestions] = useState<AccentQuestionSummary[]>([]);
    const questionsRef = useRef<AccentQuestionSummary[]>([]);
    const [questionsLoaded, setQuestionsLoaded] = useState(false);
    const [stats, setStats] = useState({ total: 0, attempted: 0, correct: 0 });
    const [currentIdx, setCurrentIdx] = useState(0);
    const [question, setQuestion] = useState<AccentQuestionResponse | null>(null);
    const [loadingList, setLoadingList] = useState(true);
    const [loadingQ, setLoadingQ] = useState(false);

    // Answer state
    const [selectedOption, setSelectedOption] = useState<string>('');
    const [numericalInput, setNumericalInput] = useState<string>('');
    const [revealed, setRevealed] = useState(false);
    const [wasCorrect, setWasCorrect] = useState<boolean | null>(null);
    const [showSolution, setShowSolution] = useState(false);

    const startTimeRef = useRef<number>(Date.now());

    // ── Load question list ──────────────────────────────────────────────────
    useEffect(() => {
        if (!chapterIdNum) return;
        setLoadingList(true);
        fetchAccentSession(chapterIdNum)
            .then(({ questions: qs, stats: s }) => {
                questionsRef.current = qs;
                setQuestions(qs);
                setStats(s);
                setCurrentIdx(0);
                setQuestionsLoaded(true);
            })
            .catch(console.error)
            .finally(() => setLoadingList(false));
    }, [chapterIdNum]);

    // ── Load full question when index changes ───────────────────────────────
    const loadQuestion = useCallback((idx: number) => {
        const q = questionsRef.current[idx];
        if (!q) return;
        setLoadingQ(true);
        setQuestion(null);
        setSelectedOption('');
        setNumericalInput('');
        setRevealed(false);
        setWasCorrect(null);
        setShowSolution(false);
        startTimeRef.current = Date.now();
        fetchAccentQuestion(q.id)
            .then(setQuestion)
            .catch(console.error)
            .finally(() => setLoadingQ(false));
    }, []);

    useEffect(() => {
        if (questionsLoaded) loadQuestion(currentIdx);
    }, [currentIdx, questionsLoaded, loadQuestion]);

    // ── Answer verification ─────────────────────────────────────────────────
    const handleVerify = async () => {
        if (!question) return;
        const isNumerical = question.section === 'Integer';
        const userAnswer = isNumerical ? numericalInput.trim() : selectedOption;
        if (!userAnswer) return;

        const correct = question.answerKey
            ? userAnswer.toUpperCase() === question.answerKey.toUpperCase()
            : null;

        setWasCorrect(correct);
        setRevealed(true);

        const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
        try {
            await recordAccentProgress({
                questionId: question.id,
                chapterId: chapterIdNum,
                wasCorrect: correct,
                wasSkipped: false,
                timeSpentSeconds: elapsed,
            });
            setQuestions((prev) => {
                const next = prev.map((q) => q.id === question.id ? { ...q, attempted: true, wasCorrect: correct } : q);
                questionsRef.current = next;
                return next;
            });
            setStats((s) => ({
                ...s,
                attempted: s.attempted + (questions[currentIdx]?.attempted ? 0 : 1),
                correct: s.correct + (correct ? 1 : 0),
            }));
        } catch (err) {
            console.error('Failed to record attempt:', err);
        }
    };

    const handleSkip = async () => {
        if (!question) return;
        const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
        try {
            await recordAccentProgress({
                questionId: question.id,
                chapterId: chapterIdNum,
                wasCorrect: null,
                wasSkipped: true,
                timeSpentSeconds: elapsed,
            });
        } catch (err) {
            console.error('Failed to record skip:', err);
        }
        goNext();
    };

    const goNext = () => { if (currentIdx < questions.length - 1) setCurrentIdx((i) => i + 1); };
    const goPrev = () => { if (currentIdx > 0) setCurrentIdx((i) => i - 1); };

    // ── Full-screen loading ─────────────────────────────────────────────────
    if (loadingList) {
        return (
            <div className="bg-background-light dark:bg-background-dark min-h-screen flex flex-col items-center">
                <Navbar />
                <div className="flex-1 flex flex-col items-center justify-center">
                    <SriChakramLoader className="w-48 h-48" />
                    <p className="mt-8 font-serif text-xl text-primary dark:text-indigo-300 animate-pulse font-medium">
                        Loading JEE questions…
                    </p>
                </div>
            </div>
        );
    }

    if (questions.length === 0) {
        return (
            <div className="bg-background-light dark:bg-background-dark min-h-screen flex flex-col items-center">
                <Navbar />
                <div className="flex-1 flex flex-col items-center justify-center gap-4 text-text-muted-light dark:text-slate-400">
                    <span className="material-symbols-outlined text-5xl">quiz</span>
                    <p className="text-lg font-serif font-semibold">No JEE questions available for this chapter yet.</p>
                    <Link to="/practice" className="text-primary hover:underline text-sm font-medium">
                        Back to Practice
                    </Link>
                </div>
            </div>
        );
    }

    const currentQ = questions[currentIdx];
    const isNumerical = question?.section === 'Integer';
    const canVerify = !revealed && (isNumerical ? numericalInput.trim().length > 0 : selectedOption.length > 0);

    return (
        <div className="bg-background-light dark:bg-background-dark min-h-screen flex flex-col font-sans">
            <Navbar />

            <div className="flex flex-1 w-full max-w-7xl mx-auto px-4 py-6 gap-6">

                {/* ── Left sidebar: question navigator ── */}
                <aside className="hidden lg:flex flex-col w-52 shrink-0">
                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-gray-200 dark:border-indigo-900/50 shadow-sm overflow-hidden sticky top-6">
                        {/* Header */}
                        <div className="px-4 py-3 border-b border-gray-200 dark:border-indigo-900/50 bg-gradient-to-r from-gray-50 to-white dark:from-slate-800 dark:to-slate-800/50">
                            <p className="text-xs font-bold text-orange-600 dark:text-orange-400 uppercase tracking-wider">
                                JEE Ascent
                            </p>
                            <p className="text-xs text-text-muted-light dark:text-slate-400 mt-0.5 font-sans">
                                {stats.attempted}/{stats.total} attempted · {stats.correct} correct
                            </p>
                        </div>
                        {/* Question list */}
                        <div className="overflow-y-auto max-h-[calc(100vh-200px)] p-2 space-y-0.5">
                            {questions.map((q, i) => (
                                <QuestionChip
                                    key={q.id}
                                    q={q}
                                    index={i}
                                    active={i === currentIdx}
                                    onClick={() => setCurrentIdx(i)}
                                />
                            ))}
                        </div>
                    </div>
                </aside>

                {/* ── Main content ── */}
                <main className="flex-1 min-w-0 space-y-6">

                    {/* Back + breadcrumb */}
                    <div className="flex items-center justify-between">
                        <Link
                            to="/practice"
                            className="flex items-center gap-2 text-text-muted-light dark:text-indigo-300 hover:text-primary dark:hover:text-white transition-colors font-medium text-sm"
                        >
                            <span className="material-symbols-outlined text-lg">arrow_back</span>
                            Back to Practice
                        </Link>
                        <div className="flex items-center gap-2 text-sm text-text-muted-light dark:text-slate-400">
                            <span className="font-bold text-orange-600 dark:text-orange-400">JEE Ascent</span>
                            <span>·</span>
                            <span>Q{currentIdx + 1} / {questions.length}</span>
                            {currentQ?.section === 'Integer' && (
                                <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 text-xs font-semibold">
                                    Numerical
                                </span>
                            )}
                            {currentQ?.subject && (
                                <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-xs">
                                    {currentQ.subject}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Question card */}
                    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-gray-200 dark:border-indigo-900/50 overflow-hidden">

                        {/* Question header */}
                        <div className="bg-gradient-to-r from-gray-50 to-white dark:from-slate-800 dark:to-slate-800/50 border-b border-gray-200 dark:border-indigo-900/50 p-6">
                            {loadingQ ? (
                                <div className="flex items-center gap-3 text-text-muted-light py-8 justify-center">
                                    <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
                                    <span className="font-serif text-primary dark:text-indigo-300">Loading question…</span>
                                </div>
                            ) : question ? (
                                <div className="flex items-start gap-4">
                                    <span className="bg-primary text-white font-mono text-xs font-bold px-2.5 py-1.5 rounded-md mt-1 shadow-sm shrink-0">
                                        Q{currentIdx + 1}
                                    </span>
                                    <div className="prose dark:prose-invert max-w-none text-gray-800 dark:text-gray-200">
                                        <div className="text-base leading-relaxed font-medium font-serif">
                                            <QuestionContent content={question.questionContent.raw_text} />
                                        </div>
                                    </div>
                                </div>
                            ) : null}
                        </div>

                        {/* Figure */}
                        {question?.questionContent.has_figure && question.questionContent.figure_blob_url && (
                            <div className="p-6 flex justify-center bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-indigo-900/50">
                                <img
                                    src={question.questionContent.figure_blob_url}
                                    alt="Question figure"
                                    className="max-h-[600px] w-full object-contain rounded-lg dark:invert-[.85] cursor-zoom-in"
                                    onClick={() => window.open(question.questionContent.figure_blob_url!, '_blank')}
                                    title="Click to open full size"
                                />
                            </div>
                        )}

                        {/* Options — MCQ */}
                        {!loadingQ && question && !isNumerical && question.questionContent.options.length > 0 && (
                            <div className="p-6 space-y-3 border-b border-gray-200 dark:border-indigo-900/50">
                                {question.questionContent.options.map((opt, i) => {
                                    const label = optionLabel(i);
                                    const isSelected = selectedOption === label;
                                    const isCorrect = revealed && label === question.answerKey?.toUpperCase();
                                    const isWrong = revealed && isSelected && !isCorrect;

                                    return (
                                        <button
                                            key={opt.nta_option_id}
                                            onClick={() => !revealed && setSelectedOption(label)}
                                            disabled={revealed}
                                            className={`w-full flex items-start gap-3 px-4 py-3 rounded-xl border text-left transition-all
                                                ${isCorrect
                                                    ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-400 dark:border-emerald-700'
                                                    : isWrong
                                                        ? 'bg-rose-50 dark:bg-rose-900/20 border-rose-400 dark:border-rose-700'
                                                        : isSelected
                                                            ? 'bg-indigo-50 dark:bg-indigo-900/30 border-primary dark:border-indigo-600'
                                                            : 'bg-gray-50 dark:bg-slate-700 border-gray-200 dark:border-slate-600 hover:border-primary/50 dark:hover:border-indigo-700'
                                                }
                                                ${revealed ? 'cursor-default' : 'cursor-pointer'}
                                            `}
                                        >
                                            <span className={`font-bold text-sm mt-0.5 shrink-0 w-5 font-mono
                                                ${isCorrect ? 'text-emerald-700 dark:text-emerald-400'
                                                    : isWrong ? 'text-rose-700 dark:text-rose-400'
                                                        : isSelected ? 'text-primary dark:text-indigo-300'
                                                            : 'text-text-muted-light dark:text-slate-400'
                                                }`}>
                                                {label}.
                                            </span>
                                            <div className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed font-serif flex-1">
                                                <LatexRenderer content={opt.text} />
                                            </div>
                                            {isCorrect && (
                                                <span className="material-symbols-outlined text-emerald-500 ml-auto shrink-0 text-base">check_circle</span>
                                            )}
                                            {isWrong && (
                                                <span className="material-symbols-outlined text-rose-500 ml-auto shrink-0 text-base">cancel</span>
                                            )}
                                        </button>
                                    );
                                })}
                            </div>
                        )}

                        {/* Numerical input — Section B */}
                        {!loadingQ && question && isNumerical && (
                            <div className="p-6 border-b border-gray-200 dark:border-indigo-900/50">
                                <label className="block text-sm font-medium text-text-muted-light dark:text-slate-300 mb-2 font-sans">
                                    Enter your numerical answer:
                                </label>
                                <input
                                    type="text"
                                    value={numericalInput}
                                    onChange={(e) => !revealed && setNumericalInput(e.target.value)}
                                    disabled={revealed}
                                    placeholder="e.g. 25"
                                    className="w-48 px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60 font-mono"
                                />
                                {revealed && (
                                    <p className={`mt-3 text-sm font-semibold font-sans ${wasCorrect ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'}`}>
                                        {wasCorrect ? '✓ Correct!' : `✗ Incorrect. Answer: ${question.answerKey}`}
                                    </p>
                                )}
                            </div>
                        )}

                        {/* Result banner — MCQ */}
                        {revealed && !isNumerical && (
                            <div className={`flex items-center gap-3 px-6 py-4 font-semibold text-sm border-b border-gray-200 dark:border-indigo-900/50
                                ${wasCorrect
                                    ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300'
                                    : 'bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-300'
                                }`}>
                                <span className="material-symbols-outlined">
                                    {wasCorrect ? 'check_circle' : 'cancel'}
                                </span>
                                {wasCorrect ? 'Correct!' : `Incorrect. Answer: ${question?.answerKey}`}
                            </div>
                        )}

                        {/* Action buttons */}
                        {question && !loadingQ && (
                            <div className="px-6 py-4 flex gap-3 flex-wrap bg-gray-50 dark:bg-slate-800/50">
                                {!revealed && (
                                    <>
                                        <button
                                            onClick={handleVerify}
                                            disabled={!canVerify}
                                            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-vedic-indigo-hover text-white font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                                        >
                                            <span className="material-symbols-outlined text-base">check</span>
                                            Check Answer
                                        </button>
                                        <button
                                            onClick={handleSkip}
                                            className="flex items-center gap-2 px-5 py-2.5 rounded-lg border border-gray-200 dark:border-slate-600 text-text-muted-light dark:text-slate-400 hover:bg-gray-100 dark:hover:bg-slate-700 text-sm transition-all"
                                        >
                                            Skip
                                        </button>
                                    </>
                                )}
                                {revealed && (
                                    <button
                                        onClick={() => setShowSolution((s) => !s)}
                                        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/40 text-primary dark:text-indigo-200 hover:bg-primary hover:text-white dark:hover:bg-indigo-800 text-sm font-semibold transition-all border border-indigo-100 dark:border-indigo-800"
                                    >
                                        <span className="material-symbols-outlined text-base">calculate</span>
                                        {showSolution ? 'Hide Solution' : 'Show Solution'}
                                    </button>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Solution */}
                    {revealed && showSolution && question && (
                        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-gray-200 dark:border-indigo-900/50 overflow-hidden">
                            <SolutionView solution={question.solution} />
                        </div>
                    )}

                    {/* Prev / Next navigation */}
                    <div className="flex items-center justify-between py-4 border-t border-gray-200 dark:border-indigo-900/50">
                        <button
                            onClick={goPrev}
                            disabled={currentIdx === 0}
                            className={`group flex items-center gap-3 transition-colors ${currentIdx === 0 ? 'opacity-30 cursor-not-allowed' : 'text-text-muted-light dark:text-indigo-300 hover:text-primary dark:hover:text-white'}`}
                        >
                            <div className="w-10 h-10 rounded-full bg-surface-light dark:bg-surface-dark shadow-sm border border-gray-200 dark:border-indigo-900 flex items-center justify-center group-hover:border-primary group-hover:bg-primary group-hover:text-white transition-all">
                                <span className="material-symbols-outlined">arrow_back</span>
                            </div>
                            <span className="font-medium font-serif">Prev Problem</span>
                        </button>

                        <button
                            onClick={goNext}
                            disabled={currentIdx === questions.length - 1}
                            className={`group flex items-center gap-3 transition-colors ${currentIdx === questions.length - 1 ? 'opacity-30 cursor-not-allowed' : 'text-text-muted-light dark:text-indigo-300 hover:text-primary dark:hover:text-white'}`}
                        >
                            <span className="font-medium font-serif">Next Problem</span>
                            <div className="w-10 h-10 rounded-full bg-surface-light dark:bg-surface-dark shadow-sm border border-gray-200 dark:border-indigo-900 flex items-center justify-center group-hover:border-primary group-hover:bg-primary group-hover:text-white transition-all">
                                <span className="material-symbols-outlined">arrow_forward</span>
                            </div>
                        </button>
                    </div>
                </main>
            </div>
        </div>
    );
}
