import express, { Request, Response, Router } from 'express';
import { PrismaClient } from '@prisma/client';
import { sessionUser } from '../config/session.config';

const router = Router();
const prisma = new PrismaClient();

// ==========================================
// AUTHENTICATION
// ==========================================
router.post('/auth/login', async (req: Request, res: Response) => {
    try {
        console.log(`[AUTH] Logging in as default user: ${sessionUser.Name} (${sessionUser.UserId})`);

        // Fetch full profile from DB
        const userProfile = await prisma.userprofiledata.findUnique({
            where: { userid: sessionUser.UserId }
        });

        if (!userProfile) {
            console.warn(`[AUTH] User ID ${sessionUser.UserId} not found in DB. Returning basic session info.`);
            // Fallback if user doesn't exist in DB (though they should)
            return res.json({
                userId: sessionUser.UserId,
                userName: sessionUser.Name,
                userClass: null,
                board: null,
                goal: null,
                email: null
            });
        }

        res.json({
            userId: userProfile.userid,
            userName: userProfile.username,
            userClass: userProfile.class,
            board: userProfile.board,
            goal: userProfile.goal,
            email: userProfile.email
        });

    } catch (error) {
        console.error('[AUTH] Login error:', error);
        res.status(500).json({ error: 'Internal server error during login' });
    }
});

// ==========================================
// RESUME LEARNING
// ==========================================
router.get('/user/resume', async (req: Request, res: Response) => {
    try {
        // In a real app, we'd get userId from req.user (middleware).
        // Here we use the session config/header, but sticking to sessionUser for simplicity 
        // as per instructions to "use sessionUser configuration".
        const userId = sessionUser.UserId;

        // Find the latest attempted question
        const lastAttempt = await prisma.userexercisedata.findFirst({
            where: { userid: userId },
            orderBy: { attemptedat: 'desc' },
            include: {
                chapterdata: true
            }
        });

        if (!lastAttempt) {
            return res.json(null); // No resume data
        }

        res.json({
            chapterId: lastAttempt.chapterid,
            questionId: lastAttempt.questionid,
            chapterTitle: lastAttempt.chapterdata.chaptertitle,
            timestamp: lastAttempt.attemptedat
        });

    } catch (error) {
        console.error('[RESUME] Error fetching resume data:', error);
        res.status(500).json({ error: 'Failed to fetch resume data' });
    }
});

// ==========================================
// PRACTICE DASHBOARD
// ==========================================
router.get('/practice/dashboard', async (req: Request, res: Response) => {
    try {
        console.log('[DASHBOARD] Request received');
        const { class: queryClass, subject: querySubject, board: queryBoard } = req.query;

        // 1. Determine Board (Default to 'CBSE' if not provided)
        const activeBoard = (queryBoard as string) || 'CBSE';

        // 2. Fetch Supported Classes & Subjects for this Board
        console.log('[DASHBOARD] Fetching classes...');
        const classesData = await prisma.classsubjectdata.findMany({
            where: { board: activeBoard },
            select: { class: true },
            distinct: ['class'],
            orderBy: { class: 'asc' }
        });
        console.log(`[DASHBOARD] Classes fetched: ${classesData.length}`);
        const supportedClasses = classesData.map(c => c.class);

        // 3. Determine Active Class
        let formatClass = (queryClass as string);
        if (!formatClass) {
            console.log('[DASHBOARD] Fetching user profile for default class...');
            const user = await prisma.userprofiledata.findUnique({ where: { userid: sessionUser.UserId } });
            formatClass = user?.class || '11';
        }

        // 4. Fetch Supported Subjects for Active Class & Board
        console.log(`[DASHBOARD] Fetching subjects for Class ${formatClass}...`);
        const subjectsData = await prisma.classsubjectdata.findMany({
            where: { board: activeBoard, class: formatClass },
            select: { subject: true },
            distinct: ['subject']
        });
        const supportedSubjects = subjectsData.map(s => s.subject);

        // 5. Determine Active Subject
        let activeSubject = (querySubject as string);
        if (!activeSubject && supportedSubjects.length > 0) {
            const randomIndex = Math.floor(Math.random() * supportedSubjects.length);
            activeSubject = supportedSubjects[randomIndex];
        }

        console.log(`[DASHBOARD] Active Subject: ${activeSubject}`);

        // 6. Fetch Chapters
        if (activeSubject) {
            console.log('[DASHBOARD] Fetching chapters...');
            const chapters = await prisma.chapterdata.findMany({
                where: {
                    class: formatClass,
                    subject: activeSubject,
                    board: activeBoard,
                    exercisedata: {
                        some: {}
                    }
                },
                orderBy: { chapternumber: 'asc' }
            });
            console.log(`[DASHBOARD] Chapters fetched: ${chapters.length}`);

            res.json({
                supportedClasses,
                supportedSubjects,
                activeClass: formatClass,
                activeSubject,
                activeBoard,
                chapters: chapters.map(c => ({
                    id: c.chapterid,
                    title: c.chaptertitle,
                    chapterNumber: c.chapternumber,
                    pdfUrl: c.pdffileurl
                }))
            });
        } else {
            res.json({
                supportedClasses,
                supportedSubjects,
                activeClass: formatClass,
                activeSubject: null,
                activeBoard,
                chapters: []
            });
        }

    } catch (error) {
        console.error('[DASHBOARD] Error:', error);
        res.status(500).json({ error: 'Failed to load dashboard' });
    }
});

