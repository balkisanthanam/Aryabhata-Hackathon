import { ManagedIdentityCredential, AzureCliCredential, ChainedTokenCredential } from '@azure/identity';

export async function getAzureAccessToken(): Promise<string> {
    console.log("=== getAzureAccessToken START ===");
    console.log("ENV vars:", {
        AZURE_FUNCTIONS_ENVIRONMENT: process.env.AZURE_FUNCTIONS_ENVIRONMENT,
        WEBSITE_SITE_NAME: process.env.WEBSITE_SITE_NAME,
        FUNCTIONS_WORKER_RUNTIME: process.env.FUNCTIONS_WORKER_RUNTIME
    });
    
    try {
        // Detect environment: Azure has WEBSITE_SITE_NAME set
        const isAzure = !!process.env.WEBSITE_SITE_NAME;
        console.log(`Environment: ${isAzure ? 'AZURE' : 'LOCAL'}`);
        
        let credential;
        if (isAzure) {
            // In Azure: Use ONLY ManagedIdentityCredential (avoids SWA credential chain issue)
            console.log("Using ManagedIdentityCredential for Azure environment");
            credential = new ManagedIdentityCredential();
        } else {
            // Local dev: Use CLI credential
            console.log("Using AzureCliCredential for local dev");
            credential = new AzureCliCredential();
        }
        
        // Scope for Azure PostgreSQL with Entra ID
        const scope = "https://ossrdbms-aad.database.windows.net/.default";
        console.log(`Getting token for scope: ${scope}`);
        const tokenResponse = await credential.getToken(scope);
        console.log("Successfully acquired Azure AD access token.");
        return tokenResponse.token;
    } catch (error) {
        console.error("=== TOKEN ERROR ===");
        console.error("Error fetching Azure AD access token:", error);
        throw error;
    }
}
