import { useEffect, useState } from 'react';

interface ProcessingIndicatorProps {
    subject: string;
    problemTextRef: string | null;
}

/**
 * Processing state indicator with animated spinner and elapsed timer.
 * Shown when an evaluation is PENDING or PROCESSING.
 */
export const ProcessingIndicator = ({ subject, problemTextRef }: ProcessingIndicatorProps) => {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        const timer = setInterval(() => {
            setElapsed(prev => prev + 1);
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    const timeStr = minutes > 0
        ? `${minutes}m ${seconds.toString().padStart(2, '0')}s`
        : `${seconds}s`;

    return (
        <div className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-6 sm:p-8 border border-gray-200 dark:border-indigo-900/50 shadow-sm flex flex-col items-center gap-4 text-center">
            {/* Animated spinner */}
            <div className="relative">
                <div className="w-16 h-16 border-4 border-gray-200 dark:border-gray-700 rounded-full"></div>
                <div className="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin absolute top-0 left-0"></div>
                <div className="absolute inset-0 flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary text-xl">auto_awesome</span>
                </div>
            </div>

            <div className="flex flex-col gap-1">
                <h3 className="text-slate-900 dark:text-white font-bold text-lg">
                    Evaluating Your Solution
                </h3>
                <p className="text-slate-500 dark:text-slate-400 text-sm">
                    {subject} — {problemTextRef || 'Your submission'}
                </p>
            </div>

            <p className="text-slate-600 dark:text-gray-300 text-sm max-w-md">
                Your solution is being evaluated by our AI. This typically takes 3–5 minutes.
                Feel free to navigate away and come back later.
            </p>

            <div className="flex items-center gap-2 text-slate-400 text-xs">
                <span className="material-symbols-outlined text-sm">timer</span>
                Elapsed: {timeStr}
            </div>
        </div>
    );
};
