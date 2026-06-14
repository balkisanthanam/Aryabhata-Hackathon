import katex from 'katex';
import 'katex/dist/contrib/mhchem'; // Enable mhchem for chemical equations
import { useEffect, useRef } from 'react';

// ── Chemistry pre-processing heuristics ──────────────────────────────

/**
 * Regex that matches common chemical formulas NOT already inside $ or \ce{}.
 * Matches patterns like:  CH3COOH, H2SO4, NaOH, Ca(OH)2, Fe2O3, CO2, CH3CH2OH
 * Requires at least one uppercase letter followed by (lowercase letter or digit or parenthesised group)
 * and must contain at least one digit (to avoid matching plain words like "In" or "No").
 */
const CHEM_FORMULA_RE =
    /(?<!\$|\\ce\{)(?<![A-Za-z])([A-Z][a-z]?(?:\d+|(?:\([A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*\)\d*)|[A-Z][a-z]?\d*){1,}(?=[\s,.):\]}\n]|$))(?![^$]*\$)/g;

/**
 * Quick check: does the candidate look like a real chemical formula?
 * Must have at least one digit AND at least 2 element-like uppercase letters, or be a known compound.
 */
const KNOWN_NO_DIGIT = new Set([
    'NaOH', 'KOH', 'HCl', 'HBr', 'HI', 'HF', 'NaCl', 'KCl',
    'NaBr', 'KBr', 'CaO', 'MgO', 'FeO', 'CuO', 'ZnO', 'AlN',
]);

function looksLikeFormula(s: string): boolean {
    if (s.length < 2) return false;
    // Skip common English words that match the regex
    const skip = new Set(['In', 'On', 'No', 'He', 'If', 'Or', 'As', 'At', 'Be', 'Do', 'So', 'Up', 'By']);
    if (skip.has(s)) return false;
    if (KNOWN_NO_DIGIT.has(s)) return true;
    // Must contain at least one digit
    if (!/\d/.test(s)) return false;
    // Must start with a valid element symbol (uppercase + optional lowercase)
    if (!/^[A-Z][a-z]?/.test(s)) return false;
    return true;
}

/**
 * Pre-process text to wrap standalone chemical formulas and reaction arrows
 * in mhchem notation so KaTeX renders them properly.
 */
function chemistryPreProcess(text: string): string {
    // 1. Convert reaction arrows in plain text to mhchem notation
    //    <-> → $\ce{<->}$   and   -> → $\ce{->}$
    //    Only match arrows NOT already inside $ delimiters.
    text = text.replace(/(?<!\$)(<->|<-->)(?![^$]*\$)/g, '$\\ce{<=>}$');
    text = text.replace(/(?<!\$)(-->?)(?![^$]*\$)/g, '$\\ce{->}$');

    // 2. Wrap standalone chemical formulas
    text = text.replace(CHEM_FORMULA_RE, (match) => {
        if (looksLikeFormula(match)) {
            return `$\\ce{${match}}$`;
        }
        return match;
    });

    return text;
}

interface LatexRendererProps {
    content: string;
    displayMode?: boolean;
    className?: string;
}

// Splits on **bold** spans. A bold span may contain math/chem ($...$ or \ce{})
// so we anchor on `**` boundaries that aren't escaped or part of `***`.
// The inner content is then re-fed through the math/chem pipeline.
const BOLD_SPAN_RE = /(\*\*(?!\s)(?:[^*]|\*(?!\*))+?\*\*)/g;

