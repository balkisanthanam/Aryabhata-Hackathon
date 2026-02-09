# Migration Plan: Azure to Google Cloud Platform (GCP)

This document outlines the strategy, service mapping, and execution steps for migrating the **Aryabhata** application from Microsoft Azure to Google Cloud Platform (GCP).

## 1. Service Mapping Strategy

| Feature | Current Azure Service | Target GCP Service | Reasoning |
| :--- | :--- | :--- | :--- |
| **Compute (API)** | Azure App Service / VM | **Cloud Run** | Serverless container platform, scales to zero, easy to deploy Node.js apps. |
| **Compute (Worker)** | Azure Functions | **Cloud Functions (2nd Gen)** | Event-driven serverless functions, native triggers from Pub/Sub and Storage. |
| **Object Storage** | Azure Blob Storage | **Google Cloud Storage (GCS)** | Direct equivalent. "Containers" become "Buckets". |
| **Queue/Messaging** | Azure Storage Queue | **Cloud Pub/Sub** | More robust, scalable messaging system. Note: Pub/Sub is "push" or "streaming pull", rarely "simple pull". |
| **Database** | Azure Database for PostgreSQL | **Cloud SQL for PostgreSQL** | Managed PostgreSQL service. High compatibility. |
| **Authentication** | Azure Active Directory (Entra ID) | **Google Identity Platform / Firebase Auth** | Use Service Accounts for backend-to-backend auth. |
| **AI Models** | Azure OpenAI / Gemini via API | **Vertex AI (Gemini API)** | Native integration with Google's Gemini models (Pro/Flash). |

---

## 2. Migration To-Do List

### Phase 1: Infrastructure Setup (GCP)
- [ ] **Project Setup**: Create a new GCP Project.
- [ ] **IAM**: Set up Service Accounts for:
    - `backend-service-account` (for the API to access DB, Storage, Pub/Sub)
    - `worker-service-account` (for Cloud Functions to access Vertex AI, DB)
- [ ] **Storage**: Create GCS buckets (e.g., `student-solutions-bucket`).
- [ ] **Messaging**: Create Pub/Sub topic `evaluator-jobs-topic` and a subscription `evaluator-jobs-sub`.
- [ ] **Database**: Provision Cloud SQL for PostgreSQL instance.

### Phase 2: Code Refactoring (Node.js Backend)
- [ ] **Remove Azure SDKs**: Uninstall `@azure/identity`, `@azure/storage-blob`.
- [ ] **Add GCP SDKs**: Install `@google-cloud/storage`, `@google-cloud/pubsub`.
- [ ] **Storage Logic**:
    - Replace `BlobServiceClient` with `Storage` client.
    - Update upload/download logic (Streams are similar but API differs).
- [ ] **Queue Logic**:
    - Replace "Add Message to Queue" with "Publish Message to Topic".
    - Update message payload structure if needed (Pub/Sub messages are base64 encoded buffers).
- [ ] **Database Config**:
    - Update `DATABASE_URL` in `.env` to point to Cloud SQL.
    - Run `prisma migrate deploy` against the new DB.

### Phase 3: Worker Migration (Azure Function -> Cloud Function)
- [ ] **Refactor Trigger**: Change trigger from "Queue Trigger" to "Cloud Pub/Sub Trigger".
- [ ] **Gemini Integration**: Use `@google-cloud/vertexai` SDK to call Gemini directly (lower latency than external API calls).
- [ ] **Deployment**: Create `gcloud functions deploy` scripts.

---

## 3. Key Challenges & Considerations

### Authentication Model
- **Azure**: Uses `DefaultAzureCredential` which tries Environment Vars, Managed Identity, then CLI login.
- **GCP**: Uses `GoogleAuth` (ADC - Application Default Credentials).
- **Challenge**: You need to ensure the correct Service Account keys (`GOOGLE_APPLICATION_CREDENTIALS` json file) are present locally for dev, and attached to the Cloud Run/Function instance in prod.

### Queue Semantics (The biggest code change)
- **Azure Storage Queue**: You explicitly "poll" or "get" messages. Azure Functions implicitly poll for you.
- **GCP Pub/Sub**: It is a Publisher/Subscriber model.
    - **Publishing**: Similar (send a JSON payload).
    - **Consuming**: Cloud Functions are "pushed" events. You don't ask for a message; your function `(event) => { ... }` is called whenever a message arrives. This is actually *simpler* but requires understanding the shift from "pull" to "push".

### Database Migration
- **Data Transfer**: If you have live production data, you'll need to dump (pg_dump) and restore (pg_restore) to Cloud SQL.
- **Connectivity**: Cloud SQL often requires the **Cloud SQL Auth Proxy** for local development, unlike Azure Postgres which often exposes a public IP (with firewall rules).

### Latency & Region
- Ensure all resources (Cloud Run, Cloud SQL, Storage, Vertex AI) are in the **same region** (e.g., `asia-south1` Mumbai or `us-central1`) to minimize latency and data transfer costs. Vertex AI model availability varies by region.
