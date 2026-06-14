export const PathTo99Teaser = () => {
    return (
        <section className="relative overflow-hidden rounded-2xl border border-gray-200 dark:border-indigo-900/50 bg-gradient-to-br from-surface-light via-white to-amber-50/30 dark:from-surface-dark dark:via-gray-900 dark:to-indigo-950/30 shadow-card p-6 lg:p-8">
            {/* Decorative gradient border */}
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-primary/10 via-secondary/10 to-primary/10 pointer-events-none" />

            <div className="relative flex flex-col sm:flex-row items-start sm:items-center gap-4">
                <div className="p-3 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-xl border border-amber-200 dark:border-amber-800 flex-shrink-0">
                    <span className="material-symbols-outlined text-3xl">rocket_launch</span>
                </div>

                <div className="flex-1">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        Path to 99 Percentile in JEE
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                            Coming Soon
                        </span>
                    </h3>
                    <p className="text-text-muted-light dark:text-gray-400 mt-1.5 text-sm leading-relaxed max-w-2xl">
                        Personalized chapter recommendations based on your standing and JEE weightage patterns.
                        We'll analyze which chapters give you the highest ROI to reach your target percentile.
                    </p>
                </div>

                <div className="flex-shrink-0 opacity-30">
                    <span className="material-symbols-outlined text-5xl text-primary">target</span>
                </div>
            </div>
        </section>
    );
};
