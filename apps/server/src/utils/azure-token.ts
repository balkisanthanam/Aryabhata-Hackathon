import { DefaultAzureCredential } from '@azure/identity';

export async function getAzureAccessToken(): Promise<string> {
    console.log("Attempting to fetch Azure AD access token...");
    try {
        const credential = new DefaultAzureCredential();
        // Scope for Azure SQL Database
        const scope = "https://ossrdbms-aad.database.windows.net/.default";
        const tokenResponse = await credential.getToken(scope);
        console.log("Successfully acquired Azure AD access token.");
        return tokenResponse.token;
    } catch (error) {
        console.error("Error fetching Azure AD access token:", error);
        throw error;
    }
}
