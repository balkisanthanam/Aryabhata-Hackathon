import { useState } from 'react';
import type { ProblemEvaluation } from '../../types/evaluation';
import { LatexRenderer } from '../common/LatexRenderer';
import clsx from 'clsx';

interface EvaluationCardProps {
    evaluation: ProblemEvaluation;
    index: number;
}

const ERROR_TYPE_LABELS: Record<string, string> = {
    conceptual_misconception: 'Conceptual Misconception',
    wrong_formula: 'Wrong Formula',
    sign_error: 'Sign Error',
    unit_error: 'Unit Error',
    algebraic_error: 'Algebraic Error',
    arithmetic_error: 'Arithmetic Error',
    incomplete_solution: 'Incomplete Solution',
    misread_problem: 'Misread Problem',
};

/**
 * Per-problem evaluation card — redesigned for clarity:
 * 1. Status badge + Problem ID
 * 2. Error pinpoint callout (if incorrect/acceptable)
 * 3. Student tip (most actionable info)
 * 4. Collapsible evaluation details
 * 5. Collapsible full solution
 */
export const EvaluationCard = ({ evaluation, index: _index }: EvaluationCardProps) => {
    const { evaluation: detail } = evaluation;
    const status = detail.evaluation_status || 'Unknown';
    const isIncorrectOrAcceptable = status.includes('Incorrect') || status.includes('Acceptable');
    const isCorrect = status.includes('Correct') && !status.includes('Incorrect');

    // Collapsible state — open by default for incorrect/error, collapsed for correct
    const [detailsOpen, setDetailsOpen] = useState(!isCorrect);
    const [solutionOpen, setSolutionOpen] = useState(!isCorrect);

    // Handle error case — prominent red banner
    if (detail.error || status === 'Error') {
        return (
            <div className="bg-red-50 dark:bg-red-900/20 rounded-xl border-2 border-red-300 dark:border-red-700 overflow-hidden">
                <div className="bg-red-100 dark:bg-red-900/40 px-4 sm:px-6 py-4 flex items-center gap-3">
                    <span className="material-symbols-outlined text-red-500 text-2xl">error</span>
                    <div>
                        <h4 className="font-bold text-red-700 dark:text-red-400 text-lg">
                            Problem {evaluation.problem_id}
                        </h4>
                        <span className="text-xs font-medium text-red-500 dark:text-red-400">
                            Evaluation Error
                        </span>
                    </div>
                </div>
                <div className="px-4 sm:px-6 py-4">
                    <p className="text-red-700 dark:text-red-300 text-sm leading-relaxed">
                        {detail.error || 'An error occurred during evaluation. This problem could not be assessed.'}
                    </p>
                    <p className="text-red-500 dark:text-red-400 text-xs mt-2">
                        This may happen if the problem wasn't found in your submitted pages, or if the evaluation model encountered an issue.
                    </p>
                </div>
            </div>
        );
    }

    const getStatusStyle = (s: string) => {
        if (s.includes('Correct') && !s.includes('Incorrect'))
            return { bg: 'bg-green-50 dark:bg-green-900/20', text: 'text-green-700 dark:text-green-400', border: 'border-green-200 dark:border-green-800/50', headerBg: 'bg-green-50 dark:bg-green-900/30', icon: 'check_circle', iconColor: 'text-green-600' };
        if (s.includes('Acceptable'))
            return { bg: 'bg-amber-50 dark:bg-amber-900/20', text: 'text-amber-700 dark:text-amber-400', border: 'border-amber-200 dark:border-amber-800/50', headerBg: 'bg-amber-50 dark:bg-amber-900/30', icon: 'info', iconColor: 'text-amber-600' };
        return { bg: 'bg-red-50 dark:bg-red-900/20', text: 'text-red-700 dark:text-red-400', border: 'border-red-200 dark:border-red-800/50', headerBg: 'bg-red-50 dark:bg-red-900/30', icon: 'cancel', iconColor: 'text-red-600' };
    };

    const style = getStatusStyle(status);

    return (
        <div className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl border border-gray-200 dark:border-indigo-900/50 shadow-sm overflow-hidden">
            {/* Header — Status + Problem ID */}
            <div className={clsx('p-4 sm:p-6 border-b border-gray-100 dark:border-gray-800', style.headerBg)}>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <h4 className="text-slate-900 dark:text-white font-bold text-base sm:text-lg flex items-center gap-2">
                        <span className={clsx('material-symbols-outlined text-2xl', style.iconColor)}>{style.icon}</span>
                        Problem {evaluation.problem_id}
                    </h4>
                    <span className={clsx('px-3 py-1 rounded-full text-xs font-bold border self-start sm:self-auto', style.bg, style.text, style.border)}>
                        {status}
                    </span>
                </div>
            </div>

            <div className="p-4 sm:p-6 flex flex-col gap-4">
                {/* Error Pinpoint — THE most important info for incorrect answers */}
                {detail.error_pinpoint && isIncorrectOrAcceptable && (
                    <div className={clsx(
                        'rounded-xl p-4 border-l-4',
                        status.includes('Incorrect')
                            ? 'bg-red-50 dark:bg-red-900/15 border-l-red-500'
                            : 'bg-amber-50 dark:bg-amber-900/15 border-l-amber-500'
                    )}>
                        <div className="flex items-start gap-3">
                            <span className={clsx(
                                'material-symbols-outlined mt-0.5 shrink-0',
                                status.includes('Incorrect') ? 'text-red-500' : 'text-amber-500'
                            )}>
                                pinpoint
                            </span>
                            <div className="flex-1">
                                <h5 className="font-bold text-slate-900 dark:text-white text-sm mb-2 flex items-center gap-2">
                                    Where You Went Wrong
                                    {detail.error_pinpoint.severity && (
                                        <span className={clsx(
                                            'px-2 py-0.5 rounded-full text-[10px] font-bold uppercase',
                                            detail.error_pinpoint.severity === 'fundamental'
                                                ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                                                : 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
                                        )}>
                                            {detail.error_pinpoint.severity === 'fundamental' ? 'Key Concept' : 'Minor Slip'}
                                        </span>
                                    )}
                                </h5>

                                <div className="text-sm text-slate-700 dark:text-gray-300 space-y-2">
                                    <p>
                                        <span className="font-semibold text-slate-900 dark:text-white">
                                            {detail.error_pinpoint.divergence_step}:
                                        </span>
                                    </p>

                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                                        <div className="bg-red-100/50 dark:bg-red-900/20 rounded-lg p-3 border border-red-200/50 dark:border-red-800/30">
                                            <span className="text-[10px] font-bold uppercase text-red-500 dark:text-red-400 tracking-wider">
                                                You wrote
                                            </span>
                                            <div className="text-sm text-red-800 dark:text-red-200 mt-1">
                                                <LatexRenderer content={detail.error_pinpoint.student_wrote} />
                                            </div>
                                        </div>
                                        <div className="bg-green-100/50 dark:bg-green-900/20 rounded-lg p-3 border border-green-200/50 dark:border-green-800/30">
                                            <span className="text-[10px] font-bold uppercase text-green-500 dark:text-green-400 tracking-wider">
                                                Expected
                                            </span>
                                            <div className="text-sm text-green-800 dark:text-green-200 mt-1">
                                                <LatexRenderer content={detail.error_pinpoint.expected} />
                                            </div>
                                        </div>
                                    </div>

                                    {detail.error_pinpoint.error_type && (
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                            <span className="font-medium">Error type:</span>{' '}
                                            {ERROR_TYPE_LABELS[detail.error_pinpoint.error_type] || detail.error_pinpoint.error_type}
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Student Tip — prominent callout, shown right after pinpoint */}
                {detail.feedback_for_student?.tip && (
                    <div className="bg-indigo-50 dark:bg-indigo-900/20 p-4 rounded-xl border border-indigo-200 dark:border-indigo-800/50">
                        <div className="flex items-start gap-3">
                            <span className="material-symbols-outlined text-primary mt-0.5 shrink-0">lightbulb</span>
                            <div>
                                <h5 className="font-bold text-indigo-900 dark:text-indigo-300 text-sm mb-1">
                                    {isCorrect ? 'Great Job!' : 'Tip for You'}
                                </h5>
                                <div className="text-sm text-indigo-800 dark:text-indigo-200 leading-relaxed">
                                    <LatexRenderer content={detail.feedback_for_student.tip} />
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Evaluation Details — Collapsible */}
                {detail.evaluation_details && (
                    <div>
                        <button
                            onClick={() => setDetailsOpen(!detailsOpen)}
                            className="w-full flex items-center justify-between py-2 text-sm font-bold text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors"
                        >
                            <span className="flex items-center gap-2">
                                <span className="material-symbols-outlined text-lg text-primary">assessment</span>
                                Detailed Analysis
                            </span>
                            <span className={clsx(
                                'material-symbols-outlined text-lg transition-transform',
                                detailsOpen ? 'rotate-180' : ''
                            )}>
                                expand_more
                            </span>
                        </button>
                        {detailsOpen && (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-1 animate-in fade-in slide-in-from-top-2 duration-200">
                                <div className="bg-white dark:bg-surface-dark p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="material-symbols-outlined text-green-500 text-lg">psychology</span>
                                        <h5 className="font-bold text-slate-900 dark:text-white text-sm">Concepts</h5>
                                    </div>
                                    <div className="text-sm text-slate-600 dark:text-gray-300 leading-relaxed">
                                        <LatexRenderer content={detail.evaluation_details.conceptual_understanding} />
                                    </div>
                                </div>
                                {detail.evaluation_details.calculation_errors && (
                                    <div className="bg-white dark:bg-surface-dark p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="material-symbols-outlined text-amber-500 text-lg">calculate</span>
                                            <h5 className="font-bold text-slate-900 dark:text-white text-sm">Calculations</h5>
                                        </div>
                                        <div className="text-sm text-slate-600 dark:text-gray-300 leading-relaxed">
                                            <LatexRenderer content={detail.evaluation_details.calculation_errors} />
                                        </div>
                                    </div>
                                )}
                                {detail.evaluation_details.presentation_and_steps && (
                                    <div className="bg-white dark:bg-surface-dark p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="material-symbols-outlined text-blue-500 text-lg">edit_note</span>
                                            <h5 className="font-bold text-slate-900 dark:text-white text-sm">Presentation</h5>
                                        </div>
                                        <div className="text-sm text-slate-600 dark:text-gray-300 leading-relaxed">
                                            <LatexRenderer content={detail.evaluation_details.presentation_and_steps} />
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Full Solution Steps — Collapsible */}
                {detail.full_solution && detail.full_solution.steps.length > 0 && (
                    <div>
                        <button
                            onClick={() => setSolutionOpen(!solutionOpen)}
                            className="w-full flex items-center justify-between py-2 text-sm font-bold text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors"
                        >
                            <span className="flex items-center gap-2">
                                <span className="material-symbols-outlined text-lg text-green-600 dark:text-green-400">check_circle</span>
                                Correct Solution
                                <span className="text-xs font-normal text-slate-400">
                                    ({detail.full_solution.steps.length} step{detail.full_solution.steps.length !== 1 ? 's' : ''})
                                </span>
                            </span>
                            <span className={clsx(
                                'material-symbols-outlined text-lg transition-transform',
                                solutionOpen ? 'rotate-180' : ''
                            )}>
                                expand_more
                            </span>
                        </button>
                        {solutionOpen && (
                            <div className="flex flex-col gap-2 mt-1 animate-in fade-in slide-in-from-top-2 duration-200">
                                {detail.full_solution.steps.map((step) => (
                                    <div
                                        key={step.step_number}
                                        className="bg-emerald-50/50 dark:bg-emerald-900/10 p-4 rounded-xl border border-emerald-100 dark:border-emerald-800/30 border-l-4 border-l-primary"
                                    >
                                        <div className="flex justify-between items-start mb-1.5">
                                            <h6 className="text-slate-900 dark:text-white font-medium text-sm leading-relaxed">
                                                <span className="mr-1 font-bold">Step {step.step_number}:</span>
                                                <LatexRenderer content={step.description} />
                                            </h6>
                                        </div>
                                        <div className="bg-slate-50 dark:bg-slate-800 p-3 rounded-lg border border-gray-200 dark:border-gray-700 font-mono text-sm text-slate-700 dark:text-gray-300 shadow-inner overflow-x-auto mt-1">
                                            <LatexRenderer content={step.calculation} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};
