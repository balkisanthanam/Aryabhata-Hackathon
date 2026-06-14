# AryaBhatta — Claude Code Project Guide

## Project Overview

**AryaBhatta** is an AI-powered educational web app for Class 11–12 CBSE / JEE students.
It digitizes NCERT content (Physics, Chemistry, Maths), presents exercises with AI-generated solutions,
and provides feedback on handwritten student solutions via a Gemini-powered evaluation pipeline.

---

## Repository Structure

```
AryaBhatta/
├── apps/
│   ├── FrontEnd/          # React 18 + TypeScript + Vite frontend
│   ├── functions/         # Azure Functions v4 backend (PRIMARY — use this)
│   ├── server/            # Legacy Express.js backend (DEPRECATED — do not use)
│   └── backend/           # Supplementary backend utilities
├── pipelines/
│   ├── ExtractionPipeline/SchoolDataExtraction/MultiStep/  # Python NCERT extraction
│   ├── DataCollection/    # JEE paper downloader (Selenium + blob upload)
│   └── AzureFunctions/    # Durable Functions for async evaluation pipeline
├── Design/                # Architecture, branding, wireframes
├── Scripts/
│   └── DB_Master.sql      # Full PostgreSQL schema (source of truth for raw SQL)
└── apps/functions/prisma/schema.prisma  # Prisma ORM schema (source of truth for ORM)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Zustand, KaTeX, React Router |
| Backend | **Azure Functions v4** (Node.js / TypeScript) — PRIMARY |
| ORM | Prisma 7.3.0 |
| Database | PostgreSQL — Azure managed (`<DB_HOST>`) |
| Storage | Azure Blob Storage (`stevaluationstorage` / `kalidasa` containers) |
| Queue | Azure Storage Queue (async AI evaluation jobs) |
| AI | Google Gemini API (multiple models) |
| Extraction Pipeline | Python (NCERT PDF extraction + solution generation) |

---

## Backend Rules

- **Always use Azure Functions** (`apps/functions/`). Never add new code to `apps/server/` (deprecated Express).
- Functions live in `apps/functions/src/functions/`. Add new endpoints here.
- Use `PrismaClient` from `apps/functions/src/utils/prisma.ts` for all DB access.
- Use `apps/functions/src/utils/azure-storage.ts` / `azure-token.ts` for blob operations.
- SAS tokens are injected **server-side** for all Azure Blob image URLs (1-hour TTL). Never expose raw blob URLs to the client.

### API Endpoints (Azure Functions — port 7071 locally)

| Method | Path | Function File |
|--------|------|--------------|
| POST | `/api/auth/login` | `authLogin.ts` |
| GET | `/api/user/resume` | `userResume.ts` |
| GET | `/api/practice/dashboard` | `practiceDashboard.ts` |
| GET | `/api/practice/question` | `practiceQuestion.ts` |
| POST | `/api/practice/progress` | `practiceProgress.ts` |
| POST | `/api/practice/submit-evaluation` | `submitEvaluation.ts` |
| GET | `/api/practice/evaluations` | `getCompletedEvaluations.ts` |
| GET | `/api/practice/evaluation/:id` | `getEvaluationById.ts` |
| GET | `/api/practice/last-evaluation` | `getLastEvaluation.ts` |
| GET | `/api/practice/chapter-map` | `practiceChapterMap.ts` |
| GET | `/api/practice/exercise-questions` | `practiceExerciseQuestions.ts` |

---

## Database Schema (Prisma Models)

| Model | Purpose |
|-------|---------|
| `chapterdata` | NCERT chapters — class, subject, chapter number/title, PDF URL |
| `exercisedata` | Exercises within a chapter |
| `questiondata` | Individual questions — `content` (JSONB), `solution` (JSONB) |
| `userprofiledata` | User accounts — username, class, board, goal, email |
| `userexercisedata` | Tracks which questions a user has attempted |
| `classsubjectdata` | Supported class/subject/board combinations |
| `solution_evaluations` | AI evaluation jobs — status, feedback_json, pipeline_steps (all JSONB) |

**JSONB is used extensively** for `content`, `solution`, `feedback_json`, and `pipeline_steps`.

---

## Authentication (Hardcoded — Temporary)

Authentication is **not yet implemented**. A single hardcoded user is used everywhere:

```typescript
// apps/functions/src/utils/session.config.ts
export const sessionUser = { Name: 'Viswanathan', UserId: 1 };
```

Do not add real auth logic until a proper auth system (Azure AD B2C / Auth0) is planned.

---

## Frontend Structure

```
apps/FrontEnd/src/
├── pages/           # Route-level page components
│   ├── MainDashboard.tsx
│   ├── PracticeDashboard.tsx
│   ├── PracticeSession.tsx
│   ├── SolutionFeedback.tsx
│   ├── ChallengeDashboard.tsx    # Under development
│   └── PerformanceCompass.tsx    # Under development
├── components/      # Shared UI components (practice, feedback, layout, dashboard)
├── store/           # Zustand stores (useStore, useUserStore, useFeedbackStore)
├── types/           # TypeScript type definitions
└── config/          # App-level config
```

Frontend dev server runs on `http://localhost:5173`.

