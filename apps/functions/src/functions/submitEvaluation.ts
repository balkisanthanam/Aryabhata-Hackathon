import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getPrisma } from "../utils/prisma";
import { sessionUser } from "../utils/session.config";
import { withCors, corsPreflightResponse } from "../utils/cors";
import { parseMultipart } from "../utils/multipart";
import { uploadFilesToBlob, UploadedFile } from "../utils/blob-upload";
import { pushToQueue } from "../utils/queue";

/**
 * POST /api/evaluations
 * Submit a new solution for evaluation.
 * Accepts multipart/form-data with image files + JSON fields.
 * 
 * Fields:
 *   - subject (required)
 *   - problemTextRef (required)
 *   - class (optional, defaults from user profile)
 *   - board (optional, defaults from user profile)
 * 
 * Files:
 *   - solutionImages (required, 1-5 files)
 *   - problemImages (optional, 0-5 files)
 */
async function submitEvaluationHandler(
    request: HttpRequest,
    context: InvocationContext
): Promise<HttpResponseInit> {
    if (request.method === 'OPTIONS') {
        return corsPreflightResponse;
    }

    try {
        context.log('[EVAL] Parsing multipart form data...');
        const { fields, files } = await parseMultipart(request);

        // Validate required fields
        const subject = fields.subject;
        const problemTextRef = fields.problemTextRef;
        if (!subject) {
            return withCors({ status: 400, jsonBody: { error: 'subject is required' } });
        }
        if (!problemTextRef) {
            return withCors({ status: 400, jsonBody: { error: 'problemTextRef is required' } });
        }

        // Separate solution and problem images
        const solutionFiles = files.filter(f => f.fieldname === 'solutionImages');
        const problemFiles = files.filter(f => f.fieldname === 'problemImages');

        if (solutionFiles.length === 0) {
            return withCors({ status: 400, jsonBody: { error: 'At least one solution image is required' } });
        }
        if (solutionFiles.length > 5) {
            return withCors({ status: 400, jsonBody: { error: 'Maximum 5 solution images allowed' } });
        }
        if (problemFiles.length > 5) {
            return withCors({ status: 400, jsonBody: { error: 'Maximum 5 problem images allowed' } });
        }

        const userId = sessionUser.UserId;
        const userClass = fields.class || null;
        const board = fields.board || null;

        // Generate a UUID for the job via Prisma (DB generates it)
        const prisma = await getPrisma();

        // Upload images to blob storage - we need a jobId first
        // Create the DB record first to get the UUID, then upload, then update URLs
        const evaluation = await prisma.solution_evaluations.create({
            data: {
                userid: userId,
                class: userClass,
                board: board,
                subject: subject,
                problem_text_ref: problemTextRef,
                student_work_url: 'pending-upload', // placeholder
                problem_image_url: problemFiles.length > 0 ? 'pending-upload' : null,
                status: 'PENDING',
            },
        });

        const jobId = evaluation.id;
        context.log(`[EVAL] Created evaluation record ${jobId}`);

        // Upload solution images
        const solutionUploadFiles: UploadedFile[] = solutionFiles.map(f => ({
            originalName: f.filename,
            buffer: f.buffer,
            mimeType: f.mimeType,
        }));
        const solutionUrls = await uploadFilesToBlob(userId, jobId, solutionUploadFiles, 'solution');
        context.log(`[EVAL] Uploaded ${solutionUrls.length} solution images`);

        // Upload problem images (if any)
        let problemUrls: string[] = [];
        if (problemFiles.length > 0) {
            const problemUploadFiles: UploadedFile[] = problemFiles.map(f => ({
                originalName: f.filename,
                buffer: f.buffer,
                mimeType: f.mimeType,
            }));
            problemUrls = await uploadFilesToBlob(userId, jobId, problemUploadFiles, 'problem');
            context.log(`[EVAL] Uploaded ${problemUrls.length} problem images`);
        }

        // Update the record with actual blob URLs
        // student_work_url stores comma-separated URLs (pipeline handles this)
        await prisma.solution_evaluations.update({
            where: { id: jobId },
            data: {
                student_work_url: solutionUrls.join(','),
                problem_image_url: problemUrls.length > 0 ? problemUrls.join(',') : null,
            },
        });

        // Push to queue
        await pushToQueue(jobId);
        context.log(`[EVAL] Job ${jobId} pushed to queue`);

        return withCors({
            status: 202,
            jsonBody: { jobId },
        });

    } catch (error: any) {
        context.error('[EVAL] Submit error:', error);
        const message = error.message || 'Internal server error';
        const status = message.includes('not allowed') || message.includes('limit') || message.includes('required')
            ? 400 : 500;
        return withCors({
            status,
            jsonBody: { error: message },
        });
    }
}

app.http('submitEvaluation', {
    methods: ['POST', 'OPTIONS'],
    authLevel: 'anonymous',
    route: 'evaluations',
    handler: submitEvaluationHandler,
});
