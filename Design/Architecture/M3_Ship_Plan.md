# M3 Ship Plan — Tuned Flash, Stricter Bar, Production Integration

> **Status (2026-05-28):** STRATEGIC PIVOT — dropping the LoRA tuning track. Phase F confirmed capacity displacement (tuning HURTS solver accuracy). Google Cloud deprecation: **tuning OFF June 15, 2026 for all projects.** Untuned `gemini-3-flash-preview` (95% Acc-routable) already beats our best tuned 2.5-flash. New direction: untuned-3-flash 3-stage architecture. **Phase V (rigorous solver verification) approved + NEXT.** Phases A-H below are HISTORY.

## ⚠️ STRATEGIC PIVOT (2026-05-28)

**Two forcing functions converged:**
1. **Data:** the "Floor" baseline (95% Acc-routable) was **untuned `gemini-3-flash-preview`** all along (`UNTUNED_FLASH_MODEL_ID`), NOT 2.5-flash. It beats our best tuned 2.5-flash (80% no-router / 92.9% routed). Phase F proved tuning 2.5-flash actively HURT solver accuracy (capacity displacement — e.g. JEE Maths non-fig 100% Floor → 75% Tuned-v2). Tuning only ever helped Ped + Fmt, both achievable on untuned 3-flash via prompt + `response_schema`.
2. **Deprecation (Google Cloud email 2026-05-28):** model **tuning turns OFF June 15, 2026 for ALL projects** (2.5-flash, 2.5-flash-lite, 3-flash-preview). Inference access stays (project active). ~18 days to do any last tuning if needed.

**New target architecture** — Pro's proven 3-stage design, cheaper models per stage, NO tuning dependency:
- **Solver:** untuned `gemini-3-flash-preview` (Phase V verifies)
- **Tutor:** untuned `gemini-3-flash-preview` + adapted Pro Stage-2 Socratic prompt (Phase W tests; tune-2.5-before-June-15 only as fallback)
- **Formatter:** `response_schema` enforcement (proven Phase 6.5)
- **Router:** figure-bearing → Pro (KI-3 + image-needed)

Existing v1/v2 tuned endpoints → legacy/fallback. Rationale: deprecation-proof, higher accuracy, buys runway for own-model (S-DAG) work.

### Phase V — Rigorous solver verification (APPROVED 2026-05-28, NEXT) (~$10, ~1.5 hr)

Confirm on a WIDE sample (both sources, all strata) that untuned gemini-3-flash is genuinely accurate as a solver. Two arms by answer-key format.

- **Common solver prompt:** adapt Pro Stage-1 (`solver_engine.py:164-170`) + force `{final_answer, reasoning}` via response_schema for clean extraction. New `solver_verify_system_instruction.txt`.
- **ARM 1 — JEE objective (~250 rows, no judge, ~$4):** clean answer keys (MCQ=letter, Integer=numeric) → programmatic match. Stratify subject × difficulty × figure. Include figs (report separately — JEE fig = KI-3 blind, confirms router need). Sample PENDING answer_key-NOT-NULL, exclude 100 holdout + 369 gold. New `verify_solver_accuracy.py`.
- **ARM 2 — NCERT judged (~150 rows, LLM judge, ~$6):** freeform keys → accuracy_only judge. Stratify subject × figure. **PASS IMAGES for NCERT figure rows** (images exist, unlike JEE) → tests multimodal solving, informs whether router can shrink for NCERT figs. Reuse `batch_evaluator.py --model flash-untuned` + mode=accuracy_only (1-line tweak).
- **Deliverable:** `runs/_SOLVER_VERIFICATION_3flash.md` — combined, fully stratified.
- **Exit (USER GATE):** ≥95% non-fig both sources → proceed to Phase W (tutor). 90-94% → discuss router fallback. <90% → reconsider. PAUSE for user before W/X/Y.

### Phase W/X/Y — sketch (GATED on V + user approval)
- **W — Tutor test:** untuned 3-flash + adapted Pro Stage-2 Socratic prompt (`solver_engine.py:180-199`), LLM-judge Pedagogy on 100-row holdout. ≥4.5 Ped → no tuning. Short → tune-2.5-tutor-before-June-15 fallback.
- **X — Assemble + eval:** full untuned-3-flash 3-stage + figure router on frozen 100-row holdout; full 3-D vs Pro Target + 95% bar.
- **Y — Ship:** `--use-untuned-3flash` flag in bulk pipelines, smoke test, broad rollout. v1/v2 endpoint retain/decommission decision.

