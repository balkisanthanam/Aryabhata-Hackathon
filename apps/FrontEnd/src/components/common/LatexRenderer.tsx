import katex from 'katex';
import 'katex/dist/contrib/mhchem'; // Enable mhchem for chemical equations
import { useEffect, useRef } from 'react';

interface LatexRendererProps {
    content: string;
    displayMode?: boolean;
    className?: string;
}

export const LatexRenderer = ({ content, className = '' }: LatexRendererProps) => {
    // If no content, return nothing
    if (!content) return null;

    // Helper: Wrap specific LaTeX commands that might be "orphan" (not inside $...$)
    // We use a tokenizer approach to strictly distinguish between "Math Mode" and "Text Mode"
    const processContent = (text: string): string => {
        if (!text) return text;

        let result = "";
        let lastIndex = 0;

        // Regex to find:
        // 1. Block Math: $$...$$
        // 2. Inline Math: $...$
        // 3. Target to Wrap: \ce{ 
        // Note: We prioritize finding existing math to SKIP it.
        const tokenRegex = /(\$\$[\s\S]*?\$\$)|(\$[^\$\n]*?\$)|(\\ce\s*\{)/g;

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
    const parts = processedContent.split(/(\$\$[\s\S]+?\$\$)|\$?(\$[^\$\n]+?\$)\$?|(\n)/g).filter(Boolean);


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
                // Regular text
                return <span key={index}>{part}</span>;
            })}
        </span>
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
