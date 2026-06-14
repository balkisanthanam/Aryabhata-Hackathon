import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/layout/Navbar';
import { ClassSubjectTabs } from '../components/analytics/ClassSubjectTabs';
import { ChapterTreemap } from '../components/analytics/ChapterTreemap';
import { SubTopicPanel } from '../components/analytics/SubTopicPanel';
import { StandingLegend } from '../components/analytics/StandingLegend';
import { PathTo99Teaser } from '../components/analytics/PathTo99Teaser';
import { StandingBadge } from '../components/analytics/StandingBadge';
import { perfCompassData, Chapter } from '../data/perfCompassData';
import { useUserStore } from '../store/useUserStore';

export const PerformanceCompass = () => {
    const userClass = useUserStore(state => state.userClass);

    // Default to user's class or '11'
    const [selectedClass, setSelectedClass] = useState<string>(userClass || '11');
    const [selectedSubject, setSelectedSubject] = useState<string>('Physics');
    const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null);

    // Derived data
    const classData = useMemo(
        () => perfCompassData.find(c => c.class === selectedClass),
        [selectedClass]
    );

    const subjects = useMemo(() => classData?.subjects ?? [], [classData]);

    const activeSubject = useMemo(
        () => subjects.find(s => s.name === selectedSubject) ?? subjects[0],
        [subjects, selectedSubject]
    );

    const chapters = useMemo(
        () => activeSubject?.chapters ?? [],
        [activeSubject]
    );

    const handleClassChange = (cls: string) => {
        setSelectedClass(cls);
        setSelectedSubject('Physics'); // Reset to first subject
        setSelectedChapter(null);
    };

    const handleSubjectChange = (sub: string) => {
        setSelectedSubject(sub);
        setSelectedChapter(null);
    };

    return (
        <div className="bg-background-light dark:bg-background-dark text-text-main-light dark:text-text-main-dark min-h-screen font-sans flex flex-col items-center">
            <Navbar />

            <main className="w-full max-w-6xl space-y-6 py-4 lg:py-8 px-4 sm:px-6 lg:px-8">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <Link
                            to="/"
                            className="flex items-center text-sm text-text-muted-light dark:text-text-muted-dark hover:text-primary mb-2 transition-colors font-medium"
                        >
                            <span className="material-symbols-outlined text-sm mr-1">arrow_back</span> Back to Dashboard
                        </Link>
                        <h1 className="text-2xl lg:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
                            <span className="p-2 lg:p-2.5 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-xl shadow-sm border border-indigo-200 dark:border-indigo-800">
                                <span className="material-symbols-outlined text-2xl lg:text-3xl">explore</span>
                            </span>
                            Performance Compass
                        </h1>
                        <p className="text-text-muted-light dark:text-text-muted-dark mt-2 ml-14 lg:ml-16 max-w-xl text-lg academic-serif">
                            Know where you stand in your JEE preparation
                        </p>
                        <p className="ml-14 lg:ml-16 mt-2 text-sm text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/25 border border-amber-300 dark:border-amber-700/50 rounded-lg px-3 py-1.5 inline-flex items-center gap-2 w-fit font-medium">
                            <span className="material-symbols-outlined text-base">science</span>
                            Preview with sample data — live data coming soon
                        </p>
                    </div>

                    {/* Overall standing summary */}
                    {activeSubject && (
                        <div className="hidden md:flex gap-4">
                            <div className="bg-surface-light dark:bg-surface-dark px-5 py-3 rounded-xl border border-gray-200 dark:border-indigo-900 shadow-soft flex flex-col justify-center min-w-[140px]">
                                <span className="block text-xs text-text-muted-light dark:text-indigo-300 uppercase tracking-wider font-semibold mb-1">
                                    {activeSubject.name}
                                </span>
                                <StandingBadge standing={activeSubject.studentStanding} />
                            </div>
                            <div className="bg-surface-light dark:bg-surface-dark px-5 py-3 rounded-xl border border-gray-200 dark:border-indigo-900 shadow-soft flex flex-col justify-center min-w-[140px]">
                                <span className="block text-xs text-text-muted-light dark:text-indigo-300 uppercase tracking-wider font-semibold mb-1">Chapters</span>
                                <span className="text-2xl font-bold text-primary">{chapters.length}</span>
                            </div>
                        </div>
                    )}
                </div>

                {/* Standing Legend */}
                <StandingLegend />

                {/* Class & Subject Tabs */}
                <ClassSubjectTabs
                    classes={perfCompassData.map(c => c.class)}
                    subjects={subjects}
                    selectedClass={selectedClass}
                    selectedSubject={activeSubject?.name ?? ''}
                    onClassChange={handleClassChange}
                    onSubjectChange={handleSubjectChange}
                />

                {/* Chapter Treemap */}
                {chapters.length > 0 && (
                    <ChapterTreemap
                        chapters={chapters}
                        onChapterClick={setSelectedChapter}
                    />
                )}

                {/* Path to 99 Percentile Teaser */}
                <PathTo99Teaser />
            </main>

            {/* Sub-topic slide panel */}
            <SubTopicPanel
                chapter={selectedChapter}
                onClose={() => setSelectedChapter(null)}
            />
        </div>
    );
};
