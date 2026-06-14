# Model Engineering — Claude Code Guide

## What This Is

The RLAIF **Gold Set + evaluation machinery** for the "nimble model" initiative: move
Aryabhata off costly Gemini 3.1 Pro by fine-tuning **Gemini 3 Flash** on a corpus of
strict-5/5/5 (`APPROVED_GOLD`) solutions. Solutions are generated/cleansed through a
decoupled **Assembly Line** and graded by a 3-dimension judge (Accuracy / Pedagogy /
Formatting).

## Current State (2026-05-23)

**Gold Set is COMPLETE** — 255 examples (153 NCERT + 102 JEE) exported to
`gold_sft_dataset.jsonl` (OpenAI ChatML; needs Vertex-native conversion before tuning).

**M3 Tuning Loop: APPROVED 2026-05-23, Phase A scaffolding landed.** Base model =
**`gemini-2.5-flash`** on Vertex AI (Gemini 3 Flash isn't tunable yet; only the 2.5
family is — verified via GCP docs research). Authoritative plan:
**`Design/Architecture/M3_TuningLoop_Plan.md`**. Decision matrix: ship single-call
if Tuned Full-pass within 2pp of Pro AND ≥85%; ship hybrid if Acc-routable ≥85%;
iterate distillation loop if <85%; drawing-board if still <70% after 2-3 retunes.
Gold dataset and `UniversalEvaluator` are model-agnostic — survive any 2.5
deprecation. Full history: `Design/Architecture/GoldSet_Execution_Tracker.md`.

## Key Files

| File | Role |
|------|------|
| `evaluator_engine.py` | `UniversalEvaluator` (Gemini 3.1 Pro 3-D judge) + the `--target-status` **GOLD gate** — promotes strict-5/5/5 rows to `APPROVED_GOLD`; works on both `questiondata` and `jee_question_bank` |
| `ncert_pipeline_orchestrator.py` | NCERT Assembly Line — `--task regenerate\|pedagogy\|format` |
| `run_ncert_goldset.py` | Parallel 6-combo scale-runner (pedagogy → format → gate) |
| `evaluate_ncert_baseline.py` | LEGACY accuracy gate (`LEGACY → MATH_PASSED \| REJECTED`) |
| `jsonl_exporter.py` | Exports `APPROVED_GOLD` from both tables → ChatML JSONL |
| `batch_evaluator.py` | **M3 baselining harness** — `--model {pro-assembly\|flash-untuned\|flash-tuned}`, `--holdout-file`, per-(source × subject × figure) breakdown, Full-pass / Acc-routable decision metrics; also legacy random-JEE mode |
| `build_holdout_set.py` | **M3 Phase A** — builds the frozen 100-record `holdout_eval_set.json` (50 NCERT + 50 JEE, balanced by subject, ~35% figure-bearing, ~20 `never_distill` final-exam slice, zero APPROVED_GOLD overlap) |
| `canonical_system_instruction.txt` | Frozen system prompt — byte-identical between training data and `batch_evaluator.py` flash modes (Vertex SFT requirement) |
| `evaluate_saved_generations.py` | DB-sample evaluation (existing solutions, no regeneration) |
| `verify_db_state.py` | Read-only DB state inspector |

Shared libs (`gemini_client.py`, `config.py`, `db_client.py`, `solver_engine.py`) are
imported via `sys.path` from `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/`.

## review_status State Machine

```
LEGACY ──[accuracy gate]──► MATH_PASSED | REJECTED
MATH_PASSED ──[pedagogy]──► PEDAGOGY_ADDED ──[format]──► APPROVED ──[GOLD gate 5/5/5]──► APPROVED_GOLD
REJECTED ──[regenerate]──► MATH_REGENERATED      (rewrite loop wired but DEFERRED)
```

## Conventions / Gotchas

- **GOLD = strict 5/5/5** (Accuracy = Pedagogy = Formatting = 5).
- DB writes go through `execute_write()` (reconnect-on-drop). Azure PostgreSQL closes the
  connection during long LLM calls — never hold one connection across a row loop.
- `config.formatter_model` = Gemini 3 Flash with `thinking_level=LOW` (formatting is
  mechanical; uncapped Gemini-3 thinking is slow). Pedagogy/solver keep full thinking.
- Canonical solution schema: per step `step_number, step_type, nudge_hint, explanation,
  latex_formula`; top level `steps[]`, `final_answer`. Chemistry uses mhchem `\ce{...}`.
- NCERT pipeline run book: `Design/Architecture/NCERT_Pipeline_Runbook.md`.

## Open Items

- 14 NCERT formatting-miss rows parked at `APPROVED` (recoverable by re-format).
- REJECTED-row rewrite loop deferred until after the tuned model exists.
- Tuning may want 500+ examples — re-run the pipelines to harvest more; machinery is ready.
