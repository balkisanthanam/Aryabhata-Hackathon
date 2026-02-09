import { ReactNode } from 'react';
import { Header } from './Header';

interface LayoutProps {
    children: ReactNode;
    hideHeader?: boolean;
}

export const Layout = ({ children, hideHeader = false }: LayoutProps) => {
    return (
        <div className="mesh-bg dark:bg-background-dark text-text-main-light dark:text-text-main-dark min-h-screen font-sans flex flex-col items-center py-4 md:py-6 px-4 sm:px-6 md:px-8 transition-colors duration-300">
            {!hideHeader && <Header />}
            <main className="w-full max-w-6xl space-y-4 md:space-y-8 relative z-10">
                {children}
            </main>

            {/* Dark Mode Toggle */}
            <div className="fixed bottom-8 right-8 z-50">
                <button
                    className="bg-vedic-indigo-main dark:bg-vedic-yellow-main text-white dark:text-vedic-indigo-darkest p-4 rounded-full shadow-lg hover:shadow-glow hover:-translate-y-1 transition-all duration-300 focus:outline-none"
                    onClick={() => document.documentElement.classList.toggle('dark')}
                >
                    <span className="material-symbols-outlined block dark:hidden">dark_mode</span>
                    <span className="material-symbols-outlined hidden dark:block">light_mode</span>
                </button>
            </div>
        </div>
    );
};
