# Solution Evaluation — Python Durable Function Implementation Plan

**Date**: February 2026  
**Status**: Approved  
**Branch**: `feature/studentfeedback`

---

## TL;DR

Fully standalone Python Azure Durable Function in `pipelines/AzureFunctions/StudentEvaluationFunction/`. Triggered by `feedback-jobs` queue. Reads/writes only the `solution_evaluations` DB table. TS server handles UX input/output + queue push (Phase 2). No cross-language dependencies.

Reuses proven Gemini call patterns from `function_app.py` and PIL cropping from `apps/backend/experiment/validate_split.py`. Three Gemini models. Input validation after text parsing. Test script for end-to-end verification.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  TS Server (apps/server/ or apps/functions/) │  ← PHASE 2
│  POST /evaluations                           │
│    → validate basic inputs (image non-empty) │
│    → INSERT solution_evaluations (PENDING)   │
│    → push jobId to feedback-jobs queue       │
│    → return 202 to UX                        │
│                                              │
│  GET /evaluations/:id                        │
│    → SELECT status, feedback_json            │
│    → return to UX                            │
└──────────────────┬──────────────────────────┘
                   │ queue message (jobId)
                   ▼
┌─────────────────────────────────────────────┐
│  Python Durable Function (standalone)        │  ← PHASE 1
│  pipelines/AzureFunctions/                   │
│       StudentEvaluationFunction/             │
│                                              │
│  Queue trigger → Orchestrator (unified flow) │
│    → Activity: read DB record                │
│    → Activity: fetch student images          │
│    → Activity: fetch textbook images (opt.)  │
│    → Activity: parse text reference          │
│    → Activity: validate inputs (chapter etc) │
│    → Activity: get chapter PDF               │
│    → Activity: batch evaluate (fan-out ×N)   │
│         ↑ full student pages sent to each    │
│         ↑ optional textbook pages as context │
│         ↑ batch of 3 problems (default)      │
│    → Activity: update DB (COMPLETED/FAILED)  │
└─────────────────────────────────────────────┘
```

**Interface**: `solution_evaluations` table only. No HTTP calls between TS and Python.

---

## Phase 1: Azure Durable Function (this phase)

### Unified Flow (v4)

**Pipeline steps:**
1. Read evaluation record from DB
2. Fetch student work images (download, no Gemini call)
3. Optionally fetch textbook page images (if `problem_image_url` provided — download only)
4. Parse text reference → structured problem numbers (Gemini flash-lite)
5. Validate all inputs (class, board, subject, chapter resolved?)
6. Get chapter PDF from ChapterData table
7. Batch evaluate — direct (fan-out, `EVAL_BATCH_SIZE` problems per Gemini call, default 3)
   - ALL student pages sent to each batch, Gemini locates the relevant work
   - Optional textbook page images sent as reference context (labeled `[TEXTBOOK PAGE N]`)
8. Update DB

> **v4 Architecture Decision**: Unified single flow — always requires `problem_text_ref`.
> The student must always specify which problems they solved (e.g. "13.8, 13.9").
> `problem_image_url` (textbook photo) is optional reference context — full page images
> are forwarded to Gemini alongside the chapter PDF, not split/cropped.
>
> Previous Path A/B branching has been collapsed. `split_textbook` and `split_student_hw`
> activities are retained as legacy but unused in the main flow.
>
> Batch size is parameterized via `EVAL_BATCH_SIZE` env var (default: 3).

### Gemini Models

| Task | Model | Rationale |
|------|-------|-----------|
| Solution evaluation | `gemini-3-pro-image-preview` | Supports image output for diagrams in solutions |
| Image splitting / bounding boxes | `gemini-3-pro-preview` | Proven in experiment (`validate_split.py`) |
| Text reference parsing | `gemini-2.5-flash-lite` | Lightweight, fast for structured text extraction |

### File Structure

```
StudentEvaluationFunction/
├── function_app.py              (MODIFY — register orchestrator + activities + queue trigger)
├── orchestrator.py              (v4 — unified single flow, no Path A/B branching)
├── host.json                    (MODIFY — add durableTask config if needed)
├── requirements.txt             (MODIFY — add dependencies)
├── local.settings.json          (NEW)
├── PLAN.md                      (this file)
├── utils/
│   ├── __init__.py
│   ├── gemini_client.py         (NEW — extract + enhance from function_app.py)
│   ├── db.py                    (NEW — psycopg2 + Azure AD token)
│   ├── blob_storage.py          (NEW — extract from function_app.py)
│   ├── image_processing.py      (NEW — port from validate_split.py)
│   └── prompt_loader.py         (NEW — extract from function_app.py)
├── activities/
│   ├── __init__.py
│   ├── read_evaluation.py
│   ├── fetch_student_images.py   (v3 — simple image downloader; reused for textbook images)
│   ├── split_student_hw.py       (legacy — retained but unused in main flow)
│   ├── parse_text_ref.py
│   ├── split_textbook.py         (legacy — retained but unused in v4 unified flow)
│   ├── validate_inputs.py        (v4 — always requires parsed_ref)
│   ├── get_chapter_pdf.py
│   ├── evaluate_batch.py         (v4 — unified eval, optional textbook pages)
│   ├── evaluate_batch_v1_split_based.py  (backup of pre-v3)
│   └── update_evaluation.py
├── tests/
│   ├── test_activities.py       (v4 — CLI tool for isolated activity testing)
│   ├── test_durable_e2e.py      (NEW — end-to-end test)
│   ├── test_helper.py           (KEEP — useful base64/payload helpers)
│   ├── test_prod.py             (KEEP — production test client)
│   ├── sample_problem.txt       (KEEP)
│   ├── test_response.json       (KEEP — reference output)
│   └── test_response_azure.json (KEEP — reference output)
```

### Step 1: Project Restructure + Dependencies

1. Extract existing utilities from `function_app.py` into `utils/` modules.
2. Add dependencies to `requirements.txt`:
   - `azure-functions-durable` — Durable Functions SDK
   - `psycopg2-binary` — PostgreSQL access
   - `Pillow` — image cropping (proven in experiment)
3. Create `local.settings.json` with `AzureWebJobsStorage`, DB params, queue connection.
4. Clean up obsolete documentation files.

### Step 2: Shared Utilities

**`utils/gemini_client.py`** — extracted + enhanced from `function_app.py`:
- `get_api_key()` — Key Vault retrieval (`<KEY_VAULT_SECRET_NAME>` from `<KEY_VAULT_HOSTNAME>`), in-memory cache.
- `call_gemini(model_id, content_parts, response_json=False)` — generic call with:
  - Exponential backoff (3 retries, 5s/10s/20s) — from `validate_split.py`.
  - JSON response parsing via `response_mime_type="application/json"`.
  - Content part ordering preserved from prototype.
- Model constants: `MODEL_EVALUATION`, `MODEL_BOUNDING_BOX`, `MODEL_TEXT_PARSE`.

**`utils/db.py`** — new:
- PostgreSQL via `psycopg2` with Azure AD token.
- `read_evaluation(job_id)`, `update_evaluation(job_id, status, feedback_json)`.
- Connection pooling `max_connections=1` (serverless-safe).

**`utils/image_processing.py`** — ported from `validate_split.py` lines 103-171:
- `crop_from_bounding_box(image_bytes, box_2d)` — 0–1000 → pixel, PIL crop.
- `group_and_stitch(solutions, image_bytes)` — multi-part vertical stitching on white canvas.
- `upload_cropped_images(cropped_images)` → temp blob container.

**`utils/blob_storage.py`** — extracted from `function_app.py`:
- `fetch_blob_content(url, as_text)` — Managed Identity with public fallback.

**`utils/prompt_loader.py`** — extracted from `function_app.py`:
- `load_prompt(prompt_name)` → from `<BLOB_STORAGE_URL>/feedback/{prompt_name}.txt`.
- `fill_template(template, **kwargs)` → placeholder substitution.
- In-memory cache.

### Step 3: Activity Functions

| Activity | Input | Core Logic | Output |
|----------|-------|------------|--------|
| `read_evaluation` | `job_id` | Read DB row, set PROCESSING, idempotency check | Record dict or `{skip: true}` |
| `fetch_student_images` | `student_work_url` (str or list) | Download student work images, convert to base64 — NO Gemini call | `{pages: [{page_index, image_b64}], page_count}` |
| `parse_text_ref` | `problem_text_ref, class, board, subject, chapter_title` | Gemini (`gemini-2.5-flash-lite`) + Text_ParsingPrompt | `{metadata, exercises[{exercise_label, problem_numbers[]}]}` |
| `validate_inputs` | Record fields + parsed ref | Check class, board, subject, chapter all resolved | `{valid, resolved: {...}}` or `{valid: false, error: "..."}` |
| `get_chapter_pdf` | `class, board, subject, chapter_id/number/title` | DB query ChapterData (PK → exact → ILIKE fallback) | `{pdf_url, pdf_bytes_b64, chapter_title}` |
| `split_textbook` | `problem_image_url` | Gemini (`gemini-3-pro-preview`) + TBD Prompt → PIL crop | `[{problem_id, image_b64, confidence}]` |
| `evaluate_batch` | `{problems[], student_pages_b64[], class, subject, chapter_title, pdf_bytes_b64?, textbook_pages_b64?}` | Gemini (`gemini-3-pro-image-preview`) + Evaluation prompt — ONE call per batch of ≤3 problems, ALL student pages + optional textbook page images included | `{evaluations: [{problem_id, found_in_student_work, evaluation_status, feedback_for_student, full_solution}], _meta}` |
| `update_evaluation` | `job_id, status, feedback_json` | UPDATE solution_evaluations | `{success}` |
| `split_student_hw` (legacy) | `student_work_url` | Gemini bounding-box + PIL crop — retained but unused in v3 flow | `{solutions: [...]}` |

### Step 4: Orchestrator (v4 — unified flow)

```python
# Pseudocode (v4)
BATCH_SIZE = int(os.environ.get("EVAL_BATCH_SIZE", "3"))

