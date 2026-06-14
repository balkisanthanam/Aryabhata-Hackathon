import { LatexRenderer } from './LatexRenderer';

/**
 * Renders JEE question text that may contain GitHub-flavored markdown pipe-tables
 * (used by Match-List-I-with-List-II type questions extracted by the LLM).
 *
 * Splits the raw text into text-segments (rendered via LatexRenderer) and
 * table-segments (rendered as <table>, each cell run through LatexRenderer for
 * inline LaTeX + mhchem support).
 */

type TableBlock = { kind: 'table'; header: string[]; rows: string[][] };
type TextBlock = { kind: 'text'; content: string };
type Block = TableBlock | TextBlock;

const SEPARATOR_RE = /^\s*\|(?:\s*:?-{2,}:?\s*\|)+\s*$/;
const PIPE_LINE_RE = /^\s*\|.*\|\s*$/;

function splitPipeRow(line: string): string[] {
    const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
    return trimmed.split('|').map((c) => c.trim());
}

function parseBlocks(text: string): Block[] {
    if (!text) return [];
    const lines = text.split('\n');
    const blocks: Block[] = [];
    let buffer: string[] = [];

    const flushText = () => {
        if (buffer.length > 0) {
            blocks.push({ kind: 'text', content: buffer.join('\n') });
            buffer = [];
        }
    };

    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        const next = lines[i + 1];
        // Detect start of markdown table: header pipe-row followed by separator row
        if (PIPE_LINE_RE.test(line) && next !== undefined && SEPARATOR_RE.test(next)) {
            flushText();
            const header = splitPipeRow(line);
            const rows: string[][] = [];
            i += 2; // skip header + separator
            while (i < lines.length && PIPE_LINE_RE.test(lines[i])) {
                rows.push(splitPipeRow(lines[i]));
                i += 1;
            }
            blocks.push({ kind: 'table', header, rows });
            continue;
        }
        buffer.push(line);
        i += 1;
    }
    flushText();
    return blocks;
}

export const QuestionContent = ({ content, className = '' }: { content: string; className?: string }) => {
    if (!content) return null;
    const blocks = parseBlocks(content);

    if (blocks.length === 1 && blocks[0].kind === 'text') {
        return <LatexRenderer content={blocks[0].content} className={className} />;
    }

    return (
        <div className={className}>
            {blocks.map((block, idx) => {
                if (block.kind === 'text') {
                    if (!block.content.trim()) return null;
                    return <LatexRenderer key={idx} content={block.content} />;
                }
                return (
                    <div key={idx} className="my-3 overflow-x-auto">
                        <table className="min-w-full border-collapse text-sm">
                            <thead>
                                <tr className="border-b border-gray-300 dark:border-slate-600">
                                    {block.header.map((cell, ci) => (
                                        <th
                                            key={ci}
                                            className="px-3 py-2 text-left font-semibold text-gray-700 dark:text-slate-200 border-r last:border-r-0 border-gray-200 dark:border-slate-700"
                                        >
                                            <LatexRenderer content={cell} />
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {block.rows.map((row, ri) => (
                                    <tr key={ri} className="border-b last:border-b-0 border-gray-200 dark:border-slate-700">
                                        {row.map((cell, ci) => (
                                            <td
                                                key={ci}
                                                className="px-3 py-2 align-top text-gray-800 dark:text-slate-100 border-r last:border-r-0 border-gray-200 dark:border-slate-700"
                                            >
                                                <LatexRenderer content={cell} />
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                );
            })}
        </div>
    );
};

export default QuestionContent;
