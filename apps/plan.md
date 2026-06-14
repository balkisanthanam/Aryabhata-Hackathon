# Migration Plan: Node.js Middleware to Azure Functions v4

## Overview

This document outlines the migration strategy for moving the Express-based middleware in [apps/server/src/routes/api.ts](apps/server/src/routes/api.ts) to Azure Functions v4 in `apps/functions`.

---

## Current Architecture Analysis

### Existing Express Routes in `api.ts`

| Route | Method | Purpose |
|-------|--------|---------|
| `/auth/login` | POST | User authentication/session initialization |
| `/user/resume` | GET | Fetch last attempted question for resume functionality |
| `/practice/dashboard` | GET | Get dashboard data (classes, subjects, chapters) |
| `/practice/question` | GET | Fetch question content with SAS token injection |
| `/practice/progress` | POST | Save user progress |

### Key Dependencies
- **Prisma Client** - Database operations
- **Azure Storage SDK** - SAS token generation for blob URLs
- **Session Configuration** - Hardcoded `sessionUser` object

### Response Pattern (Express)
```typescript
res.json({ data }); // Success
res.status(400).json({ error: 'message' }); // Error
```

---

## Target Architecture

### Azure Functions v4 Structure

```
apps/functions/
├── src/
│   ├── functions/
│   │   ├── authLogin.ts
│   │   ├── userResume.ts
│   │   ├── practiceDashboard.ts
│   │   ├── practiceQuestion.ts
│   │   └── practiceProgress.ts
│   ├── utils/
│   │   ├── prisma.ts          # Already created
│   │   ├── azure-storage.ts   # Port from server
│   │   └── session.config.ts  # Port from server
│   └── types/
│       └── index.ts           # Shared TypeScript interfaces
├── host.json
├── local.settings.json
├── package.json
└── tsconfig.json
```

---

## Migration Steps

### Phase 1: Project Setup

1. **Initialize Azure Functions Project**
   - Create `apps/functions` directory
   - Initialize with `func init --typescript --model V4`
   - Configure `host.json` for HTTP triggers with custom routes

2. **Configure TypeScript**
   - Ensure `tsconfig.json` targets ES2020+
   - Enable strict mode for type safety
   - Configure path aliases if needed

3. **Install Dependencies**
   - `@azure/functions` (v4)
   - `@prisma/client` + `prisma`
   - `@azure/storage-blob`
   - `@azure/identity`

4. **Copy & Adapt Shared Utilities**
   - Port `azure-storage.ts` (SAS token generation)
   - Port `session.config.ts` (temporary hardcoded user)
   - Verify `prisma.ts` utility works with Prisma 7

### Phase 2: Response Model Transformation

**Express Response → Azure Functions v4 HttpResponseInit**

| Express Pattern | Azure Functions v4 Pattern |
|-----------------|---------------------------|
| `res.json(data)` | `return { jsonBody: data }` |
| `res.status(400).json({ error })` | `return { status: 400, jsonBody: { error } }` |
| `res.status(500).json({ error })` | `return { status: 500, jsonBody: { error } }` |

**Key Differences:**
- Express mutates `res` object; Azure Functions returns `HttpResponseInit`
- No `next()` middleware pattern; each function is self-contained
- Query params accessed via `request.query.get('param')` instead of `req.query.param`
- Body accessed via `await request.json()` instead of `req.body`

### Phase 3: Route-by-Route Migration

#### 3.1 `authLogin.ts`
- **Trigger**: HTTP POST `/api/auth/login`
- **Logic**: 
  - Query `userprofiledata` using Prisma
  - Return user profile or fallback session info
- **Response Mapping**:
  - Success: `{ jsonBody: { userId, userName, ... } }`
  - Error: `{ status: 500, jsonBody: { error: 'message' } }`

#### 3.2 `userResume.ts`
- **Trigger**: HTTP GET `/api/user/resume`
- **Logic**:
  - Query `userexercisedata` with `chapterdata` include
  - Return last attempt or null
- **Response Mapping**:
  - No data: `{ jsonBody: null }`
  - Success: `{ jsonBody: { chapterId, questionId, ... } }`

#### 3.3 `practiceDashboard.ts`
- **Trigger**: HTTP GET `/api/practice/dashboard`
- **Logic**:
  - Complex multi-query flow for classes, subjects, chapters
  - Query params: `class`, `subject`, `board`
