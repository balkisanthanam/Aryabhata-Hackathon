# M3 Phase B-prime — Tuned Flash v2 Plan

> **Status (2026-05-26):** Revised after Phase 0 diagnostic. **Phase 6.5 (schema-enforcement + figure-aware router) runs FIRST**, before any v2 retune work. v2 retune happens only if Phase 6.5 fails to clear the hybrid ship bar.
> **Phase 0 outcome:** see `pipelines/ModelEngineering/runs/_PED_REGRESSION_ANALYSIS_v1.md`. Dominant Pedagogy failure is **schema field omission** (`step_type`/`nudge_hint` missing from model output ~40% of the time, even on training rows). Fixable via Vertex `response_schema` at inference — no retune required.
> **Companion docs:** `M3_TuningLoop_Plan.md` (v1 plan + Phase A/B/C history), `E2E_SolutionModel_Implementation_Plan.md` (master tracker), `pipelines/ModelEngineering/CLAUDE.md` (folder guide).
> **Living artifacts produced by this plan:** `pipelines/ModelEngineering/runs/_PED_REGRESSION_ANALYSIS_v1.md`, `runs/tuning_jobs.json[1]` (v2 job), `runs/Experiment_Run_*Flash-Tuned_v2*.md`, `runs/M3.2_Decision_Outcome.md`.

## Context

M3 Tuned Flash v1 (255-example, text-only SFT of `gemini-2.5-flash`) was evaluated against the frozen 100-row holdout and failed both ship gates:

| Metric | Pro Target | Floor (Untuned) | **Tuned v1** |
|---|---|---|---|
| Full-pass % | 85.0% | 0.0% | **66.7%** (66/99) |
| Acc-routable % | 98.0% | 95.0% | **78.8%** (78/99) |
| Avg Acc / Ped / Fmt | 4.96 / 4.63 / 4.87 | 4.89 / 1.06 / 1.53 | **4.47 / 4.24 / 4.56** |

Per the M3 plan's decision matrix this triggers **(c) Iterate**. Two specific surfaces drive the gap:

1. **Figure-bearing collapse** — non-figure rows hit 84.4% Acc-routable (1pp from hybrid ship bar); figure-bearing hit 59.1% (gap 25.3pp >> Path B trigger of 15pp). Two subjects (JEE Physics-figure, NCERT Chem-figure) fall below the 50% per-subject veto. NCERT figures can be added to training (`figure_info[*].url` populated); JEE figures cannot (KI-3 — `figure_url` NULL on 100% of `jee_question_bank`).
2. **Pedagogy regression** — Phase A predicted Tuned > Pro on Ped (training data was 5/5/5-filtered); reality is Tuned 4.24 < Pro 4.63. Hypothesis failed. Needs diagnosis before assuming "more data fixes it."

**Goal:** Build Tuned Flash v2 by:
- (a) augmenting NCERT figure-bearing training rows with image blobs (Path B),
- (b) adding ~100 targeted new 5/5/5 examples (33 distilled from v1 holdout failures + ~70 fresh from weak-bucket pools),
- (c) deploying with a deterministic figure-aware router (JEE+figure → Pro Assembly, else → Tuned Flash v2),
- (d) preceded by a Pedagogy-regression diagnostic so we know whether (b) is the right lever.

Target: clear hybrid ship gate — **Acc-routable ≥85% on routed holdout** (figure-bearing JEE rows already handled by Pro).

## Approach (REVISED after Phase 0)

**Two-stage sequencing:**

1. **Phase 6.5 first (~1 hour, ~$2):** Add Vertex `response_schema` enforcement + figure-aware router to `batch_evaluator.py`, re-eval the *same v1 endpoint* on the holdout. Expected: schema-strip Pedagogy failures vanish, Acc-routable jumps from 78.8% toward 90%+. If hybrid ship gate (≥85%) clears → ship v1+schema+router as the M3 outcome, defer v2 retune indefinitely.

