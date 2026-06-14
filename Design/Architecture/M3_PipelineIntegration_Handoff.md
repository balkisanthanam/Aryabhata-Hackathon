# M3 Pipeline Integration — Execution Handoff (for the Sonnet build session)

> **Read this first, then build.** This is a focused handoff from the planning session. The design,
> the options we weighed, and the calls we took are all below — you should **not** need to re-derive
> any of it. Your job:
>
> 1. Read this doc + the authoritative plan `Design/Architecture/M3_PipelineIntegration_Plan.md`.
> 2. Read the exact code anchors cited below (signatures + line numbers are current as of 2026-06-01).
> 3. **Ask any clarifying doubts before you start coding** — the planning owner is available.
> 4. Then implement in **phases, pausing at each checkpoint** (see §Build order). Default behavior must
>    stay **byte-identical** until a new flag is flipped (regression guard — respect it strictly).
> 5. The human will run any DB/LLM scripts for you (smoke tests, ingestion). Hand them exact commands;
>    don't assume you can run long Gemini/DB jobs yourself.
> 6. **Stop at each CHECKPOINT, report what you did + verification results, and wait for green-light**
>    before starting the next phase. Do not run ahead.
>
> **Branch:** `feature/jeeascent`. **Do not commit** until the smoke test passes and the owner approves.

---

## 0. The one-paragraph "why"

M3's measurement sprint is done; architecture is **locked**. We ship a **Flash 3-stage Assembly Line**
(Solver→Tutor→Format, all `gemini-3-flash-preview`) + an **answer-key gate** + a **JEE-figures-only
router** to Gemini 3.1 Pro + Pro fallback. It matches/beats Pro at ~6–7× lower cost. The winning solver
exists **only in the measurement harness** today (`pipelines/ModelEngineering/batch_evaluator.py
--model flash-assembly`). This work moves it into the **production** generators — but rather than
copy-paste it twice, we **abstract the 3-step process into one parameterized, key-blind shared spine**,
because the same process will be reused by JEE, NCERT, the **M4 Feedback** pipeline, and the **Teacher
Agent**, with more sources to come. (Evidence: `pipelines/ModelEngineering/runs/_SPRINT_OUTCOME.md`,
`runs/_NCERT_VISUAL_TEST.md`.)

---

## 1. Where the proven code lives right now (read these)

| Thing | Location (current, verified 2026-06-01) |
|---|---|
| The 3-stage Assembly Line | `MultiStep/solver_engine.py` → `GoldenGenerator.generate_assembly_line()` (**line 219**); stages at **161 / 180 / 201** |
| All-Flash variant (the override we ship) | `batch_evaluator.py:540-548` (sets `solver_model` + `tutor_model` to `gemini-3-flash-preview`) |
| Mode dispatch | `batch_evaluator.py:250-307` (`generate_solution`, the `flash-assembly` branch at 270-280) |
| Router (NOT yet narrowed) | `batch_evaluator.py:94-117` (`select_mode_for_record`) — still fires on **all** figure rows |
| Answer-key gate (standalone, unwired) | `pipelines/ModelEngineering/answer_match.py` (`match`, `score_rows`, `is_corrupt_key`) |
| Gemini client call | `MultiStep/gemini_client.py:267` → `generate(model_config, prompt, document_path=None, system_instruction=None, image_urls=None) -> GeneratedContent` (`.text`) |
| Model config defaults | `MultiStep/config.py:65-89` (`PipelineConfig`; solver/tutor = `gemini-3.1-pro-preview`, formatter already `gemini-3-flash-preview` thinking=LOW) |
| NCERT key ingestion | `MultiStep/ingest_answer_keys.py` (exists; resumable) |
| Key-blind critique primitive (Phase-2) | `MultiStep/solver_engine.py:234` `generate_with_feedback` |

`MultiStep/` = `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/`. It is already on
`sys.path` for both production pipelines and the harness — that's why shared code goes there.

---

## 2. Decisions taken (do not relitigate)