- **Query Param Access**:
  ```typescript
  const queryClass = request.query.get('class');
  ```
- **Response Mapping**:
  - Success: `{ jsonBody: { supportedClasses, chapters, ... } }`

#### 3.4 `practiceQuestion.ts`
- **Trigger**: HTTP GET `/api/practice/question`
- **Logic**:
  - Mode-based question fetching (start/resume)
  - SAS token injection for blob URLs
  - Next/prev question calculation
- **Critical**: Port `generateSasUrl` utility
- **Response Mapping**:
  - Not found: `{ status: 404, jsonBody: { error: 'message' } }`
  - Success: `{ jsonBody: { questionId, content, ... } }`

#### 3.5 `practiceProgress.ts`
- **Trigger**: HTTP POST `/api/practice/progress`
- **Logic**:
  - Parse JSON body: `await request.json()`
  - Create `userexercisedata` record
- **Body Access**:
  ```typescript
  const { chapterId, exerciseId, questionId } = await request.json() as ProgressPayload;
  ```
- **Response Mapping**:
  - Success: `{ jsonBody: { success: true, entryId } }`

### Phase 4: Shared Utilities

#### 4.1 Prisma Client Singleton
- Already created at `src/utils/prisma.ts`
- Ensure connection pooling is appropriate for serverless (use `connection_limit=1` or PgBouncer)
- Handle cold start implications

#### 4.2 Azure Storage Utility
- Port `generateSasUrl` function from [apps/server/src/utils/azure-storage.ts](apps/server/src/utils/azure-storage.ts)
- Adapt initialization for serverless (lazy load credentials)
- Handle both Shared Key and Managed Identity auth

#### 4.3 Session Configuration
- Port `sessionUser` from [apps/server/src/config/session.config.ts](apps/server/src/config/) (path inferred)
- **Future**: Replace with proper auth (Azure AD B2C, Auth0, etc.)

### Phase 5: Configuration

#### 5.1 `host.json`
```json
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": "api"
    }
  }
}
```

#### 5.2 `local.settings.json`
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "node",
    "DATABASE_URL": "...",
    "AZURE_STORAGE_ACCOUNT_NAME": "...",
    "AZURE_STORAGE_KEY": "..."
  }
}
```

#### 5.3 Route Registration (v4 Model)
Each function self-registers via `app.http()`:
```typescript
import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";

app.http('authLogin', {
    methods: ['POST'],
    authLevel: 'anonymous', // or 'function' for key-based
    route: 'auth/login',
    handler: authLoginHandler
});
```

### Phase 6: Testing Strategy

1. **Local Testing**
   - Use Azure Functions Core Tools (`func start`)
   - Test with same curl/Postman commands used for Express

2. **Integration Testing**
   - Verify Prisma queries return expected data
   - Verify SAS tokens are generated correctly
   - Test cold start behavior

3. **Frontend Compatibility**
   - Update [apps/FrontEnd/src/lib/api.ts](apps/FrontEnd/src/lib/api.ts) `baseURL` to point to Functions endpoint
   - Verify all API calls work unchanged (same request/response shapes)

### Phase 7: Deployment

1. **Azure Resources**
   - Create Function App (Node.js 20 LTS, Consumption Plan)
   - Configure Application Settings (env vars)
   - Enable Managed Identity for Key Vault/Storage access

2. **CI/CD**
   - Add GitHub Actions workflow for `apps/functions`
   - Deploy on push to main branch

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Cold start latency | Use Premium Plan or keep-warm pings; optimize imports |
| Prisma connection limits | Use `connection_limit=1` in DATABASE_URL; consider PgBouncer |
| SAS token errors | Cache credentials; handle auth failures gracefully |
| Breaking frontend | Maintain exact same response shapes; test thoroughly |

---

## Success Criteria

- [ ] All 5 routes migrated and functional
- [ ] Frontend works without code changes (only baseURL update)
- [ ] Local development workflow documented
- [ ] Response times comparable to Express server
- [ ] Error handling consistent with original implementation

---

## Timeline Estimate

| Phase | Duration |
|-------|----------|
| Phase 1: Setup | 1-2 hours |
| Phase 2-3: Migration | 4-6 hours |
| Phase 4-5: Utilities & Config | 2-3 hours |
| Phase 6-7: Testing & Deploy | 2-4 hours |
| **Total** | **9-15 hours** |

---

## Next Steps

1. Review this plan and confirm approach
2. Initialize Azure Functions project in `apps/functions`
3. Begin Phase 1 setup
4. Migrate routes one-by-one, testing after each

---
---

# Student Evaluation Pipeline — Micro-State Checkpointing

## Overview

The Student Evaluation Durable Function pipeline (`pipelines/AzureFunctions/StudentEvaluationFunction`)
processes student homework evaluations through an 8-step orchestrator. This section adds micro-state
checkpointing for **recovery on failure**, **production debugging**, and **fine-tuning data collection**.

### Goals

| Goal | Description |
|------|-------------|
| **Recovery** | Resume a failed pipeline from the last successful step instead of re-running from scratch |
| **Debugging** | Per-step timing, model info, and status visible in the DB for production troubleshooting |
| **Fine-tuning** | Capture Gemini model outputs, token usage, prompt versions, and raw responses for future model fine-tuning |

---

## Architecture

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage location | JSONB column on `solution_evaluations` | Fewer joins, atomic updates, single table query |
| Large artifacts | Blob storage (`pipeline-artifacts/`) | Keep JSONB lean (<1 MB), images/PDFs stay in blob |
| Checkpoint mechanism | Durable Functions activities | Keeps orchestrator deterministic (no direct DB calls) |
| JSONB vs separate table | JSONB | 1:1 relationship, no N+1 queries, simpler schema |
| Gemini enrichment | Return `{result, raw_text, model, usage}` | Activities decide what to checkpoint |

### Pipeline Steps (Checkpointed)

```
1. read_evaluation      — DB read, PENDING → PROCESSING
2. split_student_hw     — Gemini bounding box → crop student solutions
3. parse_text_ref       — (Path A) Parse text reference with Gemini
   split_textbook       — (Path B) Split textbook image with Gemini
