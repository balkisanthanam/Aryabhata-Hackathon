import type { EvaluationSummaryStats } from '../../types/evaluation';
import clsx from 'clsx';

interface EvaluationSummaryCardProps {
    summary: EvaluationSummaryStats;
    activeFilter: string | null;
    onFilterByStatus: (status: string | null) => void;
}

/**
 * Summary card showing correct/acceptable/incorrect/error counts.
 * Tiles are clickable — clicking filters the problem navigator to that category.
 */
export const EvaluationSummaryCard = ({ summary, activeFilter, onFilterByStatus }: EvaluationSummaryCardProps) => {
    const items = [
        { label: 'Correct', filterKey: 'Correct', count: summary.correct, color: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/20', activeBorder: 'ring-green-500', icon: 'check_circle' },
        { label: 'Acceptable', filterKey: 'Acceptable', count: summary.acceptable, color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', activeBorder: 'ring-amber-500', icon: 'info' },
        { label: 'Incorrect', filterKey: 'Incorrect', count: summary.incorrect, color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20', activeBorder: 'ring-red-500', icon: 'cancel' },
        { label: 'Errors', filterKey: 'Error', count: summary.errors, color: 'text-slate-500 dark:text-slate-400', bg: 'bg-slate-50 dark:bg-slate-800/50', activeBorder: 'ring-slate-500', icon: 'warning' },
    ];

    return (
        <div className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-4 sm:p-6 border border-gray-200 dark:border-indigo-900/50 shadow-sm">
            <h3 className="text-slate-900 dark:text-white font-bold text-base sm:text-lg mb-3 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">summarize</span>
                Evaluation Summary
                <span className="text-sm font-normal text-slate-400 ml-1">
                    ({summary.total_problems} problem{summary.total_problems !== 1 ? 's' : ''})
                </span>
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
                {items.map(item => {
                    const isActive = activeFilter === item.filterKey;
                    const isClickable = item.count > 0;
                    return (
                        <button
                            key={item.label}
                            onClick={() => {
                                if (!isClickable) return;
                                onFilterByStatus(isActive ? null : item.filterKey);
                            }}
                            disabled={!isClickable}
                            className={clsx(
                                'rounded-lg p-3 flex flex-col items-center gap-1 border transition-all',
                                item.bg,
                                isClickable ? 'cursor-pointer hover:scale-105 hover:shadow-md' : 'cursor-default',
                                item.count === 0 ? 'opacity-50' : '',
                                isActive ? `ring-2 ${item.activeBorder} shadow-md scale-105` : ''
                            )}
                        >
                            <span className={clsx('material-symbols-outlined text-xl', item.color)}>
                                {item.icon}
                            </span>
                            <span className={clsx('text-2xl font-bold', item.color)}>
                                {item.count}
                            </span>
                            <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                                {item.label}
                            </span>
                        </button>
                    );
                })}
            </div>
            {activeFilter && (
                <div className="mt-3 flex items-center justify-center">
                    <button
                        onClick={() => onFilterByStatus(null)}
                        className="text-xs text-primary hover:text-indigo-600 font-medium flex items-center gap-1 transition-colors"
                    >
                        <span className="material-symbols-outlined text-sm">filter_alt_off</span>
                        Show all problems
                    </button>
                </div>
            )}
        </div>
    );
};
