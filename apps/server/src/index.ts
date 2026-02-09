import express from 'express';
import cors from 'cors';
import * as dotenv from 'dotenv';
import { getAzureAccessToken } from './utils/azure-token';
import { verifyStorageConnection } from './utils/azure-storage';

dotenv.config();

const PORT = process.env.PORT || 3000;

async function bootstrap() {
    try {
        console.log('Bootstrapping server...');

        // Verify Storage Connectivity
        await verifyStorageConnection();

        // 1. Construct DATABASE_URL dynamically
        if (!process.env.DATABASE_URL) {
            console.log('DATABASE_URL not found in env, constructing dynamically via Azure AD...');

            const dbUser = process.env.DB_USER;
            const dbHost = process.env.DB_HOST;
            const dbName = process.env.DB_NAME;
            const dbPort = process.env.DB_PORT || '5432';

            if (!dbUser || !dbHost || !dbName) {
                throw new Error('Missing required DB environment variables (DB_USER, DB_HOST, DB_NAME)');
            }

            const token = await getAzureAccessToken();
            const dbUserEncoded = encodeURIComponent(dbUser);

            // Construct Postgres Connection String
            // Note: password is the token
            const connectionString = `postgresql://${dbUserEncoded}:${token}@${dbHost}:${dbPort}/${dbName}?connection_limit=5`;

            // Set it for Prisma to pick up
            process.env.DATABASE_URL = connectionString;
            console.log('DATABASE_URL set successfully (masked token).');
        }

        // 2. Import Routes (Dynamically, so PrismaClient is instantiated AFTER env var is set)
        const { default: apiRoutes } = await import('./routes/api');

        const app = express();

        // Middleware
        app.use(cors());
        app.use(express.json());

        // Routes
        app.use('/api', apiRoutes);

        // Health Check
        app.get('/', (req, res) => {
            res.send('Aryabhata Backend is running');
        });

        // Start Server
        app.listen(PORT, () => {
            console.log(`Server running on http://localhost:${PORT}`);
        });

    } catch (error) {
        console.error('Failed to start server:', error);
        process.exit(1);
    }
}

bootstrap();
