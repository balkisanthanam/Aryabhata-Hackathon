# M3 — Pipeline Integration of the Flash Assembly-Line Solver

**Status:** Approved 2026-06-01 · Execution doc (Copilot-actionable)
**Owner:** Balakrishnan · **Branch:** `feature/jeeascent`

---

## Context

The M3 measurement sprint is complete and the architecture is **locked** (2026-05-31): ship
`Untuned_with_support` =

- a **Flash 3-stage Assembly Line** (Solver → Tutor → Format, all on `gemini-3-flash-preview`)
- an **answer-key gate** (`answer_match.py`)
- a **JEE-figure-only router** to Gemini 3.1 Pro
- Pro fallback.

On the clean 100-row holdout this matches/beats Gemini 3.1 Pro (Acc-routable 99.0 / Full-pass 96.9 /
Ped 4.76) at ~6–7× lower cost. Decomposing the single Pro call into three focused Flash stages was
the lever that fixed pedagogy and lifted accuracy. Evidence: `pipelines/ModelEngineering/runs/_SPRINT_OUTCOME.md`,
`runs/_NCERT_VISUAL_TEST.md`.

**Current code state (what exists vs. what this work adds):**
- The winning solver lives **only in the measurement harness** — `batch_evaluator.py`,
  `--model flash-assembly` (committed in `43c26e3`).
- The gate `answer_match.py` exists but is **standalone, wired into nothing**.
- The router `select_mode_for_record` (`batch_evaluator.py:115`) still fires on **all** figure rows
  (NOT yet narrowed to JEE-only).
- No `router.py` exists; no production pipeline uses Flash assembly.

**Why abstract the 3-step process now** (the key decision driving this plan): the Solver→Tutor→Format
process is common to **JEE and NCERT today**, and will be reused by the **M4 Feedback** pipeline and
the **Teacher Agent** solution path, with **more sources to onboard**. That clears the project's
"abstract only when duplication actually hurts" bar — so we build **one parameterized, key-blind
spine** rather than copy-pasting the assembly into each consumer.

---

## Locked decisions

| Decision | Detail |
|---|---|
| **Recovery cascade** | `Flash assembly → answer-key gate → independent Pro re-solve → flag GATE_FAILED if Pro also misses`. **No key-fed fixer.** |
| **Keys feed the GATE, never the SOLVER** | Generation is always key-blind; the key only verifies + routes post-hoc. (NCERT `regenerate` task is key-fed *curation* — out of scope for production path.) |
| **NCERT keys** | Ingest the full NCERT corpus now (`ingest_answer_keys.py`) so the gate covers NCERT's checkable subset. Parallel, resumable track. |
| **Router** | Narrow to **JEE-figures-only**. NCERT figures → Flash (proven equal to Pro, `runs/_NCERT_VISUAL_TEST.md`); JEE figures stay Pro until KI-3. |
| **Shared spine** | Parameterized, key-blind assembly line (prompts injectable per source); gates/routers/DB stay per-pipeline. |

---

## Components

### 0. Parameterized Assembly-Line abstraction — `MultiStep/solver_engine.py`
The 3-step spine for ≥4 consumers (JEE, NCERT, M4 Feedback, Teacher Agent — same repo, importable).

**Motivating finding:** stage prompts are currently *hardcoded JEE-specific* — stage 2
(`_stage_2_pedagogical_tutor`, `solver_engine.py:180-199`) literally references "IIT-JEE student" /
"Le Chatelier's"; only stage 3 is parameterized (takes the schema instruction). Running as-is on
NCERT/Teacher silently inherits a JEE persona — a latent quality bug the abstraction fixes.

**Refactor (additive, low-risk):**
- Introduce a `PromptSet` dataclass: `solver_system`, `tutor_system`, `formatter_system` (+ optional
  user-prompt builders). `generate_assembly_line(payload, prompts: PromptSet, image_urls)` reads from
  it. **Default `PromptSet` = the current baked strings → existing behavior byte-identical.** Each
  source supplies its own.
- **Expose the stage functions as public primitives** (`_stage_1_*`/`_stage_2_*`/`_stage_3_*` →
  public). M4 Feedback (grades student work) and Teacher Agent (live/Socratic) won't always want the
  rigid Solver→Pedagogy→Format order — they compose the same primitives differently. Keep
  `generate_assembly_line` as the canonical path for JEE/NCERT solution-generation.