---

## Evaluation Pipeline (Async AI Flow)

1. Student uploads handwritten solution image → Azure Blob Storage
2. `submitEvaluation.ts` enqueues a job → Azure Storage Queue
3. Azure Durable Function pipeline runs:
   - `read_evaluation` → `split_student_hw` → `parse_text_ref` → `match_solutions` → `evaluate_batch`
4. Gemini API evaluates the solution and writes `feedback_json` back to `solution_evaluations`
5. Frontend polls every 10 seconds via `getEvaluationById` until status = `COMPLETED`

---

## Extraction Pipeline (Python)

Location: `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/`

- Extracts questions and solutions from NCERT PDFs
- Uploads images to Azure Blob Storage (`blob_client.py`)
- Writes structured data to PostgreSQL
- Pipeline is **resumable** via checkpoint state files
- Gemini Vertex AI used for PDF image parsing

---

## Planned / In-Progress Features

- **JEE Ascent** (`feature/jeeascent` branch) — new major feature for JEE exam paper ingestion and practice. Design doc in `Design/` folder.
  - M1a (Download): Done — papers 2021–2025 downloaded to blob
  - M1b (Extraction): Parked — 2024 complete (~6,400+ questions in `jee_question_bank`); other years deferred until E2E validated
  - M1d (DB Tables): Done — all 8 JEE Ascent tables created (`Scripts/JEEAscent_DB_Migration.sql`)
  - M2 (NCERT Concept Index): Done — 2,708 nodes across 74 chapters in `ncert_concept_hierarchy` + embeddings
  - M3 (Question Tagger): **Done for 2024** — 2024 fully tagged (Math 2290 / Chemistry 2088 / Physics 2045, 0 untagged); 2023 tagging in progress; `question_tagger.py` uses hybrid mode (default) + full mode fallback (`--mode full --batch-size 1`) for persistent failures
  - M4 (Solution Generator): Parked — return after E2E validated
  - M5 (Question Generator): Deferred — Phase 2
  - M6 (Progression Engine): Done (light) — logic embedded in M7 endpoints
  - M7 (API Layer): Done — 4 endpoints live (`accentSession`, `accentQuestion`, `accentProgress`, `accentChapterMap`)
  - M8 (Frontend UX): Done — `AccentSession.tsx` implemented
- **PerformanceCompass** (`/analytics`) — analytics page, under development
- **ChallengeDashboard** (`/challenge`) — challenge mode, under development
- **GCP Migration** — future: Cloud Run, Pub/Sub, GCS, Cloud SQL (Azure is current)
- **Real authentication** — Azure AD B2C or Auth0 (not yet started)

---

## Dev Setup

```bash
# Backend (Azure Functions)
cd apps/functions
npm install
npx prisma generate
npm start          # runs on http://localhost:7071

# Frontend
cd apps/FrontEnd
npm install
npm run dev        # runs on http://localhost:5173
```

Prerequisites: Azure Functions Core Tools v4, Node.js 18+, Azure CLI (`az login`).

---

## Key Conventions

- **No new Express routes** — Azure Functions only.
- **Prisma for all DB queries** — no raw SQL in application code (raw SQL only in `Scripts/DB_Master.sql`).
- **JSONB fields** — use typed interfaces; do not assume structure without checking schema.
- **SAS tokens** — always server-side; 1-hour TTL; never expose raw blob URLs.
- **Async evaluation polling** — 10-second intervals from frontend; do not change without coordinating pipeline timing.
- **Single user** — `UserId = 1` everywhere until real auth lands.

---

## Reference Files

| File | Purpose |
|------|---------|
| `apps/functions/prisma/schema.prisma` | ORM schema — source of truth for models |
| `Scripts/DB_Master.sql` | Raw PostgreSQL schema |
| `apps/Architecture_Design.md` | End-to-end architecture overview |
| `apps/functions/src/utils/session.config.ts` | Hardcoded auth user |
| `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/blob_client.py` | Blob upload utility (reuse for new pipelines) |
