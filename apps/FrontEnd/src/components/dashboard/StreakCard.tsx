export const StreakCard = ({ streak }: { streak: number }) => {
    return (
        <div className="hidden md:flex flex-col items-center justify-center p-6 bg-white dark:bg-vedic-indigo-darkest/50 rounded-2xl border border-vedic-indigo-lighter/20 dark:border-vedic-indigo-hover/50 shadow-soft w-48 text-center backdrop-blur-sm relative overflow-hidden group/streak">
            <div className="absolute inset-0 bg-gradient-to-b from-transparent to-vedic-yellow-lighter/10 dark:to-vedic-yellow-main/10 opacity-0 group-hover/streak:opacity-100 transition-opacity"></div>
            <span className="material-symbols-outlined text-5xl text-vedic-yellow-main mb-3 drop-shadow-md transform group-hover/streak:scale-110 transition-transform duration-300">emoji_events</span>
            <span className="text-xs font-bold uppercase tracking-wider text-text-muted-light dark:text-vedic-indigo-lighter mb-1">Current Streak</span>
            <span className="text-3xl font-extrabold text-vedic-indigo-darkest dark:text-white">{streak} <span className="text-base font-medium text-text-muted-light">Days</span></span>
        </div>
    );
};