- **Boundary:** abstraction is key-blind and stateless — prompts + config in, solution out. Gates,
  routers, answer-keys, and DB stay in each consumer pipeline.
- Naming: keep `GoldenGenerator` for now (neutral rename → later, cosmetic).

### 1. Shared Flash-assembly config factory — `MultiStep/config.py`
Lift `batch_evaluator.py:540-548` into a factory so all consumers share one definition:
```python
def flash_assembly_config() -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.solver_model = GeminiModelConfig(model_id="gemini-3-flash-preview", temperature=0.4, max_output_tokens=32768)
    cfg.tutor_model  = GeminiModelConfig(model_id="gemini-3-flash-preview", temperature=0.6, max_output_tokens=32768)
    # formatter_model already gemini-3-flash-preview (thinking=LOW)
    return cfg
```
Refactor `batch_evaluator.py` to call this factory (no behavior change there).

### 2. Shared router — new `MultiStep/router.py`
Lift `select_mode_for_record` out of `batch_evaluator.py`, **narrowed to JEE-figures-only**: route to
Pro only when `record.source == "jee"` **and** `record.has_figure`. NCERT figs → Flash. Home it in
`MultiStep/` (already on `sys.path` for both pipelines + the harness). `batch_evaluator.py` imports
from here instead of its local copy.

### 3. Answer-key gate — re-home `answer_match.py` → `MultiStep/`
Move the pure-python gate (`match()`, `score_rows()`, `is_corrupt_key()`) into `MultiStep/` so JEE,
NCERT, and the harness import one copy. Add a thin cascade helper (in `router.py` or a small
`gate.py`) implementing the locked cascade:
`solve(Flash) → match → on 'wrong' re-solve(Pro assembly, key-blind) → on second 'wrong' return
GATE_FAILED`; `'unknown'`/corrupt → store Flash + flag `KEY_UNVERIFIED` (do not silently trust).

### 4. JEE wiring — `pipelines/JEEAscentPipeline/jee_solution_pipeline.py`
- Add `--solver-tier {pro,flash}` (default `pro` until validated). `flash` selects
  `flash_assembly_config()` + router + gate cascade.
- Replace the inline model selection (~lines 224-241) with one call into the shared cascade helper,
  reusing the existing `image_urls` gathering + `payload_dict`.
- New `review_status` values: `GATE_FAILED`, `KEY_UNVERIFIED`. Keep the resumable-by-DB-state pattern
  (`solution IS NULL`, `retry_count < 3`).

### 5. NCERT wiring — `pipelines/ModelEngineering/ncert_pipeline_orchestrator.py` (+ generation entry)
- The orchestrator's `regenerate`/`pedagogy`/`format` tasks are *key-fed curation*, not key-blind
  production. Production NCERT generation must mirror JEE: **one key-blind `generate_assembly_line`
  call + gate**, writing `questiondata.solution`. **Recommended:** add `--task generate` (or a small
  `ncert_solution_pipeline.py` mirroring the JEE one) doing key-blind Flash assembly + the same
  cascade helper, using the now-ingested `questiondata.answer_key` for the **gate only**. The existing
  key-fed tasks stay for Gold-Set curation, untouched.
- Reuse `db_client.get_smart_context_for_question` if `--use-smart-context`.
- Gate applies only where `answer_key` is non-null + checkable (numeric/objective); proof/derivation
  rows store Flash + `KEY_UNVERIFIED` (Phase-2 verifier territory).

### 6. Parallel track — full NCERT answer-key ingestion
Run `MultiStep/ingest_answer_keys.py` across the NCERT corpus (resumable cache).
**Verification 0:** `SELECT count(*) FILTER (WHERE answer_key IS NOT NULL) FROM questiondata`
before/after — the `regenerate` task does `str(ans_key)` and would silently pass `"None"`, so confirm
real coverage, not nominal.

---

## Reuse (do not rebuild)
- `MultiStep/solver_engine.py` — `generate_assembly_line` (the 3 stages, line 219) +
  `generate_with_feedback` (key-blind critique primitive, line 234 — the honest Phase-2 fixer).