def orchestrator(ctx):
    job_id = ctx.get_input()
    
    record = yield ctx.call_activity("read_evaluation", job_id)
    if record.get("skip"): return
    
    # Require text reference
    if not record.get("problem_text_ref"):
        fail("problem_text_ref is required")
    
    # Fetch student images (download only, no Gemini)
    fetch_result = yield ctx.call_activity("fetch_student_images", {
        "student_work_url": record["student_work_url"]
    })
    student_pages_b64 = [p["image_b64"] for p in fetch_result["pages"]]
    
    # Optionally fetch textbook page images (reuse same downloader)
    textbook_pages_b64 = []
    if record.get("problem_image_url"):
        tb_fetch = yield ctx.call_activity("fetch_student_images", {
            "student_work_url": record["problem_image_url"]
        })
        textbook_pages_b64 = [p["image_b64"] for p in tb_fetch["pages"]]
    
    batch_size = record.get("batch_size", BATCH_SIZE)
    
    parsed = yield ctx.call_activity("parse_text_ref", {...})
    validation = yield ctx.call_activity("validate_inputs", {...})
    chapter = yield ctx.call_activity("get_chapter_pdf", {...})
    
    # Build problem list, chunk, fan-out
    all_problems = [{"problem_id": p["problem_number"], ...} for p in resolved["problems"]]
    batches = chunk(all_problems, batch_size)
    
    tasks = [ctx.call_activity("evaluate_batch", {
        "problems": batch,
        "student_pages_b64": student_pages_b64,
        "class": ..., "subject": ..., "chapter_title": ...,
        "pdf_bytes_b64": chapter.get("pdf_bytes_b64"),
        "textbook_pages_b64": textbook_pages_b64,  # optional reference
    }) for batch in batches]
    results = yield ctx.task_all(tasks)
    
    feedback = aggregate_results(results)
    yield ctx.call_activity("update_evaluation", {
        "job_id": job_id, "status": "COMPLETED", "feedback_json": feedback
    })
