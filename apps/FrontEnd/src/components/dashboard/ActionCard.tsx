import { Link } from 'react-router-dom';
import { cn } from '../../lib/utils';

interface ActionCardProps {
    title: string;
    description: string;
    icon: string;
    link: string;
    variant: 'secondary' | 'indigo' | 'orange';
}

export const ActionCard = ({ title, description, icon, link, variant }: ActionCardProps) => {
    const isSecondary = variant === 'secondary'; // green/yellow
    const isIndigo = variant === 'indigo';
    // isOrange is implicitly handled by !isSecondary && !isIndigo in the ternary chains below

    const bgIcon = isSecondary ? 'bg-green-50 dark:bg-secondary/10 text-secondary' :
        isIndigo ? 'bg-indigo-50 dark:bg-vedic-indigo-main/20 text-vedic-indigo-main dark:text-vedic-indigo-lighter' :
            'bg-orange-50 dark:bg-vedic-yellow-warm/20 text-vedic-yellow-warm';

    const groupHoverBorder = isSecondary ? 'group-hover:border-secondary/30' :
        isIndigo ? 'group-hover:border-vedic-indigo-main/30' :
            'group-hover:border-vedic-yellow-warm/30';

    const groupHoverIcon = isSecondary ? 'group-hover:bg-secondary group-hover:text-vedic-indigo-darkest' :
        isIndigo ? 'group-hover:bg-vedic-indigo-main group-hover:text-white' :
            'group-hover:bg-vedic-yellow-warm group-hover:text-white';

    const groupHoverTitle = isSecondary ? 'group-hover:text-secondary' :
        isIndigo ? 'group-hover:text-vedic-indigo-main dark:group-hover:text-vedic-indigo-lighter' :
            'group-hover:text-vedic-yellow-warm';

    const gradient = isSecondary ? 'from-secondary/20' :
        isIndigo ? 'from-vedic-indigo-main/20' :
            'from-vedic-yellow-warm/20';

    const textButton = isSecondary ? 'text-secondary' :
        isIndigo ? 'text-vedic-indigo-main dark:text-vedic-indigo-lighter' :
            'text-vedic-yellow-warm';

    return (
        <Link to={link} className="card-hover sirorekha-card flex flex-col h-full bg-surface-light dark:bg-surface-dark rounded-xl md:rounded-3xl p-1 shadow-soft relative group">
            <div className={cn("absolute inset-0 bg-gradient-to-b to-transparent rounded-xl md:rounded-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-300", gradient)}></div>
            <div className={cn("bg-white dark:bg-surface-dark/95 h-full rounded-lg md:rounded-[1.3rem] p-4 md:p-6 flex flex-row md:flex-col items-center md:items-start relative z-10 border border-transparent transition-colors gap-3 md:gap-0", groupHoverBorder)}>
                <div className="flex md:w-full justify-between items-start md:mb-6">
                    <div className={cn("p-2 md:p-3.5 rounded-lg md:rounded-2xl shadow-sm group-hover:scale-110 transition-transform duration-300", bgIcon)}>
                        <span className="material-symbols-outlined text-xl md:text-3xl">{icon}</span>
                    </div>
                    <div className={cn("hidden md:block bg-gray-50 dark:bg-white/5 rounded-full p-2 transition-colors duration-300", groupHoverIcon)}>
                        <span className="material-symbols-outlined text-gray-400 group-hover:text-inherit transition-colors text-xl">arrow_outward</span>
                    </div>
                </div>
                <div className="flex-1 md:w-full">
                    <h4 className={cn("text-xl md:text-2xl font-bold font-sans text-vedic-indigo-darkest dark:text-white md:mb-3 transition-colors", groupHoverTitle)}>{title}</h4>
                    <p className="hidden md:block text-lg text-text-muted-light dark:text-text-muted-dark academic-serif leading-relaxed font-medium">
                        {description}
                    </p>
                </div>
                <div className={cn("md:hidden text-text-muted-light dark:text-text-muted-dark transition-colors", groupHoverTitle)}>
                    <span className="material-symbols-outlined text-xl">arrow_forward_ios</span>
                </div>
                <div className={cn("hidden md:flex mt-4 pt-4 border-t border-gray-100 dark:border-white/5 w-full items-center gap-2 text-xs font-bold uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity transform translate-y-2 group-hover:translate-y-0", textButton)}>
                    View Details
                </div>
            </div>
        </Link>
    );
};