- `MultiStep/gemini_client.py` — `generate(model_config, prompt, system_instruction, image_urls)`.
- `MultiStep/db_client.py` — `get_smart_context_for_question` (line 361), connection-resilient `connect()`.
- `MultiStep/ingest_answer_keys.py` — NCERT key ingestion (exists).
- `ModelEngineering/answer_match.py` — the gate (re-homed, not rewritten).
- `ModelEngineering/{analyze_holdout,dump_failures,diag_*}.py` — smoke-test diagnostics.
- JEE pipeline's `update_solution_in_db`, smart-context payload, figure inlining.

---

## Execution order — phased, with checkpoints (pause + verify at each boundary)

NCERT is wired **before** JEE: Component 0's payoff (de-JEE-ified prompts) is only observable on NCERT,
its rendered KaTeX is the trustworthy quality signal, and its figure-router branch is a no-op.

**Phase 1 — shared contract: Components 0 → 1 → 2 → 3** (abstraction, factory, router, gate). Refactor
`batch_evaluator.py` to consume them — **no behavior change there**.
→ **CHECKPOINT 1 (cheap, mostly offline):** pure-unit tests (router decisions, `answer_match` cases,
`flash_assembly_config` ids, `batch_evaluator` imports) + a `pro-assembly` regression diff (byte-identical
to pre-change). **Pause; report; get green-light before any vertical.**

**Phase 2a — NCERT vertical: Component 5 + Component 6 (parallel).** Key ingestion runs alongside the
new key-blind generate path. Quality is verifiable *before* keys land (gate needs keys; quality doesn't).
→ **CHECKPOINT 2:** view rendered KaTeX in the app on one chapter/subject (pedagogy + formatting +
no-JEE-persona); confirm the gate fires once NCERT keys are ingested. **Pause; report; green-light JEE.**

**Phase 2b — JEE vertical: Component 4.** `--solver-tier flash` on one paper-shift slice.
→ **CHECKPOINT 3:** cascade + router logic on real 2024 keys (mismatch → Pro re-solve, double-miss →
`GATE_FAILED`, JEE-figure → Pro, non-figure → Flash). **Then commit.**

## Verification (per-checkpoint detail)
- **CP1 — regression + contract (fully offline, deterministic, $0):** pytest (no LLM/DB) for `router.py`
  + re-homed `answer_match` + `flash_assembly_config` + `solve_with_gate` cascade branches (stub
  generators). **Byte-identical guard = full-equality assertion** that `DEFAULT_PROMPT_SET` strings equal
  golden copies of the pre-change literals — NOT a stochastic model re-run (pro-assembly is temp 0.4/0.6,
  so an output diff can't prove byte-identicalness and risks false alarms). Default `PromptSet` + default
  `--solver-tier pro` remain the runtime regression guards.
- **CP2 — NCERT visual + gate:** ingest keys (`ingest_answer_keys.py`, resumable) + run Flash-assembly on
  **one chapter per subject** (Physics/Chemistry/Maths). View rendered KaTeX in the app (catches
  formatting/pedagogy the LLM judge misses) **and** confirm the gate fires on real NCERT keys.
- **CP3 — JEE gate/router:** `--solver-tier flash` on one paper-shift slice. Confirm Flash solves, gate
  matches, mismatch → independent Pro re-solve, double-miss → `GATE_FAILED`, JEE-figure rows → Pro,
  non-figure stay Flash. Inspect with `dump_failures.py` / `analyze_holdout.py`.
- **Commit** after CP3 passes: refactored `batch_evaluator.py`, re-homed `answer_match.py`, new
  `router.py` (+ `gate.py`), config factory, `solver_engine.py` PromptSet, pipeline + DB edits.

## Phase 2 (deferred — decide on observed post-ship weakness)
1. **Key-blind verifier/repair** via `generate_with_feedback` — general confidence gate for keyless
   content (NCERT proof/derivation rows, M4 Feedback, M5).
2. **Visual + KI-3** — JEE figure crop/upload → `figure_url`, then test multimodal Flash; unblocks
   shrinking the router further.
3. **RAG-grounding** in the Tutor stage (needs a new grounding metric).
