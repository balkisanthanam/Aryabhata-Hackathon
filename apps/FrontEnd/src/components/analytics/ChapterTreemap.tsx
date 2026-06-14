import { Treemap } from 'recharts';
import { Chapter, standingConfig, Standing } from '../../data/perfCompassData';

interface ChapterTreemapProps {
    chapters: Chapter[];
    onChapterClick: (chapter: Chapter) => void;
}

interface TreemapNode {
    name: string;
    size: number;
    standing: Standing;
    chapter: Chapter;
    weightLabel: string;
    [key: string]: unknown;
}

// Custom content renderer for Treemap tiles — passed as a function (recharts v3 pattern)
const renderCustomContent = (props: any) => {
    const { x, y, width, height, name, standing, weightLabel } = props;

    if (!width || !height || width < 20 || height < 20) return <g />;

    // Recharts v3 calls this for internal/parent nodes too — skip if no standing data
    const config = standingConfig[standing as Standing];
    if (!config) return <g />;
    const isSmall = width < 100 || height < 50;
    const isTiny = width < 70 || height < 40;

    return (
        <g>
            <rect
                x={x}
                y={y}
                width={width}
                height={height}
                rx={8}
                ry={8}
                style={{
                    fill: config.color,
                    stroke: '#ffffff',
                    strokeWidth: 2,
                    cursor: 'pointer',
                    opacity: standing === 0 ? 0.4 : 0.85,
                }}
            />
            {/* Chapter name */}
            {!isTiny && (
                <foreignObject x={x + 6} y={y + 6} width={width - 12} height={height - 12}>
                    <div
                        style={{
                            width: '100%',
                            height: '100%',
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'center',
                            alignItems: 'center',
                            textAlign: 'center',
                            overflow: 'hidden',
                            padding: '4px',
                        }}
                    >
                        <span
                            style={{
                                fontSize: isSmall ? '10px' : '12px',
                                fontWeight: 600,
                                color: standing === 0 ? '#374151' : '#1a1a2e',
                                lineHeight: 1.3,
                                display: '-webkit-box',
                                WebkitLineClamp: isSmall ? 2 : 3,
                                WebkitBoxOrient: 'vertical',
                                overflow: 'hidden',
                            }}
                        >
                            {name}
                        </span>
                        <span
                            style={{
                                fontSize: isSmall ? '9px' : '11px',
                                fontWeight: 700,
                                color: standing === 0 ? '#6B7280' : '#1a1a2e',
                                marginTop: '2px',
                                opacity: 0.8,
                            }}
                        >
                            {weightLabel}
                        </span>
                    </div>
                </foreignObject>
            )}
        </g>
    );
};

export const ChapterTreemap = ({ chapters, onChapterClick }: ChapterTreemapProps) => {
    const data: TreemapNode[] = chapters.map(ch => ({
        name: ch.name,
        size: ch.jeeWeightPct,
        standing: ch.studentStanding,
        chapter: ch,
        weightLabel: `${ch.jeeWeightPct}%`,
    }));

    const handleClick = (node: any) => {
        // In recharts v3, onClick receives the TreemapNode with our custom props spread in
        if (node && node.chapter) {
            onChapterClick(node.chapter);
        }
    };

    const treemapHeight = Math.max(380, chapters.length * 24);

    return (
        <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-4 lg:p-6 border border-gray-200 dark:border-indigo-900/50">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <span className="material-symbols-outlined text-xl text-primary">grid_view</span>
                    Chapter Weightage in JEE
                </h3>
                <span className="text-xs text-text-muted-light dark:text-gray-400">
                    Tile size = JEE weightage • Color = your standing • Click to explore
                </span>
            </div>
            <Treemap
                width={800}
                height={treemapHeight}
                data={data}
                dataKey="size"
                aspectRatio={4 / 3}
                stroke="#fff"
                content={renderCustomContent}
                onClick={handleClick}
                isAnimationActive={false}
                style={{ width: '100%', maxHeight: '70vh' }}
            />
        </section>
    );
};
