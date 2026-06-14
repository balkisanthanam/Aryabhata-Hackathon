import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";
import { Prisma } from "@prisma/client";

/**
 * GET /api/accent/session?chapterId=X
 *
 * Returns the ordered list of JEE questions for a chapter, with per-question
 * attempt status for the current user. The frontend uses this to render the
 * question navigator and compute prev/next without extra round-trips.
 *
 * Response:
 * {
 *   chapterId: number;
 *   questions: [
 *     {
 *       id: number; subject: string; section: string; difficulty: string | null;
 *       hasFigure: boolean; attempted: boolean; wasCorrect: boolean | null;
 *     }
 *   ];
 *   stats: { total: number; attempted: number; correct: number }
 * }
 */
async function accentSessionHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === "OPTIONS") return corsPreflightResponse;

    try {
        const chapterIdParam = request.query.get("chapterId");
        if (!chapterIdParam) {
            return withCors({ status: 400, jsonBody: { error: "chapterId is required" } });
        }
        const chapterId = parseInt(chapterIdParam);
        const userId = sessionUser.UserId;
        const prisma = await getPrisma();

        // All distinct JEE questions tagged to a concept in this chapter
        const questionRows = await prisma.$queryRaw<
            {
                id: number;
                subject: string | null;
                section: string | null;
                difficulty: string | null;
                has_figure: boolean;
            }[]
        >(
            Prisma.sql`
                SELECT DISTINCT
                    jqb.id,
                    jqb.subject,
                    jqb.section,
                    jqb.difficulty,
                    COALESCE((jqb.question_content->>'has_figure')::boolean, false) AS has_figure
                FROM jee_question_bank jqb
                JOIN jee_question_tags jqt ON jqt.question_id = jqb.id
                JOIN ncert_concept_hierarchy nch ON nch.id = jqt.concept_id
                WHERE nch.chapter_id = ${chapterId}
                  AND jqt.similarity_score >= 0.85
                ORDER BY jqb.id
            `
        );

        if (questionRows.length === 0) {
            return withCors({
                jsonBody: { chapterId, questions: [], stats: { total: 0, attempted: 0, correct: 0 } },
            });
        }

        const questionIds = questionRows.map((q) => q.id);

        // User's most recent attempt per question (latest wins)
        const attemptRows = await prisma.$queryRaw<
            { question_id: number; was_correct: boolean | null }[]
        >(
            Prisma.sql`
                SELECT DISTINCT ON (question_id)
                    question_id,
                    was_correct
                FROM user_accent_attempts
                WHERE user_id  = ${userId}
                  AND question_id = ANY(${questionIds}::int[])
                ORDER BY question_id, attempted_at DESC
            `
        );

        const attemptMap = new Map(attemptRows.map((r) => [r.question_id, r.was_correct]));

        const questions = questionRows.map((q) => ({
            id: q.id,
            subject: q.subject,
            section: q.section,
            difficulty: q.difficulty,
            hasFigure: q.has_figure,
            attempted: attemptMap.has(q.id),
            wasCorrect: attemptMap.has(q.id) ? attemptMap.get(q.id) ?? null : null,
        }));

        const attempted = questions.filter((q) => q.attempted).length;
        const correct = questions.filter((q) => q.wasCorrect === true).length;

        return withCors({
            jsonBody: {
                chapterId,
                questions,
                stats: { total: questions.length, attempted, correct },
            },
        });
    } catch (error) {
        context.error("[ACCENT] session error:", error);
        return withCors({ status: 500, jsonBody: { error: "Failed to load session" } });
    }
}

app.http("accentSession", {
    methods: ["GET", "OPTIONS"],
    authLevel: "anonymous",
    route: "accent/session",
    handler: accentSessionHandler,
});