```

### Step 5: Queue Trigger

```python
# In function_app.py
@app.queue_trigger(arg_name="msg", queue_name="feedback-jobs", connection="FEEDBACK_QUEUE_CONNECTION")
@app.durable_client_input(client_name="client")
async def feedback_queue_trigger(msg: func.QueueMessage, client):
    job_id = msg.get_body().decode("utf-8")
    instance_id = await client.start_new("evaluation_orchestrator", instance_id=job_id, client_input=job_id)
    logging.info(f"Started orchestration {instance_id} for job {job_id}")
```

### Step 6: TBD Prompts

| Prompt | File | Model | Description |
|--------|------|-------|-------------|
| TBD #1 | `SplitTextBookProblems.txt` | `gemini-3-pro-preview` | Bounding boxes for printed textbook problems |
| TBD #2 | `BatchEvaluation_TextRef.txt` | `gemini-3-pro-image-preview` | Batch eval: problem number + PDF → evaluation results |
| TBD #3 | `BatchEvaluation_ImageRef.txt` | `gemini-3-pro-image-preview` | Batch eval: problem image → evaluation results |

All stored in blob: `<BLOB_STORAGE_URL>/feedback/`

### Step 7: End-to-End Test Script

`tests/test_durable_e2e.py`:
1. Insert test `solution_evaluations` row (PENDING) with sample data.
2. Push `jobId` to `feedback-jobs` queue.
3. Poll DB every 5s for status change.
4. Assert: COMPLETED, valid `feedback_json` with expected fields.
5. Cleanup: delete test row and temp blobs.
6. Failure test: invalid image URL → assert FAILED with meaningful error.

---

## Phase 2: UX + Azure Functions Server (this phase)

**Date**: February 2026  
**Status**: In Progress  
**UX Spec**: `Design/Architecture/SolutionFeedback_UX.md`

### Architecture

```
┌──────────────────────────────────────────────────────┐
│  React Frontend (apps/FrontEnd/)                      │
│  SolutionFeedback.tsx                                 │
│    → Zustand store (useFeedbackStore.ts)              │
│    → 3 zones: Action Area / Dropdown / Viewing Space  │
│    → Polls GET /api/evaluations/{id} every 10s        │
│    → multipart/form-data upload to POST /evaluations  │
└──────────────┬───────────────────────────────────────┘
               │ HTTP
               ▼