2. **v2 retune (Phases 1-5) — conditional:** only if Phase 6.5 fails to clear the hybrid gate. If triggered, scoped down (~$25-30) targeting just the residual failure modes that schema enforcement does NOT fix: KI-4 direct-instruction (~22% of Ped failures) and accuracy-cascade rows.

Original ~$55 budget reduces to ~$2 in the best case (Phase 6.5 ships) or ~$27-32 in the iterate case.

## Execution Phases

### Phase 0 — Pedagogy regression diagnostic (gating; ~2 hours, ~$0.50)

**Deliverable:** `pipelines/ModelEngineering/runs/_PED_REGRESSION_ANALYSIS_v1.md` with categorized findings + one-line plan adjustment.

Three small inspection scripts; do all three:

1. **CREATE `pipelines/ModelEngineering/inspect_pedagogy_failures.py`** (~80 lines):
   - Read `runs/Experiment_Run_20260526_105654_RAW.json` (Tuned v1).
   - Filter rows where `scores.pedagogy_score < 5`.
   - For each, dump: `id`, `source`, `subject`, Ped score, judge `feedback` (the verbatim prose complaint).
   - Group by first-sentence keyword cluster (rough categorize: "direct", "missing", "shallow", "skip", "leak").

2. **CREATE `pipelines/ModelEngineering/diff_tuned_vs_pro.py`** (~120 lines):
   - Cross-reference `runs/Experiment_Run_20260523_231104_RAW.json` (Pro Target) vs `runs/Experiment_Run_20260526_105654_RAW.json` (Tuned v1).
   - Select rows where Pro Ped=5 AND Tuned Ped<5 (these are the true regressions).
   - For each pair, render side-by-side the `nudge_hint` text per step from both solutions.
   - Output a markdown report: 5-10 head-to-head examples.

3. **CREATE `pipelines/ModelEngineering/probe_tuned_on_gold.py`** (~80 lines):
   - Pick 5 random IDs from `gold_sft_dataset.jsonl`.
   - For each, regenerate the solution via Tuned v1 endpoint AND via Pro Assembly.
   - Judge both via `UniversalEvaluator`.
   - Report: does Tuned score 5/5/5 on its own training data? If not, what's it scoring?

**Branching on Phase 0 outcome** (write the synthesis into `_PED_REGRESSION_ANALYSIS_v1.md`):

| Diagnosis | Adjustment to Phase 2/3 |
|---|---|
| Same KI-4 leak from Pro into Gold curation | Add a Pro Tutor-prompt tightening step before fresh-harvest in Phase 2 |
| SFT didn't take on Pedagogy (Gold rows themselves score Ped<5 via Tuned v1) | Tune v2 with duplicated strong-Socratic examples (sample weighting); OR park hybrid path with Ped-sensitive content routed to Pro |
| Coverage gap (specific topics weak) | Proceed as-is — targeted 100 will fix |
| Other / mixed | Pause, raise findings to user before launching v2 tune |

### Phase 1 — Image-augmented training data export (~30 min code, ~10 min run)

**MODIFY `pipelines/ModelEngineering/jsonl_exporter.py`:**
- Add `extract_image_urls()` helper (mirror `_extract_ncert_image_urls` from `build_holdout_set.py:84-96`).
- Modify `build_user_payload()` signature to accept an optional `image_urls: list[str]` arg.
- When images present AND `--multimodal` flag is set, emit the user content as a list of parts (text + image refs) instead of a single text string.
- For now keep the URL list passthrough; image-bytes inlining happens at Vertex-conversion time (next step).

**MODIFY `pipelines/ModelEngineering/convert_to_vertex_jsonl.py`:**
- Add `--multimodal` flag.
- When set, for each line: if `user_content` is a list (from new exporter), iterate parts:
  - `{"text": "..."}` → emit as Vertex `{"text": ...}` part.
  - `{"image_url": "..."}` → fetch bytes via `GeminiClient._fetch_image_bytes(url)` (reuse helper at `gemini_client.py:226-250`), base64-encode, emit as `{"inlineData": {"mimeType": <content_type>, "data": <base64>}}`.
