
export const PracticeStats = () => {
    return (
        <div className="hidden md:flex gap-4">
            <div className="bg-surface-light dark:bg-surface-dark px-5 py-3 rounded-xl border border-gray-200 dark:border-indigo-900 shadow-soft flex flex-col justify-center min-w-[140px]">
                <span className="block text-xs text-text-muted-light dark:text-indigo-300 uppercase tracking-wider font-semibold mb-1">Problems Solved</span>
                <span className="text-2xl font-bold text-primary">124</span>
            </div>
            <div className="bg-surface-light dark:bg-surface-dark px-5 py-3 rounded-xl border border-gray-200 dark:border-indigo-900 shadow-soft flex flex-col justify-center min-w-[140px]">
                <span className="block text-xs text-text-muted-light dark:text-indigo-300 uppercase tracking-wider font-semibold mb-1">Tests Taken</span>
                <span className="text-2xl font-bold text-secondary">8</span>
            </div>
        </div>
    );
};

export const ProTipCard = () => {
    return (
        <div className="bg-gradient-to-br from-secondary/20 to-amber-100 dark:from-amber-900/30 dark:to-indigo-900/20 rounded-2xl p-6 border border-amber-200 dark:border-amber-800/50 shadow-lg shadow-amber-500/5">
            <div className="flex items-start gap-3">
                <div className="p-2 bg-white dark:bg-amber-900/50 rounded-full shadow-sm">
                    <span className="material-symbols-outlined text-secondary text-xl">lightbulb</span>
                </div>
                <div>
                    <h4 className="font-bold text-gray-900 dark:text-white text-sm">Aryabhata's Pro Tip</h4>
                    <p className="text-xs text-text-main-light dark:text-indigo-100 mt-1 leading-relaxed font-medium">
                        The "Similar Problems" set is designed to reinforce the <span className="text-primary font-bold">sutra</span> (principle) you just learned. Solving them increases retention by 40%.
                    </p>
                </div>
            </div>
        </div>
    );
};

export const UploadSolutionCard = () => {
    return (
        <div className="hidden lg:block bg-surface-light dark:bg-surface-dark rounded-2xl p-6 border border-gray-200 dark:border-indigo-900/50 shadow-card relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-bl-full -mr-10 -mt-10 transition-transform group-hover:scale-110"></div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2 relative z-10 flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary">verified</span>
                Verify Your Solution
            </h3>
            <p className="text-sm text-text-muted-light dark:text-text-muted-dark mb-4 relative z-10">Upload any problem statement and your handwritten solution. We will grade it and provide feedback.</p>
            <label className="block w-full cursor-pointer relative z-10 group/upload">
                <div className="w-full border-2 border-dashed border-primary/30 group-hover/upload:border-primary bg-primary/5 group-hover/upload:bg-primary/10 rounded-xl p-6 flex flex-col items-center justify-center transition-all duration-300">
                    <div className="relative w-12 h-12 mb-2 flex items-center justify-center group-hover/upload:scale-110 transition-transform">
                        <span className="material-symbols-outlined absolute text-4xl text-primary/40 transform -rotate-12 translate-x-1">description</span>
                        <span className="material-symbols-outlined absolute text-4xl text-primary transform rotate-6 bg-white dark:bg-transparent rounded z-10">description</span>
                    </div>
                    <span className="text-sm font-semibold text-primary">Click to upload</span>
                    <span className="text-xs text-text-muted-light dark:text-indigo-300 mt-1">Problem + Solution</span>
                </div>
                <input className="hidden" multiple type="file" />
            </label>
            <div className="mt-4 flex items-center justify-between text-xs text-text-muted-light dark:text-indigo-300 relative z-10 font-medium">
                <span className="flex items-center gap-1"><span className="material-symbols-outlined text-sm text-secondary">check_circle</span> Fast Review</span>
                <span className="flex items-center gap-1"><span className="material-symbols-outlined text-sm text-secondary">check_circle</span> Expert Comments</span>
            </div>
        </div>
    );
};
