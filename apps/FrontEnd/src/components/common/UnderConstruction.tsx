import { Navbar } from '../layout/Navbar';

interface UnderConstructionProps {
    title: string;
    variant?: 'full' | 'embedded';
    onBack?: () => void;
}

export const UnderConstruction = ({ title, variant = 'full', onBack }: UnderConstructionProps) => {
    const isFull = variant === 'full';

    // Default back behavior
    const handleBack = () => {
        if (onBack) {
            onBack();
        } else {
            window.history.back();
        }
    };

    const content = (
        <div className={`flex-1 flex flex-col items-center justify-center p-6 text-center ${!isFull ? 'bg-transparent' : ''}`}>
            <div className="max-w-md w-full mb-8 transform hover:scale-105 transition-transform duration-500">
                <img
                    src="/assets/filler/UnderConstruction.png"
                    alt="Construction"
                    className="w-full max-w-lg h-auto object-contain [mask-image:radial-gradient(circle,rgba(0,0,0,1)_40%,rgba(0,0,0,0)_100%)] opacity-90 drop-shadow-xl"
                />
            </div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">{title} Module</h1>
            <p className="text-lg text-text-muted-light dark:text-gray-400 font-medium">Coming Soon</p>
            <button
                onClick={handleBack}
                className="mt-8 px-6 py-2 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors font-semibold"
            >
                {isFull ? 'Go Back' : 'Close'}
            </button>
        </div>
    );

    if (!isFull) {
        return content;
    }

    return (
        <div className="min-h-screen bg-background-light dark:bg-background-dark flex flex-col items-center">
            <Navbar />
            {content}
        </div>
    );
};