export const LatexRenderer = ({ content, className = '' }: LatexRendererProps) => {
    // If no content, return nothing
    if (!content) return null;

    // Split top-level by markdown bold so a bold span can wrap math/chem too.
    const boldSegments = content.split(BOLD_SPAN_RE).filter(Boolean);
    if (boldSegments.length > 1) {
        return (
            <span className={`${className} whitespace-pre-wrap`}>
                {boldSegments.map((seg, i) =>
                    seg.length >= 4 && seg.startsWith('**') && seg.endsWith('**')
                        ? <strong key={i}><LatexRenderer content={seg.slice(2, -2)} /></strong>
                        : <LatexRenderer key={i} content={seg} />
                )}
            </span>
        );
    }

    // Helper: Wrap specific LaTeX commands that might be "orphan" (not inside $...$)
    // We use a tokenizer approach to strictly distinguish between "Math Mode" and "Text Mode"
    const processContent = (text: string): string => {
        if (!text) return text;

        // --- Phase 0: Pre-processing heuristics for chemistry ---
        text = chemistryPreProcess(text);

        let result = "";
        let lastIndex = 0;

        // Regex to find:
        // 1. Block Math: $$...$$
        // 2. Inline Math: $...$
        // 3. Target to Wrap: \ce{
        // Note: We prioritize finding existing math to SKIP it.
        // Inline math allows any non-$ character including newlines, mirroring
        // block math behavior — pipeline-emitted LaTeX sometimes contains a
        // stray newline inside $...$ which would otherwise render as raw text.
        const tokenRegex = /(\$\$[\s\S]*?\$\$)|(\$[^\$]*?\$)|(\\ce\s*\{)/g;

        let match;
        while ((match = tokenRegex.exec(text)) !== null) {
            // Append text before the match
            result += text.slice(lastIndex, match.index);

            const fullMatch = match[0];

            if (match[1] || match[2]) {
                // Case A: Existing Math ($$ or $)
                // Just append it as is. We don't touch inside.
                result += fullMatch;
            } else if (match[3]) {
                // Case B: \ce{ found in TEXT mode (not consumed by math above)
                // We need to parse ahead to find the balancing closing brace '}'
                const startIndex = match.index;
                let openBraces = 0;
                let foundEnd = false;
                let endIndex = startIndex + match[0].length; // Start after \ce{

                // Scan forward from the end of "\ce{"
                for (let i = startIndex + match[0].length - 1; i < text.length; i++) { // Start at '{'
                    if (text[i] === '{') openBraces++;
                    if (text[i] === '}') openBraces--;

                    if (openBraces === 0) {
                        endIndex = i + 1;
                        foundEnd = true;
                        break;
                    }
                }

                if (foundEnd) {
                    // Extract the full \ce{...} block
                    const ceBlock = text.slice(startIndex, endIndex);
                    // Wrap it in math delimiters
                    result += `$${ceBlock}$`;

                    // Advance regex lastIndex to skip what we just manually consumed
                    tokenRegex.lastIndex = endIndex;
                } else {
                    // Unbalanced or failed? Just append the match start and continue
                    result += fullMatch;
                }
            }

            lastIndex = tokenRegex.lastIndex;
        }

        // Append remaining text
        result += text.slice(lastIndex);

        // Cleanup: Normalize commas in TEXT segments (optional, kept from before)
        // But doing it globally is risky for math. Let's skip it or do it carefully.
        // For now, simple comma normalization on the whole result might be safe enough for this specific app usage,
        // but strictly it should only be on text.
        // Let's remove the generic comma replace to avoid breaking math coordinates like (1, 2).

        return result;
    };

    let processedContent = processContent(content);

    // 4. Cleanup double $$ if any created
    processedContent = processedContent.replace(/\$\$+/g, '$$$$');

    // Split content by LaTeX delimiters ($$...$$ for block, $...$ for inline)
    const parts = processedContent.split(/(\$\$[\s\S]+?\$\$)|\$?(\$[^\$]+?\$)\$?|(\n)/g).filter(Boolean);


    return (
        <span className={`${className} whitespace-pre-wrap`}>
            {parts.map((part, index) => {
                // Check for Block Math ($$)
                if (part.startsWith('$$') && part.endsWith('$$')) {
                    const math = part.slice(2, -2);
                    return <LatexSegment key={index} math={math} displayMode={true} />;
                }
                // Check for Inline Math ($)
                if (part.startsWith('$') && part.endsWith('$')) {
                    const math = part.slice(1, -1);
                    return <LatexSegment key={index} math={math} displayMode={false} />;
                }
                // Regular text — render markdown bold (**...**) so AI-generated
                // solutions don't show literal asterisks (issue #30).
                return <TextSegment key={index} text={part} />;
            })}
        </span>
    );
};

// Renders a plain-text segment, converting **bold** markdown to <strong>.
// Single-asterisk italics intentionally not supported — too risky next to
// chemistry footnote markers.
const TextSegment = ({ text }: { text: string }) => {
    const segments = text.split(/(\*\*[^*\n][^*]*?\*\*)/g);
    return (
        <>
            {segments.map((seg, i) => {
                if (seg.length >= 4 && seg.startsWith('**') && seg.endsWith('**')) {
                    return <strong key={i}>{seg.slice(2, -2)}</strong>;
                }
                return <span key={i}>{seg}</span>;
            })}
        </>
    );
};

// Internal component to handle individual LaTeX segments
const LatexSegment = ({ math, displayMode }: { math: string; displayMode: boolean }) => {
    const containerRef = useRef<HTMLSpanElement>(null);

    useEffect(() => {
        if (containerRef.current) {
            try {
                katex.render(math, containerRef.current, {
                    displayMode,
                    throwOnError: false,
                    output: 'html',
                });
            } catch (error) {
                console.error('KaTeX error:', error);
                if (containerRef.current) containerRef.current.textContent = `$${math}$`;
            }
        }
    }, [math, displayMode]);

    return <span ref={containerRef} />;
};
