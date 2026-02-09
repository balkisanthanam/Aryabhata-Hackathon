import { LatexRenderer } from '../common/LatexRenderer';


interface QuestionViewProps {
    question: any;
}

export const QuestionView = ({ question }: QuestionViewProps) => {
    return (
        <div className="flex flex-col">
            <div className="bg-gradient-to-r from-gray-50 to-white dark:from-slate-800 dark:to-slate-800/50 p-6 border-b border-gray-200 dark:border-indigo-900/50">
                <div className="flex items-start gap-4">
                    <span className="bg-primary text-white font-mono text-xs font-bold px-2.5 py-1.5 rounded-md mt-1 shadow-sm border border-primary-light">
                        {question.question_id}
                    </span>
                    <div className="prose dark:prose-invert max-w-none text-gray-800 dark:text-gray-200">
                        <div className="mb-0 text-lg leading-snug font-medium font-serif">
                            <LatexRenderer content={question.question_text} />
                        </div>
                    </div>
                </div>
            </div>

            {question.figure && (
                <div className="p-8 flex justify-center bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-indigo-900/50">
                    <div className="relative w-full max-w-4xl bg-white dark:bg-slate-800 rounded-xl border border-gray-200 dark:border-slate-700 p-4 shadow-inner flex items-center justify-center">
                        {/* Debug info hidden */}
                        <img
                            src={question.figure.url}
                            alt={question.figure.caption}
                            className="max-h-[500px] object-contain dark:invert-[.85]"
                            onError={(e) => {
                                e.currentTarget.style.display = 'none';
                                e.currentTarget.nextElementSibling?.classList.remove('hidden');
                            }}
                        />
                        <div className="hidden flex flex-col items-center justify-center h-48 text-gray-400">
                            <span className="material-symbols-outlined text-4xl mb-2">image</span>
                            <span className="text-sm">Diagram: {question.figure.caption}</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
