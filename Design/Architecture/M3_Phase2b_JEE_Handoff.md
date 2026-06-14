# M3 Phase 2b — JEE Wiring (Component 4) — Execution Handoff for Sonnet

> **Read this, then build. Single phase, single file edit + a verification run.** Phase 1 (shared
> contract) and Phase 2a (NCERT) are DONE and CP1/CP2 are GREEN. This is the **last build phase
> before commit.** The planning owner (Opus) is available — **ask before coding if anything is unclear.**
>
> **Branch:** `feature/jeeascent`. **Do NOT commit** until CP3 passes and the owner signs off.
> **Default behavior must stay byte-identical** until `--solver-tier flash` is explicitly passed.

---

## 0. One-paragraph why
The Flash 3-stage Assembly-Line solver + answer-key gate + JEE-figures-only router is already built and
shared in `MultiStep/` (`solver_engine.py` PromptSet, `config.flash_assembly_config()`, `router.py`,
`answer_match.py`, `gate.solve_with_gate`). NCERT already consumes it (Phase 2a). **This phase wires the
same shared spine into the JEE production generator** — behind a new opt-in flag — and validates the
gate + router + cascade against the **real 2024 answer keys** that already live on `jee_question_bank`.

## 1. The ONE file you edit
`pipelines/JEEAscentPipeline/jee_solution_pipeline.py` — the row loop is **lines 180–282** (anchors below,
verified 2026-06-02). Reuse everything already built in that loop; do **not** rebuild payload/image/parse logic.

| Anchor | What's there now |
|---|---|
| `198–205` | `payload_dict` built; **`actual_answer_key` injected at 204–205 if present** ← the ⚠ below |
| `207–210` | smart-context block (`--use-smart-context`) |
| `212–218` | `image_urls` from `figure_url` + `option_figure_urls` |
| `220` | `system_prompt` (subject-substituted) |
| `222` | `user_prompt` (wraps `payload_dict` as JSON) |
| `224–241` | call site: `--use-assembly` → `generate_assembly_line`, else single-pass |
| `243–260` | markdown-strip + `json.loads` → on fail `generator._sanitize_json_escapes` (reuse verbatim — Gotcha G4) |
| `262` | `update_solution_in_db(db_writer, q_id, json.dumps(parsed))` — **read this fn's signature**; success write sets `review_status='UNVERIFIED'`, `is_generated=TRUE`. You must be able to pass `GATE_FAILED`/`KEY_UNVERIFIED` through it (extend it if it hardcodes the status). |
| `269–282` | exception path: `retry_count++`, `GENERATION_FAILED` at ≥3 — **leave as-is.** |

## 2. What to build

### 2a. New flag
Add to the existing argparse: `--solver-tier {pro,flash}`, **default `pro`**.

### 2b. `pro` tier (default) = NO CHANGE
The existing branch stays **exactly as-is, key-fed** (the `actual_answer_key` injection at 204–205 stays).
This is the byte-identical regression guard. Do not touch this path.

