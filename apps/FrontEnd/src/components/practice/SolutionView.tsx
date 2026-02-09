import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { LatexRenderer } from '../common/LatexRenderer';

interface SolutionViewProps {
    solution: any;
}

// Utility to clean malformed LaTeX from DB
// Specific fix for \frac becoming Form Feed (\u000c) + "rac"
const cleanLatex = (text: string | null | undefined): string => {
    if (!text) return "";
    return text
        // Fix \frac (Form Feed \f -> \u000c)
        .replace(/\u000crac/g, '\\frac')
        .replace(/\u000call/g, '\\forall')

        // Fix \t... (Tab \t -> \u0009)
        .replace(/\u0009imes/g, '\\times')
        .replace(/\u0009ext/g, '\\text')
        .replace(/\u0009an/g, '\\tan')
        .replace(/\u0009au/g, '\\tau')
        .replace(/\u0009heta/g, '\\theta')
        .replace(/\u0009o/g, '\\to')

        // Fix \n... (Newline \n -> \u000a)
        // Be careful with \nu to avoid replacing actual newlines followed by 'u' in text
        // Most \nu usages are in math, so look for \nu followed by non-letter or end
        .replace(/\u000au/g, '\\nu')
        .replace(/\u000aabla/g, '\\nabla')
        .replace(/\u000aeq/g, '\\neq')
        .replace(/\u000aeg/g, '\\neg')
        .replace(/\u000aot/g, '\\not')

        // Fix \r... (Carriage Return \r -> \u000d)
        .replace(/\u000dho/g, '\\rho')
        .replace(/\u000dight/g, '\\right')

        // Fix \b... (Backspace \b -> \u0008)
        .replace(/\u0008ar/g, '\\bar')
        .replace(/\u0008eta/g, '\\beta')
        .replace(/\u0008egin/g, '\\begin')
        .replace(/\u0008f/g, '\\bf')

        // Fix \a... (Bell \a -> \u0007 - IF supported/mangled)
        .replace(/\u0007lpha/g, '\\alpha')
        .replace(/\u0007pprox/g, '\\approx')

        // Fix \v... (Vertical Tab \v -> \u000b)
        .replace(/\u000bec/g, '\\vec')
        .replace(/\u000bert/g, '\\vert')
        .replace(/\u000barphi/g, '\\varphi');
};

