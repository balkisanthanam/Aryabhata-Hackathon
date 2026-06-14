import { useCallback, useRef, useState } from 'react';
import clsx from 'clsx';

interface ImageUploadZoneProps {
    label: string;
    description: string;
    files: File[];
    onFilesChange: (files: File[]) => void;
    maxFiles?: number;
    required?: boolean;
}

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'application/pdf'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

export const ImageUploadZone = ({
    label,
    description,
    files,
    onFilesChange,
    maxFiles = 5,
    required = false,
}: ImageUploadZoneProps) => {
    const [isDragOver, setIsDragOver] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const validateAndAddFiles = useCallback(
        (newFiles: FileList | File[]) => {
            setError(null);
            const incoming = Array.from(newFiles);
            const totalCount = files.length + incoming.length;

            if (totalCount > maxFiles) {
                setError(`Maximum ${maxFiles} files allowed. You have ${files.length}, trying to add ${incoming.length}.`);
                return;
            }

            for (const file of incoming) {
                if (!ACCEPTED_TYPES.includes(file.type)) {
                    setError(`${file.name}: Invalid format. Only JPG, PNG, PDF accepted.`);
                    return;
                }
                if (file.size > MAX_FILE_SIZE) {
                    setError(`${file.name}: File too large (max 10 MB).`);
                    return;
                }
            }

            onFilesChange([...files, ...incoming]);
        },
        [files, maxFiles, onFilesChange]
    );

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setIsDragOver(false);
            if (e.dataTransfer.files.length > 0) {
                validateAndAddFiles(e.dataTransfer.files);
            }
        },
        [validateAndAddFiles]
    );

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(true);
    };

    const handleDragLeave = () => setIsDragOver(false);

    const handleClick = () => inputRef.current?.click();

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            validateAndAddFiles(e.target.files);
        }
        // Reset so the same file can be re-selected
        e.target.value = '';
    };

    const removeFile = (index: number) => {
        const updated = files.filter((_, i) => i !== index);
        onFilesChange(updated);
    };

    const getPreviewUrl = (file: File): string | null => {
        if (file.type.startsWith('image/')) {
            return URL.createObjectURL(file);
        }
        return null;
    };

    return (
        <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    {label}
                </label>
                {required && <span className="text-red-500 text-xs">*</span>}
                <span className="text-xs text-slate-400">
                    ({files.length}/{maxFiles})
                </span>
            </div>

            {/* Drop zone */}
            {files.length < maxFiles && (
                <div
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onClick={handleClick}
                    className={clsx(
                        'border-2 border-dashed rounded-xl p-6 sm:p-8 flex flex-col items-center justify-center gap-2 cursor-pointer transition-all min-h-[120px]',
                        isDragOver
                            ? 'border-primary bg-primary/10 dark:bg-primary/20'
                            : 'border-gray-300 dark:border-gray-700 hover:border-primary hover:bg-primary/5 dark:hover:bg-primary/10 bg-slate-50/50 dark:bg-slate-800/30'
                    )}
                >
                    <div className="bg-white dark:bg-slate-700 p-2.5 rounded-full shadow-sm border border-gray-200 dark:border-gray-600">
                        <span className="material-symbols-outlined text-2xl text-primary">cloud_upload</span>
                    </div>
                    <div className="text-center">
                        <p className="text-slate-700 dark:text-gray-200 font-medium text-sm sm:text-base">{description}</p>
                        <p className="text-slate-400 text-xs mt-1">JPG, PNG, PDF • Max 10 MB each</p>
                    </div>
                </div>
            )}

            <input
                ref={inputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.pdf"
                multiple
                onChange={handleInputChange}
                className="hidden"
            />

            {/* Error message */}
            {error && (
                <p className="text-red-500 dark:text-red-400 text-xs flex items-center gap-1">
                    <span className="material-symbols-outlined text-sm">error</span>
                    {error}
                </p>
            )}

            {/* File previews */}
            {files.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-1">
                    {files.map((file, i) => {
                        const previewUrl = getPreviewUrl(file);
                        return (
                            <div
                                key={`${file.name}-${i}`}
                                className="relative group bg-white dark:bg-slate-800 border border-gray-200 dark:border-gray-700 rounded-lg p-1.5 flex items-center gap-2 max-w-[200px]"
                            >
                                {previewUrl ? (
                                    <img
                                        src={previewUrl}
                                        alt={file.name}
                                        className="w-10 h-10 object-cover rounded"
                                        onLoad={() => URL.revokeObjectURL(previewUrl)}
                                    />
                                ) : (
                                    <div className="w-10 h-10 bg-red-50 dark:bg-red-900/20 rounded flex items-center justify-center">
                                        <span className="material-symbols-outlined text-red-500 text-lg">picture_as_pdf</span>
                                    </div>
                                )}
                                <span className="text-xs text-slate-600 dark:text-slate-300 truncate max-w-[100px]">
                                    {file.name}
                                </span>
                                <button
                                    onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                                    className="ml-auto p-0.5 rounded-full hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                                    title="Remove"
                                >
                                    <span className="material-symbols-outlined text-sm text-red-500">close</span>
                                </button>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};
