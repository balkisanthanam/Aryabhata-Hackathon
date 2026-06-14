import { motion, AnimatePresence } from 'framer-motion';
import { Chapter, standingConfig, Standing } from '../../data/perfCompassData';
import { StandingBadge } from './StandingBadge';

interface SubTopicPanelProps {
    chapter: Chapter | null;
    onClose: () => void;
}

export const SubTopicPanel = ({ chapter, onClose }: SubTopicPanelProps) => {
    if (!chapter) return null;

    // Sort sub-topics by weight descending
    const sortedTopics = [...chapter.subTopics].sort((a, b) => b.jeeWeightPct - a.jeeWeightPct);
    const maxWeight = Math.max(...sortedTopics.map(t => t.jeeWeightPct));

    return (
        <AnimatePresence>
            {chapter && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                    />

                    {/* Panel */}
                    <motion.div
                        className="fixed right-0 top-0 h-full w-full sm:w-[480px] lg:w-[540px] bg-surface-light dark:bg-surface-dark shadow-2xl z-50 flex flex-col border-l border-gray-200 dark:border-indigo-900/50"
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
                    >
                        {/* Header */}
                        <div className="flex items-start justify-between p-5 border-b border-gray-200 dark:border-gray-700/50">
                            <div className="flex-1 pr-4">
                                <h3 className="text-lg font-bold text-gray-900 dark:text-white leading-tight">
                                    {chapter.name}
                                </h3>
                                <div className="flex items-center gap-3 mt-2">
                                    <span className="text-sm text-text-muted-light dark:text-gray-400 font-medium">
                                        JEE Weight: <span className="text-primary font-bold">{chapter.jeeWeightPct}%</span>
                                    </span>
                                    <StandingBadge standing={chapter.studentStanding} size="sm" />
                                </div>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex-shrink-0"
                            >
                                <span className="material-symbols-outlined text-xl text-gray-500">close</span>
                            </button>
                        </div>

                        {/* Sub-topics list */}
                        <div className="flex-1 overflow-y-auto p-5 space-y-3">
                            <p className="text-xs text-text-muted-light dark:text-gray-500 uppercase tracking-wide font-semibold mb-3">
                                {sortedTopics.length} Sub-topics
                            </p>
                            {sortedTopics.map((topic, idx) => {
                                const config = standingConfig[topic.studentStanding as Standing];
                                const barWidth = maxWeight > 0 ? (topic.jeeWeightPct / maxWeight) * 100 : 0;

                                return (
                                    <div
                                        key={idx}
                                        className="rounded-xl border border-gray-200 dark:border-gray-700/50 p-3.5 transition-all hover:shadow-soft"
                                        style={{ borderLeftWidth: '4px', borderLeftColor: config.color }}
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <span className="text-sm font-medium text-gray-800 dark:text-gray-200 flex-1 leading-snug">
                                                {topic.name}
                                            </span>
                                            <StandingBadge standing={topic.studentStanding} size="sm" />
                                        </div>
                                        <div className="mt-2.5 flex items-center gap-2">
                                            <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full rounded-full transition-all duration-500"
                                                    style={{
                                                        width: `${barWidth}%`,
                                                        backgroundColor: `${config.color}90`,
                                                    }}
                                                />
                                            </div>
                                            <span className="text-xs font-semibold text-text-muted-light dark:text-gray-400 w-10 text-right tabular-nums">
                                                {topic.jeeWeightPct}%
                                            </span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        {/* Footer */}
                        <div className="p-4 border-t border-gray-200 dark:border-gray-700/50">
                            <button
                                onClick={onClose}
                                className="w-full py-2.5 px-4 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary text-sm font-medium transition-colors"
                            >
                                Close Panel
                            </button>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
};