| # | Decision | Why this, not the alternative |
|---|---|---|
| D1 | **Abstract the spine now** (one `PromptSet`-parameterized assembly), don't copy-paste per pipeline. | ≥4 consumers (JEE/NCERT/Feedback/Teacher) → clears the project's "abstract only when duplication hurts" bar. |
| D2 | **Keys feed the GATE, never the SOLVER.** Generation is always key-blind. | A key-fed solver "fudges" numbers to match the key (corrupt keys → garbage). The gate verifies *after*. |
| D3 | **Recovery cascade:** Flash → gate → independent **Pro re-solve (key-blind)** → if Pro also misses → `GATE_FAILED`. **No key-fed fixer.** | Pro is the accuracy ceiling. A second key-fed "fixer" pass was considered and **rejected** (would hide real misses + amplify corrupt-key damage). |
| D4 | **Router narrowed to JEE-figures-only.** NCERT figures → Flash. | NCERT-visual test proved Flash ≈ Pro on NCERT figures (`_NCERT_VISUAL_TEST.md`). JEE figures have *no image at all* (KI-3) → must stay Pro until KI-3 is fixed. |
| D5 | **Corrupt / unknown keys never count as a model miss and never trigger Pro.** | KI-6: 6% of 2024 JEE keys are leaked NTA ids (`is_corrupt_key`, 9+ digits). Store Flash result + flag `KEY_UNVERIFIED`. |
| D6 | **NCERT production generation is a NEW key-blind path**, separate from the existing `regenerate`/`pedagogy`/`format` tasks. | Those existing tasks are *key-fed Gold-Set curation* — leave them untouched. |
| D7 | **Default `PromptSet` = the current baked stage strings.** Existing callers get byte-identical output. | Regression guard. New behavior only via new flag/PromptSet. |
| D8 | Keep the name `GoldenGenerator` for now. | A neutral rename (`SolverAssembly`) is cosmetic; defer to avoid churn across importers. |

---

## 2.5 Build order & checkpoints (NCERT before JEE — read before §3)

