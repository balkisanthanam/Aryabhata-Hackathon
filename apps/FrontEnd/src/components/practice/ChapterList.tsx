import { Link } from 'react-router-dom';
import { Chapter } from '../../lib/api-mocks';

interface ChapterListProps {
    chapters: Chapter[];
}

export const ChapterList = ({ chapters }: ChapterListProps) => {
    return (
        <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between mb-2">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">Physics Chapters</h2>
                <span className="text-sm font-medium text-text-muted-light dark:text-text-muted-dark bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">
                    Showing {chapters.length} of {chapters.length + 5}
                </span>
            </div>
            <div className="max-h-[600px] overflow-y-auto pr-2 space-y-3 lg:space-y-4 custom-scrollbar">
                {chapters.map((chapter) => (
                    <div key={chapter.id} className="bg-surface-light dark:bg-surface-dark rounded-xl p-3 lg:p-5 border border-gray-200 dark:border-indigo-900/50 shadow-sm hover:shadow-card hover:border-primary/30 dark:hover:border-primary/50 transition-all group">
                        {/* Mobile View of Item */}
                        <div className="flex lg:hidden items-center justify-between gap-3">
                            <div className="flex flex-col min-w-0">
                                <span className="text-[10px] font-bold text-primary uppercase tracking-wider mb-0.5">Chapter {String(chapter.chapterNumber).padStart(2, '0')}</span>
                                <h3 className="text-sm font-bold text-gray-900 dark:text-white truncate">{chapter.title}</h3>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                <Link to={`/practice/${chapter.id}`} className="w-9 h-9 flex items-center justify-center rounded-lg bg-indigo-50 dark:bg-indigo-900/40 text-primary dark:text-indigo-200 border border-indigo-100 dark:border-indigo-800 hover:bg-primary hover:text-white transition-colors">
                                    <span className="material-symbols-outlined text-lg">menu_book</span>
                                </Link>
                                <button className="w-9 h-9 flex items-center justify-center rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 hover:bg-red-500 hover:text-white transition-colors">
                                    <span className="material-symbols-outlined text-lg">timer</span>
                                </button>
                            </div>
                        </div>

                        {/* Desktop View of Item */}
                        <div className="hidden lg:block">
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <span className="text-xs font-bold text-primary uppercase tracking-wider mb-1 block">Chapter {String(chapter.chapterNumber).padStart(2, '0')}</span>
                                    <h3 className="text-lg font-bold text-gray-900 dark:text-white group-hover:text-primary transition-colors">{chapter.title}</h3>
                                </div>
                                <div className="bg-gray-50 dark:bg-indigo-900/30 p-2 rounded-full text-gray-400 dark:text-indigo-300 group-hover:text-secondary transition-colors cursor-pointer">
                                    <span className="material-symbols-outlined">bookmark_border</span>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <Link to={`/practice/${chapter.id}`} className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/40 text-primary dark:text-indigo-200 hover:bg-primary hover:text-white transition-all text-sm font-semibold border border-indigo-100 dark:border-indigo-800">
                                    <span className="material-symbols-outlined text-lg">menu_book</span> NCERT Problems
                                </Link>
                                <button className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-red-500 hover:text-white transition-all text-sm font-semibold border border-gray-200 dark:border-gray-700">
                                    <span className="material-symbols-outlined text-lg">timer</span> Test
                                </button>
                            </div>
                        </div>
                    </div>
                ))}

                {/* Mock Locked Item */}
                <div className="bg-surface-light dark:bg-surface-dark rounded-xl p-3 lg:p-5 border border-gray-200 dark:border-indigo-900/50 shadow-sm transition-shadow opacity-75 grayscale hover:grayscale-0">
                    <div className="flex lg:hidden items-center justify-between gap-3">
                        <div className="flex flex-col min-w-0">
                            <span className="text-[10px] font-bold text-text-muted-light dark:text-indigo-400 uppercase tracking-wider mb-0.5">Chapter ...</span>
                            <h3 className="text-sm font-bold text-gray-900 dark:text-white truncate">Future Chapter</h3>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                            <span className="material-symbols-outlined text-gray-400 text-lg">lock</span>
                        </div>
                    </div>
                    <div className="hidden lg:block">
                        <div className="flex justify-between items-start mb-4">
                            <div>
                                <span className="text-xs font-bold text-text-muted-light dark:text-indigo-400 uppercase tracking-wider mb-1 block">Chapter ...</span>
                                <h3 className="text-lg font-bold text-gray-900 dark:text-white">Future Chapter</h3>
                            </div>
                            <div className="bg-gray-100 dark:bg-gray-800 p-2 rounded-full">
                                <span className="material-symbols-outlined text-gray-400">lock</span>
                            </div>
                        </div>
                        <div className="p-3 bg-gray-50 dark:bg-background-dark rounded-lg text-center text-sm text-text-muted-light dark:text-indigo-300 italic border border-gray-100 dark:border-indigo-900">
                            Complete previous chapters to unlock
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
