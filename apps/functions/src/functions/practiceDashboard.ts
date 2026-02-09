import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * GET /api/practice/dashboard
 * Get dashboard data (classes, subjects, chapters)
 */
async function practiceDashboardHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        context.log('[DASHBOARD] Request received');
        
        const queryClass = request.query.get('class');
        const querySubject = request.query.get('subject');
        const queryBoard = request.query.get('board');

        const prisma = await getPrisma();

        // 1. Determine Board (Default to 'CBSE' if not provided)
        const activeBoard = queryBoard || 'CBSE';

        // 2. Fetch Supported Classes & Subjects for this Board
        context.log('[DASHBOARD] Fetching classes...');
        const classesData = await prisma.classsubjectdata.findMany({
            where: { board: activeBoard },
            select: { class: true },
            distinct: ['class'],
            orderBy: { class: 'asc' }
        });
        context.log(`[DASHBOARD] Classes fetched: ${classesData.length}`);
        const supportedClasses = classesData.map(c => c.class);

        // 3. Determine Active Class
        let formatClass = queryClass as string | undefined;
        if (!formatClass) {
            context.log('[DASHBOARD] Fetching user profile for default class...');
            const user = await prisma.userprofiledata.findUnique({ where: { userid: sessionUser.UserId } });
            formatClass = user?.class || '11';
        }

        // 4. Fetch Supported Subjects for Active Class & Board
        context.log(`[DASHBOARD] Fetching subjects for Class ${formatClass}...`);
        const subjectsData = await prisma.classsubjectdata.findMany({
            where: { board: activeBoard, class: formatClass },
            select: { subject: true },
            distinct: ['subject']
        });
        const supportedSubjects = subjectsData.map(s => s.subject);

        // 5. Determine Active Subject
        let activeSubject = querySubject as string | undefined;
        if (!activeSubject && supportedSubjects.length > 0) {
            const randomIndex = Math.floor(Math.random() * supportedSubjects.length);
            activeSubject = supportedSubjects[randomIndex];
        }

        context.log(`[DASHBOARD] Active Subject: ${activeSubject}`);

        // 6. Fetch Chapters
        if (activeSubject) {
            context.log('[DASHBOARD] Fetching chapters...');
            const chapters = await prisma.chapterdata.findMany({
                where: {
                    class: formatClass,
                    subject: activeSubject,
                    board: activeBoard,
                    exercisedata: {
                        some: {}
                    }
                },
                orderBy: { chapternumber: 'asc' }
            });
            context.log(`[DASHBOARD] Chapters fetched: ${chapters.length}`);

            return withCors({
                jsonBody: {
                    supportedClasses,
                    supportedSubjects,
                    activeClass: formatClass,
                    activeSubject,
                    activeBoard,
                    chapters: chapters.map(c => ({
                        id: c.chapterid,
                        title: c.chaptertitle,
                        chapterNumber: c.chapternumber,
                        pdfUrl: c.pdffileurl
                    }))
                }
            });
        } else {
            return withCors({
                jsonBody: {
                    supportedClasses,
                    supportedSubjects,
                    activeClass: formatClass,
                    activeSubject: null,
                    activeBoard,
                    chapters: []
                }
            });
        }

    } catch (error) {
        context.error('[DASHBOARD] Error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Failed to load dashboard' }
        });
    }
}

app.http('practiceDashboard', {
    methods: ['GET', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'practice/dashboard',
    handler: practiceDashboardHandler
});
