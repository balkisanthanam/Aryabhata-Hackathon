export const azureConfig = {
    sasUrl: import.meta.env.VITE_AZURE_STORAGE_SAS_URL || "",
    containerName: import.meta.env.VITE_AZURE_STORAGE_CONTAINER_NAME || "answer-sheets",
};
