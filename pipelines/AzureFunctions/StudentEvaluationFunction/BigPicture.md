# Solution Feedback — Phase 3 Complete

## Big Picture: What We Built (Product Level)

AryaBhatta's **Solution Feedback** feature lets students photograph their handwritten homework, upload it, and receive AI-powered evaluation — problem by problem — with error pinpointing, step-by-step corrections, and tips.

**Phase 2** (previously completed) delivered the end-to-end pipeline: upload → queue → Python Durable Functions orchestrator → Gemini evaluation → results stored → React UI.

**Phase 3** (this session's work) was a **quality and UX overhaul** that made the feature production-ready:

- **Evaluation quality**: The AI now reliably distinguishes between genuinely missing work vs. wrong-problem-solved, catches LaTeX-heavy chemistry/physics notation without JSON parse failures, and provides consistent `error_pinpoint` data across all problem types.
- **UX refinement**: One-problem-at-a-time navigator with color-coded pills, clickable summary tiles that filter by status, collapsible error pinpoint callouts, tip-first feedback layout, and proper LaTeX/chemistry formula rendering.
- **Image transparency**: Students can now expand a "View Uploaded Work" panel to see exactly what they submitted — both problem photos and their handwritten solutions — alongside the AI's feedback.

---

## Implementation Details

### A. Quality & UX Overhaul (11 Steps)

**Pipeline fixes (Python — `StudentEvaluationFunction/`):**

1. **Evaluation prompt rewrite** (`Feedback/Prompt/Evaluation.txt`) — Restructured the Gemini evaluation prompt to produce `error_pinpoint` (divergence step, what student wrote vs. expected, error type, severity) and `evaluation_details` (conceptual understanding, calculation errors, presentation). Added explicit "Not Found" vs. "Work Present but Wrong Problem Solved" classification rules.

2. **Text parsing prompt** (`prompts/Text_ParsingPrompt.md`) — Improved natural language problem reference parsing (e.g., "Organic Chemistry 10.1 and 10.5" → structured chapter/exercise/problem data).

3. **Batch evaluation** (`activities/evaluate_batch.py`) — Tuned batch size, model selection (`gemini-3-pro-image-preview`), and response parsing.

4. **Orchestrator** (`orchestrator.py`) — Checkpoint management, error handling, step coordination.

5. **Text ref parser** (`activities/parse_text_ref.py`) — Improved parsing activity.

**Frontend (React + Tailwind — `apps/FrontEnd/`):**

6. **SolutionFeedback page** (`src/pages/SolutionFeedback.tsx`) — Replaced flat list with `ProblemNavigator`: one-problem-at-a-time view, prev/next navigation, color-coded pill strip (green/amber/red/slate), filtered navigation by status.

7. **EvaluationSummaryCard** (`src/components/feedback/EvaluationSummaryCard.tsx`) — Clickable tiles showing correct/acceptable/incorrect/error counts. Clicking a tile filters the navigator to that category.

8. **EvaluationCard** (`src/components/feedback/EvaluationCard.tsx`) — Per-problem card with: error pinpoint callout box (divergence step, student wrote vs. expected, error type badge, severity), tip-first layout, collapsible detailed analysis sections, full model solution with numbered steps.

9. **Zustand store** (`src/store/useFeedbackStore.ts`) — Navigation state (`currentProblemIndex`, `statusFilter`), `getFilteredIndices` utility, `nextProblem`/`prevProblem` actions that respect active filter.

10. **LaTeX renderer** (`src/components/feedback/LatexRenderer.tsx`) — Chemistry formula heuristic pre-processing for KaTeX + mhchem.

11. **TypeScript types** (`src/types/evaluation.ts`) — `error_pinpoint` interface, `ProblemEvaluationDetail`, `SolutionStep`, full `FeedbackJson` shape matching Python pipeline output.

---

### B. JSON Escape Bug Fix

**Problem**: Chemistry evaluations (problems 1-3) failed with `"Invalid \escape"` during JSON parsing. Gemini returns LaTeX backslashes (`\ce`, `\sigma`, `\frac`) inside JSON string values, which are invalid JSON escapes.

**Fix** (`utils/gemini_client.py`):
- Added `_sanitize_json_escapes()` — a state-machine walker that tracks whether it's inside a JSON string literal, and doubles backslashes for non-standard escape characters.
- Intentionally omits `b`, `f`, `t` from the "valid JSON escape" set because Gemini means `\beta`, `\frac`, `\text` — not backspace/formfeed/tab.
- Two-pass parsing: try `json.loads()` first, sanitize only on `JSONDecodeError`.
- 5 unit tests passed covering: clean JSON, LaTeX-heavy JSON, nested structures, edge cases.

---

### C. "Not Found" Misclassification Prompt Fix

**Problem**: In a 13-problem Chemistry test, 4 problems (3, 4, 6, 7) were marked "Not Found" even though student work existed under those labels — the student had simply solved a different question than assigned. Meanwhile, problems 8, 11, 12 (identical situation) were correctly marked "Incorrect" with `misread_problem`. Inconsistent batch-level model behavior.

**Fix** (3 edits to `Feedback/Prompt/Evaluation.txt`):
- Redefined "Not Found" = strictly *zero work exists* under the problem label
- Added "Work Present but Wrong Problem Solved" subsection → directs model to `found_in_student_work: true`, `evaluation_status: "Answer is Incorrect"`, `error_type: "misread_problem"` with full `error_pinpoint`
- Split the Not Found JSON example into two: genuinely absent vs. wrong problem solved

**Deployment**: Uploaded to blob storage (`kalidasa/feedback`), deployed to `<FUNCTION_APP_NAME>` (13 functions synced), restarted.

---

### D. View Uploaded Work — Image Viewer Feature

**Problem**: When reviewing feedback, users couldn't see what they originally wrote. The AI says "Step 3 diverges" but there's no way to look at your actual handwriting.

**Architecture assessment**:
- `student_work_url` and `problem_image_url` already stored in DB (comma-separated blob URLs)
- API was explicitly excluding these fields from response
- Blobs require SAS tokens (not publicly accessible)
- `generateSasUrl()` already existed (2-hour read-only tokens)
- Only full-page images available (no per-problem crops in v4 pipeline)

**Implementation** (5 files, +282 lines):

| Layer | File | Change |
|-------|------|--------|
| API | `apps/functions/src/functions/getEvaluationById.ts` | Read `student_work_url` + `problem_image_url`, split by comma, sign each with `generateSasUrl()`, return `studentWorkUrls[]` + `problemImageUrls[]` |
| Types | `apps/FrontEnd/src/types/evaluation.ts` | Added optional `studentWorkUrls` and `problemImageUrls` arrays |
| Component | `apps/FrontEnd/src/components/feedback/StudentWorkViewer.tsx` | **New** — collapsible panel, two sub-sections ("Problem Statement" + "My Work"), thumbnail grid, lazy `<img loading="lazy">`, lightbox with Escape-to-close, SAS expiry fallback (`broken_image` state), page number badges |
| Page | `apps/FrontEnd/src/pages/SolutionFeedback.tsx` | Wired `StudentWorkViewer` between summary card and problem navigator |

**Design decisions**: Page-level fold (not per-problem, since only full-page images exist), both problem + solution images, lazy loading (zero bandwidth if never opened), Tailwind styling consistent with existing cards.

---

## Specifics

### Commits

| Commit | Message | Files | Lines |
|--------|---------|-------|-------|
| `eff2fea` | Phase 3: Solution feedback quality & UX overhaul | 15 | +1028/−168 |
| `58cf08d` | fix: Evaluation prompt — Not Found vs misread_problem | 2 | +131/−20 |
| `57d00b9` | feat: View Uploaded Work — collapsible image viewer | 5 | +282/−2 |

### Deployments

| Target | Method | Status |
|--------|--------|--------|
| Python Functions (`<FUNCTION_APP_NAME>`) | `func azure functionapp publish` + restart | Deployed (13 functions) |
| Frontend + Node.js Functions | CI/CD via GitHub Actions on push to master | Triggered (`04d996b`) |
| Evaluation prompt blob | `az storage blob upload` to `kalidasa/feedback` | Uploaded |

### Infrastructure (unchanged)

| Resource | Name |
|----------|------|
| Python Functions | `<FUNCTION_APP_NAME>` / `<FUNCTION_RESOURCE_GROUP>` |
| Node.js Functions | `func-aryabhatta-api` / `rg-aryabhata-app` |
| Static Web App | `black-grass-09d7cf710` |
| Storage (prompts/uploads) | `kalidasa` (container `feedback`) + `<QUEUE_STORAGE_ACCOUNT>` |
| PostgreSQL | `<DB_HOST>` |

### CDN Assessment (Parked)

Researched whether Azure CDN should front blob storage for image delivery. Conclusion:
- **Question figures** (~hundreds, static, shared) and **textbook PDFs** (~30-50, static) are ideal CDN candidates
- **Student uploads** (dynamic, user-specific) get minimal benefit
- **Not blocking now** — current SAS approach works at current scale, CDN is a clean bolt-on later with no rearchitecture needed
- Parked for future optimization when concurrent user load grows

### Pending Verification

- Re-test Chemistry evaluation to confirm problems 3, 4, 6, 7 now return "Incorrect" + `misread_problem` instead of "Not Found"
- Test image viewer in production (merged before manual verification)

