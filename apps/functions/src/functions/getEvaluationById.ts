import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { withCors, corsPreflightResponse } from "../utils/cors";
import { generateSasUrl } from "../utils/azure-storage";

/**
 * GET /api/evaluations/detail/{id}
 * Retrieve a specific evaluation by its UUID.
 * Used for:
 *   - Polling status after submission
 *   - Loading a selected previous solution
 *
 * Route uses 'detail/' prefix to avoid conflict with
 * /evaluations/last and /evaluations/completed (Azure Functions
 * registers parameterized routes that can shadow literal siblings).
 */
async function getEvaluationByIdHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const id = request.params.id;
        if (!id) {
            return withCors({ status: 400, jsonBody: { error: 'Evaluation ID is required' } });
        }

        const prisma = await getPrisma();
        const evaluation = await prisma.solution_evaluations.findUnique({
            where: { id },
        });

        if (!evaluation) {
            return withCors({
                status: 404,
                jsonBody: { error: 'Evaluation not found' },
            });
        }

        // Generate SAS-signed URLs for student work and problem images
        let studentWorkUrls: string[] = [];
        let problemImageUrls: string[] = [];

        if (evaluation.student_work_url && evaluation.student_work_url !== 'pending-upload') {
            const rawUrls = evaluation.student_work_url.split(',').map(u => u.trim()).filter(Boolean);
            studentWorkUrls = await Promise.all(rawUrls.map(url => generateSasUrl(url)));
        }

        if (evaluation.problem_image_url) {
            const rawUrls = evaluation.problem_image_url.split(',').map(u => u.trim()).filter(Boolean);
            problemImageUrls = await Promise.all(rawUrls.map(url => generateSasUrl(url)));
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
                    studentWorkUrls,
                    problemImageUrls,
                },
            },
        });

    } catch (error) {
        context.error('[EVAL] Get evaluation by ID error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Internal server error' },
        });
    }
}

app.http('getEvaluationById', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'evaluations/detail/{id}',
    handler: getEvaluationByIdHandler,
});
