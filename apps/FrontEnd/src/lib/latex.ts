// Restores LaTeX backslash escapes that the extraction pipeline occasionally
// turns into control characters (JSON-decoded \f, \t, \n, \r, \b, \a, \v).
// Mirrors the recovery logic that previously lived in SolutionView.tsx so
// QuestionView and any other consumer can apply the same cleanup.

// [controlCharCode, suffix, latexCommand]
const CORRUPTIONS: ReadonlyArray<readonly [number, string, string]> = [
    // \f (Form Feed, 0x0C)
    [0x0c, 'rac', '\\frac'],
    [0x0c, 'all', '\\forall'],

    // \t (Tab, 0x09)
    [0x09, 'imes', '\\times'],
    [0x09, 'ext', '\\text'],
    [0x09, 'an', '\\tan'],
    [0x09, 'au', '\\tau'],
    [0x09, 'heta', '\\theta'],
    [0x09, 'o', '\\to'],

    // \n (Newline, 0x0A)
    [0x0a, 'u', '\\nu'],
    [0x0a, 'abla', '\\nabla'],
    [0x0a, 'eq', '\\neq'],
    [0x0a, 'eg', '\\neg'],
    [0x0a, 'ot', '\\not'],

    // \r (Carriage Return, 0x0D)
    [0x0d, 'ho', '\\rho'],
    [0x0d, 'ight', '\\right'],

    // \b (Backspace, 0x08)
    [0x08, 'ar', '\\bar'],
    [0x08, 'eta', '\\beta'],
    [0x08, 'egin', '\\begin'],
    [0x08, 'f', '\\bf'],

    // \a (Bell, 0x07)
    [0x07, 'lpha', '\\alpha'],
    [0x07, 'pprox', '\\approx'],

    // \v (Vertical Tab, 0x0B)
    [0x0b, 'ec', '\\vec'],
    [0x0b, 'ert', '\\vert'],
    [0x0b, 'arphi', '\\varphi'],
];

const COMPILED = CORRUPTIONS.map(([code, suffix, latex]) => ({
    pattern: new RegExp(String.fromCharCode(code) + suffix, 'g'),
    replacement: latex,
}));

export const cleanLatex = (text: string | null | undefined): string => {
    if (!text) return "";
    let out = text;
    for (const { pattern, replacement } of COMPILED) {
        out = out.replace(pattern, replacement);
    }
    return out;
};
