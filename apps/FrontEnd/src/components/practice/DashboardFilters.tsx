import { useState } from 'react';
import { cn } from '../../lib/utils';

export const DashboardFilters = () => {
    // In a real app, these would invoke callbacks passed as props
    const [selectedClass, setSelectedClass] = useState('11th');
    const [selectedSubject, setSelectedSubject] = useState('Physics');

    const classes = ['8th', '9th', '10th', '11th', '12th'];
    const subjects = [
        { name: 'Physics', icon: 'science' },
        { name: 'Chemistry', icon: 'biotech' },
        { name: 'Maths', icon: 'calculate' },
        { name: 'Biology', icon: 'coronavirus' }
    ];

    return (
        <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-4 lg:p-6 border border-gray-200 dark:border-indigo-900/50">
            {/* Mobile View - Simplified */}
            <div className="flex lg:hidden gap-3 w-full">
                <button className="flex-1 flex items-center justify-between px-3 py-2.5 rounded-lg bg-primary text-white border border-primary shadow-lg shadow-primary/30 text-sm font-medium">
                    <span>Class: {selectedClass}</span>
                    <span className="material-symbols-outlined text-lg">expand_more</span>
                </button>
                <button className="flex-1 flex items-center justify-between px-3 py-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-surface-dark text-text-main-light dark:text-text-main-dark hover:border-primary dark:hover:border-primary transition-all text-sm font-medium">
                    <span>Subject: {selectedSubject}</span>
                    <span className="material-symbols-outlined text-lg">expand_more</span>
                </button>
            </div>

            {/* Desktop View */}
            <div className="hidden lg:flex flex-col gap-6">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    <span className="text-sm font-bold text-text-muted-light dark:text-indigo-300 w-20 uppercase tracking-wide">Class</span>
                    <div className="flex flex-wrap gap-2">
                        {classes.map((cls) => (
                            <button
                                key={cls}
                                onClick={() => setSelectedClass(cls)}
                                className={cn(
                                    "px-4 py-2 rounded-lg border text-sm font-medium transition-all",
                                    selectedClass === cls
                                        ? "bg-primary text-white border-primary shadow-lg shadow-primary/30"
                                        : "border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary hover:text-primary dark:text-text-main-dark"
                                )}
                            >
                                {cls}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    <span className="text-sm font-bold text-text-muted-light dark:text-indigo-300 w-20 uppercase tracking-wide">Subject</span>
                    <div className="flex flex-wrap gap-2">
                        {subjects.map((subj) => (
                            <button
                                key={subj.name}
                                onClick={() => setSelectedSubject(subj.name)}
                                className={cn(
                                    "px-5 py-2 rounded-lg border text-sm font-medium flex items-center gap-2 transition-all",
                                    selectedSubject === subj.name
                                        ? "bg-primary text-white border-primary shadow-lg shadow-primary/30"
                                        : "border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary hover:text-primary dark:text-text-main-dark"
                                )}
                            >
                                <span className="material-symbols-outlined text-sm">{subj.icon}</span> {subj.name}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
};
