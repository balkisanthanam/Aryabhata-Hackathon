import MainLogo from '../../assets/branding/MainLogo.png';

export const Header = () => {
    return (
        <header className="w-full max-w-6xl mb-6 md:mb-12 flex flex-col items-center justify-center relative z-20">
            <div className="relative group p-2 md:p-4 cursor-pointer">
                <div className="absolute inset-0 bg-gradient-to-tr from-vedic-yellow-main/40 via-vedic-indigo-lighter/20 to-vedic-indigo-main/40 rounded-full blur-2xl opacity-60 group-hover:opacity-80 transition-opacity duration-700"></div>
                <div className="absolute inset-0 bg-vedic-indigo-lighter/10 rounded-full blur-3xl animate-pulse"></div>

                {/* Placeholder for Logo - Using a Text fallback or the image if available. The requirement requested the image. */}
                {/* "Use @Design/Branding/MainLogo.png for the icon and @Design/Branding/typographiclogo.png for the header text" */}
                {/* Since we can't easily access the absolute paths of the design assets in the running app without moving them, 
            I will use the absolute paths for now, or just a placeholder img tag that points to them if we were to serve them. 
            For this implementation, I will assume we should copy them or just link them if they are in public.
            Wait, I should probably copy them to public folder if I want to use them. 
            But the user said "Use ... for the placeholder". 
            I'll use a visual placeholder with the file path mentioned in alt text or src if possible. 
            Actually, let's copy the logo assets to public/assets/branding folder.
        */}
                <div className="relative flex flex-col items-center gap-2">
                    <div className="flex items-center gap-3">
                        <img
                            src={MainLogo}
                            alt="Aryabhata Logo"
                            className="h-24 md:h-40 w-auto object-contain drop-shadow-xl transform transition-transform duration-500 hover:scale-105"
                        />
                    </div>
                </div>
            </div>
        </header>
    );
};