---

## HISTORY (Phases A-H — superseded by the pivot above)

> **Status (2026-05-27 PM):** Phase A done (93.0%), Phase B v2 retune done (92.9% — **headline accuracy did NOT lift** despite +114 new Gold rows). Architectural question raised: are we overloading LoRA capacity by training Solver+Tutor+Formatter in one call?

## Key terms (read this first)

- **Acc-routable %** — fraction of holdout rows where the model got the math/answer correct (Accuracy score = 5), regardless of Pedagogy/Formatting. The dimension we can't patch downstream — wrong math is wrong math.
- **Router** — per-row dispatcher that sends some rows to Pro Assembly and others to Tuned Flash. Currently fires on any `has_figure=True` row.
- **Schema enforcement** — Vertex `response_schema` parameter that forces Tuned Flash to include `step_type`, `nudge_hint`, etc. in every output (otherwise the tuned model intermittently strips them).
- **KI-3** — Known Issue #3 from `pipelines/JEEAscentPipeline/QA_Tracker.md`: JEE extraction pipeline never cropped/uploaded figure images, so `figure_url` is NULL on 100% of `jee_question_bank` even where `has_figure=True`. Result: ~170 JEE figure-dependent problems have no image available, so both Pro and Tuned guess from text alone. Fix = re-run extraction with proper figure crop + blob upload + DB write. ~3-5 days, post-MVP work. This is the natural ceiling we can't break without it (Pro Target itself only hits 98% Acc-routable, not 100%, because of KI-3).
- **Path A (text-only)** — current state; tune on text-only training data.
- **Path B (multimodal)** — add `inlineData` image parts to training data (NCERT images via `figure_info[*].url`); JEE blocked by KI-3.

## Context

Phase 6.5 (Vertex `response_schema` enforcement + figure-aware router for JEE) lifted Tuned Flash v1 from 66.7% → 87.0% Full-pass and 78.8% → 88.0% Acc-routable on the 100-row frozen holdout. Without any retune. Full result: `pipelines/ModelEngineering/runs/M3.2_Decision_Outcome.md`.

**Phase A** (executed 2026-05-26) extended the router to ALL figure-bearing rows (not just JEE) and lifted further: **Full-pass 91.0%, Acc-routable 93.0%, NCERT Chem-fig veto resolved (25% → 100%), figure-bearing gap closed (12.6pp → 2.2pp).** Report: `runs/Experiment_Run_20260526_193008.md`. Per-subject veto cleared everywhere; lowest bucket is jee Physics-fig at 66.7% (KI-3-limited).

**Phase A landed 2pp short of the 95% bar.** Per the exit decision, we're in the "92-94% → scoped v2 retune" zone.

**Phase B v2 retune** (executed 2026-05-27): +114 new Gold examples (255 → 369). v2 endpoint: `projects/556442477537/locations/us-central1/endpoints/5262641432291704832`. Re-eval: **Full-pass 90.9%, Acc-routable 92.9%** — essentially flat vs Phase A (93.0% → 92.9%). Mixed per-bucket: NCERT Chem-fig +8.4pp (good), JEE Maths non-fig **-12.5pp (regression)**. Classic capacity-displacement signal. **+45% more data → 0pp headline lift** ⇒ "we're data-bound" hypothesis disproven.

**Comparison snapshot for restart context:**

| Metric | Pro Target | Untuned Floor | v1+schema+JEE-router (P6.5) | v1+schema+ext-router (Phase A) | **v2+schema+ext-router (Phase B)** |
|---|---|---|---|---|---|
| Full-pass % | 85.0 | 0.0 | 87.0 | 91.0 | **90.9** |
| Acc-routable % | 98.0 | 95.0 | 88.0 | 93.0 | **92.9** |
| Avg Acc | 4.96 | 4.89 | 4.75 | 4.80 | **4.85** |
| Avg Ped | 4.63 | 1.06 | 4.87 | 4.85 | **4.89** |
| Avg Fmt | 4.87 | 1.53 | 4.87 | 4.91 | **4.88** |

