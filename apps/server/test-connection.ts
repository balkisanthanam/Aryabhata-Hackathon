import { Client } from 'pg';
import { DefaultAzureCredential } from '@azure/identity';
import * as dotenv from 'dotenv';
dotenv.config();

async function testConnection() {
    console.log("--- Starting Connectivity Test ---");

    const dbUser = process.env.DB_USER;
    const dbHost = process.env.DB_HOST;
    const dbName = process.env.DB_NAME;
    const dbPort = parseInt(process.env.DB_PORT || "5432");

    if (!dbUser || !dbHost || !dbName) {
        console.error("❌ Missing env vars: DB_USER, DB_HOST, DB_NAME");
        return;
    }

    console.log(`Target: ${dbHost}:${dbPort} / DB: ${dbName} / User: ${dbUser}`);

    try {
        console.log("1. Fetching Azure Token...");
        const credential = new DefaultAzureCredential();
        const token = await credential.getToken("https://ossrdbms-aad.database.windows.net/.default");
        console.log("✅ Token acquired.");

        console.log("2. Attempting connection with 'pg' driver...");
        // Note: Azure Postgres Flexible Server with AD Auth usually requires the password to be the token
        const client = new Client({
            host: dbHost,
            user: dbUser,
            password: token.token,
            database: dbName,
            port: dbPort,
            ssl: { rejectUnauthorized: false } // Required for Azure
        });

        await client.connect();
        console.log("✅ Connection established successfully!");

        const res = await client.query('SELECT NOW() as now');
        console.log(`✅ Query Result: ${res.rows[0].now}`);

        await client.end();
        console.log("--- Test Passed ---");

    } catch (err: any) {
        console.error("❌ Connection Failed:", err.message);
        if (err.stack) console.error(err.stack);
        console.log("------------------------");
        console.log("Suggestion: If this fails with 'password authentication failed', double check:");
        console.log("  - DB_USER is exactly the Azure AD User Principal Name (email).");
        console.log("  - The user has been created in the Postgres DB using 'CREATE USER ... FROM EXTERNAL PROVIDER'.");
        console.log("  - Your IP is allowed in the Azure Firewall settings.");
    }
}

testConnection();