- Skip image fetching for JEE rows even if URL present (KI-3 sanity — they're NULL anyway).
- Token budget check: bump char/4 estimate to add `258 tokens/image` per Vertex docs; assert sum < 131_072 per row.
- Output: `gold_sft_vertex_v2.jsonl` (versioned, do not overwrite v1).

**Verify:**
- `python jsonl_exporter.py --source ncert --output gold_sft_dataset_v1_with_ncert_images.jsonl --multimodal` produces 153 ChatML lines with image_url parts on NCERT figure-bearing rows.
- `python convert_to_vertex_jsonl.py --in gold_sft_dataset_v1_with_ncert_images.jsonl --out gold_sft_vertex_v2_imgaug.jsonl --multimodal` produces Vertex JSONL with `inlineData` parts.
- Sanity: line count == 153; ~30-50 lines should contain `inlineData` parts; head -1 inspected by eye for shape correctness.

### Phase 2 — Targeted fresh harvest (~3 hours, ~$20)

**Goal: net ~70 fresh 5/5/5 examples, weighted to v1 weak buckets.**

Allocation (rough — adjust based on Phase 0 findings):
- JEE Maths non-figure: 25 examples (v1 was 68.8% — weakest non-fig)
- NCERT Chemistry (any): 25 examples (v1 Ped 3.58 — weakest Ped)
- JEE Chemistry non-figure: 10 examples
- JEE Physics figure-bearing: 10 examples (KI-3 caveat — these will inflate JEE+fig training BUT still no images; useful only for text reasoning)

**Run existing scripts with targeting flags** (no new code needed):

JEE Maths fresh:
```bash
python pipelines/JEEAscentPipeline/jee_solution_pipeline.py \
    --subject Mathematics --year 2024 --use-assembly --use-smart-context --limit 50
```

NCERT Chemistry fresh:
```bash
python pipelines/ModelEngineering/ncert_pipeline_orchestrator.py \
    --task regenerate --subject Chemistry --status LEGACY --limit 50
python pipelines/ModelEngineering/ncert_pipeline_orchestrator.py \
    --task pedagogy --subject Chemistry --limit 50
python pipelines/ModelEngineering/ncert_pipeline_orchestrator.py \
    --task format --subject Chemistry --limit 50
```

Then GOLD-gate:
```bash
python pipelines/ModelEngineering/evaluator_engine.py \
    --target-status APPROVED --source ncert --limit 200
python pipelines/ModelEngineering/evaluator_engine.py \
    --target-status APPROVED --source jee --limit 200
```

Expected yield: ~80% pass rate × ~120 candidates → ~95 new APPROVED_GOLD (we keep ~70, slightly over-deliver).

**Verify:**
- `SELECT COUNT(*) FROM questiondata WHERE review_status='APPROVED_GOLD' GROUP BY <subject>;` deltas match allocation.
- `SELECT COUNT(*) FROM jee_question_bank WHERE review_status='APPROVED_GOLD' GROUP BY subject;` same.
- Critically: zero overlap with the 100 holdout IDs (the GOLD gate exclusion logic + `holdout_eval_set.json` ID set comparison).

### Phase 3 — Distillation harvest from v1 failures (~1 hour, ~$10)

**CREATE `pipelines/ModelEngineering/collect_distillation_examples.py`** per the M3 plan §Phase D spec:
- Read `runs/Experiment_Run_20260526_105654_RAW.json`.
- Filter rows where `scores.is_pass == False` AND `record.never_distill != True`.
- For each, regenerate via `GoldenGenerator.generate_assembly_line()` (Pro 3-pass), reusing the same problem payload.
- Gate each through `UniversalEvaluator` keeping only `result.is_gold` (strict 5/5/5) — prevents model collapse from training on imperfect data.
- Append survivors to `gold_sft_dataset_distillation_v1.jsonl` (separate file, merged at Phase 4).
- Resumable per-row checkpoint at `runs/_distill_ckpt_<output-basename>.jsonl` per feedback-prefer-resumable-pipelines.
- CLI: `python collect_distillation_examples.py --failures-from runs/Experiment_Run_20260526_105654_RAW.json --out gold_sft_dataset_distillation_v1.jsonl`

**Expected:** ~33 distillation candidates (the v1 holdout failures excluding `never_distill`). After 5/5/5 gating, conservatively ~20 survivors.

**Verify:**
- Output file line count: ~15-25.
- Each line is valid ChatML with system + user + model roles.
- Zero overlap with original Gold Set IDs (defensive — the failure IDs are from the holdout, which is by definition disjoint from Gold).

### Phase 4 — Build v2 dataset (~10 min)

Merge sources into a single v2 file:
1. `gold_sft_dataset.jsonl` (original 255)
2. `gold_sft_dataset_distillation_v1.jsonl` (~20 new from Phase 3)
3. Re-export from DB: `python jsonl_exporter.py --source all --output gold_sft_dataset_v2.jsonl --multimodal` will naturally include the Phase 2 newly-APPROVED_GOLD rows + Phase 3 distillation outputs (if appended to the table) AND image-augmented NCERT rows.

Note: simplest path is to land Phase 3 outputs in the DB (mark them `APPROVED_GOLD`) so the re-export from `jsonl_exporter.py` pulls everything in one call. Alternatively concat the JSONLs directly.

Then convert to Vertex format with images:
```bash
python convert_to_vertex_jsonl.py --in gold_sft_dataset_v2.jsonl --out gold_sft_vertex_v2.jsonl --multimodal
```

**Verify:**
- v2 line count: ~340 (255 + ~70 fresh + ~20 distillation).
- Image part count: ~50 (the NCERT figure-bearing subset).
- Strict system-prompt byte-equality assertion passes (existing check in converter).

### Phase 5 — Launch v2 tuning job (~45 min)

Use existing `launch_tuning_job.py` with v2 dataset:
```powershell
python launch_tuning_job.py --dry-run --dataset gold_sft_vertex_v2.jsonl --display-name aryabhata-flash-sft-v2
python launch_tuning_job.py --dataset gold_sft_vertex_v2.jsonl --display-name aryabhata-flash-sft-v2
```

No script changes needed — `launch_tuning_job.py` accepts `--dataset` and `--display-name` flags. Job record appends to `runs/tuning_jobs.json`.

**Verify:** `state=JOB_STATE_SUCCEEDED` + non-empty `tuned_endpoint` written to `runs/tuning_jobs.json[1]`.

### Phase 6.5 (NEW — runs FIRST) — Schema enforcement + figure-aware router (~1 hour code, ~$2 re-eval)

**Per Phase 0 finding:** the dominant Pedagogy failure mode is schema field-omission (`step_type`/`nudge_hint`), not coverage. Vertex `response_schema` enforces field presence at inference. Combined with the figure-aware router (originally Phase 6), this is the cheapest path to closing the gap.

**MODIFY `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/config.py`:**
- Add `response_schema: Optional[dict] = None` field to `GeminiModelConfig`.

**MODIFY `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py`:**
- In `generate()` around line 328, propagate `response_schema` to `gen_config.response_schema` when set.

**MODIFY `pipelines/ModelEngineering/batch_evaluator.py`:**
- Define `CANONICAL_SOLUTION_SCHEMA` (dict matching {steps[step_number, step_type, nudge_hint, explanation, latex_formula], final_answer} with all string fields `minLength: 1`).
- Set `tuned_model_config.response_schema = CANONICAL_SOLUTION_SCHEMA`.
- Add `_select_mode_for_record()` router (originally Phase 6 — JEE+has_figure → pro-assembly, else → requested mode).
- Add `--no-router` CLI flag for ablation.
- Add "Routing summary" section to markdown report.

**Re-run v1 eval with the enhancements:**
```powershell
Start-Job -Name FlashTuneEvalv1Schema -ScriptBlock {
    cd 'C:\Bala\Coding\AryaBhatta\pipelines\ModelEngineering'
    python batch_evaluator.py --model flash-tuned --tuned-endpoint "projects/556442477537/locations/us-central1/endpoints/8436131057215995904" --holdout-file holdout_eval_set.json --label "M3.2 Candidate Flash-Tuned v1 schema+router" *>&1 | Tee-Object -FilePath 'runs/_eval_v1_schema.log'
}
```

Also run ablations to attribute the win:
```powershell
# Schema only (no router) — measures pure schema impact
python batch_evaluator.py --model flash-tuned --tuned-endpoint <...> --holdout-file holdout_eval_set.json --no-router --label "M3.2 Candidate Flash-Tuned v1 schema only"
```

**Decision:**
- If routed Acc-routable ≥85% AND no subject <50%: ship v1+schema+router as M3 outcome, mark Phases 1-5 deferred.
- If still <85% but materially better than v1's 78.8%: proceed with scoped v2 (Phases 1-5) targeting residual issues.
- If no improvement: pause, investigate schema-enforcement is being honored (look at raw outputs).

### Phase 6 — Add figure-aware router to batch_evaluator (~30 min code)

**NOTE:** This phase is **merged into Phase 6.5** above. The router (`_select_mode_for_record`) ships together with schema enforcement.

**MODIFY `pipelines/ModelEngineering/batch_evaluator.py`:**

Add new function:
```python
def _select_mode_for_record(record: dict, default_mode: str) -> str:
    """Per-record model dispatcher. JEE figure-bearing rows route to Pro Assembly
    (KI-3 means we have no image data to feed Tuned Flash); everything else
    uses the requested mode (typically flash-tuned for v2 evaluation)."""
    if default_mode == "flash-tuned" and record["source"] == "jee" and record.get("has_figure"):
        return "pro-assembly"
    return default_mode
```

In the row loop (around line 543), replace the hardcoded `mode` with:
```python
row_mode = _select_mode_for_record(rec, mode)
LOGGER.info(f"[{idx}/{len(records)}] mode={row_mode} ({source}/{q_id}, fig={rec.get('has_figure')})")
response = generate_solution(mode=row_mode, ...)
```

Add `--no-router` CLI flag for ablation runs (so we can also measure pure Tuned v2 without routing for comparison).

Report tweak: add a "Routing summary" section to the markdown report — N routed to Pro vs N to Tuned, and per-source/per-figure routing decision counts.

**Verify:**
- Dry-eval on 10 rows shows JEE+figure routed to pro-assembly, others to flash-tuned.
- Report markdown includes routing summary section.

### Phase 7 — Re-eval v2 against same holdout (~40 min wall, ~$15)

```powershell
Start-Job -Name FlashTuneEvalv2 -ScriptBlock {
    cd 'C:\Bala\Coding\AryaBhatta\pipelines\ModelEngineering'
    python batch_evaluator.py --model flash-tuned --tuned-endpoint <v2-endpoint-from-tuning_jobs.json> --holdout-file holdout_eval_set.json --label "M3.2 Candidate Flash-Tuned v2 routed" *>&1 | Tee-Object -FilePath 'runs/_eval_v2.log'
}
```

Also run an ablation (no router) for clean Tuned v2 measurement:
```powershell
python batch_evaluator.py --model flash-tuned --tuned-endpoint <v2-endpoint> --holdout-file holdout_eval_set.json --no-router --label "M3.2 Candidate Flash-Tuned v2 noroute"
```

### Phase 8 — Apply decision matrix

Compare v2 routed vs Pro Target. Per M3 plan ship criteria:

| Outcome | Trigger | Action |
|---|---|---|
| (a) Ship single-call | Tuned v2 noroute Full-pass within 2pp of Pro AND ≥85% | Most ambitious — single Tuned Flash call replaces all |
| **(b) Ship hybrid (likely target)** | Routed Acc-routable ≥85% (no subject <50% Acc-routable) | Ship the router; production = JEE-fig→Pro + rest→Tuned v2 |
| (c) Iterate | Acc-routable still <85% | Phase 0 diagnosis informs next dataset additions |
| (c′) Drawing board | Same/worse than v1 | Surface to user; revisit base-model choice |

Expected outcome: hybrid ship (b). Non-figure v1 was 84.4%; with +images on NCERT and +100 targeted, plus the JEE-figure rows offloaded to Pro, the routed Acc-routable should clear 85%.

## Files Summary

**CREATE:**
- `pipelines/ModelEngineering/inspect_pedagogy_failures.py` (Phase 0.1)
- `pipelines/ModelEngineering/diff_tuned_vs_pro.py` (Phase 0.2)
- `pipelines/ModelEngineering/probe_tuned_on_gold.py` (Phase 0.3)
- `pipelines/ModelEngineering/collect_distillation_examples.py` (Phase 3)
- `pipelines/ModelEngineering/runs/_PED_REGRESSION_ANALYSIS_v1.md` (Phase 0 deliverable)

**MODIFY:**
- `pipelines/ModelEngineering/jsonl_exporter.py` — add `--multimodal` flag + optional image-URL part emission
- `pipelines/ModelEngineering/convert_to_vertex_jsonl.py` — add `--multimodal` flag + image-bytes inlining
- `pipelines/ModelEngineering/batch_evaluator.py` — add `_select_mode_for_record()` + `--no-router` flag + routing summary in report

**REUSE unchanged:**
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py` (`_fetch_image_bytes` helper at lines 226-250)
- `pipelines/ModelEngineering/launch_tuning_job.py` (no changes — `--dataset` + `--display-name` flags already exist)
- `pipelines/ModelEngineering/evaluator_engine.py` (GOLD gate, judge)
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/solver_engine.py` (`GoldenGenerator.generate_assembly_line` for Phase 3)
- `pipelines/JEEAscentPipeline/jee_solution_pipeline.py` + `pipelines/ModelEngineering/ncert_pipeline_orchestrator.py` (Phase 2 — already support targeting flags)

## Verification (end-to-end)

1. **Phase 0:** `_PED_REGRESSION_ANALYSIS_v1.md` exists with a one-line diagnosis + plan adjustment. Three inspection scripts run cleanly.
2. **Phase 1:** `gold_sft_vertex_v2_imgaug.jsonl` produced; ~50 lines contain `inlineData` parts; strict canonical system prompt assertion passes.
3. **Phase 2:** APPROVED_GOLD count in DB increased by ~70 with allocation matching weak buckets; zero overlap with holdout IDs.
4. **Phase 3:** `gold_sft_dataset_distillation_v1.jsonl` exists with ~15-25 lines, all valid ChatML.
5. **Phase 4:** `gold_sft_vertex_v2.jsonl` exists with ~340 lines, image parts present, sys-prompt byte-equal.
6. **Phase 5:** `runs/tuning_jobs.json[1]` shows `state=JOB_STATE_SUCCEEDED`, `display_name=aryabhata-flash-sft-v2`, non-empty endpoint.
7. **Phase 6:** Routing summary appears in v2 report markdown; ablation `--no-router` run also exists.
8. **Phase 7:** Two reports exist: `*M3.2_Candidate_Flash-Tuned_v2_routed*.md` AND `*v2_noroute*.md`. Final scored row count = 100/100 (with v1's retry logic + the figure-aware router, no row should fail).
9. **Phase 8:** Decision matrix applied + written into `pipelines/ModelEngineering/runs/M3.2_Decision_Outcome.md` with one of {a, b, c, c′}.

## Cost Estimate

| Phase | Cost |
|---|---|
| 0 (diagnostic) | ~$0.50 (5 Pro judge calls + 5 Tuned generations on Gold rows) |
| 1 (image augmentation) | $0 (image fetch + base64; no API calls) |
| 2 (fresh harvest) | ~$20 (Pro 3-pass × ~120 candidates + 5/5/5 gate on ~120) |
| 3 (distillation) | ~$10 (Pro 3-pass × ~33 + gate × ~33) |
| 4 (build v2 dataset) | $0 |
| 5 (v2 tuning) | ~$8 (~340 rows × ~3 epochs at $8/M training tokens) |
| 6 (router code) | $0 |
| 7 (re-eval) | ~$15 (100 Pro judge calls + 100 Tuned generations) |
| **Total** | **~$55** (~₹4,500) |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Phase 0 reveals SFT didn't take → "more data" is wrong lever | Medium | Branch in plan; don't blindly proceed |
| Multimodal Vertex tuning silently rejects image parts | Low | Sanity-run on tiny subset first; check job logs for warnings |
| Vertex bucket / region issue (mirrored from v1 regional-host bug) | Low | `launch_tuning_job.py --dry-run` first |
| Phase 2 5/5/5 gating yields fewer than projected | Medium | Over-generate (Phase 2 targets ~120 candidates for ~70 survivors); plan tolerates 50-90 net |
| v2 doesn't move the needle | Medium-Low | Triggers (c′) drawing-board — surface to user, don't auto-retry |
| Router has unintended interaction with judge | Very Low | `--no-router` ablation run isolates the effect |

## Explicitly Deferred

- **KI-3 fix (JEE figure_url backfill)** — out of M3 scope; the router sidesteps it for production purposes. Post-MVP.
- **Phase-2 multi-model architecture** (Flash-Lite per-stage) — gated on 1000+ examples; we'll have ~340 after v2.
- **Output-image generation** — parked per E2E plan.
- **`tuned_solver_model` integration into production pipelines** — happens only if (b) ships; happens in a follow-up M3 sub-task, not in this plan.

## Recovery / Resume Notes

If execution is interrupted (machine restart, terminal disconnect, etc.):
- **Phase 0:** Re-run any of the three scripts; they're read-only on prior data.
- **Phase 1:** Re-run the exporter + converter; outputs are deterministic, safe to overwrite.
- **Phase 2:** Existing pipelines are resumable via DB state (rows in MATH_PASSED / PEDAGOGY_ADDED / APPROVED queue). Rerun with the same flags.
- **Phase 3:** `collect_distillation_examples.py` writes a per-row checkpoint at `runs/_distill_ckpt_*.jsonl`; rerun the same command resumes.
- **Phase 5:** If the tuning job is launched but the script dies, the job_name is in `runs/tuning_jobs.json`; resume via `python launch_tuning_job.py --check <job_name>`.
- **Phase 7:** Same per-row checkpoint pattern as v1 (`runs/_checkpoint_M3.2_Candidate_Flash-Tuned_v2_*.jsonl`); rerun the same command auto-skips completed rows.

## Cross-references

- Memory: `project_m3_tuning_plan_approved_2026_05_23.md`, `project_pro_baseline_socratic_regression_2026_05_25.md`, `project_jee_figure_url_gap_2026_05_23.md`, `project_vertex_tuned_endpoint_regional_host_2026_05_26.md`
- QA tracker: `pipelines/JEEAscentPipeline/QA_Tracker.md` — KI-3 (JEE figure_url NULL), KI-4 (Tutor Socratic regression), KI-5 (Formatter LaTeX `\f`/`\t` bug)
- v1 artifacts: `pipelines/ModelEngineering/runs/Experiment_Run_20260523_231104.md` (Pro Target), `Experiment_Run_20260525_090049.md` (Floor Untuned), `Experiment_Run_20260526_105654.md` (Tuned v1 Candidate)