**Architectural question raised 2026-05-27 (user):** is the single-call architecture overloading LoRA? Asking Flash to do solver+tutor+formatter from 369 LoRA examples may exceed adapter capacity. Inference-side `response_schema` already takes formatter off the LoRA's plate; if we could also take tutor off (run Pro tutor as a downstream stage), LoRA could dedicate full capacity to the hardest skill (solver). The original M3 plan deliberately chose single-call for cost-and-data-simplicity reasons; that tradeoff is now showing.

**Two corrections to the M3 plan's ship criteria, made 2026-05-26:**

1. **Router-to-Pro is scaffolding, not destination.** The figure-aware router is the right *current* architecture, but it must shrink over time as Tuned learns to handle figure-bearing rows directly. NCERT chem-fig rows that today go to Pro are tomorrow's training data for v2 (via Path B — multimodal training with `figure_info` images). JEE figure-bearing stays routed to Pro until KI-3 (figure_url backfill) is fixed post-MVP.

2. **The original 85% Acc-routable bar was a *gate* bar, not a *ship* bar.** For an educational product where wrong math = student learns wrong answer, 15% accuracy error is unacceptable. **New ship bar: Acc-routable ≥95%** (1-in-20 error rate, still catchable by downstream review workflow). Pedagogy/Formatting can be patched at app level; Accuracy cannot.

The path: extend router (DONE) → v2 retune (next) → re-evaluate to 95% → THEN integrate into production bulk pipelines.

## Execution Phases

### Phase A — Extended router measurement [DONE 2026-05-26]

Extended `select_mode_for_record()` in `pipelines/ModelEngineering/batch_evaluator.py` from "JEE+has_figure → Pro" to "ANY has_figure → Pro". Re-ran 100-row eval; report `runs/Experiment_Run_20260526_193008.md`. Result: 91.0% Full-pass / 93.0% Acc-routable / NCERT Chem-fig veto resolved. 2pp short of bar → Phase B required.

### Phase B — Scoped v2 retune (~$25-30, ~1-2 days) [IN PROGRESS]

**Goal:** lift Acc-routable from 93% → 95-96% via accuracy-focused training data targeting the 5 Tuned non-figure residual failures.

**Data reality discovered 2026-05-27** (after B.1 code landed and DB was queried):
- **NCERT Chemistry has only ~1% figure-bearing problems in the entire DB** (4 of 446 NCERT chem rows). Source content (Class 11-12 NCERT chem) is naturally text-heavy.
- **All 4 NCERT chem-fig LEGACY rows are in the holdout** → harvest pool = 0 for NCERT chem-fig. Only 4 REJECTED chem-fig rows exist as fallback.
- **NCERT Physics has 19 figure-bearing LEGACY rows** → ~13 harvestable (after holdout exclusion).
- **Path B image-aug on existing Gold Set has near-zero leverage**: only 1 of 153 NCERT Gold rows has populated figure_info.

**Implication for cost-savings narrative:** routing NCERT chem-fig to Pro forever costs ~1% of NCERT chem traffic (1 in 100 problems). The "shrink router via NCERT chem-fig training" lever doesn't move much cost regardless of v2 outcome. **Accept this; focus v2 on the actual accuracy gap.**

**Revised v2 training data composition:**

| Source | Allocation | Why this bias |
|---|---|---|
| Existing 255 Gold (text-only, no image-aug since pool ~ empty) | base 255 | |
| ~~8 NCERT Phase A Pro outputs (5/5/5-gated)~~ — **DROPPED** | invalid | Those Phase A Pro outputs were generated on HOLDOUT rows. Promoting them to APPROVED_GOLD and including in training would contaminate the holdout (train + test on same IDs). Holdout integrity > free training data. |
| **~15-20 NEW NCERT Physics figure-bearing examples** (with images) | **figure-bearing target** | NCERT physics has enough data to train on (~13 harvestable). Path B applied to these. |
| **~20-25 NEW JEE Maths non-figure examples** | **PRIMARY accuracy target** | Tuned residual: 2/16 fail Acc on this bucket; reasoning-heavy problems. |
| **~15-20 NEW NCERT Chemistry non-figure examples** | secondary accuracy target | Tuned residual: 2/12 fail Acc on this bucket; also weak Ped (3.58 avg in v1, 4.83 in Phase A). |
| **~10 NEW NCERT Physics non-figure examples** | tertiary | Tuned residual: 1/11 fail Acc. |
| 0 NCERT Chemistry figure-bearing (DROPPED) | — | Data unavailable. Stays Pro-routed indefinitely; cost impact ~1%. |
| 0 JEE figure-bearing (DROPPED) | — | KI-3 blocks images. Stays Pro-routed indefinitely. |

