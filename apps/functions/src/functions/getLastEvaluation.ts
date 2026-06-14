import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * GET /api/evaluations/last?userId={userId}
 * Retrieve the most recently created evaluation for a user (any status).
 * Used by the frontend on page load to determine initial state.
 */
async function getLastEvaluationHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const userId = parseInt(request.query.get('userId') || '') || sessionUser.UserId;

        const prisma = await getPrisma();
        const evaluation = await prisma.solution_evaluations.findFirst({
            where: {
                userid: userId,
            },
            orderBy: {
                created_at: 'desc',
            },
        });

        if (!evaluation) {
            return withCors({
                jsonBody: { evaluation: null },
            });
        }

        return withCors({
            jsonBody: {
                evaluation: {
                    id: evaluation.id,
                    status: evaluation.status,
                    subject: evaluation.subject,
                    problemTextRef: evaluation.problem_text_ref,
                    feedbackJson: evaluation.feedback_json,
                    createdAt: evaluation.created_at,
                },
            },
        });

    } catch (error) {
        context.error('[EVAL] Get last evaluation error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Internal server error' },
        });
    }
}

app.http('getLastEvaluation', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'evaluations/last',
    handler: getLastEvaluationHandler,
});
