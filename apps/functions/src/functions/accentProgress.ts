import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * POST /api/accent/progress
 *
 * Records a single question attempt. Called after the user verifies their answer
 * or skips a question. Idempotent per (user, question) — subsequent attempts
 * overwrite the previous result (last attempt wins).
 *
 * Body:
 * {
 *   questionId: number;
 *   chapterId: number;
 *   wasCorrect: boolean | null;   // null if skipped without answering
 *   wasSkipped: boolean;
 *   timeSpentSeconds: number;
 * }
 *
 * Response: { success: true }
 */
async function accentProgressHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === "OPTIONS") return corsPreflightResponse;

    try {
        const body = (await request.json()) as {
            questionId: number;
            chapterId: number;
            wasCorrect: boolean | null;
            wasSkipped: boolean;
            timeSpentSeconds: number;
        };

        const { questionId, chapterId, wasCorrect, wasSkipped, timeSpentSeconds } = body;

        if (!questionId || !chapterId) {
            return withCors({ status: 400, jsonBody: { error: "questionId and chapterId are required" } });
        }

        const userId = sessionUser.UserId;
        const prisma = await getPrisma();

        await prisma.user_accent_attempts.create({
            data: {
                user_id: userId,
                question_id: questionId,
                chapter_id: chapterId,
                tier: 3,
                time_spent_seconds: timeSpentSeconds ?? 0,
                was_skipped: wasSkipped ?? false,
                was_correct: wasCorrect ?? null,
            },
        });

        return withCors({ jsonBody: { success: true } });
    } catch (error) {
        context.error("[ACCENT] progress error:", error);
        return withCors({ status: 500, jsonBody: { error: "Failed to record progress" } });
    }
}

app.http("accentProgress", {
    methods: ["POST", "OPTIONS"],
    authLevel: "anonymous",
    route: "accent/progress",
    handler: accentProgressHandler,
});