Expected harvest: ~200-250 candidate generations, ~80% 5/5/5 pass = ~50-65 new APPROVED_GOLD. Combined with 255 originals = ~305-320 training rows.

**Existing infrastructure to reuse (no new code needed for harvest):**
- `pipelines/ModelEngineering/ncert_pipeline_orchestrator.py` — already supports `--task {regenerate|pedagogy|format}` + `--subject Chemistry` filtering
- `pipelines/ModelEngineering/evaluator_engine.py` — GOLD gate via `--target-status APPROVED --source ncert`
- `pipelines/ModelEngineering/run_ncert_goldset.py` — parallel 6-combo scale runner

**New code needed for v2:**
- `pipelines/ModelEngineering/jsonl_exporter.py` — `--multimodal` flag to emit image-URL parts in user content
- `pipelines/ModelEngineering/convert_to_vertex_jsonl.py` — `--multimodal` flag to fetch image bytes via `gemini_client._fetch_image_bytes(url)` and emit as `{"inlineData": {"mimeType": ..., "data": base64}}` Vertex parts

**Tuning + first eval (router still ON):**
- `python launch_tuning_job.py --dataset gold_sft_vertex_v2.jsonl --display-name aryabhata-flash-sft-v2` (~45 min, ~$8)
- `python batch_evaluator.py --model flash-tuned --tuned-endpoint <v2-endpoint> --holdout-file holdout_eval_set.json --label "M3.B Candidate Flash-Tuned v2 schema+extrouter"` (~40 min, ~$15)

**Phase B PRIMARY exit gate (production ship):** Acc-routable ≥95% on the 100-row holdout AND no subject <50% Acc-routable. If not met, iterate.

