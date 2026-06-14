/**
 * Multipart form-data parser using busboy.
 * Extracts fields and files from an Azure Functions HttpRequest.
 */
import { HttpRequest } from '@azure/functions';
import Busboy from 'busboy';
import { Readable } from 'stream';

export interface ParsedFile {
    fieldname: string;
    filename: string;
    mimeType: string;
    buffer: Buffer;
}

export interface ParsedFormData {
    fields: Record<string, string>;
    files: ParsedFile[];
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const MAX_FILES = 10; // 5 solution + 5 problem max
const ALLOWED_MIME_TYPES = new Set([
    'image/jpeg',
    'image/png',
    'application/pdf',
]);

/**
 * Parse a multipart/form-data request body.
 * @throws Error if file exceeds size limit, invalid mime type, or too many files.
 */
export function parseMultipart(request: HttpRequest): Promise<ParsedFormData> {
    return new Promise(async (resolve, reject) => {
        const contentType = request.headers.get('content-type') || '';
        if (!contentType.includes('multipart/form-data')) {
            reject(new Error('Content-Type must be multipart/form-data'));
            return;
        }

        const fields: Record<string, string> = {};
        const files: ParsedFile[] = [];

        const busboy = Busboy({
            headers: { 'content-type': contentType },
            limits: {
                fileSize: MAX_FILE_SIZE,
                files: MAX_FILES,
            },
        });

        busboy.on('field', (fieldname: string, value: string) => {
            fields[fieldname] = value;
        });

        busboy.on('file', (fieldname: string, stream: Readable, info: { filename: string; encoding: string; mimeType: string }) => {
            const { filename, mimeType } = info;

            if (!ALLOWED_MIME_TYPES.has(mimeType)) {
                stream.resume(); // drain the stream
                reject(new Error(`File type '${mimeType}' is not allowed. Accepted: JPG, PNG, PDF`));
                return;
            }

            const chunks: Buffer[] = [];
            let totalSize = 0;

            stream.on('data', (chunk: Buffer) => {
                totalSize += chunk.length;
                if (totalSize > MAX_FILE_SIZE) {
                    stream.destroy();
                    reject(new Error(`File '${filename}' exceeds ${MAX_FILE_SIZE / 1024 / 1024}MB limit`));
                    return;
                }
                chunks.push(chunk);
            });

            stream.on('end', () => {
                files.push({
                    fieldname,
                    filename: filename || `upload_${files.length}`,
                    mimeType,
                    buffer: Buffer.concat(chunks),
                });
            });

            stream.on('error', (err: Error) => {
                reject(err);
            });
        });

        busboy.on('finish', () => {
            resolve({ fields, files });
        });

        busboy.on('error', (err: Error) => {
            reject(err);
        });

        // Get the request body as a buffer and pipe to busboy
        try {
            const bodyBuffer = Buffer.from(await request.arrayBuffer());
            const readable = Readable.from(bodyBuffer);
            readable.pipe(busboy);
        } catch (err) {
            reject(err);
        }
    });
}
