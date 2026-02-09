import React from 'react';

interface SriChakramLoaderProps {
    className?: string;
}

const SriChakramLoader: React.FC<SriChakramLoaderProps> = ({ className = 'w-24 h-24' }) => {
    return (
        <div className={`relative flex items-center justify-center ${className}`} aria-label="Loading...">
            <svg
                viewBox="0 0 100 100"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="w-full h-full"
            >
                <defs>
                    {/* Vedic Gold Gradient */}
                    <linearGradient id="vedicGold" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#FBBF24" /> {/* amber-400 */}
                        <stop offset="50%" stopColor="#D97706" /> {/* amber-600 */}
                        <stop offset="100%" stopColor="#92400E" /> {/* amber-800 */}
                    </linearGradient>
                </defs>

                {/* --- ROTATING YANTRA (12s) --- */}
                <g className="origin-center animate-[spin_12s_linear_infinite]">

                    {/* 1. Bhupura (Outer Gates) - Thicker Stroke (1.2) */}
                    <path
                        d="M5,5 L40,5 L40,2 L60,2 L60,5 L95,5 L95,40 L98,40 L98,60 L95,60 L95,95 L60,95 L60,98 L40,98 L40,95 L5,95 L5,60 L2,60 L2,40 L5,40 Z"
                        stroke="url(#vedicGold)"
                        strokeWidth="1.2"
                        strokeLinejoin="miter"
                    />

                    {/* 2. Lotus Petal Rings */}
                    {/* Outer 16 Petals Area */}
                    <circle cx="50" cy="50" r="38" stroke="url(#vedicGold)" strokeWidth="0.8" opacity="0.6" />
                    {/* Inner 8 Petals Area */}
                    <circle cx="50" cy="50" r="32" stroke="url(#vedicGold)" strokeWidth="0.8" opacity="0.8" />

                    {/* 3. Central 9 Triangles (Navagrahas) - Fine Stroke (0.5) */}
                    <g stroke="url(#vedicGold)" strokeWidth="0.5" strokeLinecap="round" strokeLinejoin="round">
                        {/* 4 Upward Triangles (Shiva) */}
                        <polygon points="50,15 80,70 20,70" />
                        <polygon points="50,22 75,65 25,65" />
                        <polygon points="50,29 70,60 30,60" />
                        <polygon points="50,36 65,55 35,55" />

                        {/* 5 Downward Triangles (Shakti) */}
                        <polygon points="50,85 15,30 85,30" />
                        <polygon points="50,78 20,35 80,35" />
                        <polygon points="50,71 25,40 75,40" />
                        <polygon points="50,64 30,45 70,45" />
                        <polygon points="50,57 35,50 65,50" />
                    </g>
                </g>

                {/* --- STATIC BINDU (Pulse) --- */}
                <circle
                    cx="50"
                    cy="50"
                    r="1.5"
                    fill="url(#vedicGold)"
                    className="animate-pulse"
                />
            </svg>
        </div>
    );
};

export default SriChakramLoader;