┌──────────────────────────────────────────────────────┐
│  Azure Functions (apps/functions/)                    │
│                                                       │
│  POST /api/evaluations         (submitEvaluation)     │
│    → parse multipart/form-data                        │
│    → upload images to Blob Storage                    │
│    → INSERT solution_evaluations (PENDING)            │
│    → push jobId to feedback-jobs queue                │
│    → return 202 { jobId }                             │
│                                                       │
│  GET /api/evaluations/completed (getCompletedEvals)   │
│    → SELECT COMPLETED for userId                      │
│    → return lightweight list (no feedback_json)        │
│                                                       │
│  GET /api/evaluations/last     (getLastEvaluation)    │
│    → SELECT latest by created_at (any status)         │
│    → return full record                               │
│                                                       │
│  GET /api/evaluations/{id}     (getEvaluationById)    │
│    → SELECT by UUID                                   │
│    → return full record                               │
└──────────────────────────────────────────────────────┘
               │ queue message (jobId)
               ▼
┌──────────────────────────────────────────────────────┐
│  Python Durable Function (Phase 1 — DONE)             │
│  pipelines/AzureFunctions/StudentEvaluationFunction/  │
│  Queue trigger → Orchestrator → DB update             │
└──────────────────────────────────────────────────────┘
```

### Server Implementation (apps/functions/)

#### New Dependencies
- `@azure/storage-queue` — push job IDs to feedback-jobs queue
- `busboy` + `@types/busboy` — parse multipart/form-data
- `uuid` + `@types/uuid` — generate evaluation UUIDs

#### New Utilities
| File | Purpose |
|------|---------|
| `src/utils/queue.ts` | Push messages to `feedback-jobs` queue on `<QUEUE_STORAGE_ACCOUNT>` |
| `src/utils/blob-upload.ts` | Upload image files to `kalidasa/feedback/student-uploads/{userId}/{jobId}/` |

#### New Azure Functions
| Function | Route | Method | Description |
|----------|-------|--------|-------------|
| `submitEvaluation` | `/api/evaluations` | POST | Parse multipart, upload blobs, INSERT, push queue |
| `getCompletedEvaluations` | `/api/evaluations/completed` | GET | List COMPLETED evaluations (lightweight) |
| `getLastEvaluation` | `/api/evaluations/last` | GET | Latest evaluation by created_at (any status) |
| `getEvaluationById` | `/api/evaluations/{id}` | GET | Single evaluation by UUID |

#### Prisma Schema Addition
```prisma
model solution_evaluations {
  id               String   @id @default(dbgenerated("gen_random_uuid()")) @db.Uuid
  userid           Int
  class            String?  @db.VarChar(100)
  board            String?  @db.VarChar(100)
  subject          String   @db.VarChar(50)
  chapter_id       Int?
  chapter_title    String?  @db.VarChar(255)
  chapter_number   String?  @db.VarChar(50)
  pdffileurl       String?  @db.VarChar(500)
  status           String   @default("PENDING")
  problem_text_ref String?  @db.VarChar(500)
  problem_image_url String?
  student_work_url String
  feedback_json    Json?
  pipeline_steps   Json?
  current_step     String?  @db.VarChar(100)
  created_at       DateTime @default(now()) @db.Timestamptz(6)
  updated_at       DateTime @default(now()) @db.Timestamptz(6)
  userprofiledata  userprofiledata @relation(fields: [userid], references: [userid])

  @@index([userid], map: "ix_evaluations_student_userid")
  @@index([status], map: "ix_evaluations_student_status")
  @@index([userid, status], map: "ix_evaluations_student_userid_status")
}
```

#### Environment Variables (local.settings.json)
| Variable | Value |
|----------|-------|
| `FEEDBACK_QUEUE_CONNECTION` | Connection string for `<QUEUE_STORAGE_ACCOUNT>` |
| `AZURE_STORAGE_ACCOUNT_NAME` | `kalidasa` (already set) |
| `AZURE_STORAGE_KEY` | (already set) |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` | (already set) |

