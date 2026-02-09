import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * Progress payload interface
 */
interface ProgressPayload {
    chapterId: number;
    exerciseId: number;
    questionId: number;
}

/**
 * POST /api/practice/progress
 * Save user progress
 */
async function practiceProgressHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const body = await request.json() as ProgressPayload;
        const { chapterId, exerciseId, questionId } = body;
        const userId = sessionUser.UserId;

        const prisma = await getPrisma();

        const newEntry = await prisma.userexercisedata.create({
            data: {
                userid: userId,
                chapterid: chapterId,
                exerciseid: exerciseId,
                questionid: questionId,
                attemptedat: new Date()
            }
        });

        return withCors({
            jsonBody: { success: true, entryId: newEntry.userexerciseid }
        });

    } catch (error) {
        context.error('[PROGRESS] Error saving progress:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Failed to save progress' }
        });
    }
}

app.http('practiceProgress', {
    methods: ['POST', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'practice/progress',
    handler: practiceProgressHandler
});