export const SolutionView = ({ solution }: SolutionViewProps) => {
    // State to track which step is currently expanded. 
    // Default to 0 (Step 1). null means all collapsed.
    const [expandedStep, setExpandedStep] = useState<number | null>(0);

    const toggleStep = (index: number) => {
        setExpandedStep(prev => (prev === index ? null : index));
    };

    // Combine steps and final answer for unified handling
    const steps = solution.steps;
    const finalAnswerIndex = steps.length;

    return (
        <div className="p-4 lg:p-8">
            <h3 className="text-xl font-serif font-bold text-slate-900 dark:text-white mb-6 flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">calculate</span>
                Full Solution
            </h3>

            <div className="space-y-4">
                {/* Render Solution Steps */}
                {steps.map((step: any, index: number) => {
                    const isExpanded = expandedStep === index;
                    return (
                        <div
                            key={index}
                            className="group bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm transition-all"
                        >
                            <button
                                onClick={() => toggleStep(index)}
                                className={`w-full flex items-start sm:items-center justify-between p-4 cursor-pointer transition-colors select-none min-h-[44px] text-left
                                    ${isExpanded ? 'bg-white dark:bg-slate-800' : 'bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-700'}
                                `}
                            >
                                <div className="flex flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold text-slate-900 dark:text-white text-base">
                                            Step {step.step_number}
                                        </span>
                                        {/* Optional Badge if Type is Calculation/Concept - kept simple based on HTML */}
                                    </div>

                                    {/* Hint Text - Visible only when collapsed */}
                                    {!isExpanded && step.nudge_hint && (
                                        <span className="text-sm italic text-slate-500 dark:text-slate-400">
                                            {cleanLatex(step.nudge_hint)}
                                        </span>
                                    )}
                                </div>

                                <div className="flex items-center gap-2 text-slate-500 group-hover:text-primary transition-colors mt-1 sm:mt-0">
                                    {!isExpanded && (
                                        <span className="text-xs font-semibold uppercase tracking-wider hidden sm:block">
                                            Reveal
                                        </span>
                                    )}
                                    <span className={`material-symbols-outlined transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}>
                                        expand_more
                                    </span>
                                </div>
                            </button>

                            <AnimatePresence>
                                {isExpanded && (
                                    <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: "auto", opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        transition={{ duration: 0.3, ease: "easeInOut" }}
                                    >
                                        <div className="p-4 pt-0 border-t border-slate-100 dark:border-slate-700/50">
                                            <div className="mt-4 pl-4 border-l-2 border-primary/20">
                                                <div className="text-lg leading-relaxed text-slate-700 dark:text-slate-300 math-font mb-3">
                                                    <LatexRenderer content={cleanLatex(step.explanation)} />
                                                </div>

                                                {/* Key Concept / Highlight box */}
                                                {step.latex_formula && (
                                                    <div className="mb-4 bg-amber-50 dark:bg-amber-900/10 border-l-4 border-accent p-3 rounded-r-lg">
                                                        <div className="text-xs text-amber-800 dark:text-amber-200 italic flex items-start gap-2">
                                                            <span className="material-symbols-outlined text-sm">lightbulb</span>
                                                            <div className="space-y-1">
                                                                <LatexRenderer content={`$${cleanLatex(step.latex_formula)}$`} />
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    );
                })}

                {/* Final Result Accordion */}
                <div className="group bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-sm transition-all">
                    <button
                        onClick={() => toggleStep(finalAnswerIndex)}
                        className={`w-full flex items-start sm:items-center justify-between p-4 cursor-pointer transition-colors select-none min-h-[56px] text-left
                            ${expandedStep === finalAnswerIndex ? 'bg-white dark:bg-slate-800' : 'bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-700'}
                        `}
                    >
                        <div className="flex flex-col gap-1">
                            <span className="font-bold text-slate-900 dark:text-white text-base">Final Result</span>
                            {expandedStep !== finalAnswerIndex && (
                                <span className="text-sm italic text-slate-500 dark:text-slate-400">
                                    Hint: What is the net work done?
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2 text-slate-500 group-hover:text-primary transition-colors mt-1 sm:mt-0">
                            {expandedStep !== finalAnswerIndex && (
                                <span className="text-xs font-semibold uppercase tracking-wider hidden sm:block">
                                    Reveal
                                </span>
                            )}
                            <span className={`material-symbols-outlined transition-transform duration-200 ${expandedStep === finalAnswerIndex ? 'rotate-180' : ''}`}>
                                expand_more
                            </span>
                        </div>
                    </button>

                    <AnimatePresence>
                        {expandedStep === finalAnswerIndex && (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.3, ease: "easeInOut" }}
                            >
                                <div className="p-6 border-t border-slate-100 dark:border-slate-700 flex justify-center">
                                    <div className="bg-white dark:bg-slate-800 rounded-xl border-2 border-primary dark:border-indigo-400 p-6 shadow-[0_0_15px_-3px_rgba(245,158,11,0.3)] w-full max-w-sm text-center transform hover:scale-105 transition-transform duration-200">
                                        <p className="font-serif text-lg text-slate-900 dark:text-white flex flex-col items-center">
                                            <span className="block text-xs uppercase tracking-widest text-slate-500 mb-2">Answer</span>
                                            <span className="text-primary dark:text-indigo-400 font-bold text-2xl ml-1">
                                                <LatexRenderer content={cleanLatex(solution.final_answer)} />
                                            </span>
                                        </p>
                                    </div>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </div>
    );
};
