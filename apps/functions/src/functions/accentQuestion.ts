import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { withCors, corsPreflightResponse } from "../utils/cors";
import { generateSasUrl } from "../utils/azure-storage";

/**
 * GET /api/accent/question/:id
 *
 * Returns full question detail including SAS-signed figure URL and solution.
 * If no solution is stored, returns a placeholder that SolutionView renders gracefully.
 *
 * Response:
 * {
 *   id: number; subject: string; section: string; difficulty: string | null;
 *   patternLabel: string | null; answerKey: string | null;
 *   questionContent: { raw_text, options, has_figure, figure_blob_url (SAS-signed) };
 *   solution: object;   // real or placeholder
 * }
 */
async function accentQuestionHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === "OPTIONS") return corsPreflightResponse;

    try {
        const idParam = request.params.id;
        if (!idParam) {
            return withCors({ status: 400, jsonBody: { error: "Question ID is required" } });
        }
        const questionId = parseInt(idParam);
        if (isNaN(questionId)) {
            return withCors({ status: 400, jsonBody: { error: "Invalid question ID" } });
        }

        const prisma = await getPrisma();
        const question = await prisma.jee_question_bank.findUnique({
            where: { id: questionId },
        });

        if (!question) {
            return withCors({ status: 404, jsonBody: { error: "Question not found" } });
        }

        // Deep-copy content to avoid mutating cached Prisma objects
        const content = JSON.parse(JSON.stringify(question.question_content ?? {})) as any;

        // Inject SAS token for figure URL if present
        if (content?.figure_blob_url && typeof content.figure_blob_url === "string") {
            try {
                content.figure_blob_url = await generateSasUrl(content.figure_blob_url);
            } catch (sasErr) {
                context.error("[ACCENT] SAS signing failed:", sasErr);
                // Leave original URL — will 403 but won't crash
            }
        }

        // Placeholder solution when M4 hasn't run yet
        const solution = question.solution ?? {
            steps: [],
            final_answer: question.answer_key
                ? `Solution coming soon. Correct answer: ${question.answer_key}`
                : "Solution coming soon.",
        };

        return withCors({
            jsonBody: {
                id: question.id,
                subject: question.subject,
                section: question.section,
                difficulty: question.difficulty,
                patternLabel: question.pattern_label,
                answerKey: question.answer_key,
                questionContent: content,
                solution,
            },
        });
    } catch (error) {
        context.error("[ACCENT] question error:", error);
        return withCors({ status: 500, jsonBody: { error: "Failed to load question" } });
    }
}

app.http("accentQuestion", {
    methods: ["GET", "OPTIONS"],
    authLevel: "anonymous",
    route: "accent/question/{id}",
    handler: accentQuestionHandler,
});
