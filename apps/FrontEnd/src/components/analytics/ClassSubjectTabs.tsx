import { Standing, standingConfig, Subject } from '../../data/perfCompassData';

interface ClassSubjectTabsProps {
    classes: string[];
    subjects: Subject[];
    selectedClass: string;
    selectedSubject: string;
    onClassChange: (cls: string) => void;
    onSubjectChange: (sub: string) => void;
}

export const ClassSubjectTabs = ({
    classes,
    subjects,
    selectedClass,
    selectedSubject,
    onClassChange,
    onSubjectChange,
}: ClassSubjectTabsProps) => {
    return (
        <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-4 lg:p-6 border border-gray-200 dark:border-indigo-900/50">
            <div className="flex flex-col gap-5">
                {/* Class Tabs */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    <span className="text-sm font-bold text-text-muted-light dark:text-indigo-300 w-20 uppercase tracking-wide">Class</span>
                    <div className="flex flex-wrap gap-2">
                        {classes.map(cls => (
                            <button
                                key={cls}
                                onClick={() => onClassChange(cls)}
                                className={`px-5 py-2 rounded-lg border text-sm font-medium transition-all
                                    ${selectedClass === cls
                                        ? 'bg-primary text-white border-primary shadow-lg shadow-primary/30'
                                        : 'border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary hover:text-primary'
                                    }`}
                            >
                                {cls}th
                            </button>
                        ))}
                    </div>
                </div>

                {/* Subject Tabs */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    <span className="text-sm font-bold text-text-muted-light dark:text-indigo-300 w-20 uppercase tracking-wide">Subject</span>
                    <div className="flex flex-wrap gap-2">
                        {subjects.map(sub => {
                            const isActive = selectedSubject === sub.name;
                            const config = standingConfig[sub.studentStanding as Standing];
                            return (
                                <button
                                    key={sub.name}
                                    onClick={() => onSubjectChange(sub.name)}
                                    className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all flex items-center gap-2
                                        ${isActive
                                            ? 'bg-primary text-white border-primary shadow-lg shadow-primary/30'
                                            : 'border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary hover:text-primary'
                                        }`}
                                >
                                    {sub.name}
                                    <span
                                        className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                                        style={{ backgroundColor: isActive ? 'rgba(255,255,255,0.7)' : config.color }}
                                        title={config.label}
                                    />
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>
        </section>
    );
};
