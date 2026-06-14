/**
 * Azure Blob Storage upload utility for student evaluation images.
 * Uploads solution/problem images to kalidasa/feedback/student-uploads/{userId}/{jobId}/
 */
import { BlobServiceClient, StorageSharedKeyCredential } from '@azure/storage-blob';

const CONTAINER_NAME = 'feedback';
const UPLOAD_PREFIX = 'student-uploads';

let blobServiceClient: BlobServiceClient | null = null;

function getBlobServiceClient(): BlobServiceClient {
    if (blobServiceClient) return blobServiceClient;

    const accountName = process.env.AZURE_STORAGE_ACCOUNT_NAME;
    const accountKey = process.env.AZURE_STORAGE_KEY;

    if (!accountName) {
        throw new Error('AZURE_STORAGE_ACCOUNT_NAME is not set');
    }
    if (!accountKey) {
        throw new Error('AZURE_STORAGE_KEY is not set for blob upload');
    }

    const credential = new StorageSharedKeyCredential(accountName, accountKey.trim());
    blobServiceClient = new BlobServiceClient(
        `https://${accountName}.blob.core.windows.net`,
        credential
    );

    return blobServiceClient;
}

export interface UploadedFile {
    originalName: string;
    buffer: Buffer;
    mimeType: string;
}

/**
 * Upload a batch of files to blob storage under a specific userId/jobId path.
 * @param userId - The user's numeric ID
 * @param jobId - The evaluation UUID
 * @param files - Array of file buffers with metadata
 * @param subfolder - 'solution' or 'problem'
 * @returns Array of blob URLs
 */
export async function uploadFilesToBlob(
    userId: number,
    jobId: string,
    files: UploadedFile[],
    subfolder: 'solution' | 'problem'
): Promise<string[]> {
    const client = getBlobServiceClient();
    const containerClient = client.getContainerClient(CONTAINER_NAME);

    const urls: string[] = [];

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        // Sanitize the original filename
        const ext = getExtension(file.originalName, file.mimeType);
        const blobName = `${UPLOAD_PREFIX}/${userId}/${jobId}/${subfolder}/${subfolder}_${i + 1}${ext}`;

        const blockBlobClient = containerClient.getBlockBlobClient(blobName);
        await blockBlobClient.upload(file.buffer, file.buffer.length, {
            blobHTTPHeaders: {
                blobContentType: file.mimeType,
            },
        });

        urls.push(blockBlobClient.url);
        console.log(`[BlobUpload] Uploaded ${blobName} (${file.buffer.length} bytes)`);
    }

    return urls;
}

function getExtension(filename: string, mimeType: string): string {
    // Try from filename first
    const dotIdx = filename.lastIndexOf('.');
    if (dotIdx >= 0) {
        return filename.substring(dotIdx).toLowerCase();
    }

    // Fallback from MIME type
    const mimeMap: Record<string, string> = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'application/pdf': '.pdf',
    };
    return mimeMap[mimeType] || '.bin';
}
