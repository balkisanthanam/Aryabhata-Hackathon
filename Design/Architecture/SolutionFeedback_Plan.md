# Implementation Blueprint: Solution Evaluator

This document serves as a step-by-step technical guide for building the **Solution Evaluator** module within the **Aryabhata** ecosystem. This architecture is designed to handle the latency of the Gemini model while providing a resilient, "fail-safe" experience for **Viswanathan’s** JEE preparation.

---

## **Phase 1: Foundation & Infrastructure**

Before writing code, establish the "plumbing" to ensure data persistence and reliable message delivery.

### **1. Azure Storage Configuration**

* **Blob Storage**: Create a container named `student-solutions` to store uploaded images.
* **Storage Queue**: Create a queue named `evaluator-jobs` to serve as the trigger for your worker.

### **2. PostgreSQL Schema Setup**

Create the `solution_evaluations` table to act as the permanent "Source of Truth" for all feedback.

* `id`: UUID (Primary Key)
* `student_id`: References your Users table.
* `status`: Enum (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).
* `image_url`: Text (link to the Blob).
* `feedback_json`: JSONB (to store the detailed teacher-like response).
* `created_at/updated_at`: Timestamps.

---

## **Phase 2: The Interface Contract**

Define the data structures that will travel through the system. Consistent interfaces prevent integration errors across Node.js, the Azure Function, and React.

### **The Message (Input)**

```typescript
interface EvaluationJob {
  jobId: string;
  studentId: string;
  blobUrl: string;
  subject: string;
  chapterId?: string; // Essential for NCERT-specific context
}

```

### **The Feedback (Output)**

```typescript
interface SolutionFeedback {
  status: 'COMPLETED' | 'FAILED';
  ocrText: string;
  isCorrect: boolean;
  steps: {
    stepNumber: number;
    description: string;
    isCorrect: boolean;
    correctionHint?: string;
  }[];
  finalTeacherNote: string;
}

```

---

## **Phase 3: The Worker (Azure Function)**

Refine your existing prototype into a robust, queue-triggered background worker.

* **Trigger**: Configure as an **Azure Storage Queue Trigger** on `evaluator-jobs`.
* **Gemini Logic**:
* Fetch the image from the `blobUrl`.
* Use a **System Prompt** that enforces the `SolutionFeedback` JSON structure.
* Implement **Exponential Backoff** (3 retries) for model rate limits.


* **Database Write**: Directly update the PostgreSQL row for the specific `jobId` once the evaluation is complete.

---

## **Phase 4: The Backend "Plumber" (Node.js)**

Your monolithic server coordinates the interaction between the student and the worker.

* **Submission Endpoint (`POST /evaluations`)**:
1. Receives the image.
2. Saves to Blob Storage.
3. Creates the `PENDING` database record.
4. Pushes the `EvaluationJob` message to the Azure Queue.


* **Status Endpoint (`GET /evaluations/:id`)**:
1. A simple indexed lookup that returns the current status and `feedback_json` from PostgreSQL.



---

## **Phase 5: The Student Experience (React UI)**

Use **Stitch** to iterate on the visual states and **Antigravity** to wire the polling logic.

* **State Management**:
* **Idle**: The "Solution Evaluator" card with the **18px Lora caption**.
* **Processing**: A "Guru is analyzing..." screen with a progress indicator.
* **Resolved**: The detailed feedback view showing steps and the "Teacher Note."


* **The Polling Hook**:
* Implement a `useSolutionStatus` hook that queries the Status Endpoint every 5–10 seconds.
* Include a 2-minute timeout that gracefully handles any rare model failures by showing a "Retry" option.



---

### **Success Checklist**

* [ ] Azure Storage Queue receives a message upon upload.
* [ ] Azure Function wakes up and logs the incoming `jobId`.
* [ ] Gemini returns valid JSON matching our `SolutionFeedback` interface.
* [ ] PostgreSQL record updates from `PENDING` to `COMPLETED`.
* [ ] React UI stops polling and reveals the feedback automatically.
