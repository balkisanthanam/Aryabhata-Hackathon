import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { withCors, corsPreflightResponse } from "../utils/cors";

async function practiceChapterMapHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const chapterId = request.query.get('chapterId');

        if (!chapterId) {
            return withCors({
                status: 400,
                jsonBody: { error: 'Chapter ID is required' }
            });
        }

        const prisma = await getPrisma();
        const chapterIdNum = parseInt(chapterId, 10);

        const chapter = await prisma.chapterdata.findUnique({
            where: { chapterid: chapterIdNum },
            select: {
                chapterid: true,
                chaptertitle: true,
                chapternumber: true,
                subject: true,
                exercisedata: {
                    orderBy: { exerciseid: 'asc' },
                    select: {
                        exerciseid: true,
                        exercise: true,
                        totalquestions: true,
                        questiondata: {
                            orderBy: { questionid: 'asc' },
                            take: 1,
                            select: { questionid: true }
                        },
                        _count: {
                            select: { questiondata: true }
                        }
                    }
                }
            }
        });

        if (!chapter) {
            return withCors({
                status: 404,
                jsonBody: { error: 'Chapter not found' }
            });
        }

        return withCors({
            jsonBody: {
                chapterId: chapter.chapterid,
                chapterTitle: chapter.chaptertitle,
                chapterNumber: chapter.chapternumber,
                subject: chapter.subject,
                exercises: chapter.exercisedata.map(exercise => ({
                    exerciseId: exercise.exerciseid,
                    exerciseTitle: exercise.exercise,
                    questionCount: exercise.totalquestions ?? exercise._count.questiondata,
                    firstQuestionId: exercise.questiondata[0]?.questionid ?? null,
                }))
            }
        });
    } catch (error) {
        context.error('[PRACTICE CHAPTER MAP] Error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Failed to load chapter map' }
        });
    }
}

app.http('practiceChapterMap', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'practice/chapter-map',
    handler: practiceChapterMapHandler
});