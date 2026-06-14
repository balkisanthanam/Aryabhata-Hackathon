# Solution Model — Tightened Plan

## Context

You ran a parallel Copilot session that built a JEE solution generator (`jee_solution_pipeline.py`) and a reusable evaluator/training package (`pipelines/ModelEngineering/`). Scope expanded from "M4 = JEE solution generator" into a **template** for solution generation + evaluation that will eventually be reused across JEE Ascent, NCERT cleanse, and Student Feedback. The design intent is in `Design/Architecture/E2E_SolutionModel_Implementation_Plan.md` and the four sibling `SolutionModel*.md` docs.

This plan is the result of a deeper read pass. It does two things:

1. **Defines the end-to-end Solution pipeline** (Stages 1–6) — the answer to "I am not sure about the exact steps."
2. **Lists what to change per stage**, including four real bugs uncovered during the read.

Wave 3 (cross-pipeline reuse / NCERT cleanse) is consciously deferred until the JEE loop closes; trying to generalise before the loop runs end-to-end on one pipeline tends to ossify the wrong abstraction.

---

## Recommended E2E Solution Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 1 — GENERATE                                                  │
│   Where: jee_solution_pipeline.py (exists, works)                   │
│   Status: review_status='UNVERIFIED', is_generated=TRUE             │
│   Model:  Gemini 3.1 Pro, 2-pass critique loop (in solver_engine)   │
│   Filter: solution IS NULL AND answer_key IS NOT NULL               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 2 — INSPECT (rebuild review_generations.py)                   │
│   Today: ORDER BY id DESC LIMIT 3 — debug peek only                 │
│   Need:  filters that mirror the generator + a summary mode         │
│     review_generations.py --year 2024 --subject Physics             │
│     review_generations.py --paper-id 12 --status UNVERIFIED         │
│     review_generations.py --question-id 4523 --detail               │
│     review_generations.py --summary  → table of counts per status   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 3 — EVALUATE                                                  │
│   Where: evaluator_engine.py (exists, two bugs to fix)              │
│   Score: Accuracy/Pedagogy/Formatting (0–5 each), is_pass logic     │
│   New:   persist score back to jee_question_bank                    │
│   New:   image-payload shape now handles JEE's figure_url +         │
│          option_figure_urls (not just NCERT's figure_info)          │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 4 — TRIAGE  (status transition based on evaluator output)     │
│   total ≥ 13 AND accuracy == 5  → APPROVED_GOLD                     │
│   total ∈ [10,12]  OR acc < 5    → NEEDS_REWRITE                    │
│   total < 10                     → REJECTED                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 5 — NUDGE / REGENERATE (new method on GoldenGenerator)        │
│   For NEEDS_REWRITE:                                                │
│     - feed (problem, prior_solution, evaluator_feedback) → Pro      │
│     - ask Pro to fix only the called-out defects                    │
│     - write back, set status='UNVERIFIED', increment retry_count    │
│     - cap at 2 retries; on 3rd failure → REJECTED                   │
│   For REJECTED:                                                     │
│     - leave for human review (out of scope for v1)                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 6 — EXPORT / USE                                              │
│   jsonl_exporter.py — fix WHERE clause to require APPROVED_GOLD     │
│   AccentSession (M8) — already serves whatever sits in DB           │
│   (today renders UNVERIFIED solutions — fine while bootstrapping)   │
└─────────────────────────────────────────────────────────────────────┘
```

**Where "nudge" sits** — I'm placing it as Stage 5 (after evaluation, conditional on a NEEDS_REWRITE verdict). If by "nudge" you meant something different (e.g. human-in-loop edits between Inspect and Evaluate, or improving the `nudge_hint` field at prompt-tuning time), tell me and I'll re-shape Stage 5.

---

## Bugs Found During the Read (fix during Stage work, not separately)

| # | File | Issue | Severity |
|---|------|-------|----------|
| B1 | `pipelines/ModelEngineering/jsonl_exporter.py:84,108` | `WHERE solution IS NOT NULL` with no `review_status` filter — training set will be contaminated with UNVERIFIED/REJECTED data | **High** — breaks the SFT loop |
| B2 | `pipelines/ModelEngineering/evaluator_engine.py:117–121` | Reads `problem_payload["figure_info"]` (NCERT shape) — JEE's `figure_url` + `option_figure_urls` never reach the judge → image questions scored blind | **High** — silent correctness |
| B3 | `pipelines/ModelEngineering/evaluator_engine.py:169` and `pipelines/JEEAscentPipeline/jee_solution_pipeline.py:109` | Hardcoded GCP project ID `"animated-rope-453904-j7"` as fallback when `GOOGLE_CLOUD_PROJECT` is unset → silently bills wrong project | **Medium** — operational |
| B4 | `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/tutor_prompt.md:59–69` and `Design/Architecture/JEEAscentModuleBreakdown.md:343–344` | Both still document the legacy `hint`/`formula`/`visual_needed` schema. Live frontend (`SolutionView.tsx:70,104`) reads `nudge_hint`/`latex_formula`/`visual_asset` with **no defensive fallback** — anything written using the legacy schema renders as blank hint + missing formula box | **Medium** — footgun for re-runs |
| B5 | `pipelines/JEEAscentPipeline/jee_solution_pipeline.py:137,224` | `offset` only advances after a clean batch; an exception leaves the row at status=UNVERIFIED but `solution IS NULL`, so the next batch re-fetches it forever (infinite loop on a stuck question) | **Low–Medium** |

---

## Proposed Work, Stage by Stage

### Stage 1 — Generate (small fixes only)

- **B5 fix** in `jee_solution_pipeline.py`: on exception in the per-question loop (line 224), set `review_status='GENERATION_FAILED'` so the row drops out of the `solution IS NULL` filter on the next batch.
- **B3 fix** in `jee_solution_pipeline.py:109`: replace the literal fallback with a fail-fast `sys.exit(1)` and a clear error message when `GOOGLE_CLOUD_PROJECT` is unset.
- Remove the unused `import textwrap` (line 15).

No prompt or schema changes here — Stage 1 is already working.

### Stage 2 — Inspect (rewrite `review_generations.py`)

Replace the current 70-line debug script with a small CLI:

```
python review_generations.py --summary
  → prints a table: year | subject | UNVERIFIED | NEEDS_REWRITE | APPROVED | REJECTED | total

python review_generations.py --year 2024 --subject Physics --status UNVERIFIED --limit 10
  → list questions matching the cut, one line per question:
    id | nta_id | subject | review_status | preview-of-final_answer

python review_generations.py --question-id 4523 --detail
  → pretty-print the full solution JSON for one question, with evaluator score if present
```

Reuse `JEEExtractionDBWriter.connection()` for DB; no new auth code. Single file, no new dependencies.

### Stage 3 — Evaluate (fix two bugs + persist results)

**B2 fix** — extract `image_urls` from both shapes:

```python
# Today (broken on JEE):
image_urls = [fig["url"] for fig in problem_payload.get("figure_info", []) if fig.get("url")]

# Replacement:
image_urls = []
if problem_payload.get("figure_url"):
    image_urls.append(problem_payload["figure_url"])
for u in problem_payload.get("option_figure_urls", []) or []:
    if u: image_urls.append(u)
for fig in problem_payload.get("figure_info", []) or []:
    if fig.get("url"): image_urls.append(fig["url"])
```

**Persistence** — add three columns on `jee_question_bank`:

```sql
ALTER TABLE jee_question_bank
  ADD COLUMN evaluator_score JSONB,        -- {accuracy, pedagogy, formatting, total, is_pass, feedback_notes}
  ADD COLUMN evaluator_model TEXT,
  ADD COLUMN evaluated_at   TIMESTAMP;
```

Inline columns over an audit table — simpler, sufficient until you start A/B-testing prompts. Add a CLI to `evaluator_engine.py` that takes the same filters as Stage 2 and runs evaluation only on rows where `evaluator_score IS NULL` (idempotent / resumable).

Few-shots-as-real-JSON (the third Wave-2 point from earlier) is **deferred** — it improves consistency but the evaluator already produces sensible scores; ship persistence first, calibrate, then revisit prompt density.

### Stage 4 — Triage (1-line decision function)

A small helper called immediately after evaluation:

```python
def triage(score) -> str:
    if score.is_pass:                    return "APPROVED_GOLD"
    if score.total_score >= 10:          return "NEEDS_REWRITE"
    return "REJECTED"
```

Add `retry_count INT DEFAULT 0` column on `jee_question_bank` so Stage 5 can cap retries.

### Stage 5 — Nudge / Regenerate (new method)

`generate_with_critique` cannot accept feedback (the critique prompt is hardcoded at `solver_engine.py:177–194`). Add a sibling method:

```python
def generate_with_feedback(
    self,
    prompt: str,
    system_prompt: str,
    prior_solution: dict,
    evaluator_feedback: str,
    image_urls: Optional[List[str]] = None,
) -> ModelResponse:
    """One-pass regenerate. Sends prior solution + judge feedback, asks Pro to fix it."""
```

Wire from a new `nudge_solutions.py` (or as a `--mode nudge` flag on `jee_solution_pipeline.py`):

```
python jee_solution_pipeline.py --mode nudge --year 2024 --subject Physics
  → fetches NEEDS_REWRITE rows where retry_count < 2
  → for each: load solution + evaluator feedback → generate_with_feedback → write back as UNVERIFIED, retry_count += 1
```

The next evaluator pass picks them up automatically.

### Stage 6 — Export (B1 fix)

Tighten the WHERE clauses in `jsonl_exporter.py`:

```sql
-- NCERT: use the evaluator path the same way once Wave-3 lands;
-- for now (we haven't evaluated NCERT yet) keep solution-IS-NOT-NULL but warn loudly.
WHERE q.solution IS NOT NULL

-- JEE: must be approved
WHERE solution IS NOT NULL AND review_status = 'APPROVED_GOLD'
```

Add a `--require-approved` flag (default true for JEE, false for NCERT until cleanse runs) and log the count split by status before exporting so contamination is visible.

---

## What I am Deliberately *Not* Recommending Right Now

- **Smart-context injection for JEE.** The design doc (`E2E_SolutionModel_Implementation_Plan.md`) and `JEEAscentModuleBreakdown.md` both promise "top-3 NCERT concept chunks, ~4,500 tokens, ~20× cost saving." The actual JEE pipeline doesn't do this — it sends only problem + images. Worth a separate decision: today's solutions are good enough that this is an optimisation, not a correctness fix. Suggest deferring to a follow-up unless cost is biting.
- **Wave-3 generalisation** (extracting a shared `SolutionGenerator` interface used by NCERT + JEE). The two pipelines duplicate fetch-loop / clean-backticks / DB-update logic. Worth doing — but only after the JEE loop runs end-to-end. Premature abstraction risk.
- **NCERT cleanse** (Milestone 5.1 — run evaluator over `questiondata.solution`, mark low-scorers for re-gen). Same engine, different entry point. Easier after Stage 5 lands and we have the regenerate flow proven.
- **Vertex AI SFT loop** (Milestone 3). Downstream of Stage 6 producing a clean JSONL. No-op until then.
- **Few-shots-as-JSON** in evaluator. Marginal; ship persistence first.

---

## File-by-File Change List

| File | Stage | Change |
|------|-------|--------|
| `pipelines/JEEAscentPipeline/jee_solution_pipeline.py` | 1 | B3 fix (fail-fast on missing GCP project), B5 fix (mark FAILED on exception), drop unused `textwrap` |
| `pipelines/JEEAscentPipeline/jee_solution_pipeline.py` | 5 | Optional `--mode nudge` flag, or split into `nudge_solutions.py` |
| `pipelines/JEEAscentPipeline/review_generations.py` | 2 | Rewrite as filtered CLI with summary + detail modes |
| `pipelines/ModelEngineering/evaluator_engine.py` | 3 | B2 fix (image extraction), B3 fix (project fallback), persistence write, idempotent CLI filter |
| `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/solver_engine.py` | 5 | New `generate_with_feedback()` on `GoldenGenerator` |
| `pipelines/ModelEngineering/jsonl_exporter.py` | 6 | B1 fix (require APPROVED_GOLD), `--require-approved` flag, status-split log |
| `Scripts/JEEAscent_DB_Migration.sql` (or new patch file) | 3, 4 | `ALTER TABLE jee_question_bank ADD COLUMN evaluator_score / evaluator_model / evaluated_at / retry_count` |
| `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/tutor_prompt.md` | — (cleanup) | B4 fix — rewrite schema to `nudge_hint`/`latex_formula`/`visual_asset` so re-runs don't poison the DB |
| `Design/Architecture/JEEAscentModuleBreakdown.md` | — (cleanup) | B4 fix — lines 343–344 rewrite to match live schema |
| `pipelines/JEEAscentPipeline/CLAUDE.md` | — (cleanup) | Add a § for the new Stage 2/3/5/6 commands once they land |

---

## Verification

Run end-to-end on a small slice once the changes land:

```bash
# 1. Generate 5 questions  (Stage 1)
python jee_solution_pipeline.py --year 2024 --subject Physics --limit 5 --use-critique

# 2. Confirm what was written  (Stage 2)
python review_generations.py --year 2024 --subject Physics --status UNVERIFIED --limit 5
python review_generations.py --summary

# 3. Evaluate them  (Stage 3)
python evaluator_engine.py --year 2024 --subject Physics

# 4. Confirm triage decisions landed  (Stage 4)
python review_generations.py --summary
# expect: counts now split between APPROVED / NEEDS_REWRITE / REJECTED

# 5. Nudge the borderline ones  (Stage 5)
python jee_solution_pipeline.py --mode nudge --year 2024 --subject Physics
python evaluator_engine.py --year 2024 --subject Physics
python review_generations.py --summary
# expect: most NEEDS_REWRITE either promoted to APPROVED or staying with retry_count=2

# 6. Export only the gold  (Stage 6)
python jsonl_exporter.py --output dataset.jsonl
# log line: "JEE: 4 APPROVED_GOLD / 1 REJECTED / 0 UNVERIFIED — exporting 4"
```

End-state: a clean self-driving loop where the only thing the SFT path can see is `APPROVED_GOLD`.

---

## Critical Files for Implementation

| Path | Why it matters |
|------|----------------|
| `pipelines/JEEAscentPipeline/jee_solution_pipeline.py` | Stage 1 + Stage 5 entry |
| `pipelines/JEEAscentPipeline/review_generations.py` | Stage 2 |
| `pipelines/ModelEngineering/evaluator_engine.py` | Stage 3 + 4 |
| `pipelines/ModelEngineering/jsonl_exporter.py` | Stage 6 |
| `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/solver_engine.py` | `GoldenGenerator.generate_with_feedback` for Stage 5 |
| `Scripts/JEEAscent_DB_Migration.sql` | Schema additions for scores + retry_count |
| `apps/FrontEnd/src/components/practice/SolutionView.tsx` | Already correct — confirms the canonical schema |