§3 lists components **0→6 as a reference spec**, but **build them in this phased order** and **stop at
each CHECKPOINT** to report + get a green-light (see §5 for each checkpoint's exact verification):

1. **Phase 1 — shared contract:** Components **0 → 1 → 2 → 3**. Refactor `batch_evaluator.py` to consume
   them; no behavior change there. → **CHECKPOINT 1.**
2. **Phase 2a — NCERT vertical:** Component **5** + Component **6** (key ingestion, parallel).
   → **CHECKPOINT 2.**
3. **Phase 2b — JEE vertical:** Component **4**. → **CHECKPOINT 3 → commit.**

**Why NCERT before JEE** (not the other way): Component 0's whole payoff — replacing the hardcoded
JEE persona — is only *observable on NCERT* (JEE-on-JEE-prompts proves nothing about the abstraction);
NCERT's rendered KaTeX in the app is the trustworthy quality signal the LLM judge misses; and NCERT's
figure-router branch is a **no-op** (NCERT figs → Flash), so it's the simpler first integration. JEE then
validates the gate + router *logic* against the answer keys that already exist on `jee_question_bank`.
(NCERT *quality* needs no keys — verify it before Component 6 finishes; only the NCERT *gate* waits on keys.)

## 3. Component-by-component build spec

### Component 0 — `PromptSet` abstraction (`MultiStep/solver_engine.py`)
**Problem it fixes:** **only Stage 2 is JEE-specific** — it says *"…IIT-JEE student…"* and *"…Le
Chatelier's…"* (`solver_engine.py:183-191`). Stage 1 (164-171) is **generic** ("cold, calculating Math &
Physics expert") — *not* JEE-bound, though it omits **Chemistry** (a latent scope bug). Stage 3 (204-209)
is **generic** (Data Architect). So: `solver_system` + `formatter_system_prefix` defaults are
domain-neutral and reusable as-is; **only `tutor_system` carries the persona NCERT/Teacher must override.**
NCERT's `solver_system` should also broaden "Math & Physics" → "Math, Physics & Chemistry".

**Do:**
1. Add a dataclass:
   ```python
   @dataclass
   class PromptSet:
       solver_system: str
       tutor_system: str
       formatter_system_prefix: str   # prepended to the per-call schema instruction in stage 3
       # optional user-prompt builders; default None → callers pass prompt strings as today
       build_solver_user: Optional[Callable[..., str]] = None
   ```
2. Define `DEFAULT_PROMPT_SET` whose three strings are **the exact current literals** from
   `_stage_1/2/3` (copy them verbatim — byte-identical).
3. Change the stage methods to read from `self.prompts` (a `PromptSet`) instead of inline literals.
   `GoldenGenerator.__init__(self, client, config, prompts: PromptSet = DEFAULT_PROMPT_SET)`.
4. `generate_assembly_line` signature stays the same for existing callers; the per-source nuance comes
   from the injected `PromptSet`, not new args. (Stage 3 still takes the per-call `system_prompt` schema
   instruction — that is the JEE/NCERT schema text passed in today; now appended to
   `formatter_system_prefix`.)
5. **DO NOT make the stages public in Phase 1.** Keep `_stage_*` private; Component 0 here is *only* the
   `PromptSet` injection. Exposing public stage primitives is safe (no external callers — verified) but
   unneeded until M4 Feedback / Teacher Agent (out of scope, §6) compose stages out-of-order. Per "don't
   pre-build abstractions," defer it. `generate_assembly_line` remains the canonical JEE/NCERT path.

**Acceptance:** existing `--use-assembly` JEE run and `batch_evaluator --model pro-assembly` produce
identical output to before (diff the JSON). No caller passes a `PromptSet` yet except the new Flash path.

### Component 1 — Flash-assembly config factory (`MultiStep/config.py`)
Add (lift verbatim from `batch_evaluator.py:540-548`):
```python
def flash_assembly_config() -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.solver_model = GeminiModelConfig(model_id="gemini-3-flash-preview", temperature=0.4, max_output_tokens=32768)
    cfg.tutor_model  = GeminiModelConfig(model_id="gemini-3-flash-preview", temperature=0.6, max_output_tokens=32768)
    # formatter_model is already gemini-3-flash-preview, thinking=LOW — leave it.
    return cfg
```
Then refactor `batch_evaluator.py` lines 540-548 to call this factory (no behavior change).

### Component 2 — Shared router (`MultiStep/router.py`, new)
Move `select_mode_for_record` here, **narrowed**:
```python
def select_mode_for_record(record, default_mode, router_enabled=True):
    if not router_enabled:
        return default_mode
    is_flash = default_mode in ("flash-tuned", "flash-untuned", "flash-assembly")
    # JEE figures are KI-3-blind (no image). NCERT figures go to Flash (proven ≈ Pro).
    if is_flash and record.get("source") == "jee" and record.get("has_figure"):
        return "pro-assembly"
    return default_mode
```
`batch_evaluator.py` imports from here and deletes its local copy. **Note the new `source` field** —
in the harness, holdout records must carry `source` ("jee"/"ncert"). In production, the JEE pipeline
passes `source="jee"`, the NCERT path passes `source="ncert"`, so the discriminator is trivially known.

### Component 3 — Re-home the gate + cascade helper
1. Move `answer_match.py` → `MultiStep/answer_match.py` (verbatim). Update the harness import.
2. Add the cascade helper (small new `MultiStep/gate.py` or inside `router.py`). **Confirmed signature**
   — `prompt` is the caller-built **key-blind** user prompt; `prompts` is dropped (baked into each
   generator's `PromptSet`); `answer_key`/`options` feed only the gate:
   ```
   solve_with_gate(prompt, system_prompt, answer_key, options, image_urls, flash_generator, pro_generator):
       assert "answer" not in prompt.lower-ish  # prompt MUST be key-blind (D2) — see Component 4 ⚠
       sol = flash_generator.generate_assembly_line(prompt, system_prompt, image_urls)   # Flash
       verdict = answer_match.match(sol.final_answer, answer_key, options)
       if verdict == "correct":  return sol, "UNVERIFIED"        # existing JEE success status
       if verdict == "unknown":  return sol, "KEY_UNVERIFIED"    # corrupt/no key — keep Flash, don't trust
       # verdict == "wrong":
       pro_sol = pro_generator.generate_assembly_line(prompt, system_prompt, image_urls)  # independent Pro, key-blind
       v2 = answer_match.match(pro_sol.final_answer, answer_key, options)
       if v2 == "correct": return pro_sol, "UNVERIFIED"
       return pro_sol, "GATE_FAILED"                             # Pro also missed → flag for review
   ```
   (Extract `final_answer` from the parsed JSON. Reuse the existing markdown-strip +
   `generator._sanitize_json_escapes` parse logic — see Gotcha G4.)

### Component 4 — JEE wiring (`pipelines/JEEAscentPipeline/jee_solution_pipeline.py`)
- Add `--solver-tier {pro,flash}` (**default `pro`** — keeps current behavior).
- At the call site (**lines 224-241**), when `--solver-tier flash`: build a `flash_generator`
  (`GoldenGenerator(client, flash_assembly_config())`) + a `pro_generator` (current default config), and
  route each row through `solve_with_gate(...)` with `source="jee"`. When `pro`: leave the existing
  branch exactly as-is.
- **⚠ KEY-BLIND PAYLOAD (D2 — easy to miss):** today the loop injects `actual_answer_key` INTO
  `payload_dict` (**lines 204-205**), so the current solver is **key-fed**. For the **flash tier**, build
  the payload **WITHOUT** `actual_answer_key`; the key flows *only* into the gate's `answer_key` param.
  The cascade's Pro re-solve is **also** key-blind. **Regression nuance:** the legacy `--solver-tier pro`
  path **stays key-fed** (byte-identical to today) — do NOT strip the key there. The two tiers diverge
  here on purpose. Add an assert/comment in `solve_with_gate` that its `prompt` is key-blind.
- Persist new `review_status`: `GATE_FAILED`, `KEY_UNVERIFIED`. The existing success write
  (`update_solution_in_db`, sets `review_status='UNVERIFIED'`, `is_generated=TRUE`) and the
  `retry_count`/`GENERATION_FAILED` exception machine (lines 269-282) stay.
- `image_urls`, `payload_dict`, `build_smart_context_payload`, `--use-smart-context` are already built
  in the loop — reuse them. Router uses `has_figure = bool(image_urls)`.

### Component 5 — NCERT wiring (`pipelines/ModelEngineering/ncert_pipeline_orchestrator.py`)
- Add a **new key-blind generation entry** — recommended `--task generate` (or a sibling
  `ncert_solution_pipeline.py` mirroring the JEE file). It does: fetch rows → `generate_assembly_line`
  on Flash (key-blind) → `solve_with_gate` with `source="ncert"` → write `questiondata.solution`.
- Gate uses `questiondata.answer_key` (populated by Component 6) **for verification only**. Rows with no
  checkable key (proofs/derivations) → store Flash + `KEY_UNVERIFIED` (Phase-2 verifier territory).
- **Do not touch** the existing `regenerate`/`pedagogy`/`format` tasks (key-fed Gold-Set curation).
- Reuse `db_client.get_smart_context_for_question` (`db_client.py:361`) under `--use-smart-context`.

### Component 6 — NCERT answer-key ingestion (parallel track, the human runs this)
- Run `MultiStep/ingest_answer_keys.py` across the NCERT corpus (resumable).
- **Verification 0 (critical):** the `regenerate` task does `str(ans_key)` and would silently pass the
  literal string `"None"`. So confirm *real* coverage:
  `SELECT count(*) FILTER (WHERE answer_key IS NOT NULL) FROM questiondata;` before vs after.

---

## 4. Gotchas (these have bitten us — honor them)

- **G1 — Byte-identical default.** Default `PromptSet` strings must be copy-pasted exactly; default
  `--solver-tier pro`. Anything that changes existing output is a regression, not a feature.
- **G2 — DB connection drops.** Azure PostgreSQL closes connections during long LLM calls. Never hold
  one connection across the row loop — use the reconnect-on-drop `execute_write()` / `db_writer`
  pattern already in the pipelines.
- **G3 — Corrupt keys (KI-6).** `is_corrupt_key` (≥9 digits) → verdict `unknown` → never a miss, never
  routes to Pro. Honor this in the cascade.
- **G4 — JSON parsing.** Model output may be fenced in ```json … ``` and may have bad escapes. Reuse
  the existing strip + `generator._sanitize_json_escapes` fallback (`jee_solution_pipeline.py:245-260`).
- **G5 — Regional host for any *tuned* endpoint.** Not used in the ship path (we're untuned), but if you
  touch `batch_evaluator`'s tuned branch, the regional-subclient swap (`generate_solution` 295-305) must
  stay — global host returns 404 for tuned endpoints.
- **G6 — Formatter already Flash.** Don't "downgrade" the formatter; `config.formatter_model` is already
  `gemini-3-flash-preview` thinking=LOW for both Pro and Flash assembly. Only solver+tutor differ.
- **G7 — `source` field.** The narrowed router needs `record["source"]`. Make sure both production
  callers and any new harness record-builder set it.

---

## 5. Checkpoints (the human runs DB/LLM jobs; you write tests + prepare commands + read results)

**CHECKPOINT 1 — after Phase 1 (Components 0-3). Fully offline, deterministic, $0.**
- **You write** pure-unit pytest (no LLM, no DB):
  - `router.select_mode_for_record`: `{source:"jee", has_figure:True}` → `"pro-assembly"`;
    `{source:"ncert", has_figure:True}` → unchanged; any no-figure → unchanged; `router_enabled=False` → unchanged.
  - re-homed `answer_match`: corrupt key (≥9 digits) → `"unknown"`; letter match/mismatch; numeric tolerance (494 vs 494.65 → correct).
  - `flash_assembly_config()` → solver/tutor `model_id == "gemini-3-flash-preview"`; `batch_evaluator` still imports.
  - **Byte-identical guard (THE regression gate):** assert `DEFAULT_PROMPT_SET.solver_system` / `.tutor_system`
    **fully equal** golden copies of the pre-change literals (copy from `git show HEAD:…/solver_engine.py`),
    and `DEFAULT_PROMPT_SET.formatter_system_prefix + "<SCHEMA>"` equals the original Stage-3 string with
    `{original_system_prompt}="<SCHEMA>"`. **Full string equality — not substring/`in` checks** (a dropped
    sentence or doubled space must fail).
  - **Cascade behavior:** stub fake generators returning canned JSON `.text`; assert `solve_with_gate` returns
    the right `(result, status)` for all 4 branches — `correct`→UNVERIFIED, corrupt-key→KEY_UNVERIFIED,
    `wrong`→Pro-correct→UNVERIFIED, `wrong`→Pro-wrong→GATE_FAILED.
- **Do NOT run a stochastic regression diff.** pro-assembly runs at temperature 0.4/0.6 → re-running and
  diffing answers can't prove byte-identicalness (sampling noise) and risks a false alarm. The golden-string
  assert above *is* the byte-identical guarantee, done deterministically. (Optional, for execution
  confidence only: a 1-row `pro-assembly` "does it still run / parse" smoke — never a byte-diff.)
- **STOP. Report `pytest -v` results. Wait for green-light before Phase 2a.**

**CHECKPOINT 2 — after Phase 2a (NCERT vertical, Components 5 + 6).**
- **Human runs** key ingestion: `python -m ...ingest_answer_keys` (resumable) + the **Verification 0**
  count query (`count(*) FILTER (WHERE answer_key IS NOT NULL)` before/after — guard the `str(None)` trap).
- **Human runs** the new NCERT generate path on **one chapter per subject** (Physics/Chemistry/Maths),
  then views the rendered KaTeX in the app: confirm pedagogy + formatting hold **and the JEE persona is
  gone** (no "IIT-JEE"/"Le Chatelier's" framing on NCERT). Confirm the gate fires once keys are present.
- **STOP. Report visual findings + gate behavior. Wait for green-light before Phase 2b.**

**CHECKPOINT 3 — after Phase 2b (JEE vertical, Component 4).**
- **Human runs** `python jee_solution_pipeline.py --solver-tier flash --year 2024 --limit <small>` on one
  paper-shift slice. Confirm: Flash solves; gate matches; mismatch → independent Pro re-solve; double-miss
  → `GATE_FAILED`; JEE-figure rows → Pro; non-figure stay Flash. Inspect with
  `pipelines/ModelEngineering/dump_failures.py` + `analyze_holdout.py`.
- **Then commit** (owner sign-off): refactored `batch_evaluator.py`, re-homed `answer_match.py`, new
  `router.py` (+ `gate.py`), `config.flash_assembly_config`, `solver_engine.py` PromptSet, JEE + NCERT edits.

**Regression guard (all phases):** default `--solver-tier pro` + default `PromptSet` keep existing
behavior byte-identical; nothing changes until a new flag is flipped.

---

## 6. Out of scope (Phase 2 — do NOT build now)
- Key-blind verifier/repair via `generate_with_feedback` (general confidence gate for keyless content).
- JEE figure crop/upload (KI-3) + multimodal Flash test.
- RAG-grounding in the Tutor stage.

If you find yourself needing any of these to make the cascade work, **stop and ask** — it means a
boundary moved.
