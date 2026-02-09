import { ContainerClient } from "@azure/storage-blob";
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
