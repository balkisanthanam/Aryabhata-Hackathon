import { useState, useCallback } from 'react';
import clsx from 'clsx';

interface StudentWorkViewerProps {
    studentWorkUrls: string[];
    problemImageUrls: string[];
}

/**
 * Collapsible panel showing uploaded student work and problem images.
 * Images are lazy-loaded — no bandwidth cost until the user expands the section.
 * Clicking a thumbnail opens a lightbox overlay for detailed viewing.
 */
export const StudentWorkViewer = ({ studentWorkUrls, problemImageUrls }: StudentWorkViewerProps) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

    const hasStudentWork = studentWorkUrls.length > 0;
    const hasProblemImages = problemImageUrls.length > 0;

    if (!hasStudentWork && !hasProblemImages) return null;

    const totalImages = studentWorkUrls.length + problemImageUrls.length;

    return (
        <>
            <div className="bg-white/80 dark:bg-surface-dark/80 backdrop-blur-sm rounded-xl border border-gray-200 dark:border-indigo-900/50 shadow-sm overflow-hidden">
                {/* Toggle Header */}
                <button
                    onClick={() => setIsExpanded(prev => !prev)}
                    className="w-full flex items-center justify-between p-4 sm:p-5 hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors text-left group"
                >
                    <div className="flex items-center gap-3">
                        <span className="material-symbols-outlined text-primary text-xl">
                            photo_library
                        </span>
                        <div>
                            <h3 className="text-slate-900 dark:text-white font-bold text-sm sm:text-base">
                                View Uploaded Work
                            </h3>
                            <p className="text-slate-400 dark:text-slate-500 text-xs mt-0.5">
                                {totalImages} image{totalImages !== 1 ? 's' : ''} uploaded
                                {hasProblemImages && hasStudentWork && (
                                    <> — {problemImageUrls.length} problem, {studentWorkUrls.length} solution</>
                                )}
                            </p>
                        </div>
                    </div>
                    <span
                        className={clsx(
                            'material-symbols-outlined text-slate-400 dark:text-slate-500 transition-transform duration-300',
                            isExpanded && 'rotate-180'
                        )}
                    >
                        expand_more
                    </span>
                </button>

                {/* Expandable Content */}
                <div
                    className={clsx(
                        'grid transition-all duration-300 ease-in-out',
                        isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
                    )}
                >
                    <div className="overflow-hidden">
                        <div className="px-4 sm:px-5 pb-4 sm:pb-5 space-y-5">
                            {/* Problem Statement Images */}
                            {hasProblemImages && (
                                <ImageSection
                                    title="Problem Statement"
                                    icon="description"
                                    urls={problemImageUrls}
                                    isExpanded={isExpanded}
                                    onImageClick={setLightboxSrc}
                                />
                            )}

                            {/* Student Work Images */}
                            {hasStudentWork && (
                                <ImageSection
                                    title="My Work"
                                    icon="draw"
                                    urls={studentWorkUrls}
                                    isExpanded={isExpanded}
                                    onImageClick={setLightboxSrc}
                                />
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Lightbox Overlay */}
            {lightboxSrc && (
                <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
            )}
        </>
    );
};

// ─── Sub-components ────────────────────────────────────────────────

interface ImageSectionProps {
    title: string;
    icon: string;
    urls: string[];
    isExpanded: boolean;
    onImageClick: (src: string) => void;
}

const ImageSection = ({ title, icon, urls, isExpanded, onImageClick }: ImageSectionProps) => (
    <div>
        <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
            <span className="material-symbols-outlined text-base">{icon}</span>
            {title}
            <span className="font-normal normal-case tracking-normal text-slate-400 dark:text-slate-500">
                ({urls.length} page{urls.length !== 1 ? 's' : ''})
            </span>
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 sm:gap-3">
            {urls.map((url, idx) => (
                <ImageThumbnail
                    key={idx}
                    src={url}
                    alt={`${title} page ${idx + 1}`}
                    pageNumber={idx + 1}
                    shouldLoad={isExpanded}
                    onClick={() => onImageClick(url)}
                />
            ))}
        </div>
    </div>
);

interface ImageThumbnailProps {
    src: string;
    alt: string;
    pageNumber: number;
    shouldLoad: boolean;
    onClick: () => void;
}

const ImageThumbnail = ({ src, alt, pageNumber, shouldLoad, onClick }: ImageThumbnailProps) => {
    const [loaded, setLoaded] = useState(false);
    const [error, setError] = useState(false);

    return (
        <button
            onClick={onClick}
            className="relative aspect-[3/4] rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-100 dark:bg-slate-800 hover:ring-2 hover:ring-primary/50 hover:shadow-md transition-all group cursor-zoom-in"
        >
            {/* Loading skeleton */}
            {!loaded && !error && shouldLoad && (
                <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-gray-300 dark:border-gray-600 border-t-primary rounded-full animate-spin" />
                </div>
            )}

            {/* Error state */}
            {error && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-slate-400 dark:text-slate-500">
                    <span className="material-symbols-outlined text-2xl">broken_image</span>
                    <span className="text-[10px]">Image expired</span>
                </div>
            )}

            {/* Actual image — only rendered when the panel is expanded */}
            {shouldLoad && !error && (
                <img
                    src={src}
                    alt={alt}
                    loading="lazy"
                    onLoad={() => setLoaded(true)}
                    onError={() => setError(true)}
                    className={clsx(
                        'w-full h-full object-cover transition-opacity duration-300',
                        loaded ? 'opacity-100' : 'opacity-0'
                    )}
                />
            )}

            {/* Page badge */}
            <span className="absolute bottom-1.5 right-1.5 bg-black/60 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-md backdrop-blur-sm">
                {pageNumber}
            </span>

            {/* Hover zoom hint */}
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 dark:group-hover:bg-white/5 transition-colors flex items-center justify-center">
                <span className="material-symbols-outlined text-white text-2xl opacity-0 group-hover:opacity-80 transition-opacity drop-shadow-lg">
                    zoom_in
                </span>
            </div>
        </button>
    );
};

interface LightboxProps {
    src: string;
    onClose: () => void;
}

const Lightbox = ({ src, onClose }: LightboxProps) => {
    // Close on Escape
    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        },
        [onClose]
    );

    return (
        <div
            role="dialog"
            aria-modal="true"
            tabIndex={0}
            onKeyDown={handleKeyDown}
            onClick={onClose}
            className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 sm:p-8 animate-in fade-in duration-200"
        >
            {/* Close button */}
            <button
                onClick={onClose}
                className="absolute top-4 right-4 z-10 p-2 bg-black/50 hover:bg-black/70 rounded-full text-white transition-colors"
                aria-label="Close image viewer"
            >
                <span className="material-symbols-outlined text-2xl">close</span>
            </button>

            {/* Full-size image */}
            <img
                src={src}
                alt="Enlarged view"
                onClick={e => e.stopPropagation()}
                className="max-w-full max-h-full object-contain rounded-lg shadow-2xl animate-in zoom-in-95 duration-200"
            />
        </div>
    );
};
