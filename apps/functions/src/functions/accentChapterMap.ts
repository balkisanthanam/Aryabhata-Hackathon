import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";
import { Prisma } from "@prisma/client";

/**
 * GET /api/accent/chapter-map
 *
 * Returns a map of chapter IDs that have JEE content, along with per-user
 * attempt stats. Used by PracticeDashboard to badge the JEE Ascent button.
 *
 * Response:
 * {
 *   chapters: [
 *     { chapterId: number; questionCount: number; attempted: number; correct: number }
 *   ]
 * }
 */
async function accentChapterMapHandler(
    _request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (_request.method === "OPTIONS") return corsPreflightResponse;

    try {
        const userId = sessionUser.UserId;
        const prisma = await getPrisma();

        // All chapters that have at least one tagged JEE question
        const contentRows = await prisma.$queryRaw<{ chapter_id: number; question_count: bigint }[]>(
            Prisma.sql`
                SELECT nch.chapter_id, COUNT(DISTINCT jqt.question_id) AS question_count
                FROM   jee_question_tags jqt
                JOIN   ncert_concept_hierarchy nch ON nch.id = jqt.concept_id
                WHERE  nch.chapter_id IS NOT NULL
                  AND  jqt.similarity_score >= 0.85
                GROUP  BY nch.chapter_id
            `
        );

        // User's attempt stats grouped by chapter
        const attemptRows = await prisma.$queryRaw<
            { chapter_id: number; attempted: bigint; correct: bigint }[]
        >(
            Prisma.sql`
                SELECT chapter_id,
                       COUNT(DISTINCT question_id) AS attempted,
                       COUNT(DISTINCT CASE WHEN was_correct THEN question_id END) AS correct
                FROM   user_accent_attempts
                WHERE  user_id = ${userId}
                  AND  chapter_id IS NOT NULL
                GROUP  BY chapter_id
            `
        );

        const attemptMap = new Map(attemptRows.map((r) => [r.chapter_id, r]));

        const chapters = contentRows.map((r) => {
            const att = attemptMap.get(r.chapter_id);
            return {
                chapterId: r.chapter_id,
                questionCount: Number(r.question_count),
                attempted: att ? Number(att.attempted) : 0,
                correct: att ? Number(att.correct) : 0,
            };
        });

        return withCors({ jsonBody: { chapters } });
    } catch (error) {
        context.error("[ACCENT] chapter-map error:", error);
        return withCors({ status: 500, jsonBody: { error: "Failed to load chapter map" } });
    }
}

app.http("accentChapterMap", {
    methods: ["GET", "OPTIONS"],
    authLevel: "anonymous",
    route: "accent/chapter-map",
    handler: accentChapterMapHandler,
});
