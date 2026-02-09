export const KeyConceptCard = () => {
    return (
        <div className="rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800/50 overflow-hidden mb-6">
            <div className="px-4 py-3 bg-amber-100/50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800/50 flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary">lightbulb</span>
                <h3 className="text-base font-bold text-amber-900 dark:text-amber-100 font-serif">Key Concept: Area Under the Curve</h3>
            </div>
            <div className="p-4">
                <ul className="space-y-3 text-sm text-amber-900/80 dark:text-amber-100/80">
                    <li className="flex items-start">
                        <span className="mr-2 mt-1.5 w-1.5 h-1.5 bg-secondary rounded-full flex-shrink-0"></span>
                        <span>
                            <strong className="text-amber-900 dark:text-white">Expansion (V↑):</strong> Work is positive (+).<br />
                            Gas does work on surroundings.
                        </span>
                    </li>
                    <li className="flex items-start">
                        <span className="mr-2 mt-1.5 w-1.5 h-1.5 bg-secondary rounded-full flex-shrink-0"></span>
                        <span>
                            <strong className="text-amber-900 dark:text-white">Compression (V↓):</strong> Work is negative (-).<br />
                            Work is done ON the gas.
                        </span>
                    </li>
                </ul>
            </div>
        </div>
    );
};