### Frontend Implementation (apps/FrontEnd/)

#### New Files
| File | Purpose |
|------|---------|
| `src/types/evaluation.ts` | TypeScript types for evaluation data |
| `src/store/useFeedbackStore.ts` | Zustand store — polling, submissions, selected evaluation |
| `src/components/feedback/ImageUploadZone.tsx` | Drag-drop image upload with previews |
| `src/components/feedback/EvaluationSummary.tsx` | Summary card (correct/acceptable/incorrect counts) |
| `src/components/feedback/EvaluationCard.tsx` | Per-problem evaluation display |
| `src/components/feedback/ProcessingIndicator.tsx` | Animated processing state with timer |

#### Modified Files
| File | Change |
|------|--------|
| `src/lib/api.ts` | Add 4 API functions for evaluation endpoints |
| `src/pages/SolutionFeedback.tsx` | Complete rewrite — 3-zone layout, real data, polling |

#### Mobile Responsiveness
- Mobile-first Tailwind (`sm:`, `md:`, `lg:` breakpoints)
- Stacked layout on mobile, side-by-side on desktop where appropriate
- Touch-friendly upload zones (min 44px tap targets)
- Responsive typography and spacing

#### State Management (Zustand)
```
useFeedbackStore {
  // State
  completedEvaluations: EvaluationSummaryItem[]
  lastEvaluation: Evaluation | null
  selectedEvaluation: Evaluation | null
  activeJobId: string | null
  isSubmitting: boolean
  isPolling: boolean

  // Actions
  fetchInitialData(userId)
  submitEvaluation(formData)
  selectEvaluation(id)
  startPolling(jobId)
  stopPolling()
}
```

