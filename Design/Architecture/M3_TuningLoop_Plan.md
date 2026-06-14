# M3 — The Tuning Loop: Implementation Plan

> **Status (2026-05-23):** Approved. Ready for execution.
> **Companion docs:** `E2E_SolutionModel_Implementation_Plan.md` (master tracker, M3 section), `GoldSet_Execution_Tracker.md` (M2 close-out), `pipelines/ModelEngineering/CLAUDE.md` (folder guide).

## Context

Aryabhata's Gold Set is complete: 255 strict-5/5/5 SFT examples (153 NCERT + 102 JEE) exported to `pipelines/ModelEngineering/gold_sft_dataset.jsonl` in OpenAI ChatML format. The next milestone is **M3** — fine-tune a cheap Flash-class model so a single call can replace the current 3-pass Gemini 3.1 Pro Assembly Line (Solver → Tutor → Formatter) for routine NCERT/JEE solution generation.

**Why now:** The Pro assembly line is the cost driver. At today's pricing, a tuned 2.5 Flash endpoint runs at roughly 5% of Pro's per-token cost. Even a hybrid deployment (tuned Flash for the easy 80%, Pro fallback for the hard 20%) yields a 3–5× cost reduction, which (a) unlocks running the pipeline over the rest of the NCERT/JEE corpus, (b) gives us a continuous data flywheel for the next tuning iteration, and (c) is the prerequisite for any future open-weight S-DAG move.