### 2c. `flash` tier = shared cascade
Build once, before/at the top of the loop:
```python
from config import flash_assembly_config          # MultiStep (already on sys.path)
from gate import solve_with_gate
from solver_engine import GoldenGenerator
# JEE keeps the DEFAULT PromptSet (it IS the JEE persona — byte-identical). Do NOT pass NCERT_PROMPT_SET.
flash_gen = GoldenGenerator(client, flash_assembly_config())     # default PromptSet
pro_gen   = GoldenGenerator(client, generator.config)            # current/default config = the Pro re-solver
```
Then per row, when `args.solver_tier == "flash"`:
```python
sol, review_status = solve_with_gate(
    prompt=user_prompt,            # ⚠ MUST be key-blind — see §3
    system_prompt=system_prompt,
    answer_key=answer_key,         # the key goes ONLY here (gate), never the prompt
    options=options,
    image_urls=image_urls or None,
    flash_generator=flash_gen,
    pro_generator=pro_gen,
)
parsed = <reuse the 243–260 strip+parse on sol.text>
update_solution_in_db(db_writer, q_id, json.dumps(parsed), review_status)   # pass the status through
```
Router lives **inside** `solve_with_gate`/`router.py` — it already keys on `source=="jee"` + `has_figure`.
Pass `source="jee"` and `has_figure=bool(image_urls)` however `solve_with_gate`/router expects (check the
signature you built in Phase 1 — if `solve_with_gate` doesn't yet take `source`/`has_figure`, thread them in).

## 3. ⚠⚠ The one thing that will silently break correctness if missed (Decision D2)
Today the loop is **key-fed**: lines 204–205 put `actual_answer_key` *into* `payload_dict`, which becomes
the prompt. **A key-fed solver fudges numbers to match the key — including corrupt keys (KI-6).**

For the **`flash` tier**, build the payload **WITHOUT** `actual_answer_key`:
```python
payload_dict = {"problem_text": problem_text, "options": options}   # NO actual_answer_key
# (smart-context + image_urls as today)
```
The key flows **only** into `solve_with_gate(answer_key=...)`. The cascade's Pro re-solve is **also**
key-blind (it re-solves the same key-blind prompt). Add an assertion at the top of `solve_with_gate`:
```python
assert "actual_answer_key" not in prompt, "D2: solver prompt must be key-blind"
```
**The two tiers diverge here on purpose:** legacy `pro` stays key-fed (regression-identical); `flash` is
key-blind + gate-verified. Easiest clean implementation: build `payload_dict` **without** the key always,
and **only the `pro` branch** re-adds `actual_answer_key` before its call.

## 4. Gotchas (honor these)
- **G3 corrupt keys (KI-6):** `is_corrupt_key` (≥9 digits) → gate verdict `unknown` → store Flash +
  `KEY_UNVERIFIED`, **never** a miss, **never** routes to Pro. Already in `answer_match`/`gate` — just don't defeat it.
- **G2 DB drops:** use the existing `db_writer`/`execute_write` reconnect pattern; never hold one conn across the loop.
- **G4 JSON parse:** reuse the 243–260 strip + `_sanitize_json_escapes` fallback on `sol.text`.
- **G7 source field:** router needs `source="jee"`. Make sure it's set.
- **Resumability:** keep the existing `solution IS NULL` / `retry_count < 3` fetch — unchanged.

## 5. CHECKPOINT 3 (human runs the LLM/DB job; you prep the command + read results)
- **Human runs** on **one small 2024 paper-shift slice**:
  `python jee_solution_pipeline.py --solver-tier flash --year 2024 --limit <small>` (pick a slice with both
  figure and non-figure rows). Hand over the exact command + a verification query.
- **Confirm (the four cascade/router behaviors):**
  1. Non-figure row, Flash answer **matches** key → stored, `review_status='UNVERIFIED'`.
  2. Flash answer **mismatches** key → **independent Pro re-solve** fires → if Pro matches → `UNVERIFIED`;
     if Pro also misses → `GATE_FAILED`.
  3. **JEE figure row → Pro** (router), non-figure → Flash.
  4. Corrupt/≥9-digit key → `KEY_UNVERIFIED`, no Pro call.
- Inspect with `pipelines/ModelEngineering/dump_failures.py` + `analyze_holdout.py`.
- **STOP. Report results + the review_status spread. Wait for owner sign-off before commit.**

## 6. Do NOT do
- Do not touch the `pro` tier, the NCERT path, or the existing `--use-assembly` semantics.
- Do not add a key-fed "fixer" pass (rejected — D3). Cascade is Flash → gate → key-blind Pro → `GATE_FAILED`.
- Do not commit before CP3 + sign-off. Do not fix the frontend F1/F2 here (separate post-commit cleanup).
- Do not run long Gemini/DB jobs yourself — hand the human exact commands.

## 7. Commit (only after CP3 green + sign-off)
Refactored `batch_evaluator.py`, re-homed `answer_match.py`, new `router.py` + `gate.py`,
`config.flash_assembly_config`, `solver_engine.py` PromptSet, NCERT `--task generate`, JEE `--solver-tier`.

---
**Cross-refs:** `M3_PipelineIntegration_Handoff.md` (full §Component 4 + Decisions D1–D8 + Gotchas),
`M3_PipelineIntegration_Plan.md` (architecture). CP1/CP2 already GREEN.
