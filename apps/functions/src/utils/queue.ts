/**
 * Azure Queue Storage utility for pushing evaluation job IDs
 * to the feedback-jobs queue on stevaluationstorage.
 */
import { QueueClient, QueueServiceClient } from '@azure/storage-queue';

let queueClient: QueueClient | null = null;

function getQueueClient(): QueueClient {
    if (queueClient) return queueClient;

    const connectionString = process.env.FEEDBACK_QUEUE_CONNECTION;
    if (!connectionString) {
        throw new Error('FEEDBACK_QUEUE_CONNECTION is not set in environment variables');
    }

    const queueServiceClient = QueueServiceClient.fromConnectionString(connectionString);
    queueClient = queueServiceClient.getQueueClient('feedback-jobs');

    return queueClient;
}

/**
 * Push a job ID to the feedback-jobs queue.
 * The SDK base64-encodes automatically — do NOT encode manually
 * or the Python queue trigger will receive a double-encoded string.
 */
export async function pushToQueue(jobId: string): Promise<void> {
    const client = getQueueClient();
    await client.sendMessage(jobId);
    console.log(`[Queue] Pushed job ${jobId} to feedback-jobs queue`);
}
