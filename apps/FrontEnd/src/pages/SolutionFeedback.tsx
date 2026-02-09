import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/layout/Navbar';
import { LatexRenderer } from '../components/common/LatexRenderer';
import { SAMPLE_FEEDBACK_DATA } from '../lib/api-mocks';
import clsx from 'clsx';

export const SolutionFeedback = () => {
    const [ncertProblemId, setNcertProblemId] = useState('');
    const [showResults, setShowResults] = useState(false);

    const { evaluation_status, evaluation_details, full_solution } = SAMPLE_FEEDBACK_DATA;

    // Helper to determine badge color based on status
    const getStatusColor = (status: string) => {
        if (status.includes('Acceptable')) return 'amber';
        if (status.includes('Good') || status.includes('Correct')) return 'green';
        return 'red';
    };

    const statusColor = getStatusColor(evaluation_status);

    // Map of color strings to Tailwind classes
    const colorMap: Record<string, { icon: string, bg: string, text: string, border: string, iconColor: string }> = {
        amber: {
            icon: 'check_circle', // Or 'info'
            bg: 'bg-amber-50 dark:bg-amber-900/20',
            text: 'text-amber-600 dark:text-amber-400',
            border: 'border-amber-200 dark:border-amber-800/50',
            iconColor: 'text-amber-500'
        },
        green: {
            icon: 'check_circle',
            bg: 'bg-green-50 dark:bg-green-900/20',
            text: 'text-green-700 dark:text-green-400',
            border: 'border-green-200 dark:border-green-800/50',
            iconColor: 'text-green-600 dark:text-green-400'
        },
        red: {
            icon: 'cancel',
            bg: 'bg-red-50 dark:bg-red-900/20',
            text: 'text-red-600 dark:text-red-400',
            border: 'border-red-200 dark:border-red-800/50',
            iconColor: 'text-red-500'
        }
    };

    const badgeStyle = colorMap[statusColor];

    return (
        <div className="bg-gray-50 dark:bg-background-dark text-slate-900 dark:text-white min-h-screen font-sans flex flex-col items-center relative overflow-x-hidden">
            {/* Global Mesh Gradient Background */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
                <div className="absolute top-[20%] left-[10%] w-[500px] h-[500px] bg-primary/5 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-normal dark:bg-primary/10 animate-blob"></div>
                <div className="absolute top-[30%] right-[10%] w-[400px] h-[400px] bg-indigo-200/20 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-normal dark:bg-indigo-900/20 animate-blob animation-delay-2000"></div>
                <div className="absolute -bottom-[10%] left-[20%] w-[600px] h-[600px] bg-amber-100/40 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-normal dark:bg-amber-900/10 animate-blob animation-delay-4000"></div>
            </div>

            <div className="relative z-10 w-full flex flex-col items-center">
                <Navbar />

                <main className="w-full max-w-[1200px] flex-1 flex flex-col items-center py-8 px-4 md:px-8 lg:px-12 xl:px-40 mx-auto">
                    {/* Back Link */}
                    <div className="w-full mb-6">
                        <Link to="/practice" className="flex items-center gap-2 text-indigo-800 dark:text-indigo-300 hover:text-indigo-600 text-sm font-medium transition-colors group">
                            <span className="material-symbols-outlined text-lg group-hover:-translate-x-0.5 transition-transform">arrow_back</span>
                            Back to Practice Topics
                        </Link>
                    </div>

                    {!showResults ? (
                        <div className="flex flex-col w-full flex-1 gap-6">
                            {/* Main Action Section */}
                            <section className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-6 md:p-8 border border-gray-200 dark:border-indigo-900/50 shadow-sm w-full relative z-20 flex flex-col gap-8">

                                {/* Step 1 */}
                                <div className="flex flex-col gap-4">
                                    <h2 className="text-slate-900 dark:text-white font-bold text-lg flex items-center gap-2">
                                        Step 1: Which problem are you solving?
                                    </h2>
                                    <div className="bg-slate-50 dark:bg-slate-800/50 p-4 rounded-xl border border-gray-100 dark:border-gray-700 flex flex-col md:flex-row items-center gap-4">
                                        <div className="flex-1 w-full">
                                            <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 mb-1.5 uppercase tracking-wider">NCERT Exercise #</label>
                                            <div className="relative">
                                                <input
                                                    value={ncertProblemId}
                                                    onChange={(e) => setNcertProblemId(e.target.value)}
                                                    className="w-full rounded-lg border-gray-300 dark:border-gray-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm focus:border-primary focus:ring focus:ring-primary/20 text-sm h-11 px-3"
                                                    placeholder="e.g., 11.4"
                                                    type="text"
                                                />
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-3 self-center px-2">
                                            <div className="h-px w-full md:w-px md:h-8 bg-gray-300 dark:bg-gray-600"></div>
                                            <span className="text-xs font-bold text-slate-400 whitespace-nowrap">OR</span>
                                            <div className="h-px w-full md:w-px md:h-8 bg-gray-300 dark:bg-gray-600"></div>
                                        </div>
                                        <div className="flex-1 w-full">
                                            <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 mb-1.5 uppercase tracking-wider">Non-NCERT Problem</label>
                                            <button className="w-full bg-white dark:bg-slate-700 hover:bg-gray-50 dark:hover:bg-slate-600 text-slate-600 dark:text-gray-200 border border-gray-300 dark:border-gray-600 font-medium h-11 px-4 rounded-lg text-sm transition-all shadow-sm flex items-center justify-center gap-2 group">
                                                <span className="material-symbols-outlined text-xl text-slate-400 group-hover:text-primary transition-colors">add_a_photo</span>
                                                Upload Question Image
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                {/* Step 2 */}
                                <div className="flex flex-col gap-4">
                                    <h2 className="text-slate-900 dark:text-white font-bold text-lg flex items-center gap-2">
                                        Step 2: Upload your handwritten solution
                                    </h2>
                                    <div className="w-full">
                                        <div className="border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-primary hover:bg-primary/5 dark:hover:bg-primary/10 bg-slate-50/50 dark:bg-slate-800/30 rounded-xl p-8 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all group min-h-[160px] relative overflow-hidden">
                                            <div className="bg-white dark:bg-slate-700 p-3 rounded-full shadow-sm border border-gray-200 dark:border-gray-600 group-hover:scale-110 group-hover:shadow-md transition-all duration-300 z-10">
                                                <span className="material-symbols-outlined text-3xl text-primary">cloud_upload</span>
                                            </div>
                                            <div className="text-center z-10">
                                                <p className="text-slate-700 dark:text-gray-200 font-medium text-base">Drop your JPG/PDF here to get step-by-step feedback</p>
                                                <p className="text-slate-400 text-xs mt-1">Supports handwritten pages • Max 10MB</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <button
                                    onClick={() => setShowResults(true)}
                                    className="w-full bg-primary hover:bg-indigo-600 text-white font-bold text-lg py-4 px-6 rounded-xl shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all transform hover:-translate-y-0.5 flex items-center justify-center gap-3 mt-2"
                                >
                                    <span className="material-symbols-outlined text-2xl">auto_awesome</span>
                                    Correct My Solution & Provide Feedback
                                </button>

                            </section>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500 w-full">
                            {/* Problem Statement Header */}
                            <section className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl p-6 border border-gray-200 dark:border-indigo-900/50 shadow-sm relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>
                                <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-5 border border-gray-200 dark:border-gray-700 relative z-10">
                                    <div className="mb-2">
                                        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Problem Statement</span>
                                    </div>
                                    <div className="text-slate-700 dark:text-gray-300 text-base md:text-lg font-normal leading-relaxed font-body overflow-x-auto">
                                        <LatexRenderer content="Calculate heat supplied at constant pressure for Nitrogen gas. Given mass 20g, $\Delta T$ 45°C." />
                                    </div>
                                </div>
                            </section>

                            {/* Comparison Grid */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
                                {/* Left: User Attempt */}
                                <div className="flex flex-col gap-4 mb-12 lg:mb-0">
                                    <div className="flex items-center justify-between px-2">
                                        <h3 className="text-slate-900 dark:text-white text-lg font-semibold flex items-center gap-2">
                                            <span className={clsx("material-symbols-outlined", badgeStyle.iconColor)}>{badgeStyle.icon}</span>
                                            Your Attempt
                                        </h3>
                                        <span className={clsx("px-3 py-1 rounded-full text-xs font-bold border", badgeStyle.bg, badgeStyle.text, badgeStyle.border)}>
                                            {evaluation_status}
                                        </span>
                                    </div>
                                    <div className="relative bg-white dark:bg-surface-dark rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden group shadow-sm hover:shadow-md transition-shadow">
                                        <div className="relative w-full aspect-[4/5] bg-gray-100 dark:bg-gray-900 opacity-95 mix-blend-normal overflow-hidden">
                                            {/* User Uploaded Image */}
                                            <img
                                                src="/assets/images/UserUploadProblemSolutionForSample.jpg"
                                                alt="User's handwritten solution"
                                                className="w-full h-full object-cover"
                                            />

                                        </div>
                                        {/* Analysis Overlay - Moved text below image */}
                                        {evaluation_details.calculation_errors && (
                                            <div className="bg-amber-50/50 dark:bg-amber-900/20 text-slate-800 dark:text-gray-200 p-4 border-t border-amber-100 dark:border-amber-800/50 flex gap-3">
                                                <span className="material-symbols-outlined text-amber-600 dark:text-amber-500 mt-1 shrink-0">info</span>
                                                <div className="flex-1 overflow-x-auto">
                                                    <p className="text-base font-bold text-amber-700 dark:text-amber-400 mb-1 font-display">Calculation Insight</p>
                                                    <div className="text-base text-slate-700 dark:text-gray-300 leading-snug font-body">
                                                        <LatexRenderer content={evaluation_details.calculation_errors} />
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    {/* Conceptual Feedback Card */}
                                    <div className="bg-white dark:bg-surface-dark p-4 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="material-symbols-outlined text-green-500">psychology</span>
                                            <h4 className="font-bold text-slate-900 dark:text-white text-base">Conceptual Understanding</h4>
                                        </div>
                                        <div className="text-lg text-slate-600 dark:text-gray-300 leading-relaxed">
                                            <LatexRenderer content={evaluation_details.conceptual_understanding} />
                                        </div>
                                    </div>

                                    {/* Presentation Feedback Card */}
                                    <div className="bg-white dark:bg-surface-dark p-4 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="material-symbols-outlined text-blue-500">edit_note</span>
                                            <h4 className="font-bold text-slate-900 dark:text-white text-base">Presentation & Steps</h4>
                                        </div>
                                        <div className="text-lg text-slate-600 dark:text-gray-300 leading-relaxed">
                                            <LatexRenderer content={evaluation_details.presentation_and_steps} />
                                        </div>
                                    </div>
                                </div>

                                {/* Right: Correct Approach */}
                                <div className="flex flex-col gap-4">
                                    <div className="flex items-center justify-between px-2">
                                        <h3 className="text-slate-900 dark:text-white text-xl font-semibold flex items-center gap-2">
                                            <span className="material-symbols-outlined text-green-600 dark:text-green-400">check_circle</span>
                                            Correct Approach
                                        </h3>
                                        <span className="bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 px-3 py-1 rounded-full text-xs font-bold border border-green-200 dark:border-green-800/50">Step-by-Step</span>
                                    </div>
                                    <div className="flex flex-col gap-3">
                                        {full_solution.steps.map((step) => (

                                            <div key={step.step_number} className="bg-emerald-50/50 dark:bg-emerald-900/10 p-5 rounded-xl border border-emerald-100 dark:border-emerald-800/30 border-l-4 border-l-primary shadow-xl hover:shadow-2xl transition-all">
                                                <div className="flex justify-between items-start mb-2">
                                                    <h4 className="text-slate-900 dark:text-white font-medium text-lg leading-relaxed">
                                                        <span className="mr-1 font-bold">Step {step.step_number}:</span>
                                                        <LatexRenderer content={step.description} />
                                                    </h4>
                                                    <span className="text-amber-600 dark:text-amber-400 text-sm font-mono font-bold">0{step.step_number}</span>
                                                </div>
                                                <div className="bg-slate-50 dark:bg-slate-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700 font-mono text-base md:text-lg text-slate-700 dark:text-gray-300 shadow-inner overflow-x-auto mt-2">
                                                    <LatexRenderer content={step.calculation} />
                                                </div>
                                            </div>
                                        ))
                                        }
                                    </div>
                                </div>
                            </div>

                            {/* Footer Score/Actions & Pro-Tip */}
                            <section className="mt-4 bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm border border-gray-200 dark:border-gray-700 rounded-xl p-6 md:p-8 shadow-md relative overflow-hidden">
                                <div className="absolute bottom-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-primary/40 to-transparent"></div>
                                <div className="flex flex-col md:flex-row items-center justify-between gap-6 w-full relative z-10">
                                    <button className="flex items-center gap-3 rounded-xl bg-white dark:bg-slate-700 hover:bg-gray-50 dark:hover:bg-slate-600 text-slate-800 dark:text-white py-2 px-5 transition-colors border border-slate-200 dark:border-gray-600 shadow-sm group min-w-[200px] justify-center">
                                        <span className="material-symbols-outlined text-2xl text-slate-700 dark:text-slate-300 group-hover:scale-110 transition-transform">library_books</span>
                                        <div className="flex flex-col items-center leading-tight">
                                            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">Show me a</span>
                                            <span className="font-bold text-sm text-slate-900 dark:text-white">Similar Problem</span>
                                        </div>
                                    </button>
                                    <button
                                        onClick={() => setShowResults(false)}
                                        className="flex items-center gap-3 rounded-xl bg-amber-400 hover:bg-amber-500 text-slate-900 py-2 px-6 shadow-lg shadow-amber-400/20 transition-all transform hover:scale-[1.02] group min-w-[200px] justify-center"
                                    >
                                        <span className="material-symbols-outlined text-2xl group-hover:-rotate-180 transition-transform duration-500">refresh</span>
                                        <div className="flex flex-col items-center leading-tight">
                                            <span className="text-xs font-semibold">Re-attempt</span>
                                            <span className="font-bold text-sm">Problem</span>
                                        </div>
                                    </button>
                                </div>
                            </section>
                        </div>
                    )}

                </main>
            </div>
        </div>
    );
};
