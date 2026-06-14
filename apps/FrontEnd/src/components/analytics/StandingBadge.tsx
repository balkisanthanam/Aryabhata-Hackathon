import { Standing, standingConfig } from '../../data/perfCompassData';

interface StandingBadgeProps {
    standing: Standing;
    size?: 'sm' | 'md';
}

export const StandingBadge = ({ standing, size = 'md' }: StandingBadgeProps) => {
    const config = standingConfig[standing];
    const sizeClasses = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';

    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full font-medium ${sizeClasses}`}
            style={{ backgroundColor: `${config.color}20`, color: config.color, border: `1px solid ${config.color}40` }}
        >
            <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: config.color }}
            />
            {config.label}
        </span>
    );
};
