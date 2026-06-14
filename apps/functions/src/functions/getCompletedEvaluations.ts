import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * GET /api/evaluations/completed?userId={userId}
 * Fetch all COMPLETED evaluations for a user (lightweight — no feedback_json).
 */
async function getCompletedEvaluationsHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const userId = parseInt(request.query.get('userId') || '') || sessionUser.UserId;

        const prisma = await getPrisma();
        const evaluations = await prisma.solution_evaluations.findMany({
            where: {
                userid: userId,
                status: 'COMPLETED',
            },
            select: {
                id: true,
                subject: true,
                problem_text_ref: true,
                created_at: true,
            },
            orderBy: {
                created_at: 'desc',
            },
        });

        return withCors({
            jsonBody: {
                evaluations: evaluations.map(e => ({
                    id: e.id,
                    subject: e.subject,
                    problemTextRef: e.problem_text_ref,
                    createdAt: e.created_at,
                })),
            },
        });

    } catch (error) {
        context.error('[EVAL] Get completed evaluations error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Internal server error' },
        });
    }
}

app.http('getCompletedEvaluations', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'evaluations/completed',
    handler: getCompletedEvaluationsHandler,
});
