import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Navbar } from '../components/layout/Navbar';
import { UnderConstruction } from '../components/common/UnderConstruction';
import { fetchDashboardData, DashboardData } from '../lib/api';
import { useUserStore } from '../store/useUserStore';

export const PracticeDashboard = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const navigate = useNavigate();
    const userClass = useUserStore(state => state.userClass);
    const userBoard = useUserStore(state => state.board);

    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);

    // Filter States
    // Default to empty to allow backend to pick random, but prevent render until loaded
    // Improved: Check localStorage first if no URL param
    const [selectedClass, setSelectedClass] = useState<string>(searchParams.get('class') || userClass || '11');
    const [selectedSubject, setSelectedSubject] = useState<string>(() => {
        return searchParams.get('subject') || localStorage.getItem('practice_selected_subject') || '';
    });
    const [showAscentPopup, setShowAscentPopup] = useState(false);

    useEffect(() => {
        let ignore = false;

        const loadDashboard = async () => {
            setLoading(true);
            try {
                // Determine board from user store or default
                const boardToUse = userBoard || 'CBSE';

                // Pass selectedSubject (which might be from localStorage) to backend
                const dashboardData = await fetchDashboardData(selectedClass, selectedSubject, boardToUse);

                if (ignore) return;

                setData(dashboardData);

                // Update local state ONLY if we don't have a selection yet (Initial Load)
                // This prevents overriding user's explicit choice if backend returns something else
                if (dashboardData.activeSubject && !selectedSubject) {
                    setSelectedSubject(dashboardData.activeSubject);
                    localStorage.setItem('practice_selected_subject', dashboardData.activeSubject);
                }
            } catch (error) {
                if (!ignore) {
                    console.error('Failed to load dashboard:', error);
                }
            } finally {
                if (!ignore) {
                    setLoading(false);
                }
            }
        };

        loadDashboard();

        return () => {
            ignore = true;
        };
    }, [selectedClass, selectedSubject, userBoard]);

    // ... handlers ...

    const handleClassChange = (cls: string) => {
        if (cls === selectedClass) return;
        setLoading(true);
        setSelectedSubject(''); // Reset subject when class changes to force re-selection/random
        localStorage.removeItem('practice_selected_subject'); // Clear persistence for new class
        setSelectedClass(cls);
        setSearchParams({ class: cls, subject: '' });
    };

    const handleSubjectChange = (sub: string) => {
        if (sub === selectedSubject) return;
        setLoading(true);
        setSelectedSubject(sub);
        localStorage.setItem('practice_selected_subject', sub); // Persist selection
        setSearchParams({ class: selectedClass, subject: sub });
    };

    return (
        <div className="bg-background-light dark:bg-background-dark text-text-main-light dark:text-text-main-dark min-h-screen font-sans flex flex-col items-center">
            <Navbar />

            <main className="w-full max-w-6xl space-y-6 py-4 lg:py-8 px-4 sm:px-6 lg:px-8">
                {/* Header Section */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <Link to="/" className="flex items-center text-sm text-text-muted-light dark:text-text-muted-dark hover:text-primary mb-2 transition-colors font-medium">
                            <span className="material-symbols-outlined text-sm mr-1">arrow_back</span> Back to Dashboard
                        </Link>
                        <h1 className="text-2xl lg:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
                            <span className="p-2 lg:p-2.5 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-xl shadow-sm border border-amber-200 dark:border-amber-800">
                                <span className="material-symbols-outlined text-2xl lg:text-3xl">edit_note</span>
                            </span>
                            Master the Core
                        </h1>
                        <p className="text-text-muted-light dark:text-text-muted-dark mt-2 ml-14 lg:ml-16 max-w-xl text-lg academic-serif">Foundation: NCERT & Beyond</p>
                    </div>

                    {/* Stats Cards */}
                    <div className="hidden md:flex gap-4">
                        <div className="bg-surface-light dark:bg-surface-dark px-5 py-3 rounded-xl border border-gray-200 dark:border-indigo-900 shadow-soft flex flex-col justify-center min-w-[140px]">
                            <span className="block text-xs text-text-muted-light dark:text-indigo-300 uppercase tracking-wider font-semibold mb-1">Problems Solved</span>
                            <span className="text-2xl font-bold text-primary">--</span>
                        </div>
                        <div className="bg-surface-light dark:bg-surface-dark px-5 py-3 rounded-xl border border-gray-200 dark:border-indigo-900 shadow-soft flex flex-col justify-center min-w-[140px]">
                            <span className="block text-xs text-text-muted-light dark:text-indigo-300 uppercase tracking-wider font-semibold mb-1">Tests Taken</span>
                            <span className="text-2xl font-bold text-secondary">--</span>
                        </div>
                    </div>
                </div>

                {/* Loading State - Prevent Juggling */}
                {loading ? (
                    <div className="flex flex-col items-center justify-center py-20">
                        <div className="w-12 h-12 border-4 border-indigo-200 border-t-primary rounded-full animate-spin"></div>
                        <p className="mt-4 text-gray-500 font-medium">Loading your dashboard...</p>
                    </div>
                ) : !data ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center">
                        <span className="material-symbols-outlined text-4xl text-red-400 mb-2">error_outline</span>
                        <p className="text-gray-600">Unable to load dashboard data.</p>
                        <button
                            onClick={() => window.location.reload()}
                            className="mt-4 px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90"
                        >
                            Reload Page
                        </button>
                    </div>
                ) : (
                    <>
                        {/* Filters Section */}
                        <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-4 lg:p-6 border border-gray-200 dark:border-indigo-900/50">
                            <div className="flex flex-col gap-6">
                                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                                    <span className="text-sm font-bold text-text-muted-light dark:text-indigo-300 w-20 uppercase tracking-wide">Class</span>
                                    <div className="flex flex-wrap gap-2">
                                        {data?.supportedClasses.map(cls => (
                                            <button
                                                key={cls}
                                                onClick={() => handleClassChange(cls)}
                                                className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all
                                            ${selectedClass === cls
                                                        ? 'bg-primary text-white border-primary shadow-lg shadow-primary/30'
                                                        : 'border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary hover:text-primary'
                                                    }`}
                                            >
                                                {cls}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                                    <span className="text-sm font-bold text-text-muted-light dark:text-indigo-300 w-20 uppercase tracking-wide">Subject</span>
                                    <div className="flex flex-wrap gap-2">
                                        {data?.supportedSubjects.map(sub => (
                                            <button
                                                key={sub}
                                                onClick={() => handleSubjectChange(sub)}
                                                className={`px-5 py-2 rounded-lg border text-sm font-medium transition-all flex items-center gap-2
                                            ${selectedSubject === sub
                                                        ? 'bg-primary text-white border-primary shadow-lg shadow-primary/30'
                                                        : 'border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary hover:text-primary'
                                                    }`}
                                            >
                                                {/* Simple icon mapping */}
                                                <span className="material-symbols-outlined text-sm">
                                                    {sub === 'Physics' ? 'science' : sub === 'Maths' ? 'calculate' : sub === 'Chemistry' ? 'biotech' : 'menu_book'}
                                                </span>
                                                {sub}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </section>

                        {/* Chapter List */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8 items-start">
                            <div className="lg:col-span-2 space-y-4">
                                <div className="flex items-center justify-between mb-2">
                                    {/* Use DB activeSubject if available to ensure alignment */}
                                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">{(selectedSubject || data?.activeSubject) || '...'} Chapters</h2>
                                    <span className="text-sm font-medium text-text-muted-light dark:text-text-muted-dark bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">
                                        Showing {data?.chapters.length || 0}
                                    </span>
                                </div>

                                {loading ? (
                                    <div className="text-center py-10 text-gray-500">Loading chapters...</div>
                                ) : (
                                    <div className="space-y-4">
                                        {data?.chapters.map((chapter) => (
                                            <div key={chapter.id} className="sirorekha-card bg-surface-light dark:bg-surface-dark rounded-xl p-3 lg:p-5 border border-gray-200 dark:border-indigo-900/50 shadow-sm hover:shadow-card transition-all group hover:border-primary/30 dark:hover:border-primary/50">
                                                <div className="flex justify-between items-start mb-4">
                                                    <div>
                                                        <span className="text-xs font-bold text-primary uppercase tracking-wider mb-1 block">Chapter {chapter.chapterNumber.toString().padStart(2, '0')}</span>
                                                        <h3 className="text-lg font-bold text-gray-900 dark:text-white group-hover:text-primary transition-colors font-serif">{chapter.title}</h3>
                                                    </div>
                                                    <div className="p-2 rounded-full bg-gray-50 dark:bg-indigo-900/30 group-hover:text-secondary text-gray-400 dark:text-indigo-300 transition-colors">
                                                        <span className="material-symbols-outlined">bookmark_border</span>
                                                    </div>
                                                </div>

                                                <div className="grid grid-cols-2 gap-3">
                                                    <Link
                                                        to={`/practice/${chapter.id}?mode=start`}
                                                        className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/40 text-primary dark:text-indigo-200 hover:bg-primary hover:text-white transition-all text-sm font-semibold border border-indigo-100 dark:border-indigo-800"
                                                    >
                                                        <span className="material-symbols-outlined text-lg">menu_book</span> NCERT Problems
                                                    </Link>
                                                    <button
                                                        onClick={() => navigate(`/accent/${chapter.id}`)}
                                                        className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-orange-50 hover:text-orange-600 dark:hover:bg-gray-700 transition-all text-sm font-bold font-sans border border-gray-200 dark:border-gray-700"
                                                    >
                                                        <span className="material-symbols-outlined text-lg">trending_up</span> JEE Ascent
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                        {data?.chapters.length === 0 && (
                                            <div className="p-10 text-center text-gray-500">No chapters found for this selection.</div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Right Side / Mobile Bottom Actions */}
                            <div className="space-y-6">
                                {/* Solution Evaluator Card (Vertical Layout) */}
                                <Link
                                    to="/feedback"
                                    className="sirorekha-card flex flex-col gap-4 bg-surface-light dark:bg-surface-dark p-6 rounded-2xl border border-gray-200 dark:border-indigo-900/50 shadow-sm hover:shadow-card hover:border-primary/50 transition-all group cursor-pointer w-full"
                                >
                                    {/* Header */}
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 rounded-xl bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center text-primary dark:text-indigo-300 group-hover:bg-primary group-hover:text-white transition-colors">
                                            <span className="material-symbols-outlined text-2xl">assignment_turned_in</span>
                                        </div>
                                        <h3 className="text-xl font-bold font-sans text-gray-900 dark:text-white group-hover:text-primary transition-colors">
                                            Solution Evaluator
                                        </h3>
                                    </div>

                                    {/* Caption - 18px Academic Serif */}
                                    <p className="text-lg academic-serif text-text-muted-light dark:text-indigo-200 leading-relaxed font-medium">
                                        Upload any problem — NCERT, School or others — for instant teacher-like corrections.
                                    </p>

                                    {/* Footer / Action */}
                                    <div className="flex items-center justify-between w-full mt-2 pt-4 border-t border-gray-100 dark:border-white/5">
                                        <span className="text-sm font-bold text-gray-400 group-hover:text-primary transition-colors uppercase tracking-wider">
                                            Analyze Now
                                        </span>
                                        <span className="material-symbols-outlined text-gray-400 group-hover:text-primary transition-colors">
                                            arrow_forward
                                        </span>
                                    </div>
                                </Link>

                                {/* Sutra Tip Card -> Wisdom Card */}
                                <div className="bg-[#FFF9F0]/80 dark:bg-amber-900/10 rounded-xl p-5 border-l-4 border-brand-amber shadow-sm">
                                    {/* Header */}
                                    <h4 className="text-xs font-bold font-sans uppercase tracking-widest text-amber-700 dark:text-amber-500 mb-3 flex items-center gap-2">
                                        <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                                        Timeless Principle
                                    </h4>

                                    {/* Sanskrit Shloka */}
                                    <p className="text-lg md:text-xl text-vedic-indigo-darkest/90 dark:text-amber-100/90 mb-4 font-medium leading-loose font-sans opacity-95">
                                        जलबिन्दुनिपातेन क्रमशः पूर्यते घटः ।<br />
                                        स हेतुः सर्वविद्यानां धर्मस्य च धनस्य च ॥
                                    </p>

                                    {/* Meaning */}
                                    <p className="academic-serif text-base text-gray-700 dark:text-gray-300 leading-relaxed italic border-t border-amber-100 dark:border-amber-800/30 pt-3">
                                        "Just as a pot fills to the brim drop by drop, so is the journey of a scholar. True mastery is built through the steady accumulation of small, daily efforts."
                                    </p>
                                </div>
                            </div>
                        </div>

                    </>
                )}

            </main>

            {/* JEE Ascent Modal */}
            {showAscentPopup && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full mx-4 overflow-hidden relative animate-in zoom-in-95 duration-200 border border-gray-200 dark:border-gray-800">
                        <UnderConstruction
                            title="JEE Ascent"
                            variant="embedded"
                            onBack={() => setShowAscentPopup(false)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};
