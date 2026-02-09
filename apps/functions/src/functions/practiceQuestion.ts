import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { generateSasUrl } from "../utils/azure-storage";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * GET /api/practice/question
 * Fetch question content with SAS token injection
 */
async function practiceQuestionHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const chapterId = request.query.get('chapterId');
        const questionIdParam = request.query.get('questionId');
        const mode = request.query.get('mode');
        const exerciseIdParam = request.query.get('exerciseId');
        const userId = sessionUser.UserId;

        if (!chapterId) {
            return withCors({
                status: 400,
                jsonBody: { error: 'Chapter ID is required' }
            });
        }

        const prisma = await getPrisma();
        let targetQuestionId: number | null = questionIdParam ? parseInt(questionIdParam) : null;
        let targetExerciseId: number | null = exerciseIdParam ? parseInt(exerciseIdParam) : null;

        // MODE: RESUME (and no specific ID provided)
        if (mode === 'resume' && !targetQuestionId) {
            const lastData = await prisma.userexercisedata.findFirst({
                where: { userid: userId, chapterid: parseInt(chapterId) },
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
                where: { chapterid: parseInt(chapterId) },
                orderBy: { exerciseid: 'asc' },
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
                return withCors({
                    status: 404,
                    jsonBody: { error: 'No questions found for this chapter' }
                });
            }
        }

        // FETCH CONTENT
        const questionData = await prisma.questiondata.findUnique({
            where: { questionid: targetQuestionId }
        });

        if (!questionData) {
            return withCors({
                status: 404,
                jsonBody: { error: 'Question not found' }
            });
        }

        // Ensure we have exerciseId
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
                    chapterid: parseInt(chapterId),
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
                    chapterid: parseInt(chapterId),
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

        if (content && (content as any).figure_info) {
            const figures = (content as any).figure_info;
            context.log(`[SAS] Found ${figures.length} figures. Processing...`);

            for (const fig of figures) {
                if (fig.url && fig.url.includes('blob.core.windows.net')) {
                    context.log(`[SAS] Signing URL: ${fig.url}`);
                    try {
                        fig.url = await generateSasUrl(fig.url);
                        context.log(`[SAS] Signed successfully.`);
                    } catch (sasError) {
                        context.error('[SAS] Failed to sign URL:', sasError);
                        // Continue with original URL (will likely 403, but better than crash)
                    }
                }
            }
        }

        return withCors({
            jsonBody: {
                questionId: questionData.questionid,
                questionRef: questionData.question_ref,
                exerciseId: questionData.exerciseid,
                exerciseTitle: exerciseData?.exercise,
                chapterTitle: exerciseData?.chapterdata?.chaptertitle,
                subject: exerciseData?.chapterdata?.subject,
                content: content,
                solution: questionData.solution,
                nextQuestionId: nextQ?.questionid || null,
                prevQuestionId: prevQ?.questionid || null
            }
        });

    } catch (error) {
        context.error('[SESSION] Error loading question:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Failed to load question' }
        });
    }
}

app.http('practiceQuestion', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'practice/question',
    handler: practiceQuestionHandler
});
