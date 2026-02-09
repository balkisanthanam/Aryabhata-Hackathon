import { BlobServiceClient, StorageSharedKeyCredential, BlobSASPermissions, generateBlobSASQueryParameters } from '@azure/storage-blob';
import { DefaultAzureCredential } from '@azure/identity';

// Cache the BlobServiceClient
let blobServiceClient: BlobServiceClient | null = null;
let sharedKeyCredential: StorageSharedKeyCredential | null = null;

// Initialize the client (lazy loading)
const getBlobServiceClient = (): BlobServiceClient => {
    if (blobServiceClient) return blobServiceClient;

    const accountName = process.env.AZURE_STORAGE_ACCOUNT_NAME;
    const accountKey = process.env.AZURE_STORAGE_KEY;

    if (!accountName) {
        throw new Error('AZURE_STORAGE_ACCOUNT_NAME is not defined in environment variables');
    }

    if (accountKey) {
        console.log('[SAS] Using Storage Account Key for authentication.');
        // Trim key to remove accidentally pasted newlines/spaces
        const cleanKey = accountKey.trim();
        sharedKeyCredential = new StorageSharedKeyCredential(accountName, cleanKey);
        blobServiceClient = new BlobServiceClient(
            `https://${accountName}.blob.core.windows.net`,
            sharedKeyCredential
        );
    } else {
        console.warn('[SAS] WARNING: AZURE_STORAGE_KEY not found. Falling back to User Delegation (DefaultAzureCredential).');
        console.warn('[SAS] This method frequently fails in local environments with 403 Signature Mismatch errors.');
        console.log('[SAS] Using DefaultAzureCredential (User Delegation) for authentication.');
        const credential = new DefaultAzureCredential();
        blobServiceClient = new BlobServiceClient(
            `https://${accountName}.blob.core.windows.net`,
            credential
        );
    }

    return blobServiceClient;
};

// Generate a SAS Token for a specific blob URL
export const generateSasUrl = async (blobUrl: string): Promise<string> => {
    try {
        const client = getBlobServiceClient();
        const accountName = client.accountName;

        // 0. Sanitize Input
        const cleanUrl = blobUrl.trim();

        // GUARD: Prevent double-signing
        if (cleanUrl.includes('sig=')) {
            console.warn('[SAS] URL already signed. Skipping.');
            return cleanUrl;
        }

        // 1. Parse the URL to get container and blob name
        const url = new URL(cleanUrl);
        const pathParts = url.pathname.split('/').filter(p => p.length > 0);

        if (pathParts.length < 2) {
            console.warn('[SAS] Invalid blob URL format:', cleanUrl);
            return cleanUrl;
        }

        const containerName = pathParts[0];
        // Revert decodeURIComponent to avoid double-decoding issues unless strictly necessary
        const blobName = pathParts.slice(1).join('/');

        console.log(`[SAS] Details - Account: ${accountName}, Container: ${containerName}, Blob: ${blobName}`);

        const now = new Date();
        const expiresOn = new Date(now.valueOf() + 2 * 60 * 60 * 1000); // 2 hours

        const sasOptions = {
            containerName,
            blobName,
            permissions: BlobSASPermissions.parse("r"),
            expiresOn,
            protocol: "https" as any,
            resource: "b" // Explicitly set signed resource to 'blob'
        };

        let sasToken = '';

        // 2. Sign using Shared Key (Preferred/Simpler if available) OR User Delegation
        if (sharedKeyCredential) {
            sasToken = generateBlobSASQueryParameters(
                sasOptions,
                sharedKeyCredential
            ).toString();
        } else {
            // User Delegation Fallback
            const userDelegationKey = await client.getUserDelegationKey(now, expiresOn); // use 'now' as start
            console.log('[SAS] User Delegation Key acquired.');

            sasToken = generateBlobSASQueryParameters(
                sasOptions,
                userDelegationKey,
                accountName
            ).toString();
        }

        // 3. Return full URL (Handle existing query params safely)
        const separator = cleanUrl.includes('?') ? '&' : '?';
        return `${cleanUrl}${separator}${sasToken}`;

    } catch (error) {
        console.error('[SAS] Error generating token:', error);
        return blobUrl;
    }
}

// Verify connection on startup
export const verifyStorageConnection = async () => {
    try {
        const client = getBlobServiceClient();
        console.log(`[Storage] Verifying connection to account: ${client.accountName}...`);

        // Try to list containers (lightweight operation)
        // We only fetch one to separate Auth errors from empty/other errors
        const iter = client.listContainers();
        await iter.next();

        console.log('[Storage] Connection Verification: SUCCESS. Key/Identity is valid.');
        return true;
    } catch (error: any) {
        console.error('[Storage] Connection Verification: FAILED.');
        console.error(`[Storage] Error: ${error.message}`);
        console.error('[Storage] Please check AZURE_STORAGE_KEY and AZURE_STORAGE_ACCOUNT_NAME in .env');
        return false;
    }
};