4. validate_inputs      — Resolve class/subject/chapter, validate
5. get_chapter_pdf      — Fetch reference PDF from blob
6. match_solutions      — In-memory matching (no activity, logged in JSONB)
7. evaluate_batch[]     — Fan-out Gemini evaluation (N batches)
8. update_evaluation    — Write final feedback to DB
```

### JSONB Schema: `pipeline_steps`

```jsonc
{
  "split_student_hw": {
    "status": "completed",           // "started" | "completed" | "failed"
    "started_at": "2025-01-15T10:00:00Z",
    "completed_at": "2025-01-15T10:00:05Z",
    "duration_ms": 5000,
    "model": "gemini-3-pro-preview",
    "prompt_version": "Student_HW_Split.md",
    "token_usage": { "prompt_tokens": 1200, "completion_tokens": 400, "total_tokens": 1600 },
    "result_summary": { "solutions_detected": 3 },
    "artifact_urls": [ "pipeline-artifacts/{job_id}/split_student_hw/solution_0.jpg" ],
    "error": null
  },
  "evaluate_batch_0": {
    "status": "completed",
    "started_at": "...",
    "completed_at": "...",
    "duration_ms": 12000,
    "model": "gemini-3-pro-image-preview",
    "prompt_version": "Evaluation.txt",
    "token_usage": { "prompt_tokens": 8000, "completion_tokens": 2000, "total_tokens": 10000 },
    "result_summary": { "problems_in_batch": 3, "correct": 2, "incorrect": 1 },
    "error": null
  }
  // ... one entry per step
}
```

---

## DB Schema Changes

### New Columns

```sql
ALTER TABLE solution_evaluations
    ADD COLUMN pipeline_steps JSONB NULL,
    ADD COLUMN current_step VARCHAR(100) NULL;
```

- `pipeline_steps` — Full step-by-step checkpoint data (see JSONB schema above)
- `current_step` — The step currently in progress (for quick status queries)

### Indexes (optional, add later if needed)

```sql
-- Query failed pipelines by step
CREATE INDEX ix_evaluations_current_step ON solution_evaluations(current_step) WHERE status = 'PROCESSING';
-- Query step-level data (GIN for JSONB key lookups)
CREATE INDEX ix_evaluations_pipeline_steps ON solution_evaluations USING GIN (pipeline_steps);
```

---

## Implementation Components

### 1. `utils/checkpoint.py`

Two core functions using existing `_get_connection()` from `db.py`:

```python
def save_step(job_id, step_name, status, result_summary=None,
              model=None, prompt_version=None, token_usage=None,
              artifact_urls=None, error=None, duration_ms=None):
    """
    Upsert a step entry into pipeline_steps JSONB.
    Also updates current_step column.
    Uses jsonb_set() for atomic partial update.
    """

