import * as dotenv from "dotenv";
dotenv.config();

import { getAzureAccessToken } from "./get-azure-token";
import { execSync } from "child_process";

async function main() {
    try {
        console.log("Starting schema pull process...");

        // 1. Check Env Vars
        const dbUser = process.env.DB_USER;
        const dbHost = process.env.DB_HOST;
        const dbName = process.env.DB_NAME;
        const dbPort = process.env.DB_PORT || "5432";

        console.log(`Checking config: User=${dbUser}, Host=${dbHost}, Name=${dbName}`);

        if (!dbUser || !dbHost || !dbName) {
            console.error("Missing required environment variables: DB_USER, DB_HOST, DB_NAME. Please ensure .env is created and populated.");
            process.exit(1);
        }

        // 2. Get Token
        const token = await getAzureAccessToken();
        console.log("Token retrieved successfully.");

        // Ensure special characters in the token are encoded if necessary, 
        // though usually for the password field in the URL it's handled carefully.
        // For Prisma, we can pass it as the password.
        // NOTE: Tokens can contain characters that need URL encoding.
        const encodedToken = encodeURIComponent(token);
        const encodedUser = encodeURIComponent(dbUser);

        // Construct the connection string.
        const databaseUrl = `postgresql://${encodedUser}:${encodedToken}@${dbHost}:${dbPort}/${dbName}`;

        console.log(`Running prisma db pull...`);

        // Execute prisma db pull with the DATABASE_URL environment variable set
        execSync("npx prisma db pull", {
            stdio: "inherit",
            env: {
                ...process.env,
                DATABASE_URL: databaseUrl,
            },
        });

        console.log("Schema pulled successfully.");

    } catch (error) {
        console.error("Failed to pull schema:", error);
        process.exit(1);
    }
}

main();
