/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                // Brand Colors
                primary: "#1A237E", // brand-indigo
                secondary: "#FBC02D", // brand-amber
                "brand-amber": "#FBC02D",
                "text-body": "#334155", // slate-700

                // Existing Palette (Preserved)
                "vedic-indigo-lighter": "#5C86C0",
                "vedic-indigo-hover": "#3949AB",
                "vedic-indigo-main": "#1A237E",
                "vedic-indigo-deep": "#0D1560",
                "vedic-indigo-darkest": "#000040",
                // Glowing Turmeric Yellow Shades
                "vedic-yellow-lighter": "#FFF176",
                "vedic-yellow-highlight": "#FBDC35",
                "vedic-yellow-main": "#FBC02D",
                "vedic-yellow-warm": "#F57F17",
                "vedic-yellow-darkest": "#E65100",

                "background-light": "#F0F4F8", // Slightly cooler/richer white
                "background-dark": "#050A30", // Very deep indigo
                "surface-light": "#FFFFFF",
                "surface-dark": "#121840", // Slightly lighter than background
                "text-main-light": "#000040",
                "text-main-dark": "#F9FAFB",
                "text-muted-light": "#5C86C0",
                "text-muted-dark": "#9FA8DA",
            },
            fontFamily: {
                sans: ["Plus Jakarta Sans", "sans-serif"],
                serif: ["Lora", "serif"],
                hand: ["Kalam", "cursive"],
            },
            borderRadius: {
                DEFAULT: "0.5rem",
                xl: "1rem",
                "2xl": "1.5rem",
                "3xl": "2rem",
            },
            boxShadow: {
                'soft': '0 4px 20px -2px rgba(26, 35, 126, 0.05)',
                'card': '0 10px 25px -5px rgba(26, 35, 126, 0.1), 0 8px 10px -6px rgba(26, 35, 126, 0.1)',
                'glow': '0 0 20px rgba(251, 192, 45, 0.5)',
                'glow-indigo': '0 0 20px rgba(26, 35, 126, 0.3)',
            }
        },
    },
    plugins: [],
}
