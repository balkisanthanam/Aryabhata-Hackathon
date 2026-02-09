import { Link } from 'react-router-dom';
import TypoLogo from '../../assets/branding/typographiclogo.png';



export const Navbar = () => {
    // We might want to use useStore for user initials if we had them, 
    // or just hardcode JD for now as per design/mock.
    return (
        <header className="w-full bg-surface-light dark:bg-surface-dark border-b border-gray-200 dark:border-indigo-900/50 sticky top-0 z-40 shadow-sm transition-colors duration-300">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-20 py-2 flex items-center justify-between">
                <Link to="/" className="flex items-center gap-3 group">
                    <img
                        src={TypoLogo}
                        alt="Aryabhata"
                        className="h-12 md:h-16 w-auto opacity-90 object-contain sm:block"
                    />
                </Link>

                <div className="flex items-center gap-4">
                    <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-secondary-light dark:bg-amber-900/20 rounded-full border border-amber-200 dark:border-amber-800/50">
                        <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
                        <span className="text-xs font-bold text-amber-800 dark:text-amber-400 uppercase tracking-wide">JEE Mains: 45 Days</span>
                    </div>
                    <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-primary to-indigo-500 p-0.5 cursor-pointer hover:shadow-glow transition-shadow">
                        <div className="h-full w-full rounded-full bg-surface-light dark:bg-surface-dark flex items-center justify-center text-primary dark:text-white font-bold text-sm">
                            JD
                        </div>
                    </div>
                </div>
            </div>
        </header>
    );
};
