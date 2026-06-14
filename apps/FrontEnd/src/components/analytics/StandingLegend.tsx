import { Standing, standingConfig } from '../../data/perfCompassData';

export const StandingLegend = () => {
    const levels: Standing[] = [5, 4, 3, 2, 1, 0];

    return (
        <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="font-semibold text-text-muted-light dark:text-indigo-300 uppercase tracking-wide mr-1">Standing:</span>
            {levels.map((level) => {
                const config = standingConfig[level];
                return (
                    <span key={level} className="inline-flex items-center gap-1.5">
                        <span
                            className="inline-block w-3 h-3 rounded-sm border"
                            style={{ backgroundColor: config.color, borderColor: `${config.color}80` }}
                        />
                        <span className="text-text-muted-light dark:text-gray-400">{config.label}</span>
                    </span>
                );
            })}
        </div>
    );
};
