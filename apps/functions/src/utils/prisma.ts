import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import { Pool } from 'pg';
import { getAzureAccessToken } from './azure-token';

let prisma: PrismaClient | null = null;

/**
 * Singleton function to get or create the Prisma Client.
 * Handles the dynamic Azure AD token injection for Prisma 7.
 */
export async function getPrisma() {
    if (prisma) return prisma;

    try {
        // 1. Get your dynamic token using your existing logic
        const token = await getAzureAccessToken();
        const dbUser = encodeURIComponent(process.env.DB_USER!);
        
        // 2. Build the connection string manually
        const connectionString = `postgresql://${dbUser}:${token}@${process.env.DB_HOST}:${process.env.DB_PORT}/${process.env.DB_NAME}?sslmode=require`;

        // 3. Create a pg Pool (required for the Prisma 7 adapter)
        const pool = new Pool({ 
            connectionString,
            max: 1 // Crucial for serverless to avoid 'too many connections'
        });

        // 4. Initialize the Prisma Client with the Driver Adapter
        const adapter = new PrismaPg(pool);
        prisma = new PrismaClient({ adapter });

        return prisma;
    } catch (error) {
        console.error('Failed to initialize Prisma Client:', error);
        throw error;
    }
}