**Phase B SECONDARY exit gate (router shrink — the cost-savings goal):** run an additional eval with `--no-router` (Tuned handles everything, no Pro fallback) and inspect the NCERT figure-bearing subset specifically:
- If Tuned-v2 hits ≥95% Acc-routable on the 10 NCERT figure-bearing holdout rows → **shrink the router rule** to fire only on JEE-fig (drop NCERT). NCERT figure-bearing then flows through Tuned at ~5% Pro cost = real long-term cost savings.
- If Tuned-v2 < 95% on NCERT-fig → keep extended router as-is; document the chem-fig bucket as "needs more training data or v3" in `M3.2_Decision_Outcome.md`.
- JEE-fig stays Pro-routed regardless (KI-3 blocks until that's fixed).

### Phase F — Tactical investigation (~1 hour, ~$20) [NEXT — AUTO-MODE APPROVED 2026-05-27]

Before committing to either ship-at-92.9% OR architecture pivot, settle two empirical questions cheaply.

**(F.1) Investigate JEE Maths regression** (~30 min, free — read-only):
- Pull the 4 JEE Maths non-fig failures from v2 (`runs/Experiment_Run_20260527_131515_RAW.json`) and the 2 from Phase A (`runs/Experiment_Run_20260526_193008.md`).
- For each: dump problem statement + judge feedback. Diff what kind of error v2 made vs Phase A.
- Identify which of: (a) v2 model regressed on rows v1 got right (true capacity displacement), (b) v2 failed on DIFFERENT rows (random sampling noise), (c) judge non-determinism (same rows fail/pass run-to-run inconsistently).
- Deliverable: `pipelines/ModelEngineering/runs/_JEE_MATHS_REGRESSION_DIFF_v1_vs_v2.md` with classified diagnosis.

**(F.2) `--no-router` ablation on v2** (~40 min, ~$15):
- `python batch_evaluator.py --model flash-tuned --tuned-endpoint projects/556442477537/locations/us-central1/endpoints/5262641432291704832 --holdout-file holdout_eval_set.json --no-router --label "M3.B Candidate Flash-Tuned v2 noroute"`
- Tells us pure single-call Tuned performance, isolated from Pro fallback. If hits ≥95% somehow, single-call ship (a) is achievable. If similar to v1's pure-Tuned (~80%), router is essential (confirms current architecture).
- More importantly: identifies WHICH rows are dragging Tuned down without Pro fallback — needed input for Phase G design if triggered.

**Phase F exit decision** (USER REVIEW GATE — DO NOT auto-proceed to G):
- If F.1 shows JEE Maths regression is judge noise / sampling artifact → recommend ship at 92.9% via Path H.b
- If F.1 shows real capacity displacement AND F.2 confirms pure-Tuned ceiling ~80-85% → recommend Phase G (architecture pivot test)
- If F.2 surprises with pure-Tuned at 90%+ → architecture is fine; recommend ship at 92.9% via Path H.b
- **All three outcomes require explicit user approval before Phase G or Phase H execution.**

### Phase G — Cheap focused-solver experiment (CONDITIONAL on Phase F + USER APPROVAL) (~3-4 hours, ~$25)

**DO NOT execute without user sign-off after Phase F.** Architecture pivot decision rests with user.

Goal: test the user's hypothesis cheaply — can Tuned Flash hit Pro-level accuracy when trained on SOLVER-ONLY outputs (no tutor, no formatter)?

**Phase G design rests on three explore-verified findings (2026-05-27):**
1. Stage 1 `_stage_1_expert_solver` outputs **free-form prose math derivations**, not JSON (`solver_engine.py:161-178`). Training data shape = `{user: problem, model: solver prose}`.
2. `_stage_1_expert_solver` is private but trivially exposable as a public `generate_solver_only()` wrapper.
3. **Vertex tuning API does not expose LoRA rank or epochs.** Can't directly test capacity hypothesis; must infer from end-to-end metrics.

**(G.1) Derive solver-only training data** (~1 hour, ~$5):
- Add public `GoldenGenerator.generate_solver_only(question_text, image_urls)` method wrapping `_stage_1_expert_solver`. Trivial.
- New script `pipelines/ModelEngineering/build_solver_only_dataset.py`: iterate over 369 APPROVED_GOLD rows, call `generate_solver_only()` per row, save prose output to `gold_sft_dataset_v3_solver_only.jsonl` (ChatML format, `model.content` = solver prose). Resumable per-row checkpoint.

**(G.2) Convert + tune** (~50 min, ~$8):
- Extend `convert_to_vertex_jsonl.py` with `--solver-only` flag: skips the model-content-must-parse-as-canonical-JSON check.
- New `canonical_solver_system_instruction.txt` = byte-identical copy of the Stage 1 system prompt from `solver_engine.py:164-170`.
- Tune: `python launch_tuning_job.py --dataset gold_sft_vertex_v3_solver_only.jsonl --display-name aryabhata-flash-sft-v3-solver-only`.

**(G.3) Accuracy-only eval on v3-solver-only** (~30 min, ~$10):
- Add `--model flash-tuned-solver-only` mode to `batch_evaluator.py`. Uses Stage 1 system prompt, gets prose output, judges ACCURACY ONLY (`evaluator_engine.py --mode accuracy_only`).
- Don't wire up tutor or formatter yet — focused experiment, not production architecture.
- Run on the 100-row holdout. Report Avg Acc + Acc-routable.

**Phase G exit decision** (USER REVIEW GATE again):
- If v3-solver-only Acc-routable ≥ 95% AND Avg Acc ≥ 4.9 → capacity hypothesis CONFIRMED; recommend Phase H.a (architecture pivot).
- If v3-solver-only Acc-routable still ~92-93% → capacity wasn't the bottleneck; recommend Phase H.b (ship at 92.9%).
- If v3-solver-only is WORSE than 92% → focused training hurt; ship v2 via Path H.b.

### Phase H — Decision + Ship (revised) [REPLACES old Phase D sequencing]

Two ship paths based on Phase G outcome:

**Path H.a (architecture pivot — if Phase G shows accuracy lift):**
- Build full v3 multi-stage inference: Tuned-v3-solver (prose) → Pro Tutor → Pro Formatter (or cheap Flash for Stages 2+3 if quality holds).
- Wire `_select_mode_for_record` router to dispatch to v3 instead of v2 for non-figure rows.
- Run full 3-D eval to confirm Ped + Fmt don't regress.
- Cost mix with cheap Flash Stages 2+3: ~12% of Pro (still ~8x cheaper than all-Pro).
- Production integration follows: `--use-tuned-flash` flag in bulk pipelines, smoke test, then broad rollout.

**Path H.b (ship at 92.9% — if Phase G shows no lift, OR if user accepts the ceiling after Phase F):**
- Document the ceiling honestly in `runs/M3.2_Decision_Outcome.md` (update with v2 numbers + Phase F findings + KI-3 caveat).
- Ship Tuned-v2 + schema + extended router as the M3 outcome. Endpoint: `projects/556442477537/locations/us-central1/endpoints/5262641432291704832`.
- Defer M3+ improvements until KI-3 backfill OR Gemini 3 Flash tuning unlocks more capability.

### Phase C — Shared router module + attribution ablation (~30 min, ~$2-6)

Two distinct sub-tasks bundled here:

**(C.1) Shared router module — code hygiene before production integration.**

Currently `select_mode_for_record()` + `CANONICAL_SOLUTION_SCHEMA` both live inside `pipelines/ModelEngineering/batch_evaluator.py` (a test harness). Phase D will wire the same logic into the bulk pipelines (`jee_solution_pipeline.py`, `ncert_pipeline_orchestrator.py`); duplicating risks divergence.

- **CREATE `pipelines/ModelEngineering/router.py`** with `select_mode_for_record()` + `CANONICAL_SOLUTION_SCHEMA`.
- **MODIFY `pipelines/ModelEngineering/batch_evaluator.py`** to import from `router.py`; delete the inline duplicate.
- No behavior change; just structural refactor for single-source-of-truth.

**(C.2) Schema-vs-router attribution ablation — answers "where did the lift come from?"**

We have combined numbers (Phase 6.5 = +X overall, Phase A = +Y overall) but no clean per-lever attribution. Three ablation runs against whichever endpoint clears Phase B:

| Run | `--no-schema` | `--no-router` | What it tells us |
|---|---|---|---|
| `--no-router` | — | YES | Pure single-call Tuned. Decides whether (a) single-call ship was actually achievable on its own without router. |
| `--no-schema` | YES | — | What does router alone contribute when schema enforcement is off? |
| `--no-schema --no-router` | YES | YES | Bare endpoint baseline (already have this from v1's original run — 78.8%). |

Attribution table goes into `runs/M3.2_Decision_Outcome.md`. Useful for future architecture decisions.

### Phase D — Production bulk-pipeline integration (~1 hour, $0)

Gated on Acc-routable ≥95% from Phase B.

**MODIFY `pipelines/JEEAscentPipeline/jee_solution_pipeline.py`** — at the row-loop model-selection point (~line 227), call `router.select_mode_for_record()` per row. Add `--use-tuned-flash` CLI flag that toggles between legacy all-Pro and routed-Tuned-with-Pro-fallback. Default: legacy (safe rollout).

**MODIFY `pipelines/ModelEngineering/ncert_pipeline_orchestrator.py`** — same pattern at the three task-handler functions (`regenerate_core_math` / `inject_pedagogy` / `apply_strict_formatting`). Per-row router call before model dispatch.

**MODIFY `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/config.py`** — add a `tuned_solver_model` `GeminiModelConfig` (`response_schema=CANONICAL_SOLUTION_SCHEMA`, `response_mime_type="application/json"`, `max_output_tokens=32768`, `temperature=0.4`). Point at the v2 endpoint.

**Per-call regional-client swap pattern** (already correctly implemented in `batch_evaluator.py` after the inverse-404 fix) — factor into `gemini_client.py` helper so both eval and bulk paths use the same code.

### Phase E — Smoke test before broad rollout (~30 min, ~$3)

Run each integrated pipeline on a tiny batch (5 rows each):
```bash
python pipelines/JEEAscentPipeline/jee_solution_pipeline.py \
    --use-tuned-flash --subject Mathematics --year 2024 --limit 5

python pipelines/ModelEngineering/ncert_pipeline_orchestrator.py \
    --task regenerate --use-tuned-flash --subject Maths --status LEGACY --limit 5
```

Verify clean runs, correct DB writes, router decisions match expectations, spot-check 2-3 solutions visually. Only after this smoke test, run larger batches over uncovered NCERT chapters / JEE papers.

## Files Summary

**CREATE:**
- `pipelines/ModelEngineering/router.py` — shared per-record dispatcher + `CANONICAL_SOLUTION_SCHEMA` constant.

**MODIFY:**
- `pipelines/ModelEngineering/jsonl_exporter.py` — `--multimodal` flag (Phase B).
- `pipelines/ModelEngineering/convert_to_vertex_jsonl.py` — `--multimodal` flag (Phase B).
- `pipelines/ModelEngineering/batch_evaluator.py` — import from `router.py` (Phase C).
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/config.py` — add `tuned_solver_model` (Phase D).
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py` — factor regional sub-client helper (Phase D).
- `pipelines/JEEAscentPipeline/jee_solution_pipeline.py` — `--use-tuned-flash` flag + router call (Phase D).
- `pipelines/ModelEngineering/ncert_pipeline_orchestrator.py` — same pattern in 3 task handlers (Phase D).

**REUSE unchanged:**
- `solver_engine.py` (`GoldenGenerator.generate_assembly_line` still used for routed-to-Pro rows).
- `evaluator_engine.py` (judge unchanged).
- `launch_tuning_job.py` (invoked for v2).

## Cost Estimate

| Phase | Cost | Status |
|---|---|---|
| A (extended router re-eval) | ~$2 | **DONE — 93.0%, 2pp short of bar** |
| B (scoped v2 retune — biased toward NCERT chem-fig) | ~$25-30 | next, REQUIRED |
| C (router module + 1-3 ablation runs) | ~$2-6 | after B |
| D (production integration code) | $0 | after C |
| E (smoke tests) | ~$3 | after D |
| **Total spent through Phase A** | **~$2** | |
| **Total projected (full plan)** | **~$35** | |

## Verification (end-to-end)

1. **Phase A:** ✅ done. Report `runs/Experiment_Run_20260526_193008.md`. Acc-routable 93.0%, NCERT Chem-fig veto resolved.
2. **Phase B:** v2 endpoint live in `runs/tuning_jobs.json`; re-eval report with Acc-routable ≥95% AND no per-subject <50%; SECONDARY eval (`--no-router`) tested on NCERT-fig subset to decide router shrink.
3. **Phase C:** `router.py` exists; `batch_evaluator.py` imports from it; attribution table in `runs/M3.2_Decision_Outcome.md`.
4. **Phase D:** `config.py` shows `tuned_solver_model`; both bulk pipelines have `--use-tuned-flash` flag that routes per-row.
5. **Phase E:** 5+5 smoke rows in DB with correct schema + sensible solutions; router log lines present in both pipelines.

## Risks

| Risk | Mitigation |
|---|---|
| v2 retune doesn't lift to 95% either | Iterate distillation loop (M3 plan §Phase D) OR fall back to even stricter post-hoc gating (queue tuned-generated solutions for explicit review state). |
| Bulk pipeline integration introduces a regression Phase 6.5 didn't catch | `--use-tuned-flash` is opt-in; default stays Pro-only. Smoke test (Phase E) validates before broad runs. |
| v2 endpoint cost overrun | Tuning is $8 fixed; harvest is variable cost — over-generate by 1.5x to absorb 5/5/5 gate misses, no more. |
| Regional-client swap regression (the bug that broke Phase 6.5's first run) | Refactor into `gemini_client.py` helper, single source of truth. |
| Multimodal Vertex tuning silently rejects image parts | Sanity-run on tiny subset first; check job logs for warnings. |

## Explicitly Out of Scope

- **M4 Student Feedback pipeline** — different model (`gemini-3-pro-image-preview`), different input (handwritten student work), different output (per-step evaluations). Not involved in M3.
- **KI-3 fix (JEE figure_url backfill)** — post-MVP. Router handles JEE-fig via Pro indefinitely until KI-3 is addressed.
- **Frontend changes** — frontend reads pre-stored `solution` JSONB; no live-inference path; no API changes needed.
- **A/B testing infrastructure** — `--use-tuned-flash` is the rollout control for now.
- **Output-image generation** — parked per E2E plan.

## Reference

- `Design/Architecture/M3_TuningLoop_v2_Plan.md` — prior v2 plan, superseded by this one for the ship path.
- `pipelines/ModelEngineering/runs/M3.2_Decision_Outcome.md` — Phase 6.5 result writeup.
- `pipelines/ModelEngineering/runs/_PED_REGRESSION_ANALYSIS_v1.md` — Phase 0 diagnostic.
- `pipelines/ModelEngineering/runs/Experiment_Run_20260526_193008.md` — Phase A report.
- Memory: `project_vertex_tuned_endpoint_regional_host_2026_05_26.md` — regional-host gotcha + per-call swap pattern.
