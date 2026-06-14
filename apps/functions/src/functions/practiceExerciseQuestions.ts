import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { withCors, corsPreflightResponse } from "../utils/cors";

async function practiceExerciseQuestionsHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        const exerciseId = request.query.get('exerciseId');

        if (!exerciseId) {
            return withCors({
                status: 400,
                jsonBody: { error: 'Exercise ID is required' }
            });
        }

        const prisma = await getPrisma();
        const exerciseIdNum = parseInt(exerciseId, 10);

        const exercise = await prisma.exercisedata.findUnique({
            where: { exerciseid: exerciseIdNum },
            select: {
                exerciseid: true,
                exercise: true,
                chapterid: true,
                questiondata: {
                    orderBy: { questionid: 'asc' },
                    select: {
                        questionid: true,
                        question_ref: true,
                        content: true,
                        solution: true,
                    }
                }
            }
        });

        if (!exercise) {
            return withCors({
                status: 404,
                jsonBody: { error: 'Exercise not found' }
            });
        }

        return withCors({
            jsonBody: {
                exerciseId: exercise.exerciseid,
                exerciseTitle: exercise.exercise,
                chapterId: exercise.chapterid,
                questions: exercise.questiondata.map(question => ({
                    questionId: question.questionid,
                    questionRef: question.question_ref,
                    questionText: typeof question.content === 'object' && question.content !== null && 'question_text' in question.content
                        ? String((question.content as any).question_text || '')
                        : '',
                    hasSolution: question.solution !== null,
                }))
            }
        });
    } catch (error) {
        context.error('[PRACTICE EXERCISE QUESTIONS] Error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Failed to load exercise questions' }
        });
    }
}

app.http('practiceExerciseQuestions', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'practice/exercise-questions',
    handler: practiceExerciseQuestionsHandler
});