def load_step(job_id, step_name) -> dict | None:
    """
    Read a single step from pipeline_steps JSONB.
    Returns the step dict or None if not checkpointed.
    """
```

### 2. `utils/step_blob.py`

Helper for persisting large artifacts to blob storage:

```python
def save_artifact(job_id, step_name, filename, data_bytes, content_type) -> str:
    """
    Upload to: feedback/pipeline-artifacts/{job_id}/{step_name}/{filename}
    Returns the blob URL.
    """

def load_artifact(blob_url) -> bytes:
    """Fetch artifact bytes from blob storage."""
```

### 3. `gemini_client.py` — Enriched Return

Change `call_gemini()` to return a dict with metadata:

```python
# Before:
return json.loads(response.text)  # or response.text

# After:
return {
    "parsed_result": json.loads(response.text),  # or raw text
    "raw_response_text": response.text,
    "model": model_id,
    "usage_metadata": {
        "prompt_tokens": response.usage_metadata.prompt_token_count,
        "completion_tokens": response.usage_metadata.candidates_token_count,
        "total_tokens": response.usage_metadata.total_token_count,
    } if response.usage_metadata else None,
}
```

Activities extract `["parsed_result"]` for logic, pass full dict to checkpoint.

### 4. Orchestrator Checkpoint Pattern

Each step follows this flow:

```python
# Check if already completed (recovery)
cached = yield context.call_activity("load_checkpoint", {
    "job_id": job_id, "step_name": "split_student_hw"
})

if cached and cached["status"] == "completed":
    student_solutions = cached["result"]  # skip re-execution
else:
    # Save "started" checkpoint
    yield context.call_activity("save_checkpoint", {
        "job_id": job_id, "step_name": "split_student_hw",
        "status": "started"
    })

    # Execute the activity
    student_solutions = yield context.call_activity("split_student_hw", {...})

    # Save "completed" checkpoint
    yield context.call_activity("save_checkpoint", {
        "job_id": job_id, "step_name": "split_student_hw",
        "status": "completed",
        "result_summary": {"solutions_detected": len(student_solutions)},
        "model": "gemini-3-pro-preview",
        "prompt_version": "Student_HW_Split.md"
    })
```

### 5. Recovery Logic

In `read_evaluation`, detect PROCESSING state (crashed pipeline):

```python
# Current: only grab PENDING
WHERE id = %s AND status = 'PENDING'

# New: also grab PROCESSING (resume)
WHERE id = %s AND status IN ('PENDING', 'PROCESSING')
```

The orchestrator checks `pipeline_steps` and skips completed steps on replay.

### 6. RetryOptions

Add Durable Functions retry to idempotent activities:

```python
retry = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)

