import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";

/**
 * POST /api/auth/login
 * User authentication/session initialization
 */
async function authLoginHandler(request: HttpRequest, context: InvocationContext): Promise<HttpResponseInit> {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        context.log(`[AUTH] Logging in as default user: ${sessionUser.Name} (${sessionUser.UserId})`);

        const prisma = await getPrisma();

        // Fetch full profile from DB
        const userProfile = await prisma.userprofiledata.findUnique({
            where: { userid: sessionUser.UserId }
        });

        if (!userProfile) {
            context.warn(`[AUTH] User ID ${sessionUser.UserId} not found in DB. Returning basic session info.`);
            // Fallback if user doesn't exist in DB (though they should)
            return withCors({
                jsonBody: {
                    userId: sessionUser.UserId,
                    userName: sessionUser.Name,
                    userClass: null,
                    board: null,
                    goal: null,
                    email: null
                }
            });
        }

        return withCors({
            jsonBody: {
                userId: userProfile.userid,
                userName: userProfile.username,
                userClass: userProfile.class,
                board: userProfile.board,
                goal: userProfile.goal,
                email: userProfile.email
            }
        });

    } catch (error) {
        context.error('[AUTH] Login error:', error);
        return withCors({
            status: 500,
            jsonBody: { error: 'Internal server error during login' }
        });
    }
}

app.http('authLogin', {
    methods: ['POST', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'auth/login',
    handler: authLoginHandler
});
