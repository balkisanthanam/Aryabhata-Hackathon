// motion import removed - not currently used
// import { motion } from 'framer-motion';

interface UserState {
    name: string;
    details: string;
    goal: string;
    email: string;
}

export const ProfileCard = ({ user }: { user: UserState }) => {
    return (
        <div className="space-y-2 md:space-y-6 flex-1 w-full">
            <div className="flex items-center justify-between w-full md:w-auto md:justify-start gap-3 mb-2">
                <span className="bg-vedic-indigo-main/5 dark:bg-white/10 text-vedic-indigo-main dark:text-vedic-yellow-lighter px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider border border-vedic-indigo-main/10 dark:border-white/10">
                    Student Profile
                </span>
                <div className="flex items-center gap-2">
                    <button aria-label="Edit Profile" className="text-text-muted-light dark:text-text-muted-dark hover:text-vedic-yellow-warm dark:hover:text-vedic-yellow-main transition-colors p-1 rounded-full hover:bg-gray-100 dark:hover:bg-white/5">
                        <span className="material-symbols-outlined text-sm">edit</span>
                    </button>
                </div>
            </div>
            <div className="flex flex-col gap-2">
                <div className="flex items-baseline gap-2 mb-2">
                    <h2 className="text-3xl md:text-5xl font-bold text-vedic-indigo-darkest dark:text-white tracking-tight">{user.name}</h2>
                    <span className="text-base md:text-lg text-text-muted-light dark:text-text-muted-dark font-hand">Welcome back!</span>
                </div>
                <div className="hidden md:flex md:flex-wrap lg:grid lg:grid-cols-4 gap-y-4 gap-x-8 w-full mt-2 md:mt-0 transition-all duration-300">
                    <div className="flex items-center gap-3 group/item">
                        <div className="p-2 rounded-lg bg-vedic-indigo-lighter/10 text-vedic-indigo-main dark:bg-white/5 dark:text-vedic-yellow-main group-hover/item:bg-vedic-indigo-main group-hover/item:text-white transition-colors">
                            <span className="material-symbols-outlined text-xl">school</span>
                        </div>
                        <div className="flex flex-col">
                            <span className="text-xs font-semibold text-text-muted-light dark:text-text-muted-dark uppercase tracking-wide">Class</span>
                            <span className="text-vedic-indigo-darkest dark:text-white font-bold">{user.details}</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 group/item">
                        <div className="p-2 rounded-lg bg-vedic-indigo-lighter/10 text-vedic-indigo-main dark:bg-white/5 dark:text-vedic-yellow-main group-hover/item:bg-vedic-indigo-main group-hover/item:text-white transition-colors">
                            <span className="material-symbols-outlined text-xl">flag</span>
                        </div>
                        <div className="flex flex-col">
                            <span className="text-xs font-semibold text-text-muted-light dark:text-text-muted-dark uppercase tracking-wide">Goal</span>
                            <span className="text-vedic-indigo-darkest dark:text-white font-bold">{user.goal}</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 group/item col-span-1 md:col-span-2 lg:col-span-1">
                        <div className="p-2 rounded-lg bg-vedic-indigo-lighter/10 text-vedic-indigo-main dark:bg-white/5 dark:text-vedic-yellow-main group-hover/item:bg-vedic-indigo-main group-hover/item:text-white transition-colors">
                            <span className="material-symbols-outlined text-xl">mail</span>
                        </div>
                        <div className="flex flex-col">
                            <span className="text-xs font-semibold text-text-muted-light dark:text-text-muted-dark uppercase tracking-wide">Contact</span>
                            <a className="text-vedic-indigo-darkest dark:text-white font-medium hover:text-vedic-indigo-hover dark:hover:text-vedic-yellow-highlight transition-colors truncate" href={`mailto:${user.email}`}>{user.email}</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