**Strategic decisions locked (vs the Gemini Deep Research "open-weight S-DAG on Azure Foundry" alternative — see `Architectural Optimization for STEM Solution Pipelines_*.docx`):**
- Base model = **`gemini-2.5-flash`** on Vertex AI. Gemini 3 Flash is not tunable yet (the only tunable Gemini family right now is 2.5). 2.5 deprecation risk is real but mitigated: the durable assets are the Gold dataset and the eval harness (both provider-agnostic); retuning onto a future model takes days, not months; fall-back to Pro is always intact.
- **NOT** S-DAG / MergeKit / open-weight specialists. The Aryabhata 1.0 recipe (PhysicsWallah's published JEE Math model) needs ~130k examples per specialist; we have 255 total. Open-weight is the year-2 destination, gated on volume + ROI signal, not the M3 starting point.
- **NOT** OpenAI fine-tuning (penalized inference at $15/M output, worse than base Pro) or Claude (Bedrock-locked).
- **Keep** the existing Smart Context / pgvector / eval harness — they survive any model swap.
- **Defer** Chemistry-RAG verbalization upgrade to M4 (after tuned Flash ships and starts generating bulk solutions).
- **Out of M3 scope:** Student Feedback Pipeline (M4 — different model `gemini-3-pro-image-preview`, different input, different output schema), output-image generation (parked — "live to die another day"), S-DAG per-subject open-weight specialists (next phase).

## Ship criteria (decision matrix)

Run tuned-Flash on the frozen holdout set, score with `UniversalEvaluator`, compute:
- **Full-pass %** = records where Accuracy=5 AND Pedagogy≥4 AND Format≥4
- **Accuracy-routable %** = records where Accuracy=5 (regardless of Ped/Fmt)
- **Per-(source × subject × figure-bearing) breakdowns** for all of the above

| Outcome | Trigger | Action |
|---|---|---|
| **(a) Ship single-call** | Tuned Full-pass % within **2pp** of Pro Full-pass % **AND** ≥ **85%** absolute | Tuned Flash handles everything in one call. Biggest cost win. |
| **(b) Ship hybrid** | (a) fails BUT Accuracy-routable % ≥ **85%** | Per-record routing: tuned-Flash for Accuracy=5 records (post-format pass via Flash if Fmt<4; Pro pedagogy injection if Ped<4); Accuracy<5 records → full Pro fallback. Still ~3–5× cost reduction. |
| **(c) Iterate** | Accuracy-routable % < 85% | Distillation loop: collect Accuracy<5 failures, regenerate via Pro assembly line, gate to strict 5/5/5, append to training set, retune. |
| **(c′) Drawing board** | After 2–3 retunes, Accuracy-routable still flat below **70%** OR harvest pool exhausted | Revisit: base-model choice (2.5 Pro instead of Flash?), training-data quality, multimodal gap (trigger Path B if not yet), or park M3 until Gemini 3 tuning ships / volume grows. |

**Per-subject veto:** even if overall ship criterion passes, no subject (Math/Physics/Chemistry) may collapse below 50% Accuracy-routable. A collapse triggers (c) restricted to that subject's failure set.

## Held-out evaluation set

**Composition (100 records total):**
- 50 JEE + 50 NCERT (parity by source)
- Within each source: ~17 Math / ~17 Physics / ~16 Chemistry (so each subject has ~33 records pooled across sources — large enough for per-subject metrics)
- Deliberately sample so ~30–40 records contain figures (`figure_url` for JEE; `figure_info` for NCERT). Physics will dominate naturally; ensure JEE option-figure problems are represented.
- **Excludes** all `APPROVED_GOLD` ids in both tables
- Prefer NCERT `MATH_PASSED` rows (accuracy already vetted); back-fill from `LEGACY` if short
- All JEE rows must have `answer_key IS NOT NULL` (PENDING pool — 2480 rows available, disjoint from the 102 gold)
- Reserve a **~20-record never-distilled "final exam" slice** with `never_distill: true` flag (the loop-correctness slice — see Phase D)
- **Frozen once**, never regenerated. Fixed random seed + SQL `SETSEED` for reproducible rebuilds. `--force` required to overwrite.

**Output:** `pipelines/ModelEngineering/holdout_eval_set.json` — list of records `{source, id, subject, problem_payload:{problem_text, options}, answer_key, image_urls:[], has_figure: bool, never_distill: bool}`.

## Multimodal handling

**Investigation finding (2026-05-23):** NCERT solver and JEE solver both pass image blobs (`context_image_urls`, `figure_url`, `option_figure_urls`) inlined as `parts` to Gemini today via `gemini_client.generate(image_urls=...)`. Pedagogy + Format steps are text-only. The current Gold Set training JSONL strips images (see comment in `jsonl_exporter.build_user_payload`). Pipeline 3 (Student Feedback) uses a different model (`gemini-3-pro-image-preview`) with mandatory image inputs — **not in M3 scope**.

**Holdout-construction finding (2026-05-23):** While building the M3 holdout, surveying `jee_question_bank` revealed that **`figure_url` is NULL on 100% of rows** (1,491 surveyed) even though `has_figure=true` is set on ~170 figure-dependent rows. Today's Pro pipeline operates handicapped on those — text references the figure but no image is passed. Logged as **KI-3** in `pipelines/JEEAscentPipeline/QA_Tracker.md` and as a Known Gap under M2.1 in `E2E_SolutionModel_Implementation_Plan.md`. Fix is upstream (JEE extraction pipelines) and out of M3 scope. The holdout now detects figure-dependence via `has_figure` (broad) and separately records `image_urls_present` (strict), so the figure-dependent-but-image-less subset is measurable.

**Path A — Text-only v1 (default):** tune on the current text-only 255 examples. Vertex AI tuning uses LoRA adapters; the base Gemini 2.5 Flash vision encoder is not modified, so multimodal capability survives at inference. Pass `image_urls` through to the tuned model just like Pro. Measure figure-bearing holdout subset SEPARATELY.

**Path B — Multimodal v2 (trigger if Path A figure-bearing scores collapse >15pp vs non-figure):**
1. Modify `jsonl_exporter.build_user_payload()` to carry figure blobs into the JSONL (as `inlineData` base64 parts in Vertex format).
2. Re-export, re-tune as v2.
3. Re-measure on same figure-bearing subset.

Path B is reactive — only triggered by Path A measurement, not preemptive work.

## Implementation phases

### Phase A — Held-out set + baselines (M3.1)

**CREATE `pipelines/ModelEngineering/build_holdout_set.py`**
- Fetches 50 JEE from `jee_question_bank WHERE review_status='PENDING' AND answer_key IS NOT NULL AND question_content IS NOT NULL`, balanced by subject (~17/17/16), with deliberate figure-bearing sampling.
- Fetches 50 NCERT from `questiondata WHERE review_status<>'APPROVED_GOLD'`, prefer `MATH_PASSED`, balanced by subject.
- Normalizes each row via `build_user_payload()` from `jsonl_exporter.py` (same normalizer used for the gold set — payload shape parity with training).
- Tags `has_figure` per record (true if `figure_url` / `option_figure_urls` / `figure_info` present).
- Marks ~20 records `never_distill: true` (the final-exam slice).
- Writes `holdout_eval_set.json`. Refuses to overwrite without `--force`. Asserts zero id overlap with `APPROVED_GOLD`.
- CLI: `python build_holdout_set.py --jee 50 --ncert 50 [--force]`
- **Verify:** 100 records, NCERT/JEE balanced, 3 subjects represented, ~30–40 figure-bearing, ~20 never-distill, zero gold overlap.

**MODIFY `pipelines/ModelEngineering/batch_evaluator.py`**
- Add `--model {pro-assembly|flash-untuned|flash-tuned}` selector (deprecate `--use-assembly` alias).
  - `pro-assembly` → existing `generator.generate_assembly_line(...)` path.
  - `flash-untuned` → single `client.generate()` with `GeminiModelConfig(model_id="gemini-3-flash-preview")`.
  - `flash-tuned` → single `client.generate()` with `model_id` from `--tuned-endpoint` arg or `TUNED_FLASH_ENDPOINT` env.
- Add `--holdout-file` (default `holdout_eval_set.json`) — reads frozen records instead of `fetch_test_batch()` random sampling. Keep `fetch_test_batch()` as fallback for ad-hoc runs.
- Replace JEE-only `qc.get('raw_text')` access with the already-normalized `problem_payload` from holdout records (supports mixed NCERT+JEE). Pass `image_urls` from the record.
- `flash-untuned` / `flash-tuned` use the **canonical frozen system instruction** (see Phase B); `pro-assembly` keeps loading the existing `--prompt` file.
- Report header records: model used, holdout-file path, tuned-endpoint id.
- Add per-(source × subject × `has_figure`) breakdown tables to the markdown report.
- CLI examples:
  - `python batch_evaluator.py --model pro-assembly --holdout-file holdout_eval_set.json --label "M3.1 Target Pro-Assembly"`
  - `python batch_evaluator.py --model flash-untuned --holdout-file holdout_eval_set.json --label "M3.1 Floor Flash-Untuned"`
- **Verify:** two `runs/Experiment_Run_*.md` reports over the same 100 ids; record Target and Floor Full-pass / Accuracy-routable % in `Model_Engineering_History.md`.

**Phase A exit:** frozen `holdout_eval_set.json`, two baseline reports, Pro-Target and Untuned-Flash-Floor numbers logged.

### Phase A baseline findings (post-run analysis, 2026-05-25)

Pro-Assembly baseline (`Experiment_Run_20260523_231104.md`, N=100) returned:
- **Full-pass %: 85.0%** (just meeting the ≥85% sanity gate)
- **Accuracy-routable %: 98.0%** (solver is solid across the board)
- **Avg Acc / Ped / Fmt: 4.96 / 4.63 / 4.87** — Pedagogy is the weak dimension

**Pedagogy drag is NOT figure-availability** (corrects prior framing in the "Multimodal handling" section above). Cross-tab:

| Bucket | N | AvgPed | Ped<4 |
|---|---|---|---|
| NCERT figure-bearing (image inlined ✓) | 10 | **4.00** | 4/10 |
| JEE figure-bearing (image NULL — KI-3) | 13 | 4.38 | 3/13 |
| NCERT non-figure | 40 | 4.80 | 1/40 |
| JEE non-figure | 37 | 4.70 | 4/37 |

NCERT figure-bearing (with image) scored WORSE on Pedagogy than JEE figure-bearing (without image). Disproves the figure-handicap hypothesis as the dominant driver of the Pedagogy drag.

**Real root cause = Tutor Socratic regression** (`QA_Tracker.md` KI-4). 11/14 Ped<5 failures cite the same verbatim judge complaint: *"nudge_hint fields are direct statements / instructions, not Socratic guiding questions."* Same "Pedagogical Leakage" failure mode as Phase 1 Variants A/B/C; the Assembly Line was supposed to fix it but only N=10/25 validation runs (Variants E/F) missed the regression that N=100 surfaces on harder rows.

**Secondary bug = Formatter LaTeX JSON-escape** (`QA_Tracker.md` KI-5). 2/100 rows had `\frac` / `\text` collide with JSON escapes `\f` / `\t` and break rendering.

**Implications for Phase C/D ship decision:**

| Aspect | Implication |
|---|---|
| **R2 risk profile improves on Pedagogy.** Original concern: "Tuned Flash will be *worse* than Pro" — distillation can't out-quality the teacher. | The Gold Set was filtered to strict 5/5/5, so Pro's Tutor regression NEVER landed in `APPROVED_GOLD`. Tuned Flash trains only on the disciplined examples — possibly out-performing the *average* Pro Tutor on Pedagogy. Accuracy remains the open dimension. |
| **R4 (Pedagogy fails while accuracy passes) mitigation strengthens.** | Single-call ship path (a) — Tuned Flash only — sidesteps the Pro Tutor regression entirely. Hybrid path (b) inherits it via the Pro post-stages. |
| **Hybrid-ship path (b) carries inherited bug risk.** | Any Pro pedagogy or post-format step in production output leaks KI-4 / KI-5 into Tuned Flash rows. **KI-4 and KI-5 MUST be fixed before any hybrid ship.** |
| **Single-call ship path (a) is bug-free w.r.t. KI-4 / KI-5.** | Tuned Flash produces full payload in one call; no Pro stages remain in production. KI-4 / KI-5 remain bugs only in the legacy Pro pipeline used for non-Tuned-Flash bulk runs (operational concern, not production-output concern). |
| **KI-3 (JEE figure_url NULL) is real but secondary.** | Still worth fixing during 2023 re-extraction, but not the cause of Pro's 85% bar. |

### Floor baseline findings (post-run analysis, 2026-05-25)

Untuned Flash baseline (`Experiment_Run_20260525_090049.md`, N=100) returned:
- **Full-pass: 0.0%** (0/100) — schema-violating, expected
- **Acc-routable: 95.0%** (95/100) — Flash CAN solve at near-Pro capability
- **Avg Acc / Ped / Fmt: 4.89 / 1.06 / 1.53**

Read this correctly: the 0% Full-pass is NOT a Flash capability failure — it's a **schema/format gap**. Untuned Flash given a single prompt writes a plain prose solution; it has no notion of our canonical `{steps[], final_answer}` envelope with per-step `step_type` / `nudge_hint` / `latex_formula` / mhchem rules. The judge correctly scores schema-violating output at 1–2 on Ped/Fmt even when the math is right.

**The signal that matters: Acc 4.89, Acc-routable 95% — only 3pp behind Pro's 98% on raw solving capability.**

**What this means for tuning ROI:**
- The entire gap Tuned Flash needs to close is the **schema/style layer** — exactly what 255 ChatML examples of strict 5/5/5 SFT are designed to teach.
- Raw solving is already at 95% Acc-routable at the Floor. SFT teaches *format*, not *capability*. The ceiling for Tuned Flash on the M3 ship bar (Acc-routable ≥85% for hybrid path) is **above the bar before tuning has even happened.**
- Per-subject veto sanity: closest-to-veto subject in Floor is NCERT Chemistry figure-bearing at 75% Acc-routable (N=4, noisy). All subjects well clear of the 50% veto line. No structural blocker for Phase B.

**Phase A is officially closed.** Target 85/98, Floor 0/95, capability confirmed, baseline files frozen.

## Architecture: single-call tuning (decision rationale)

Open question that comes up every time: *"Why tune one model to do all 3 stages, instead of 3 specialized tuned models — or using Flash-Lite for the cheaper stages?"*

**First, a reframing:** today's Pro Assembly Line is ONE model (Gemini 3.1 Pro) called 3 times with different system prompts. It's not 3 different models. The real choice is:

- **(i) Single-call tuned Flash** — one call: `problem → canonical JSON` (this plan).
- **(ii) Multi-call** — 3 separately tuned models (or 3 fine-tuned heads), each specialized to a stage, called sequentially. Optionally mix in cheaper models (Flash-Lite) for easier stages.

### Why this plan picks (i)

1. **We only have end-to-end training data.** `gold_sft_dataset.jsonl` is 255 rows of `{user: problem, model: final canonical JSON}`. Intermediate Solver-only and Tutor-only outputs were never captured — `jsonl_exporter.py` exports only the final approved JSON. To train 3 specialists we'd need 255+ examples of *each* stage's output, gated to high quality. We don't have that data and harvesting it means fresh Pro runs with stage-level logging — significant pipeline work.

2. **Per-stage grading is much harder than end-to-end.** `UniversalEvaluator` grades on the final canonical JSON (Acc/Ped/Fmt). There's no equivalent rubric for intermediate stages — distillation supervision per stage is weak. End-to-end we have a clean 5/5/5 gate; per-stage we'd be guessing.

3. **Cost math favors single-call.** Tuned Flash ≈ 5% of Pro per token. Each call has overhead. 3 calls ≈ 15% of Pro instead of ~5% — still a win, but a 3× worse win than single-call. Latency triples too.

4. **Information flow is naturally fine after tuning.** With one prompt, the model produces hint + reasoning + formatting in lockstep. Splitting forces information through a text-string bottleneck between stages — which is *why* the Pro Assembly Line works (it deliberately limits each stage's context to prevent dilution). A tuned single-call model doesn't suffer that dilution because the entire input→output mapping is what we trained on.

### Where Flash-Lite COULD fit (Phase 2, not now)

If we ever go multi-model in a future phase, viability per stage:

| Stage | Flash-Lite viable? | Reason |
|---|---|---|
| Solver | **Probably NO** | Hardest reasoning step. Untuned Flash already trails Pro by 3pp on Acc-routable (95% vs 98%); Flash-Lite is measurably weaker. Risk of tanking Accuracy below the 85% bar. |
| Tutor | Probably yes | Style transfer (solver-text → Socratic hint) is well within Flash-Lite's capacity given enough examples. |
| Formatter | Almost certainly yes | Mechanical schema enforcement is the easiest possible task; even smaller models nail it with good few-shot. |

Plausible Phase-2 architecture: **Tuned Flash (Solver) → Flash-Lite (Tutor) → Flash-Lite (Formatter)**. Gating conditions for that pivot:
- 1000+ examples per stage (we have 255 total today)
- Volume justifying per-stage data harvesting work
- Proven need — latency/cost STILL too high after single-call Tuned Flash ships

**Decision: ship single-call (Phase A→D as planned). Revisit multi-model + Flash-Lite per-stage only after Tuned Flash is in prod and bulk-generation has produced a data flywheel.** Capture this rationale in `pipelines/ModelEngineering/CLAUDE.md` Phase-2 notes once Tuned Flash ships.

### Phase B — JSONL conversion + GCS upload + Vertex tuning job (M3.2 part 1)

**VERIFY `pipelines/ModelEngineering/canonical_system_instruction.txt`** *(file already exists — Phase A scaffolding)*
- Must be byte-identical to `jsonl_exporter.format_system_prompt()` output. `convert_to_vertex_jsonl.py` asserts this; fails loudly on drift.
- Loaded by `batch_evaluator.py` for `flash-tuned` / `flash-untuned` modes so training and inference use byte-identical system instructions (Vertex SFT requirement). This is R8 — the single source of truth.

**CREATE `pipelines/ModelEngineering/convert_to_vertex_jsonl.py`**

Input shape (current `gold_sft_dataset.jsonl`, OpenAI ChatML):
```json
{"messages":[
  {"role":"system","content":"<canonical system prompt>"},
  {"role":"user","content":"<problem payload JSON string>"},
  {"role":"assistant","content":"<canonical solution JSON string>"}
]}
```

Output shape (Vertex Gemini-native):
```json
{
  "systemInstruction":{"role":"system","parts":[{"text":"<canonical system prompt>"}]},
  "contents":[
    {"role":"user","parts":[{"text":"<problem payload JSON string>"}]},
    {"role":"model","parts":[{"text":"<canonical solution JSON string>"}]}
  ]
}
```

Per-line validation (fail loud, don't skip):
1. JSON parses cleanly
2. `systemInstruction.parts[0].text` byte-equals `canonical_system_instruction.txt`
3. `contents` length is even, alternates user → model, ends on `model`
4. Every `parts[].text` is non-empty (whitespace-only counts as empty)
5. Model `parts[0].text` itself parses to `{steps: [...], final_answer: ...}` — sanity-check the training target is a well-formed canonical solution
6. Rough token estimate (chars / 4) < 131,072 (Gemini 2.5 Flash context cap)
7. Aggregate: output line count == input line count == 255

CLI: `python convert_to_vertex_jsonl.py --in gold_sft_dataset.jsonl --out gold_sft_vertex_v1.jsonl [--strict]`
- `--strict` (default ON) enables system-prompt byte-equality assertion.

**Verify:** line count out == 255; `head -1 gold_sft_vertex_v1.jsonl | python -m json.tool` shows the Vertex schema correctly.

**CREATE `pipelines/ModelEngineering/launch_tuning_job.py`**

Imports (the SDK is `google-genai`, NOT `vertexai.generative_models` — confusion-prone):
```python
from google import genai
from google.genai.types import HttpOptions, CreateTuningJobConfig, TuningDataset
from google.cloud import storage  # for GCS upload
```

Install (only if missing): `pip install google-genai google-cloud-storage`

Client construction (REGIONAL endpoint — not `global` like generation):
```python
client = genai.Client(
    vertexai=True,
    project="animated-rope-453904-j7",
    location="us-central1",
    http_options=HttpOptions(api_version="v1beta1"),  # tuning is v1beta1
)
```

GCS upload (idempotent — skip if blob already present + same SHA):
```python
gcs = storage.Client(project="animated-rope-453904-j7")
bucket_name = "aryabhata-tuning"
try:
    bucket = gcs.get_bucket(bucket_name)
except NotFound:
    bucket = gcs.create_bucket(bucket_name, location="us-central1")
blob = bucket.blob("m3/gold_sft_vertex_v1.jsonl")
if not blob.exists() or blob.crc32c != local_crc32c(jsonl_path):
    blob.upload_from_filename(jsonl_path)
gcs_uri = f"gs://{bucket_name}/m3/gold_sft_vertex_v1.jsonl"
```

If `google-cloud-storage` isn't installed, print the manual fallback and exit:
```bash
gcloud storage cp gold_sft_vertex_v1.jsonl gs://aryabhata-tuning/m3/
```

Launch tuning:
```python
job = client.tunings.tune(
    base_model="gemini-2.5-flash",
    training_dataset=TuningDataset(gcs_uri=gcs_uri),
    config=CreateTuningJobConfig(
        tuned_model_display_name="aryabhata-flash-sft-v1",
        # No epoch_count override — Vertex auto-picks. v1 trains on all 255, no Vertex validation split.
        # The UniversalEvaluator holdout is the real signal.
    ),
)
print(f"Launched: {job.name}  state={job.state}")
```

Poll (every 60s, log state transitions):
```python
TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}
while job.state not in TERMINAL:
    time.sleep(60)
    job = client.tunings.get(name=job.name)
    log(f"state={job.state} elapsed={...}")
if job.state != "JOB_STATE_SUCCEEDED":
    raise RuntimeError(f"Tuning failed: state={job.state} error={job.error}")
```

On success, append to `runs/tuning_jobs.json` (list-of-dicts, atomic write — load, append, rewrite to tmp, rename):
```json
{
  "job_name": "projects/.../locations/us-central1/tuningJobs/123",
  "tuned_endpoint": "projects/.../locations/us-central1/endpoints/456",
  "base_model": "gemini-2.5-flash",
  "dataset_uri": "gs://aryabhata-tuning/m3/gold_sft_vertex_v1.jsonl",
  "display_name": "aryabhata-flash-sft-v1",
  "timestamp": "2026-05-25T...",
  "state": "JOB_STATE_SUCCEEDED"
}
```

Modes:
- `--dry-run` — auth check + dataset validation + GCS reachability check + bucket-existence check. NO billable submit. Print what *would* be launched and exit 0.
- *(no flag)* — full launch + poll until terminal + log endpoint.
- `--no-wait` — launch + write `runs/tuning_jobs.json` with `state=JOB_STATE_RUNNING` + exit. Useful if you want to log off while it runs.
- `--check <job.name>` — re-attach to an existing job. Polls until terminal, updates `runs/tuning_jobs.json`. Essential for crash recovery: tuning runs ~1–3 hours, terminal disconnects shouldn't lose the job.

CLI examples:
- `python launch_tuning_job.py --dry-run`
- `python launch_tuning_job.py --display-name aryabhata-flash-sft-v1`
- `python launch_tuning_job.py --check projects/animated-rope-453904-j7/locations/us-central1/tuningJobs/<id>`

**Verify:**
- `--dry-run` exits 0, prints auth identity + GCS bucket status + dataset line count.
- Real run ends `JOB_STATE_SUCCEEDED` with a non-empty `tuned_endpoint` written to `runs/tuning_jobs.json`.

**Phase B prerequisites/risks:**
- `gcloud auth application-default login` valid for project `animated-rope-453904-j7`.
- ADC principal has roles: **Vertex AI User** (`roles/aiplatform.user`) + **Storage Object Admin** (`roles/storage.objectAdmin`). Verify before `--dry-run` to avoid mid-run permission errors:
  ```bash
  gcloud projects get-iam-policy animated-rope-453904-j7 \
    --flatten="bindings[].members" \
    --filter="bindings.members:<your-email>" \
    --format="value(bindings.role)"
  ```
- GCS bucket `aryabhata-tuning` in `us-central1` (script creates if missing — needs Storage Admin role; if perms only allow Object Admin, pre-create the bucket manually via `gcloud storage buckets create`).
- Cost: single-digit USD for 255 short examples × ~3 epochs at $8/M training tokens. `--dry-run` first.
- **Region constraint:** `gemini-2.5-flash` tuning may not be available in every region. If `us-central1` fails with a model-availability error, fall back to `us-east5` or try `gemini-2.5-flash-lite` per R6.
- **API surface stability:** `google-genai` SDK is on `v1beta1` for tunings as of 2026-05. Pin a known-good version in any `requirements.txt`; surface drift is the most likely "ran fine yesterday, fails today" cause.

### Phase C — Tuned-model evaluation + decision (M3.2 part 2)

**Run Candidate evaluation** — reuse Phase A tooling:
- `python batch_evaluator.py --model flash-tuned --tuned-endpoint "<endpoint from runs/tuning_jobs.json>" --holdout-file holdout_eval_set.json --label "M3.2 Candidate Flash-Tuned v1"`
- Produces a third report on the same questions: Target (Pro) vs Floor (Untuned Flash) vs Candidate (Tuned Flash), all scored by the same evaluator.

**Apply the decision matrix** (from "Ship criteria" section above):
- Compute Full-pass %, Accuracy-routable %, and per-(source × subject × `has_figure`) breakdowns.
- **Critically:** compare figure-bearing-subset Candidate scores against non-figure-bearing Candidate scores. If figure-bearing collapses (>15pp gap to non-figure), trigger Path B multimodal augmentation (re-export with image blobs, retune as v2, re-measure).
- Apply per-subject veto check (no subject < 50% Accuracy-routable).
- Decision → (a) ship single-call / (b) ship hybrid / (c) iterate / (c′) drawing board.

**Optionally** add a commented `tuned_solver_model` `GeminiModelConfig` to `config.py` once an endpoint is accepted for production use.

### Phase D — Distillation loop OR ship + harvest

**If (a) or (b) — Ship:**
1. Add `tuned_solver_model` (or `tuned_full_pipeline_model`) `GeminiModelConfig` in `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/config.py` pointing at the production endpoint.
2. Integrate into `jee_solution_pipeline.py` and `ncert_pipeline_orchestrator.py`:
   - Path (a): single tuned-Flash call replaces the 3-pass assembly line for the routable share.
   - Path (b): per-record routing — Accuracy=5 records use tuned Flash output; weak Ped/Fmt get post-passes; Accuracy<5 records full Pro fallback.
3. Run the cheaper pipeline over the rest of the NCERT/JEE corpus (cost-down enables wider coverage) — this also produces the data flywheel for the next tuning iteration.
4. Update `Design/Architecture/E2E_SolutionModel_Implementation_Plan.md` (M3 → ✅) and `pipelines/ModelEngineering/CLAUDE.md`.

**If (c) — Iterate:**

**CREATE `pipelines/ModelEngineering/collect_distillation_examples.py`**
- Read the latest `flash-tuned` `_RAW.json` from `runs/`.
- Select records with `scores.is_pass == False` (or Accuracy < 5) — but **EXCLUDE any record marked `never_distill: true`** in the holdout (loop-correctness — preserves the final-exam slice).
- Regenerate each via `GoldenGenerator.generate_assembly_line()` (Pro 3-pass).
- Gate each through `UniversalEvaluator` keeping only `result.is_gold` (strict 5/5/5) — prevents model collapse from training on imperfect data.
- Append survivors in ChatML format via `format_chatml()` + `build_user_payload()` to `gold_sft_dataset_v2.jsonl` (never mutate v1 — versioned datasets keep iterations reproducible).
- **Resumable by default** (per [feedback-prefer-resumable-pipelines](../../../.claude/projects/C--Bala-Coding-AryaBhatta/memory/feedback_prefer_resumable_pipelines.md)): per-row JSONL checkpoint at `runs/_distill_ckpt_<output-basename>.jsonl`, auto-resume on rerun by skipping `(source, id)` pairs already in the checkpoint, `--restart` to force fresh, `KeyboardInterrupt` caught with rerun-instructions. Same pattern as `batch_evaluator.py:~280-320`.
- CLI: `python collect_distillation_examples.py --failures-from runs/Experiment_Run_<ts>_RAW.json --base-dataset gold_sft_dataset.jsonl --out gold_sft_dataset_v2.jsonl`

**Then loop:** `convert_to_vertex_jsonl.py` (v2) → `launch_tuning_job.py` (v2) → `batch_evaluator.py --model flash-tuned --tuned-endpoint <v2>` → re-apply decision matrix. v1/v2/v3 are directly comparable on the same frozen holdout.

## Files summary

**CREATE** (`pipelines/ModelEngineering/`):
- `build_holdout_set.py`
- `canonical_system_instruction.txt`
- `convert_to_vertex_jsonl.py`
- `launch_tuning_job.py`
- `collect_distillation_examples.py`

**MODIFY:**
- `pipelines/ModelEngineering/batch_evaluator.py` (`--model`, `--holdout-file`, `--tuned-endpoint`, mixed-source payloads, per-(source × subject × has_figure) reporting)
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/config.py` (add `tuned_solver_model` once endpoint exists)
- `pipelines/JEEAscentPipeline/jee_solution_pipeline.py` + `pipelines/ModelEngineering/ncert_pipeline_orchestrator.py` (integrate tuned model — Phase D only, only if shipping)
- `Design/Architecture/E2E_SolutionModel_Implementation_Plan.md` and `pipelines/ModelEngineering/CLAUDE.md` (status updates)

**REUSE unchanged:**
- `pipelines/ModelEngineering/evaluator_engine.py` (`UniversalEvaluator`, `get_evaluator`, `is_pass`/`is_gold`)
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/solver_engine.py` (`GoldenGenerator.generate_assembly_line`)
- `pipelines/ModelEngineering/jsonl_exporter.py` (`build_user_payload`, `format_chatml`, `format_system_prompt`)
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gemini_client.py` (`GeminiClient.generate` — model-agnostic, accepts any `model_id`)
- `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/db_client.py` (`DatabaseClient`, `execute_write`)

## Verification (end-to-end smoke test)

1. **Phase A:** `holdout_eval_set.json` exists with 100 records balanced as specified; `runs/Experiment_Run_*Pro-Assembly*.md` and `*Flash-Untuned*.md` exist; Pro Full-pass % ≥ 85% (sanity — Pro should easily clear its own bar on questions it can solve).
2. **Phase B:** `gold_sft_vertex_v1.jsonl` validates against Gemini-native schema; `launch_tuning_job.py --dry-run` exits clean; real tuning job logged in `runs/tuning_jobs.json` with `JOB_STATE_SUCCEEDED` and a non-empty `tuned_model.endpoint`.
3. **Phase C:** `runs/Experiment_Run_*Flash-Tuned*.md` exists with per-(source × subject × has_figure) breakdown; decision matrix applied and outcome recorded; figure-bearing collapse check performed.
4. **Phase D:** either (Ship) `config.py` has `tuned_solver_model` and at least one pipeline (jee/ncert) integrated end-to-end, OR (Iterate) `gold_sft_dataset_v2.jsonl` exists with ≥ 255 + new-survivor count, second tuning job logged, second Candidate evaluation reported.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1** Gemini 2.5 deprecated within 18 months | Medium | Low | Gold dataset + eval harness are durable; retune onto next-gen in days; fall back to Pro any time |
| **R2** 255 examples insufficient — accuracy collapses | Medium | Medium | Distillation loop (Phase C → C′); harvest more via existing pipelines if loop also flat |
| **R3** Figure-bearing problem quality regression on text-only training | Medium-High | Medium | Path B multimodal augmentation (re-export with image blobs, retune v2); route figure-bearing to Pro as fallback in hybrid mode |
| **R4** Pedagogy fails while accuracy passes (squishiest dim) | Medium | Low | (b) hybrid mode: tuned for solver+format, Pro pedagogy injection as second pass — still ~50% cost savings |
| **R5** Per-subject collapse (e.g. Chemistry tanks) | Medium | Medium | Per-subject veto in ship criteria; subject-specific distillation loop; Chemistry-RAG upgrade scheduled for M4 |
| **R6** Vertex tuning job fails / `gemini-2.5-flash` not tunable in `us-central1` | Low | Low | `--dry-run` first; fall back to `gemini-2.5-flash-lite` or another supported region |
| **R7** Cost overrun on tuning job | Low | Low | `--dry-run` confirms dataset size before billable submit; 255 short examples = single-digit USD |
| **R8** Training/inference system instruction drift | Low | High | `canonical_system_instruction.txt` is the single source of truth, loaded by both converter and `batch_evaluator.py` `flash-tuned` mode |
| **R9** Distillation leakage (holdout records used as training data after Phase C) | Medium | Low | Reserve `never_distill: true` slice (~20 records) in `holdout_eval_set.json` for final ship decision |

## Explicitly out of scope

- **Student Feedback Pipeline** (M4): different model `gemini-3-pro-image-preview`, fundamentally different input (handwritten student work pages + textbook references + optional PDF), different output (per-step evaluations). Separate multimodal SFT corpus required. Not addressed by M3.
- **Output-image generation** (Chemistry structures, geometry diagrams): explicitly parked in the E2E plan.
- **Chemistry-RAG `ltree` + verbalization upgrade**: deferred to M4 — better implemented after the tuned Flash exists and starts producing bulk solutions (the right moment to upgrade retrieval).
- **S-DAG / MergeKit / open-weight per-subject specialists** (Qwen-Math, DeepSeek-R1 distillates, Azure Foundry serverless): next phase, gated on (a) 5k+ examples per subject and (b) traffic volume justifying GPU spend. Until then, generalist tuned Gemini 2.5 Flash dominates on the 255-example-budget regime.
- **Azure migration**: project stays on Vertex AI. Existing plumbing (`gemini_client.py`, ADC, project `animated-rope-453904-j7`) is reused. Azure Foundry only re-enters consideration when open-weight is on the table.
