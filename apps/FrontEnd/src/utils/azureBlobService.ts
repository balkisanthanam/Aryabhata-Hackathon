import { BlobClient, BlockBlobClient, ContainerClient } from "@azure/storage-blob";
import { azureConfig } from "../config/azureConfig";

export const uploadFilesToBlob = async (files: File[]): Promise<string[]> => {
    if (!azureConfig.sasUrl) {
        throw new Error("Azure Storage SAS URL is not configured.");
    }

    const containerClient = new ContainerClient(azureConfig.sasUrl);

    const uploadPromises = files.map(async (file) => {
        const blobName = `${Date.now()}-${file.name}`;
        const blockBlobClient = containerClient.getBlockBlobClient(blobName);

        await blockBlobClient.uploadBrowserData(file, {
            blobHTTPHeaders: { blobContentType: file.type }
        });

        return blockBlobClient.url;
    });
    return Promise.all(uploadPromises);
};

export const uploadJsonToBlob = async (data: any, fileName: string): Promise<string> => {
    if (!azureConfig.sasUrl) {
        throw new Error("Azure Storage SAS URL is not configured.");
    }

    const containerClient = new ContainerClient(azureConfig.sasUrl);
    // Note: If the SAS is for the container, the blobs might need 'answersheet/' prefix 
    // if the actual structure in the account has that folder.
    // Based on user URL: .../answersheet/answersheet/papers/...
    // The first 'answersheet' is the container, the second is a folder.
    const blockBlobClient = containerClient.getBlockBlobClient(`answersheet/papers/${fileName}`);

    const jsonString = JSON.stringify(data);
    const blob = new Blob([jsonString], { type: 'application/json' });

    await blockBlobClient.uploadBrowserData(blob);

    return blockBlobClient.url;
};

export const listPapers = async (): Promise<string[]> => {
    if (!azureConfig.sasUrl) {
        throw new Error("Azure Storage SAS URL is not configured.");
    }

    const containerClient = new ContainerClient(azureConfig.sasUrl);

    const urls: string[] = [];
    try {
        // We use the prefix according to the structure shown by the user
        for await (const blob of containerClient.listBlobsFlat({ prefix: 'answersheet/papers/' })) {
            urls.push(containerClient.getBlockBlobClient(blob.name).url);
        }
    } catch (err) {
        console.error("Error listing blobs:", err);
        // Fallback: try without 'answersheet/' prefix if the first one failed or returned nothing
        if (urls.length === 0) {
            for await (const blob of containerClient.listBlobsFlat({ prefix: 'papers/' })) {
                urls.push(containerClient.getBlockBlobClient(blob.name).url);
            }
        }
    }

    return urls;
};

export const getBlobContent = async (url: string): Promise<any> => {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch blob content: ${response.statusText}`);
    }
    return response.json();
};

export const deletePaperBlob = async (paperId: number | string): Promise<void> => {
    if (!azureConfig.sasUrl) {
        throw new Error("Azure Storage SAS URL is not configured.");
    }

    const containerClient = new ContainerClient(azureConfig.sasUrl);
    const fileName = `${paperId}.json`;
    const candidatePaths = [`answersheet/papers/${fileName}`, `papers/${fileName}`];

    let deleted = false;
    for (const blobPath of candidatePaths) {
        try {
            const blockBlobClient = containerClient.getBlockBlobClient(blobPath);
            const result = await blockBlobClient.deleteIfExists();
            if (result.succeeded) {
                deleted = true;
                break;
            }
        } catch {
            // Try next candidate path before failing.
        }
    }

    if (!deleted) {
        throw new Error("Could not delete paper from storage.");
    }
};

export const deleteBlobByUrl = async (blobUrl: string): Promise<void> => {
    if (!blobUrl) {
        throw new Error("Blob URL is required for deletion.");
    }

    const blobClient = new BlobClient(blobUrl);
    const result = await blobClient.deleteIfExists();
    if (!result.succeeded) {
        throw new Error("Could not delete paper from storage URL.");
    }
};

export const overwriteJsonAtBlobUrl = async (blobUrl: string, data: any): Promise<void> => {
    if (!blobUrl) {
        throw new Error("Blob URL is required.");
    }

    const blockBlobClient = new BlockBlobClient(blobUrl);
    const jsonString = JSON.stringify(data);
    const blob = new Blob([jsonString], { type: 'application/json' });
    await blockBlobClient.uploadBrowserData(blob, {
        blobHTTPHeaders: { blobContentType: 'application/json' }
    });
};