// ==========================================
// PRACTICE SESSION (QUESTIONS)
// ==========================================
router.get('/practice/question', async (req: Request, res: Response) => {
    try {
        const { chapterId, questionId, mode, exerciseId } = req.query;
        const userId = sessionUser.UserId;

        if (!chapterId) {
            return res.status(400).json({ error: 'Chapter ID is required' });
        }

        let targetQuestionId: number | null = questionId ? parseInt(questionId as string) : null;
        let targetExerciseId: number | null = exerciseId ? parseInt(exerciseId as string) : null;

        // MODE: RESUME (and no specific ID provided)
        if (mode === 'resume' && !targetQuestionId) {
            const lastData = await prisma.userexercisedata.findFirst({
                where: { userid: userId, chapterid: parseInt(chapterId as string) },
                orderBy: { attemptedat: 'desc' }
            });
            if (lastData) {
                targetQuestionId = lastData.questionid;
                targetExerciseId = lastData.exerciseid;
            }
        }

        // MODE: START (or Fallback if Resume data missing)
        if (!targetQuestionId) {
            // Find first exercise->question for this chapter
            const firstExercise = await prisma.exercisedata.findFirst({
                where: { chapterid: parseInt(chapterId as string) },
                orderBy: { exerciseid: 'asc' }, // Assuming order
                include: {
                    questiondata: {
                        orderBy: { questionid: 'asc' },
                        take: 1
                    }
                }
            });

            if (firstExercise && firstExercise.questiondata.length > 0) {
                targetExerciseId = firstExercise.exerciseid;
                targetQuestionId = firstExercise.questiondata[0].questionid;
            } else {
                return res.status(404).json({ error: 'No questions found for this chapter' });
            }
        }

        // FETCH CONTENT
        const questionData = await prisma.questiondata.findUnique({
            where: { questionid: targetQuestionId }
        });

        if (!questionData) {
            return res.status(404).json({ error: 'Question not found' });
        }

        // --- SAS TOKEN INJECTION ---
        // If content has figure_info, sign the URLs
        // We do this dynamically so we don't store SAS tokens in DB
        if (questionData.content && typeof questionData.content === 'object') {
            const content: any = questionData.content;
            if (Array.isArray(content.figure_info)) {
                console.log(`[SAS] Found ${content.figure_info.length} figures. Processing...`);
                for (const fig of content.figure_info) {
                    if (fig.url && fig.url.includes('blob.core.windows.net')) {
                        console.log(`[SAS] Signing URL: ${fig.url}`);
                        try {
                            // Dynamically import to avoid top-level await issues if any, 
                            // though here we are inside async function so standard import is fine.
                            // But we need to verify import path.
                            const { generateSasUrl } = require('../utils/azure-storage');
                            const start = Date.now();
                            fig.url = await generateSasUrl(fig.url);
                            console.log(`[SAS] Signed successfully in ${Date.now() - start}ms. Result length: ${fig.url.length}`);
                        } catch (sasError) {
                            console.error('[SAS] Failed to sign URL:', sasError);
                            // Continue with original URL (will likely 403, but better than crash)
                        }
                    } else {
                        console.log(`[SAS] Skipping URL (not Azure Blob): ${fig.url}`);
                    }
                }
            } else {
                console.log('[SAS] No figure_info array found in content.');
            }
        }
        // ---------------------------

        // --- SAS TOKEN INJECTION ---
        // If content has figure_info, sign the URLs
        // We do this dynamically so we don't store SAS tokens in DB
        if (questionData.content && typeof questionData.content === 'object') {
            const content: any = questionData.content;
            if (Array.isArray(content.figure_info)) {
                for (const fig of content.figure_info) {
                    if (fig.url && fig.url.includes('blob.core.windows.net')) {
                        try {
                            // Dynamically import to avoid top-level await issues if any, 
                            // though here we are inside async function so standard import is fine.
                            // But we need to verify import path.
                            const { generateSasUrl } = require('../utils/azure-storage');
                            fig.url = await generateSasUrl(fig.url);
                        } catch (sasError) {
                            console.error('[SAS] Failed to sign URL:', sasError);
                            // Continue with original URL (will likely 403, but better than crash)
                        }
                    }
                }
            }
        }
        // ---------------------------

        // Ensure we have exerciseId (Critical Fix: If request came with just questionId, exerciseId is null)
        if (!targetExerciseId) {
            targetExerciseId = questionData.exerciseid;
        }

        // Also fetch Exercise Title & Chapter Info
        const exerciseData = await prisma.exercisedata.findUnique({
            where: { exerciseid: targetExerciseId! },
            include: {
                chapterdata: {
                    select: {
                        chaptertitle: true,
                        subject: true
                    }
                }
            }
        });

        // Find Next Question (Cross-Exercise logic)
        // 1. Try next question in SAME exercise
        let nextQ = await prisma.questiondata.findFirst({
            where: {
                exerciseid: targetExerciseId!,
                questionid: { gt: targetQuestionId }
            },
            orderBy: { questionid: 'asc' },
            select: { questionid: true }
        });

        // 2. If no next question in same exercise, find FIRST question of NEXT exercise in same chapter
        if (!nextQ) {
            const nextExercise = await prisma.exercisedata.findFirst({
                where: {
                    chapterid: parseInt(chapterId as string),
                    exerciseid: { gt: targetExerciseId! }
                },
                orderBy: { exerciseid: 'asc' },
                include: {
                    questiondata: {
                        orderBy: { questionid: 'asc' },
                        take: 1
                    }
                }
            });
            if (nextExercise && nextExercise.questiondata.length > 0) {
                nextQ = { questionid: nextExercise.questiondata[0].questionid };
            }
        }

        // Find Prev Question (Cross-Exercise logic)
        // 1. Try prev question in SAME exercise
        let prevQ = await prisma.questiondata.findFirst({
            where: {
                exerciseid: targetExerciseId!,
                questionid: { lt: targetQuestionId }
            },
            orderBy: { questionid: 'desc' },
            select: { questionid: true }
        });

        // 2. If no prev question in same exercise, find LAST question of PREV exercise
        if (!prevQ) {
            const prevExercise = await prisma.exercisedata.findFirst({
                where: {
                    chapterid: parseInt(chapterId as string),
                    exerciseid: { lt: targetExerciseId! }
                },
                orderBy: { exerciseid: 'desc' },
                include: {
                    questiondata: {
                        orderBy: { questionid: 'desc' },
                        take: 1
                    }
                }
            });
            if (prevExercise && prevExercise.questiondata.length > 0) {
                prevQ = { questionid: prevExercise.questiondata[0].questionid };
            }
        }

        // INJECT SAS TOKEN
        // Deep copy content to prevent in-memory mutation pollution across requests
        const content = JSON.parse(JSON.stringify(questionData.content));
        const { generateSasUrl } = require('../utils/azure-storage'); // Moved import here

        if (content && (content as any).figure_info) {
            const figures = (content as any).figure_info;
            console.log(`[SAS] Found ${figures.length} figures. Processing...`);

            for (const fig of figures) {
                if (fig.url && fig.url.includes('blob.core.windows.net')) {
                    console.log(`[SAS] Signing URL: ${fig.url}`);
                    try {
                        fig.url = await generateSasUrl(fig.url);
                        console.log(`[SAS] Signed successfully.`);
                    } catch (sasError) {
                        console.error('[SAS] Failed to sign URL:', sasError);
                        // Continue with original URL (will likely 403, but better than crash)
                    }
                }
            }
        }

        res.json({
            questionId: questionData.questionid, // Use question_ref for display
            questionRef: questionData.question_ref,
            exerciseId: questionData.exerciseid,
            exerciseTitle: exerciseData?.exercise,
            chapterTitle: exerciseData?.chapterdata?.chaptertitle,
            subject: exerciseData?.chapterdata?.subject,
            content: content, // Return the modified copy
            solution: questionData.solution,
            nextQuestionId: nextQ?.questionid || null,
            prevQuestionId: prevQ?.questionid || null
        });

    } catch (error) {
        console.error('[SESSION] Error loading question:', error);
        res.status(500).json({ error: 'Failed to load question' });
    }
});

// ==========================================
// PROGRESS TRACKING
// ==========================================
router.post('/practice/progress', async (req: Request, res: Response) => {
    try {
        const { chapterId, exerciseId, questionId } = req.body;
        const userId = sessionUser.UserId;

        // We need class/subject/board to insert into userexercisedata? 
        // No, the schema linking usually handles needed relations, 
        // BUT userexercisedata schema might NOT have specific columns like 'class', 'board' 
        // unless they are denormalized.
        // 
        // Looking at schema: 
        // userexercisedata(userexerciseid, userid, chapterid, exerciseid, questionid, attemptedat)
        // It DOES NOT store class/subject/board directly. Good.

        const newEntry = await prisma.userexercisedata.create({
            data: {
                userid: userId,
                chapterid: chapterId,
                exerciseid: exerciseId,
                questionid: questionId,
                attemptedat: new Date()
            }
        });

        res.json({ success: true, entryId: newEntry.userexerciseid });

    } catch (error) {
        console.error('[PROGRESS] Error saving progress:', error);
        res.status(500).json({ error: 'Failed to save progress' });
    }
});

export default router;
