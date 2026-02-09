import { DefaultAzureCredential } from "@azure/identity";

export async function getAzureAccessToken() {
    const credential = new DefaultAzureCredential();
    // The scope for Azure SQL Database is usually https://database.windows.net/.default
    // or specific to the ossrdbms URI as requested.
    // User mentioned: https://ossrdbms-aad.database.windows.net/.default
    const scope = "https://ossrdbms-aad.database.windows.net/.default";

    try {
        console.log("Fetching Azure AD Token...");
        const tokenResponse = await credential.getToken(scope);
        return tokenResponse.token;
    } catch (error) {
        console.error("Error fetching token:", error);
        throw error;
    }
}