#### Polling Logic
1. On submit → set `activeJobId`, start 10s interval
2. Each tick → `GET /api/evaluations/{activeJobId}`
3. If COMPLETED/FAILED → stop polling, update store, show result or notify
4. On page load → check `lastEvaluation` status, resume polling if PENDING/PROCESSING
5. On unmount → clear interval

### Key Design Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Image upload | Server-side (not browser-direct-to-blob) | Simpler auth, blob URLs stay private |
| State management | Zustand | Already in project (v4.5.7), lightweight |
| FAILED in dropdown | Excluded | No useful content to display |
| Last job query | Any status (not just COMPLETED/FAILED) | Resume polling for in-progress jobs |
| Polling interval | 10 seconds | Balance between responsiveness and cost |
| Upload limits | 5 images/zone, 10MB each, JPG/PNG/PDF | Practical for handwritten homework |
| Multipart parsing | `busboy` library | Standard Node.js streaming multipart parser |

---

## Prompts Reference

| Prompt | Location | Status |
|--------|----------|--------|
| Evaluation (multi-problem, v3) | `Feedback/Prompt/Evaluation.txt` + blob | Complete — v3 direct eval |
| Evaluation (single-problem, v1 backup) | `Feedback/Prompt/Evaluation_v1_split_based.txt` + blob | Archived |
| Student HW Split (V3) | `apps/backend/experiment/Student_HW_Split.md` | Complete (legacy, unused in v3 flow) |
| Text Parsing | `apps/backend/experiment/Text_ParsingPrompt.md` | Complete |
| Split Textbook Problems | TBD #1 | To develop |

## Azure Resources

| Resource | Value |
|----------|-------|
| Key Vault | `<KEY_VAULT_HOSTNAME>` |
| Key Vault Secret | `<KEY_VAULT_SECRET_NAME>` |
| Blob Storage | `<BLOB_STORAGE_HOST>` |
| Prompts Container | `feedback` |
| Queue Storage | `<QUEUE_STORAGE_ACCOUNT>.queue.core.windows.net` |
| Queue Name | `feedback-jobs` |
| Function App | `<FUNCTION_APP_NAME>` |

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Fully decoupled — Python function + DB interface | No cross-language dependencies |
| Language | Python | Proven Gemini + PIL code, no porting risk |
| Location | Evolve existing prototype in-place | Git history preserved |
| Evaluation model | `gemini-3-pro-image-preview` | Image output for diagrams |
| Bounding box model | `gemini-3-pro-preview` | Proven in experiment |
| Text parsing model | `gemini-2.5-flash-lite` | Lightweight, fast |
| Input validation | Post-parse activity | Catches missing chapter early |
| Chapter lookup | ILIKE on VARCHAR | No embeddings available |
| Chapter title grounding | Inject valid titles into Gemini parsing prompt | Gemini maps user shorthand (e.g. "thermalprops") to canonical DB title |
| Subject normalization | Alias dict in validate_inputs (`Mathematics→Maths`, `Phy→Physics`, etc.) | Cheap, no model call; UX already sends canonical values via API |
| Batch size | 3 problems per Gemini call (parameterized via `EVAL_BATCH_SIZE`) | Quality degrades at 7+; input tokens fine even for 50 images |
| Student image handling | Send full pages directly — no split/crop | Bounding-box crop unreliable for handwriting (chemistry structures, corrections) |
| Textbook image handling | Send full pages as optional context — no split/crop | Same cropping reliability issues as student images; Gemini handles full pages well |
| Unified flow (v4) | Single pipeline — always require text ref, textbook image optional | Eliminates Path A/B branching; simpler code, same Gemini quality |
| Idempotency | Instance ID + DB status check | Prevents duplicates |
| Image library | Pillow (PIL) | Used for textbook splitting; student images sent raw |