result = yield context.call_activity_with_retry(
    "get_chapter_pdf", retry, input_data
)
```

Applied to: `get_chapter_pdf`, `evaluate_batch`, `split_student_hw`, `split_textbook`, `parse_text_ref`.
NOT applied to: `read_evaluation` (must fail fast), `update_evaluation` (non-idempotent status writes).

---

## File Changes Summary

| File | Change |
|------|--------|
| `Scripts/DB_Master.sql` | Add ALTER TABLE for `pipeline_steps` and `current_step` |
| `utils/checkpoint.py` | **New** — `save_step()`, `load_step()` |
| `utils/step_blob.py` | **New** — `save_artifact()`, `load_artifact()` |
| `utils/gemini_client.py` | Enrich return value with model, tokens, raw response |
| `utils/db.py` | Update `read_evaluation()` to accept PROCESSING state for recovery |
| `activities/*.py` | Extract `["parsed_result"]` from enriched Gemini return; return richer metadata |
| `function_app.py` | Register `load_checkpoint` and `save_checkpoint` activities |
| `orchestrator.py` | Checkpoint-before/after pattern per step; recovery check; RetryOptions |

---

## Rollout Plan

1. Add DB columns (non-breaking — NULL columns)
2. Deploy `checkpoint.py` and `step_blob.py` utilities
3. Update `gemini_client.py` (backward compatible — activities updated in same deploy)
4. Update all activities to use enriched return
5. Rewrite orchestrator with checkpoint pattern
6. Deploy and test with a single job
7. Monitor `pipeline_steps` in DB for correctness

---

# Phase 3: Solution Feedback Quality & UX Overhaul

## Context

After a successful end-to-end evaluation of 4 pages of handwritten Chemistry solutions (problems 1-4, 6-8, 11-16), several quality and UX issues were identified:

### Observed Issues
1. **Wrong problem count**: "1 to 4, 6 to 8, 11 to 16" produced 16 problems (gap-filled) instead of 13
2. **Problem 4 duplicated**: Appeared as both "Q4 (Student Page 1)" and "4"
3. **Problem 2 missing**: Not parsed or evaluated
4. **Problems 1-3 errored**: "Problem not included in Gemini response" — batch 1 used student-page IDs instead of input IDs
5. **Errors not pinpointed**: Feedback says "partially incorrect" but doesn't say *exactly* which step diverged
6. **Equations not rendered**: Gemini doesn't always use LaTeX `$...$` delimiters
7. **Error presentation too subtle**: Status indicators are small badges, not prominent banners
8. **Sequential dump**: All problems shown at once, hard to focus on one
9. **Summary not interactive**: Can't click "3 Incorrect" to jump to those problems

### What's Deferred
- **Question image extraction** — showing the original question alongside feedback. Will build on the existing OnDemandImageExtraction infrastructure in a future iteration.

---

## Step 1: Fix Range Parsing Prompt

**File**: `pipelines/AzureFunctions/StudentEvaluationFunction/prompts/Text_ParsingPrompt.md`

**Problem**: "1 to 4, 6 to 8, 11 to 16" expands to 16 problems including gaps (5, 9, 10).

**Fix**: Add explicit rule — "When multiple comma-separated ranges appear, expand each independently. Do NOT fill gaps between ranges." Add a few-shot example showing this case.

---

## Step 2: Fix Evaluation Prompt — IDs, Error Pinpointing, LaTeX

**File**: `Feedback/Prompt/Evaluation.txt`

Three improvements in one prompt revision:

### 2a. Problem ID Consistency
Add strict constraint: "Use the EXACT `problem_id` from the input list. Do NOT prepend 'Q', do NOT append '(Student Page X)'. Echo IDs as-is."

### 2b. Error Pinpointing
Add instructions to:
- Identify the **exact step** where the student's solution diverges from correct
- **Quote the student's work** (what they wrote vs. what was expected)
- Categorize error granularly: sign error, unit conversion, wrong formula, algebraic error, conceptual misconception, incomplete reasoning
- Indicate **severity**: fundamental misunderstanding vs. minor slip

### 2c. LaTeX Formatting
Add: "Format ALL mathematical expressions, chemical formulas, and equations using LaTeX with `$...$` for inline and `$$...$$` for display. Use `\ce{}` for chemical formulas. Never output raw chemical formulas without LaTeX wrapping."

---

## Step 3: Fix Problem ID Echo in Batch Evaluation

**File**: `pipelines/AzureFunctions/StudentEvaluationFunction/activities/evaluate_batch.py`

**Fix**: When building the problem list for the prompt, explicitly state each problem_id. Change from:
```
- Problem 1 (Chapter: Organic Chemistry)
```
to:
```
- Problem ID: "1" — Problem 1 (Chapter: Organic Chemistry)
  You MUST use problem_id "1" in your response for this problem.
```

---

## Step 4: Post-Aggregation Validation in Orchestrator

**File**: `pipelines/AzureFunctions/StudentEvaluationFunction/orchestrator.py`

**Changes to `_aggregate_results()`**:
1. **ID normalization**: Strip "Q" prefix, strip "(Student Page X)" suffix, trim whitespace
2. **Deduplication**: If two evaluations share the same normalized problem_id, keep the non-error one
3. **Missing problem detection**: Compare returned IDs against original parsed list; add explicit "Not Evaluated" entries for missing problems
4. **Recount summary**: After normalization and dedup, recompute correct/acceptable/incorrect/errors

**New parameter**: `_aggregate_results(batch_results, expected_problems)` — receives the original problem list for comparison.

---

## Step 5: Subject Mismatch Warning

**File**: `pipelines/AzureFunctions/StudentEvaluationFunction/activities/parse_text_ref.py`

**Fix**: If Gemini extracts a chapter title (e.g., "Organic Chemistry") and the selected subject is "Physics", add `subject_mismatch_warning` to `_meta`. Non-blocking — the evaluation proceeds, but the frontend can show a warning banner.

---

## Step 6: Problem-by-Problem Navigation

**File**: `apps/FrontEnd/src/pages/SolutionFeedback.tsx`

**Change**: Replace `evaluations.map()` that renders all cards with:
- Single `EvaluationCard` for the current problem
- Navigation bar: `< Problem 3 of 13 >` with prev/next arrows
- Color-coded pill strip (green/amber/red/gray) — clickable to jump to any problem
- State: `currentProblemIndex`, `filteredIndices` (for category filtering)

---

## Step 7: Interactive Summary Card

**File**: `apps/FrontEnd/src/components/feedback/EvaluationSummaryCard.tsx`

**Change**: Make count tiles clickable.
- Clicking "3 Incorrect" filters navigation to show only those 3 problems
- Clicking again (or "All") resets the filter
- Add active/selected ring style to the clicked tile
- Pass callback: `onFilterByStatus?: (status: string | null) => void`

---

## Step 8: Redesign EvaluationCard

**File**: `apps/FrontEnd/src/components/feedback/EvaluationCard.tsx`

**Changes**:
- **Student Tip first**: Move `feedback_for_student.tip` to prominent callout immediately below status — most actionable info
- **Error emphasis**: Full-width red banner for errors (not subtle gray)
- **Collapsible sections**: Details grid and solution steps are collapsible — open by default for incorrect/error, collapsed for correct/acceptable
- **Pinpointed error callout**: New highlighted section showing exactly where the student went wrong (from the improved prompt output)

---

## Step 9: Navigation State in Store

**File**: `apps/FrontEnd/src/store/useFeedbackStore.ts`  
**File**: `apps/FrontEnd/src/types/evaluation.ts`

**Store additions**:
- `currentProblemIndex: number`
- `statusFilter: string | null`
- Actions: `setCurrentProblemIndex()`, `setStatusFilter()`, `nextProblem()`, `prevProblem()`
- Computed: `filteredEvaluations` based on `statusFilter`

**Type additions**: No changes needed (question_images deferred).

---

## Step 10: Improve LaTeX Pre-Processing

**File**: `apps/FrontEnd/src/components/common/LatexRenderer.tsx`

**Change**: Add pre-processing heuristics for common un-delimited chemistry patterns:
- Detect standalone chemical formulas (e.g., `CH3COOH`, `H2SO4`, `NaOH`) and wrap in `$\ce{...}$`
- Detect common patterns like `->`, `<->` in text and convert to reaction arrows

---

## Files Changed

| File | Track | Change |
|------|-------|--------|
| `prompts/Text_ParsingPrompt.md` | Pipeline | Add gap-fill prohibition + few-shot |
| `Feedback/Prompt/Evaluation.txt` | Pipeline | ID constraint + error pinpointing + LaTeX |
| `activities/evaluate_batch.py` | Pipeline | Echo problem IDs explicitly in prompt |
| `orchestrator.py` | Pipeline | Post-aggregation validation |
| `activities/parse_text_ref.py` | Pipeline | Subject mismatch warning |
| `src/pages/SolutionFeedback.tsx` | Frontend | Problem-by-problem navigation |
| `src/components/feedback/EvaluationSummaryCard.tsx` | Frontend | Clickable filter tiles |
| `src/components/feedback/EvaluationCard.tsx` | Frontend | Redesign: tip-first, collapsible, error banner |
| `src/store/useFeedbackStore.ts` | Frontend | Navigation state + actions |
| `src/components/common/LatexRenderer.tsx` | Frontend | Chemistry formula heuristics |

## Verification

- Submit "problems 1 to 4, 6 to 8, 11 to 16" → exactly 13 parsed
- Verify all `problem_id` values match input list (no Q prefix / page suffix)
- Gemini feedback pinpoints exact step where student diverged
- All math/chemistry in `$...$` delimiters
- Click summary tiles → navigation filters to that category
- Prev/next navigates one problem at a time
- Error problems show red banner, correct problems have collapsed details