import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * GET /api/user/resume
 * Fetch last attempted question for resume functionality
 */
async function userResumeHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const userId = sessionUser.UserId;
        const prisma = await getPrisma();

        // Find the latest attempted question
        const lastAttempt = await prisma.userexercisedata.findFirst({
            where: { userid: userId },
            orderBy: { attemptedat: 'desc' },
            include: {
                chapterdata: true
            }
        });

        if (!lastAttempt) {
            return withCors({ jsonBody: null }); // No resume data
        }

        return withCors({
            jsonBody: {
                chapterId: lastAttempt.chapterid,
                questionId: lastAttempt.questionid,
                chapterTitle: lastAttempt.chapterdata.chaptertitle,
                timestamp: lastAttempt.attemptedat
            }
        });

    } catch (error) {
        context.error('[RESUME] Error fetching resume data:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Failed to fetch resume data' }
        });
    }
}

app.http('userResume', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'user/resume',
    handler: userResumeHandler
});
