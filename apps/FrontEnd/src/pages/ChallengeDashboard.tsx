import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/layout/Navbar';

interface Question {
    id: number;
    question: string;
    type: 'mcq' | 'subjective';
    options?: string[];
    correctAnswer?: number;
    marks?: number;
    imageUrl?: string;
    imageUrls?: string[];
    chapter?: string;
    subTopic?: string;
}

interface EvaluationResult {
    questionId: string;
    question: string;
    studentAnswer: string;
    score: number;
    maxMarks: number;
    feedback: string;
    expectedAnswer?: string;
    missedPoints?: string[];
}

interface SavedPaper {
    id: number;
    subject: string;
    difficulty: string;
    questionCount: number;
    questions: Question[];
    createdAt: Date;
}

export const ChallengeDashboard = () => {
    const [subject, setSubject] = useState<string>('Science');
    const [difficulty, setDifficulty] = useState<string>('Medium');
    const [numQuestions, setNumQuestions] = useState<string>('10');
    const [questions, setQuestions] = useState<Question[]>([]);
    const [isGenerated, setIsGenerated] = useState(false);
    const [savedPapers, setSavedPapers] = useState<SavedPaper[]>([]);
    const [selectedPaper, setSelectedPaper] = useState<SavedPaper | null>(null);
    const [uploadedImage, setUploadedImage] = useState<string | null>(null);
    const [showUploadSection, setShowUploadSection] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
    const [_blobUrls, setBlobUrls] = useState<string[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [isLoadingPapers, setIsLoadingPapers] = useState(false);
    const [evaluationResults, setEvaluationResults] = useState<Record<string, EvaluationResult>>({});
    const [evalProgress, setEvalProgress] = useState(0);
    const [evalStatus, setEvalStatus] = useState('');

    const subjects = ['Science', 'Social Studies', 'Hindi'];
    const difficulties = ['Easy', 'Medium', 'Difficult'];
    const questionCounts = ['10', '15', '20'];

    useEffect(() => {
        const fetchPapers = async () => {
            setIsLoadingPapers(true);
            try {
                const { listPapers, getBlobContent } = await import('../utils/azureBlobService');
                console.log('Fetching papers from Azure...');
                const urls = await listPapers();
                console.log('Found paper URLs:', urls);

                const paperPromises = urls.map(url => {
                    console.log('Fetching content for:', url);
                    return getBlobContent(url);
                });
                const papers = await Promise.all(paperPromises);
                console.log('Successfully fetched papers:', papers.length);

                // Sort by date (descending)
                const sortedPapers = papers.sort((a, b) =>
                    new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
                );

                setSavedPapers(sortedPapers);
            } catch (err) {
                console.error('Failed to fetch past papers:', err);
            } finally {
                setIsLoadingPapers(false);
            }
        };

        fetchPapers();
    }, []);

    const generateQuestions = async () => {
        setIsGenerating(true);
        setError(null);
        try {
            // const response = await fetch('http://localhost:7071/api/generate-questions', {
            const response = await fetch('https://questiongenerationfunction.azurewebsites.net/api/generate-questions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subject,
                    difficulty,
                    numQuestions: parseInt(numQuestions),
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to generate questions');
            }

            const data = await response.json();
            const fetchedQuestions: Question[] = data.questions;

            // Save to history
            const newPaper: SavedPaper = {
                id: Date.now(),
                subject,
                difficulty,
                questionCount: parseInt(numQuestions),
                questions: fetchedQuestions,
                createdAt: new Date(),
            };

            // Save to Azure for persistence (used by evaluation backend)
            try {
                const { uploadJsonToBlob } = await import('../utils/azureBlobService');
                await uploadJsonToBlob(newPaper, `${newPaper.id}.json`);
                console.log('Paper saved to Azure:', newPaper.id);
            } catch (blobErr) {
                console.warn('Failed to save paper to blob storage:', blobErr);
                // We don't throw here to allow the user to still use the paper in memory
            }

            setSavedPapers(prev => [newPaper, ...prev]);
            setQuestions(fetchedQuestions);
            setIsGenerated(true);
        } catch (err: any) {
            console.error('Error generating questions:', err);
            setError(err.message || 'An error occurred while generating questions');
        } finally {
            setIsGenerating(false);
        }
    };

    const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (files && files.length > 0) {
            const newFiles = Array.from(files);
            setUploadedFiles(prev => [...prev, ...newFiles]);

            // For preview purposes, we only show the first image if it's an image
            if (newFiles[0].type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onloadend = () => {
                    setUploadedImage(reader.result as string);
                };
                reader.readAsDataURL(newFiles[0]);
            } else {
                setUploadedImage(null); // No preview for non-image files like PDF
            }
        }
    };

    const handleUploadAndEvaluate = async () => {
        if (uploadedFiles.length === 0) return;

        setIsUploading(true);
        setError(null);
        try {
            // Step 1: Upload to Azure Blob Storage
            const { uploadFilesToBlob } = await import('../utils/azureBlobService');
            const urls = await uploadFilesToBlob(uploadedFiles);
            setBlobUrls(urls);
            console.log('Uploaded to Azure:', urls);

            // Start simulated progress
            setEvalProgress(10);
            setEvalStatus('Analyzing answer sheets...');

            const progressInterval = setInterval(() => {
                setEvalProgress(prev => {
                    if (prev < 30) {
                        setEvalStatus('Handwriting Analysis (OCR)...');
                        return prev + 2;
                    }
                    if (prev < 60) {
                        setEvalStatus('Segmenting answers...');
                        return prev + 1.5;
                    }
                    if (prev < 90) {
                        setEvalStatus('AI Evaluation & Grading...');
                        return prev + 0.5;
                    }
                    if (prev < 98) {
                        setEvalStatus('Finalizing results...');
                        return prev + 0.1;
                    }
                    return prev;
                });
            }, 500);

            // Step 2: Call Evaluation API
            // const response = await fetch('http://localhost:7071/api/evaluate-sheet', {
            const response = await fetch('https://questiongenerationfunction.azurewebsites.net/api/evaluate-sheet', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    paperId: selectedPaper?.id,
                    blobUrls: urls
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to evaluate answers');
            }

            if (progressInterval) clearInterval(progressInterval);
            const result = await response.json();
            setEvalProgress(100);
            setEvalStatus('Completed');
            // Handle evaluation result
            console.log('Evaluation result:', result);

            if (result.details && result.details.evaluationResults) {
                const resultsMap: Record<string, EvaluationResult> = {};
                result.details.evaluationResults.forEach((evalItem: any) => {
                    // Normalize keys and coerce types to avoid UI mismatches
                    const rawQid = evalItem.questionId ?? evalItem.id ?? evalItem.qid ?? null;
                    const qid = String(rawQid ?? '');
                    if (!qid) return;

                    // Determine score robustly
                    let score = 0;
                    if (evalItem.score !== undefined && evalItem.score !== null) {
                        score = Number(evalItem.score);
                    } else if (evalItem.sc !== undefined && evalItem.sc !== null) {
                        score = Number(evalItem.sc);
                    } else if (evalItem.score && typeof evalItem.score.toString === 'function') {
                        score = Number(evalItem.score.toString());
                    }

                    // Determine maxMarks robustly
                    let maxMarks = 0;
                    if (evalItem.maxMarks !== undefined && evalItem.maxMarks !== null) {
                        maxMarks = Number(evalItem.maxMarks);
                    } else if (evalItem.max_marks !== undefined && evalItem.max_marks !== null) {
                        maxMarks = Number(evalItem.max_marks);
                    } else if (evalItem.marks !== undefined && evalItem.marks !== null) {
                        maxMarks = Number(evalItem.marks);
                    } else if (evalItem.max !== undefined && evalItem.max !== null) {
                        maxMarks = Number(evalItem.max);
                    }

                    // If maxMarks is not provided or zero, fallback to question definition
                    if ((!maxMarks || maxMarks <= 0) && questions && questions.length > 0) {
                        const qDef = questions.find((qq) => String(qq.id) === qid);
                        if (qDef && qDef.marks) {
                            maxMarks = Number(qDef.marks) || 0;
                        }
                    }
                    // final fallback
                    if (!maxMarks || maxMarks <= 0) maxMarks = 1;

                    const feedback = evalItem.feedback ?? evalItem.feedbackText ?? '';
                    const expectedAnswer = evalItem.expectedAnswer ?? evalItem.expected_answer ?? '';
                    let missedPoints: string[] = [];
                    if (Array.isArray(evalItem.missedPoints)) missedPoints = evalItem.missedPoints;
                    else if (Array.isArray(evalItem.missed_points)) missedPoints = evalItem.missed_points;
                    else if (typeof evalItem.missedPoints === 'string') missedPoints = evalItem.missedPoints.split(/\r?\n|;|,/).map((s: string) => s.trim()).filter(Boolean);
                    else if (typeof evalItem.missed_points === 'string') missedPoints = evalItem.missed_points.split(/\r?\n|;|,/).map((s: string) => s.trim()).filter(Boolean);

                    resultsMap[qid] = {
                        questionId: qid,
                        question: evalItem.question ?? '',
                        studentAnswer: evalItem.studentAnswer ?? evalItem.student_answer ?? '',
                        score: isNaN(score) ? 0 : score,
                        maxMarks: isNaN(maxMarks) ? 0 : maxMarks,
                        feedback,
                        expectedAnswer,
                        missedPoints
                    };
                });
                setEvaluationResults(resultsMap);
            }

            // Clear progress after a short delay
            setTimeout(() => {
                setEvalProgress(0);
                setEvalStatus('');
            }, 2000);
        } catch (err: any) {
            setEvalProgress(0);
            setEvalStatus('');
            console.error('Error processing answer sheet:', err);
            setError(err.message || 'An error occurred while uploading and evaluating');
        } finally {
            setIsUploading(false);
        }
    };

    const handleSelectPaper = (paper: SavedPaper) => {
        setSelectedPaper(paper);
        setQuestions(paper.questions); // Populate questions for display
        setShowUploadSection(true);
        setUploadedImage(null);
        setUploadedFiles([]);
        setBlobUrls([]);
        setEvaluationResults({});
    };

    const isFormValid = subject && difficulty && numQuestions;

    return (
        <div className="bg-background-light dark:bg-background-dark text-text-main-light dark:text-text-main-dark min-h-screen font-sans flex flex-col items-center">
            <Navbar />

            <main className="w-full max-w-6xl space-y-6 py-4 lg:py-8 px-4 sm:px-6 lg:px-8">
                {/* Header Section */}
                <div className="flex flex-col gap-4">
                    <div>
                        <Link to="/" className="flex items-center text-sm text-text-muted-light dark:text-text-muted-dark hover:text-primary mb-2 transition-colors font-medium">
                            <span className="material-symbols-outlined text-sm mr-1">arrow_back</span> Back to Dashboard
                        </Link>
                        <h1 className="text-2xl lg:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
                            <span className="p-2 lg:p-2.5 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-xl shadow-sm border border-red-200 dark:border-red-800">
                                <span className="material-symbols-outlined text-2xl lg:text-3xl">quiz</span>
                            </span>
                            Challenge Dashboard
                        </h1>
                        <p className="text-text-muted-light dark:text-text-muted-dark mt-2 ml-14 lg:ml-16 max-w-xl text-sm lg:text-base">Create custom question papers to test your knowledge</p>
                    </div>
                </div>

                {/* Main Grid: Configuration and Saved Papers Side by Side */}
                {!showUploadSection && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Configuration Section */}
                        <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-6 lg:p-8 border border-gray-200 dark:border-indigo-900/50">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
                                <span className="material-symbols-outlined text-primary">settings</span>
                                Configure Your Test
                            </h2>

                            <div className="space-y-4">
                                {/* Subject Selection */}
                                <div className="space-y-2">
                                    <label className="block text-sm font-bold text-text-muted-light dark:text-indigo-300 uppercase tracking-wide">
                                        Select Subject
                                    </label>
                                    <select
                                        value={subject}
                                        onChange={(e) => setSubject(e.target.value)}
                                        className="w-full px-4 py-3 rounded-lg border border-gray-200 dark:border-indigo-800 bg-white dark:bg-indigo-950 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all text-sm font-medium"
                                    >
                                        <option value="">Choose a subject...</option>
                                        {subjects.map((sub) => (
                                            <option key={sub} value={sub}>{sub}</option>
                                        ))}
                                    </select>
                                </div>

                                {/* Difficulty Selection */}
                                <div className="space-y-2">
                                    <label className="block text-sm font-bold text-text-muted-light dark:text-indigo-300 uppercase tracking-wide">
                                        Difficulty Level
                                    </label>
                                    <select
                                        value={difficulty}
                                        onChange={(e) => setDifficulty(e.target.value)}
                                        className="w-full px-4 py-3 rounded-lg border border-gray-200 dark:border-indigo-800 bg-white dark:bg-indigo-950 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all text-sm font-medium"
                                    >
                                        <option value="">Choose difficulty...</option>
                                        {difficulties.map((diff) => (
                                            <option key={diff} value={diff}>{diff}</option>
                                        ))}
                                    </select>
                                </div>

                                {/* Number of Questions */}
                                <div className="space-y-2">
                                    <label className="block text-sm font-bold text-text-muted-light dark:text-indigo-300 uppercase tracking-wide">
                                        Number of Questions
                                    </label>
                                    <select
                                        value={numQuestions}
                                        onChange={(e) => setNumQuestions(e.target.value)}
                                        className="w-full px-4 py-3 rounded-lg border border-gray-200 dark:border-indigo-800 bg-white dark:bg-indigo-950 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all text-sm font-medium"
                                    >
                                        <option value="">Choose count...</option>
                                        {questionCounts.map((count) => (
                                            <option key={count} value={count}>{count} Questions</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Error Message */}
                            {error && (
                                <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-start gap-3 text-red-600 dark:text-red-400">
                                    <span className="material-symbols-outlined">error</span>
                                    <p className="text-sm font-medium">{error}</p>
                                </div>
                            )}

                            {/* Generate Button */}
                            <div className="mt-6">
                                <button
                                    onClick={generateQuestions}
                                    disabled={!isFormValid || isGenerating}
                                    className={`w-full px-6 py-4 rounded-xl font-bold text-base transition-all shadow-lg flex items-center justify-center gap-3 ${isFormValid && !isGenerating
                                        ? 'bg-primary text-white hover:bg-indigo-700 hover:shadow-xl hover:scale-105 cursor-pointer'
                                        : 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed opacity-50'
                                        }`}
                                >
                                    {isGenerating ? (
                                        <>
                                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                            <span>Generating Questions...</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="material-symbols-outlined text-xl">auto_awesome</span>
                                            <span>Generate Question Paper</span>
                                        </>
                                    )}
                                </button>
                            </div>
                        </section>

                        {/* Saved Papers Section */}
                        <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-6 lg:p-8 border border-gray-200 dark:border-indigo-900/50">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
                                <span className="material-symbols-outlined text-primary">history</span>
                                Previously Generated Papers
                            </h2>

                            {isLoadingPapers ? (
                                <div className="flex flex-col items-center justify-center py-12 text-center">
                                    <div className="w-10 h-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin mb-4" />
                                    <p className="text-gray-500 dark:text-indigo-400 text-sm font-medium">
                                        Loading past papers...
                                    </p>
                                </div>
                            ) : savedPapers.length > 0 ? (
                                <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
                                    {savedPapers.map((paper) => (
                                        <div
                                            key={paper.id}
                                            className="bg-gray-50 dark:bg-indigo-950/50 rounded-xl p-4 border border-gray-200 dark:border-indigo-900 hover:border-primary dark:hover:border-primary transition-all cursor-pointer group"
                                            onClick={() => handleSelectPaper(paper)}
                                        >
                                            <div className="flex items-start justify-between mb-3">
                                                <div className="flex-1">
                                                    <h3 className="font-bold text-gray-900 dark:text-white group-hover:text-primary transition-colors">
                                                        {paper.subject}
                                                    </h3>
                                                    <p className="text-xs text-text-muted-light dark:text-indigo-400 mt-1">
                                                        {new Date(paper.createdAt).toLocaleDateString('en-IN', {
                                                            day: 'numeric',
                                                            month: 'short',
                                                            year: 'numeric',
                                                            hour: '2-digit',
                                                            minute: '2-digit'
                                                        })}
                                                    </p>
                                                </div>
                                                <span className="material-symbols-outlined text-gray-400 dark:text-indigo-500 group-hover:text-primary transition-colors">
                                                    arrow_forward
                                                </span>
                                            </div>
                                            <div className="flex gap-2 flex-wrap">
                                                <span className="px-2 py-1 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded text-xs font-semibold border border-amber-200 dark:border-amber-800">
                                                    {paper.difficulty}
                                                </span>
                                                <span className="px-2 py-1 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded text-xs font-semibold border border-indigo-200 dark:border-indigo-800">
                                                    {paper.questionCount} Qs
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center py-12 text-center">
                                    <div className="w-16 h-16 bg-gray-100 dark:bg-indigo-900/30 rounded-full flex items-center justify-center mb-4">
                                        <span className="material-symbols-outlined text-gray-400 dark:text-indigo-500 text-3xl">folder_open</span>
                                    </div>
                                    <p className="text-gray-500 dark:text-indigo-400 text-sm font-medium">
                                        No papers generated yet
                                    </p>
                                    <p className="text-gray-400 dark:text-indigo-500 text-xs mt-1">
                                        Generate your first question paper to get started
                                    </p>
                                </div>
                            )}
                        </section>
                    </div>
                )}

                {/* Info Card */}
                {!isGenerated && !showUploadSection && (
                    <div className="bg-gradient-to-br from-secondary/20 to-amber-100 dark:from-amber-900/30 dark:to-indigo-900/20 rounded-2xl p-6 border border-amber-200 dark:border-amber-800/50 shadow-lg shadow-amber-500/5">
                        <div className="flex items-start gap-3">
                            <div className="p-2 bg-white dark:bg-amber-900/50 rounded-full shadow-sm">
                                <span className="material-symbols-outlined text-secondary text-xl">lightbulb</span>
                            </div>
                            <div>
                                <h4 className="font-bold text-gray-900 dark:text-white text-sm">How It Works</h4>
                                <p className="text-xs text-text-main-light dark:text-indigo-100 mt-1 leading-relaxed font-medium">
                                    Select your preferred <span className="text-primary font-bold">subject</span>, <span className="text-primary font-bold">difficulty level</span>, and <span className="text-primary font-bold">number of questions</span> to generate a customized question paper. Perfect for practice and self-assessment!
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {/* Answer Sheet Upload Section */}
                {showUploadSection && selectedPaper && (
                    <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-6 lg:p-8 border border-gray-200 dark:border-indigo-900/50">
                        <div className="flex items-center justify-between mb-6">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <span className="material-symbols-outlined text-primary">upload_file</span>
                                Upload Answer Sheet
                            </h2>
                            <button
                                onClick={() => {
                                    setShowUploadSection(false);
                                    setSelectedPaper(null);
                                    setUploadedImage(null);
                                    setUploadedFiles([]);
                                    setBlobUrls([]);
                                }}
                                className="px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-all text-sm font-semibold"
                            >
                                Back to Papers
                            </button>
                        </div>

                        {/* Selected Paper Info */}
                        <div className="bg-indigo-50 dark:bg-indigo-950/50 rounded-xl p-4 mb-6 border border-indigo-200 dark:border-indigo-900">
                            <div className="flex items-center gap-4">
                                <span className="material-symbols-outlined text-primary text-3xl">description</span>
                                <div className="flex-1">
                                    <h3 className="font-bold text-gray-900 dark:text-white">{selectedPaper.subject}</h3>
                                    <div className="flex gap-3 mt-1 text-sm text-text-muted-light dark:text-indigo-400">
                                        <span>{selectedPaper.difficulty}</span>
                                        <span>•</span>
                                        <span>{selectedPaper.questionCount} Questions</span>
                                        <span>•</span>
                                        <span>{new Date(selectedPaper.createdAt).toLocaleDateString('en-IN')}</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Upload Area */}
                        <div className="border-2 border-dashed border-gray-300 dark:border-indigo-800 rounded-xl p-8 text-center hover:border-primary dark:hover:border-primary transition-all">
                            <div className="space-y-6">
                                <label className="cursor-pointer block">
                                    <input
                                        type="file"
                                        accept="image/*,.pdf"
                                        multiple
                                        onChange={handleFileUpload}
                                        className="hidden"
                                    />
                                    <div className="flex flex-col items-center gap-4">
                                        <div className="w-16 h-16 bg-indigo-100 dark:bg-indigo-900/30 rounded-full flex items-center justify-center">
                                            <span className="material-symbols-outlined text-primary text-3xl">cloud_upload</span>
                                        </div>
                                        <div>
                                            <p className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
                                                Click to select answer sheets (Images or PDF)
                                            </p>
                                            <p className="text-sm text-text-muted-light dark:text-indigo-400">
                                                Supports JPG, PNG, or PDF (Select multiple files)
                                            </p>
                                        </div>
                                        <div className="px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-indigo-700 transition-all shadow-lg inline-block">
                                            Browse Files
                                        </div>
                                    </div>
                                </label>

                                {uploadedFiles.length > 0 && (
                                    <div className="mt-4 p-4 bg-gray-50 dark:bg-indigo-950 rounded-xl border border-gray-200 dark:border-indigo-800">
                                        <h4 className="text-sm font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                                            <span className="material-symbols-outlined text-sm">attach_file</span>
                                            Selected Files ({uploadedFiles.length})
                                        </h4>
                                        <ul className="text-left space-y-2 mb-6">
                                            {uploadedFiles.map((file, i) => (
                                                <li key={i} className="text-xs text-gray-600 dark:text-indigo-300 flex items-center justify-between bg-white dark:bg-indigo-900/30 p-2 rounded border border-gray-100 dark:border-indigo-800">
                                                    <span className="truncate max-w-[200px]">{file.name}</span>
                                                    <span className="text-[10px] bg-gray-100 dark:bg-gray-800 px-1 rounded">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                                                </li>
                                            ))}
                                        </ul>

                                        <div className="flex gap-4 justify-center">
                                            <button
                                                onClick={handleUploadAndEvaluate}
                                                disabled={isUploading}
                                                className="flex-1 px-8 py-4 bg-primary text-white rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-xl hover:scale-105 flex items-center justify-center gap-3 disabled:opacity-50 disabled:scale-100 disabled:cursor-not-allowed"
                                            >
                                                {isUploading ? (
                                                    <>
                                                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                        <span>Processing...</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <span className="material-symbols-outlined">auto_awesome</span>
                                                        <span>Upload & Evaluate Answers</span>
                                                    </>
                                                )}
                                            </button>
                                            <button
                                                onClick={() => {
                                                    setUploadedFiles([]);
                                                    setBlobUrls([]);
                                                    setUploadedImage(null);
                                                    setEvaluationResults({});
                                                }}
                                                disabled={isUploading}
                                                className="px-6 py-4 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-xl font-semibold hover:bg-gray-200 dark:hover:bg-gray-700 transition-all flex items-center gap-2 disabled:opacity-50"
                                            >
                                                <span className="material-symbols-outlined">refresh</span>
                                                Clear
                                            </button>
                                        </div>

                                        {isUploading && (
                                            <div className="mt-8 space-y-3 px-4">
                                                <div className="flex justify-between items-end mb-1">
                                                    <span className="text-sm font-bold text-primary flex items-center gap-2">
                                                        <div className="w-2 h-2 bg-primary rounded-full animate-ping" />
                                                        {evalStatus}
                                                    </span>
                                                    <span className="text-xs font-bold text-gray-400">
                                                        {Math.round(evalProgress)}%
                                                    </span>
                                                </div>
                                                <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden shadow-inner relative">
                                                    <div 
                                                        className="h-full bg-gradient-to-r from-primary via-indigo-500 to-secondary transition-all duration-500 ease-out relative"
                                                        style={{ width: `${evalProgress}%` }}
                                                    >
                                                        <div className="absolute inset-0 bg-[linear-gradient(45deg,rgba(255,255,255,0.15)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.15)_50%,rgba(255,255,255,0.15)_75%,transparent_75%,transparent)] bg-[length:1rem_1rem] animate-[move-stripe_1s_linear_infinite]" />
                                                    </div>
                                                </div>
                                                <p className="text-[10px] text-center text-gray-500 dark:text-gray-400 font-medium animate-pulse">
                                                    Our AI is meticulously grading each answer. This may take a minute...
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {uploadedImage && (
                                    <div className="max-w-md mx-auto mt-6 bg-white dark:bg-indigo-950 rounded-lg p-2 border border-gray-200 dark:border-indigo-800">
                                        <p className="text-[10px] text-gray-400 mb-1 text-left">Preview (First Image):</p>
                                        <img
                                            src={uploadedImage}
                                            alt="Preview"
                                            className="w-full h-auto rounded shadow"
                                        />
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Error for Upload/Evaluation */}
                        {error && (
                            <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-start gap-3 text-red-600 dark:text-red-400">
                                <span className="material-symbols-outlined">error</span>
                                <p className="text-sm font-medium">{error}</p>
                            </div>
                        )}
                    </section>
                )}

                {/* Questions Display Section */}
                {(isGenerated || (showUploadSection && selectedPaper)) && questions.length > 0 && (
                    <section className="bg-surface-light dark:bg-surface-dark rounded-2xl shadow-card p-6 lg:p-8 border border-gray-200 dark:border-indigo-900/50">
                        <div className="flex items-center justify-between mb-6">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <span className="material-symbols-outlined text-secondary">description</span>
                                Question Paper
                            </h2>
                            <div className="flex items-center gap-4">
                                <span className="px-4 py-2 bg-primary/10 text-primary rounded-lg text-sm font-bold border border-primary/30">
                                    {subject}
                                </span>
                                <span className="px-4 py-2 bg-secondary/10 text-secondary rounded-lg text-sm font-bold border border-secondary/30">
                                    {difficulty}
                                </span>
                                <span className="px-4 py-2 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-lg text-sm font-bold border border-indigo-200 dark:border-indigo-800">
                                    {questions.length} Questions
                                </span>
                            </div>
                        </div>

                        <div className="space-y-6">
                            {questions.map((q, index) => (
                                <div key={q.id} className="bg-gray-50 dark:bg-indigo-950/50 rounded-xl p-5 border border-gray-200 dark:border-indigo-900 hover:border-primary/50 dark:hover:border-primary/50 transition-all">
                                    <div className="flex gap-4">
                                        <div className="flex-shrink-0 w-8 h-8 bg-primary text-white rounded-full flex items-center justify-center font-bold text-sm">
                                            {index + 1}
                                        </div>
                                        <div className="flex-1">
                                            <div className="flex items-start justify-between mb-4">
                                                <h3 className="text-base font-semibold text-gray-900 dark:text-white flex-1">
                                                    {q.question}
                                                </h3>
                                                <div className="flex flex-col items-end gap-2 ml-4">
                                                    <div className="flex items-center gap-2">
                                                        <span className={`px-3 py-1 rounded-lg text-xs font-bold border ${q.type === 'mcq'
                                                            ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800'
                                                            : 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 border-purple-200 dark:border-purple-800'
                                                            }`}>
                                                            {q.type === 'mcq' ? 'MCQ' : 'Subjective'}
                                                        </span>
                                                        <span className="px-3 py-1 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-lg text-xs font-bold border border-amber-200 dark:border-amber-800">
                                                            {q.marks} {q.marks === 1 ? 'mark' : 'marks'}
                                                        </span>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2 justify-end">
                                                        {q.chapter && (
                                                            <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded text-[10px] uppercase font-bold tracking-tight border border-gray-200 dark:border-gray-700">
                                                                {q.chapter}
                                                            </span>
                                                        )}
                                                        {q.subTopic && (
                                                            <span className="px-2 py-0.5 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 rounded text-[10px] uppercase font-bold tracking-tight border border-indigo-100 dark:border-indigo-900/50">
                                                                {q.subTopic}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>


                                            {q.imageUrl && !q.imageUrls && (
                                                <div className="mt-4 mb-6 rounded-xl overflow-hidden border border-gray-200 dark:border-indigo-800 bg-white dark:bg-indigo-950 p-2 shadow-inner">
                                                    <img
                                                        src={q.imageUrl}
                                                        alt={`Question ${index + 1}`}
                                                        className="max-w-full h-auto rounded-lg mx-auto"
                                                        onError={(e) => {
                                                            e.currentTarget.style.display = 'none';
                                                        }}
                                                    />
                                                </div>
                                            )}

                                            {q.imageUrls && q.imageUrls.length > 0 && (
                                                <div className="mt-4 mb-6 rounded-xl overflow-hidden border border-gray-200 dark:border-indigo-800 bg-white dark:bg-indigo-950 shadow-inner flex flex-col">
                                                    {q.imageUrls.map((url, i) => (
                                                        <img
                                                            key={i}
                                                            src={url}
                                                            alt={`Question ${index + 1} Part ${i + 1}`}
                                                            className="w-full h-auto"
                                                            onError={(e) => {
                                                                e.currentTarget.style.display = 'none';
                                                            }}
                                                        />
                                                    ))}
                                                </div>
                                            )}

                                            {q.type === 'mcq' && q.options && (
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                    {q.options.map((option, optIndex) => (
                                                        <div
                                                            key={optIndex}
                                                            className="flex items-center gap-3 p-3 bg-white dark:bg-indigo-900/30 rounded-lg border border-gray-200 dark:border-indigo-800 hover:border-primary dark:hover:border-primary transition-all cursor-pointer group"
                                                        >
                                                            <div className="w-6 h-6 rounded-full border-2 border-gray-300 dark:border-indigo-700 group-hover:border-primary flex items-center justify-center">
                                                                <span className="text-xs font-bold text-gray-500 dark:text-indigo-400 group-hover:text-primary">
                                                                    {String.fromCharCode(65 + optIndex)}
                                                                </span>
                                                            </div>
                                                            <span className="text-sm text-gray-700 dark:text-indigo-200 group-hover:text-primary transition-colors">
                                                                {option}
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {/* Evaluation Result Display */}
                                            {evaluationResults[q.id.toString()] && (
                                                <div className={`mt-6 p-5 rounded-xl border-2 transition-all ${
                                                    (evaluationResults[q.id.toString()].maxMarks > 0 && evaluationResults[q.id.toString()].score === evaluationResults[q.id.toString()].maxMarks)
                                                        ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                                                        : (evaluationResults[q.id.toString()].score > 0)
                                                            ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800'
                                                            : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                                                }`}>
                                                    <div className="flex items-center justify-between mb-4">
                                                        <h4 className={`text-sm font-bold flex items-center gap-2 ${
                                                            (evaluationResults[q.id.toString()].maxMarks > 0 && evaluationResults[q.id.toString()].score === evaluationResults[q.id.toString()].maxMarks)
                                                                ? 'text-green-700 dark:text-green-400'
                                                                : (evaluationResults[q.id.toString()].score > 0)
                                                                    ? 'text-amber-700 dark:text-amber-400'
                                                                    : 'text-red-700 dark:text-red-400'
                                                        }`}>
                                                            <span className="material-symbols-outlined">analytics</span>
                                                            Evaluation Result
                                                        </h4>
                                                        <div className={`px-3 py-1 rounded-full text-xs font-bold border ${
                                                            (evaluationResults[q.id.toString()].maxMarks > 0 && evaluationResults[q.id.toString()].score === evaluationResults[q.id.toString()].maxMarks)
                                                                ? 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300 border-green-200 dark:border-green-700'
                                                                : (evaluationResults[q.id.toString()].score > 0)
                                                                    ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 border-amber-200 dark:border-amber-700'
                                                                    : 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300 border-red-200 dark:border-red-700'
                                                        }`}>
                                                            Score: {evaluationResults[q.id.toString()].score} / {evaluationResults[q.id.toString()].maxMarks}
                                                        </div>
                                                    </div>

                                                    <div className="space-y-4">
                                                        <div>
                                                            <p className="text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Your Answer</p>
                                                            <p className="text-sm text-gray-800 dark:text-gray-200 bg-white/50 dark:bg-black/20 p-3 rounded-lg border border-gray-100 dark:border-gray-800 italic">
                                                                "{evaluationResults[q.id.toString()].studentAnswer}"
                                                            </p>
                                                        </div>
                                                        <div>
                                                            <p className="text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Feedback</p>
                                                            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed font-medium">
                                                                {evaluationResults[q.id.toString()].feedback}
                                                            </p>
                                                        </div>

                                                        {evaluationResults[q.id.toString()].expectedAnswer && (
                                                            <div className="bg-primary/5 dark:bg-primary/10 rounded-lg p-3 border border-primary/10">
                                                                <p className="text-[10px] font-bold text-primary uppercase tracking-wider mb-2 flex items-center gap-1">
                                                                    <span className="material-symbols-outlined text-xs">lightbulb</span>
                                                                    Expected Answer
                                                                </p>
                                                                <p className="text-sm text-gray-700 dark:text-gray-300 italic">
                                                                    {evaluationResults[q.id.toString()].expectedAnswer}
                                                                </p>
                                                            </div>
                                                        )}

                                                        {evaluationResults[q.id.toString()].missedPoints && evaluationResults[q.id.toString()].missedPoints!.length > 0 && (
                                                            <div>
                                                                <p className="text-[10px] font-bold text-red-500 dark:text-red-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                                                                    <span className="material-symbols-outlined text-xs">error_outline</span>
                                                                    Missed Points / Suggestions
                                                                </p>
                                                                <ul className="list-disc list-inside space-y-1">
                                                                    {evaluationResults[q.id.toString()].missedPoints!.map((point, idx) => (
                                                                        <li key={idx} className="text-xs text-gray-600 dark:text-gray-400">
                                                                            {point}
                                                                        </li>
                                                                    ))}
                                                                </ul>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Action Buttons */}
                        <div className="mt-8 flex gap-4 justify-center">
                            <button className="px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-indigo-700 transition-all shadow-lg hover:shadow-xl flex items-center gap-2">
                                <span className="material-symbols-outlined">play_arrow</span>
                                Start Test
                            </button>
                            <button className="px-6 py-3 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-xl font-semibold hover:bg-gray-200 dark:hover:bg-gray-700 transition-all flex items-center gap-2">
                                <span className="material-symbols-outlined">download</span>
                                Download PDF
                            </button>
                            <button
                                onClick={() => {
                                    setIsGenerated(false);
                                    setQuestions([]);
                                }}
                                className="px-6 py-3 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-xl font-semibold hover:bg-red-200 dark:hover:bg-red-900/50 transition-all flex items-center gap-2"
                            >
                                <span className="material-symbols-outlined">refresh</span>
                                Generate New
                            </button>
                        </div>
                    </section>
                )}
            </main>
        </div>
    );
};
