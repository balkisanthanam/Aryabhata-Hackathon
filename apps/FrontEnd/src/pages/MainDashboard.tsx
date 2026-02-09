import { useEffect, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { ResumeCard } from '../components/dashboard/ResumeCard';
import { ActionCard } from '../components/dashboard/ActionCard';
import { useUserStore } from '../store/useUserStore';
import { useStore } from '../store/useStore'; // Keep for Streak (mock for now or move to user store later)
import { fetchResumeData } from '../lib/api';

export const MainDashboard = () => {
    // REAL User Store
    const { userName, userClass, board, goal } = useUserStore();

    // Legacy Mock Store (for streak only right now)
    const { streak } = useStore();

    // Resume Data State
    const [resumeData, setResumeData] = useState<any>(null);

    useEffect(() => {
        const loadResume = async () => {
            try {
                const data = await fetchResumeData();
                setResumeData(data);
            } catch (error) {
                console.error('Failed to load resume data:', error);
            }
        };
        loadResume();
    }, []);

    return (
        <Layout>
            {/* Horizontal Profile Summary Bar (Iteration 2) */}
            <section className="glass-panel mx-4 lg:mx-0 rounded-2xl shadow-sm px-4 py-3 relative overflow-hidden group bg-white/65 dark:bg-surface-dark/50 backdrop-blur-md border border-white/30 dark:border-white/10">
                <div className="flex flex-row justify-between items-center gap-4 relative z-10 w-full">

                    {/* Left: Avatar & Info */}
                    <div className="flex items-center gap-4">
                        {/* Dynamic Avatar */}
                        <div className="flex-shrink-0">
                            <div className="w-12 h-12 md:w-14 md:h-14 rounded-full bg-vedic-indigo-main text-white flex items-center justify-center text-xl md:text-2xl font-bold shadow-md font-serif">
                                {userName ? userName.charAt(0).toUpperCase() : 'G'}
                            </div>
                        </div>

                        {/* User Metadata */}
                        <div className="flex flex-col justify-center">
                            <h2 className="text-xl md:text-2xl font-bold text-vedic-indigo-darkest dark:text-white leading-tight font-serif tracking-tight">
                                {userName || 'Guest User'}
                            </h2>
                            <div className="flex items-center gap-2 text-base font-medium text-text-muted-light dark:text-text-muted-dark mt-0.5">
                                <span>{userClass || '11'}th {board || 'CBSE'}</span>
                                <span className="w-1.5 h-1.5 rounded-full bg-gray-400"></span>
                                <span>{goal || 'JEE Advanced'}</span>
                            </div>
                        </div>
                    </div>

                    {/* Right: Streak Badge */}
                    <div className="flex-shrink-0">
                        <div className="flex items-center gap-2 px-4 py-2 bg-vedic-yellow-lighter/20 dark:bg-vedic-yellow-main/10 rounded-full border border-vedic-yellow-main/30 backdrop-blur-sm">
                            <span className="material-symbols-outlined text-xl text-vedic-yellow-warm dark:text-vedic-yellow-main fill-1">emoji_events</span>
                            <span className="text-base font-bold text-vedic-indigo-darkest dark:text-white whitespace-nowrap">
                                {streak || 0} Days
                            </span>
                        </div>
                    </div>

                </div>
            </section>

            {/* Resume Section - Only show if data exists */}
            {resumeData && <ResumeCard data={resumeData} />}

            {/* Action Grid */}
            <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6 lg:gap-8">
                <ActionCard
                    title="Master the Core"
                    description="Build a solid base with NCERT exercises and progressively conquer complex problems designed for the highest competitive levels."
                    icon="edit_note"
                    variant="secondary"
                    link="/practice"
                />
                <ActionCard
                    title="Smart Testing"
                    description="Take personalized tests—from chapter-wise drills to full papers—tailored to bridge your specific learning gaps."
                    icon="trending_up"
                    variant="indigo"
                    link="/challenge"
                />
                <ActionCard
                    title="Performance Compass"
                    description="Gain total clarity on your prep path. A data-driven diagnostic of your progress to ensure you never lose sight of your goal."
                    icon="analytics"
                    variant="orange"
                    link="/analytics"
                />
            </section>

            {/* Intro Section */}
            <section className="w-full flex justify-center pt-2 md:pt-6">
                <div className="w-full max-w-2xl group cursor-pointer relative">
                    <div className="absolute inset-0 bg-gradient-to-r from-vedic-indigo-lighter/20 to-vedic-yellow-lighter/20 rounded-2xl transform rotate-1 group-hover:rotate-2 transition-transform duration-300"></div>
                    <div className="relative sirorekha-card bg-white dark:bg-surface-dark rounded-2xl border-2 border-dashed border-vedic-indigo-lighter/30 dark:border-vedic-indigo-hover p-4 md:p-8 flex items-center gap-4 md:gap-6 shadow-sm group-hover:shadow-lg group-hover:border-vedic-indigo-main dark:group-hover:border-vedic-yellow-main transition-all">
                        <div className="flex-shrink-0">
                            <div className="bg-vedic-indigo-main/5 dark:bg-vedic-indigo-deep p-3 md:p-4 rounded-full group-hover:scale-110 transition-transform duration-300 group-hover:bg-vedic-indigo-main group-hover:text-white text-vedic-indigo-main dark:text-vedic-yellow-main">
                                <span className="material-symbols-outlined text-2xl md:text-4xl">smart_display</span>
                            </div>
                        </div>
                        <div className="flex-1">
                            <h5 className="text-base md:text-lg font-bold text-vedic-indigo-darkest dark:text-white group-hover:text-vedic-indigo-main dark:group-hover:text-vedic-yellow-main transition-colors mb-1">Introduction</h5>
                            <p className="text-xs md:text-sm text-text-muted-light dark:text-text-muted-dark font-medium">Learn how to make the best use of Aryabhata</p>
                        </div>
                        <div className="hidden sm:block">
                            <span className="material-symbols-outlined text-gray-300 group-hover:text-vedic-indigo-main dark:group-hover:text-vedic-yellow-main transition-colors">play_circle</span>
                        </div>
                    </div>
                </div>
            </section>
        </Layout>
    );
};
