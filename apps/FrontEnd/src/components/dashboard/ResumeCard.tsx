import { Link } from 'react-router-dom';

interface ResumeCardProps {
    data: {
        chapterId: number;
        questionId: number;
        chapterTitle: string;
    } | null;
}

export const ResumeCard = ({ data }: ResumeCardProps) => {
    if (!data) return null;

    return (
        <section className="flex justify-center transform hover:-translate-y-1 transition-transform duration-300">
            <Link to={`/practice/${data.chapterId}?mode=resume`} className="group w-full md:w-11/12 lg:w-4/5 bg-white dark:bg-vedic-indigo-main border border-vedic-indigo-lighter/20 dark:border-vedic-yellow-main/30 rounded-3xl p-1 shadow-lg hover:shadow-glow-indigo dark:hover:shadow-glow transition-all duration-300 relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-r from-vedic-indigo-main to-vedic-indigo-hover dark:from-vedic-indigo-deep dark:to-vedic-indigo-main opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                <div className="bg-white dark:bg-surface-dark group-hover:bg-opacity-0 rounded-[1.3rem] p-4 md:p-8 flex items-center justify-between relative z-10 h-full transition-colors duration-300">
                    <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-5 mix-blend-multiply pointer-events-none"></div>
                    <div className="flex items-center gap-4 md:gap-6 w-full">
                        <div className="h-12 w-12 md:h-16 md:w-16 bg-vedic-yellow-main text-vedic-indigo-darkest rounded-full flex items-center justify-center shadow-lg group-hover:scale-110 group-hover:bg-white group-hover:text-vedic-indigo-main transition-all duration-300 flex-shrink-0">
                            <span className="material-symbols-outlined text-2xl md:text-4xl fill-1">play_arrow</span>
                        </div>
                        <div className="text-left flex-1 min-w-0">
                            <p className="text-sm md:text-base font-bold uppercase tracking-widest text-vedic-indigo-lighter dark:text-vedic-yellow-lighter group-hover:text-vedic-yellow-lighter dark:group-hover:text-vedic-yellow-main mb-1 flex items-center gap-1">
                                Resume Learning <span className="w-1.5 h-1.5 md:w-2 md:h-2 rounded-full bg-vedic-yellow-main animate-pulse"></span>
                            </p>
                            <h3 className="text-sm md:text-lg lg:text-2xl font-bold text-vedic-indigo-darkest dark:text-white group-hover:text-white transition-colors line-clamp-1 md:line-clamp-none">
                                {data.chapterTitle}
                            </h3>
                        </div>
                    </div>
                    <div className="block pl-4">
                        <span className="material-symbols-outlined text-2xl md:text-4xl text-vedic-indigo-lighter dark:text-vedic-indigo-hover group-hover:text-white transform group-hover:translate-x-2 transition-all">arrow_forward_ios</span>
                    </div>
                </div>
            </Link>
        </section>
    );
};
