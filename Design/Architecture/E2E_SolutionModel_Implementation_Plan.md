> ⛔ SUPERSEDED — live status in GitHub Projects (project 2 / view 11). Kept for design/history only.
> The LoRA/Vertex fine-tuning path described here was **abandoned**; the shipped solution is an untuned
> Gemini-3-Flash 3-stage assembly line (Solver→Tutor→Format) + answer-key gate + figure router.
> Status fields below are stale.

# E2E Solution Model Implementation Plan

This document serves as the master tracking and guide plan for transitioning Aryabhata from costly, full-PDF Gemini 3.1 Pro reasoning to a highly efficient, fine-tuned Gemini 3 Flash model via a **Standardized Universal Input Pipeline** and continuous RLAIF (Reinforcement Learning from AI Feedback).

The strategy explicitly halts "full PDF" passing. All solutions will be generated using a Universal Payload: `[Problem JSON Text] + [Associated Images] + [Context Chunks from Concept Index]`. Generating visual figures in the output is explicitly parked for a future phase.

---

## 📍 Current State (2026-05-22)

**The Gold Set is COMPLETE.** 255 strict-5/5/5 training examples — 153 NCERT + 102 JEE —
are exported to `pipelines/ModelEngineering/gold_sft_dataset.jsonl` (ChatML / Vertex format).
This closes M2.2–M2.5 and the NCERT gold harvest of M5.1.

**Next milestone: M3 — the Tuning Loop.** Fine-tune Gemini 3 Flash on Vertex AI, then
baseline tuned-Flash vs Gemini 3.1 Pro with `evaluator_engine.py`.

- Folder guide for the machinery: `pipelines/ModelEngineering/CLAUDE.md`
- Full run history + every fix landed: `Design/Architecture/GoldSet_Execution_Tracker.md`
- Deferred: the `REJECTED`-row rewrite loop (M5.1 Healer/regenerate) — wired, not run.

---

## Master Status Tracker

### Module Taxonomy (Functional vs Engineering Mapping)
To clarify how these engineering milestones deliver functional capabilities:
1. **Module 1: JEE Gold Solution Pipeline** ➡️ Maps to M2.2, M2.3, M2.5 (Resilient 6-stage pipeline built first on the harder JEE domain).
2. **Module 2: NCERT Gold Pipeline & Cleanse** ➡️ Maps to M5.2 & M5.1 (Porting the hardened Module 1 pipeline to legacy NCERT data).
3. **Module 3: The Gold Set (Training Data)** ➡️ Maps to M2.4 & Pipeline Stage 6 (Exporting `APPROVED_GOLD` universally across JEE and NCERT).
4. **Module 4: New Model Creation** ➡️ Maps to M3 (Tuning one unified STEM model on Gemini Flash from Module 3's output).
5. **Module 5: Solution Feedback (Student App)** ➡️ Maps to M4 (Re-using the M2.5 Evaluator Engine for student handwriting OCR).
6. **Module 6: Production Scale Run** ➡️ Operational scaling of M2.3 and M5 using the tuned endpoint.

| Milestone | Sub-Milestone / Focus | Status | Target Area |
| :--- | :--- | :--- | :--- |
| **M1: The Foundation** | 1.1 Localized "Smart Context", GoldenGenerator, A/B Test | ✅ Complete | Multi-Step |
| **M2: Bootstrap & Evaluate** | 2.1 Input Standardization | 🔴 Not Started | Model Eng |
| | 2.2 JEE Solution Pipeline (Assembly Line Pattern) | ✅ Complete | JEE Ascent |
| | 2.3 JEE Golden Set Batch Generation | ✅ Complete | JEE Ascent |
| | 2.4 JSONL Training Set Creation | ✅ Complete | Model Eng |
| | 2.5 The Universal Evaluator Engine | ✅ Complete | Model Eng |
| **M3: Tuning Loop** | 3.1 Baselines (Pro vs Flash) | 🔴 Not Started | Model Eng |
| | 3.2 Distillation Loop & Vertex AI SFT | 🔴 Not Started | Model Eng |
| **M4: Student Eval** | 4.1 Optimize payload for Handwriting grading | 🔴 Not Started | Azure Functions |
| **M5: NCERT Cleanse** | 5.1 Retroactive Cleanse & Production Overhaul | � In Progress | Multi-Step |
| | 5.2 NCERT Assembly Line Adaptation | ✅ Complete | Model Eng |

---

## 🏗️ Milestone 1: The "Immediate Impact" Foundation (COMPLETE)

**Key Achievements:**
- Multi-Step pipeline replaced passing 150k token PDFs with a `pgvector` indexing approach. 
- Centralized `GoldenGenerator` implemented (Gemini 3.1 Pro with a 2-pass Critique Loop).
- **A/B Test Results (kech202.pdf — 40 questions):** The Smart Context pipeline matched or outperformed the massive-context Production pipeline on **80% of questions**. Validation complete.

---

## 🧠 Milestone 2: Bootstrap & Evaluate (Priority 1)

### 2.1 Input Standardization
- Enforce a strict input payload across NCERT & JEE: `JSON Text` + `Associated Image Blob` + `Concept Index Chunks`. No full PDFs.

> **KNOWN GAP — JEE figure-URL extraction (discovered 2026-05-23)**
> Surveyed all of `jee_question_bank` while building the M3 holdout. Findings:
> - **100% of rows have `figure_url = NULL`** (across PENDING, APPROVED, APPROVED_GOLD — every row).
> - **`has_figure = true` IS populated**: ~18% of JEE Physics PENDING (80/450), ~19% of Chemistry PENDING (89/460), and a handful of APPROVED_GOLD rows.
> - Net effect: ~170 JEE rows are figure-DEPENDENT (the problem text references "the given figure…") but the actual figure cannot be inlined to the model at inference. Today's Pro pipeline operates handicapped on these; the tuned Flash will inherit the same handicap.
> - Tracker entry: `pipelines/JEEAscentPipeline/QA_Tracker.md` (2026-05-23 — KI-3).
> - Impact on M3: comparison stays fair (all three baselines operate without the image) but figure-dependent JEE rows under-perform globally. M3 holdout records both `has_figure` (broad) and `image_urls_present` (strict) so the gap is measurable.
> - Fix scope: extend the JEE extraction pipelines (`jee_paper_extractor.py` and/or `jee_crop_pipeline.py`) to capture figure crops as blob URLs and write them to `question_content.figure_url` / `option_figure_urls`. The schema already supports it; only the extractor needs to populate it. Originally noted as a "Phase 2 enhancement" in `pipelines/JEEAscentPipeline/CLAUDE.md`.
> - Priority: not blocking M3 (text-only comparison is still fair). Schedule alongside the 2023 re-extraction (KI-2) so both pipelines learn the figure-crop step together.

### 2.2 JEE Solution Pipeline (Assembly Line Pattern) (✅ COMPLETE)
- **Assembly Line Pattern Implemented:** The LLM generation explicitly uses a sequential task breakdown (`Solver -> Tutor -> Formatter`) to eliminate model context dilution and guarantee high-quality pedagogical output.
- **Pipeline Execution & Scoping:** Refactored `jee_solution_pipeline.py` leveraging `argparse` restricting targeted runs via CLI flags (`--year`, `--shift`, `--subject`, `--exam-date`, `--limit`, `--batch-size`, and `--use-critique`).
- **Database State Machine Integration:** Engineered explicit saving hooks assigning generated payloads with `review_status='UNVERIFIED'` and `is_generated=TRUE`. `answer_key IS NOT NULL` is enforced.
- **Testing & Verification Script:** Implemented `review_generations.py` as a viewport endpoint to seamlessly pull and pretty-print new JSON generations from PgSQL into terminal.

### 2.3 JEE Golden Set Batch Generation (✅ COMPLETE)
- **Batch Processing:** Initiate bulk pipeline runs (e.g., Target: 100, Batch: 10) to generate the initial corpus of high-quality Ground Truth JEE solutions utilizing Gemini 3.1 Pro.
- **Design Rule:** Do not assume an official answer key is always available to ensure strong resilience toward generating derived logical steps.

### 2.4 JSONL Training Set Creation (✅ COMPLETE)
- Build a dataset extraction script.
- Pull the 899 highest-quality existing NCERT solutions + the newly generated JEE solutions securely created by the "Teacher" model (Gemini 3.1 Pro).
- Format them stringently into OpenAI JSONL / ChatML structure required by Vertex AI.

### 2.5 The Universal Evaluator Engine (`evaluator_engine.py`) (✅ COMPLETE)
- **Evaluator Script Built:** Created `evaluator_engine.py` in `pipelines/ModelEngineering/` utilizing Gemini 3.1 Pro as the automated judge.
- **Scoring Architecture:** Outputs a robust composite score tracking Accuracy (0-5), Pedagogy (0-5), and Formatting (0-5).
- **Binary Verdict Framework:** Enforces a rigid `is_pass` condition (e.g., Total >= 13 AND Accuracy == 5).
- **Extensible Integration:** Ready to power RLHF/SFT baselining, NCERT retrospective cleanups, and prompt quality tracking.

---

## 🔬 Milestone 3: The Tuning Loop (RLAIF) (Priority 2)

### 3.1 Precision Baselines
- Run the Evaluator on 100 existing NCERT and 100 JEE solutions to establish **Gemini 3.1 Pro Precision** (The Target).
- Write a `flash_solution_generator.py` (using untuned Flash).
- Run on 100 unseen mixed questions to establish **Base Flash Precision** (The Floor).

### 3.2 Distillation Loop & Vertex AI SFT
- **Training Constraints:** Train *only* on solutions generated by the Teacher model (Gemini 3.1 Pro) to prevent model collapse.
- **Vertex AI Deployment:** Utilize serverless, pay-as-you-go Google Cloud Vertex AI Tuning. Tuned endpoints scale to zero and bill strictly per 1,000 input/output tokens.
- **The Loop:**
  1. Fine-tune Gemini 3 Flash using the JSONL corpus.
  2. Test tuned model on 100 unseen mixed questions.
  3. Evaluate precision. 
  4. If tuning precision < Pro precision: Take failed questions, generate perfect solutions via Gemini 3.1 Pro, append to JSONL corpus, and retrain.
  5. Exit when Tuned Flash roughly equals Pro precision (90%+).

---

## 📝 Milestone 4: Student Evaluation Function Optimization (Priority 3)

### 4.1 Input Alignment (Azure Functions)
- **Standardize Input:** Stop pulling full chapter PDFs for text-referenced problems (e.g., "Prob 11.7"). Fetch problem JSON + Concept Index chunks directly.
- **Image Uploads:** Extract Problem Text/Images via quick pre-processing prior to grading.
- Unify inputs so `gemini-3.1-pro-image-preview` grades handwriting against the Universal Payload + Universal Solution framework.

---

## 🧹 Milestone 5: NCERT Production Overhaul (Priority 4)

### 5.1 Retrospective Cleanse (The Hybrid Assembly Line)
- **DB Migration**: Add state machine columns (`review_status`, `is_generated`, `retry_count`, `answer_key`) to `questiondata`, flagging legacy rows as `LEGACY`.
- **Answer Key Ingestion**: Pull answer key PDFs (suffixed with `an.pdf` like `kech1an.pdf`) from `kalidasa` blob container, map them to DB rows via a Gemini script to provide Ground Truth anchoring. Note: not all questions (e.g., proofs) have answers.
- **The Assembly Line Pipeline (`ncert_pipeline_orchestrator.py`)**:
  - Implements a resilient 3-task state machine resolving overlapping prompts and context dilution:
  - Task 1: `regenerate` (Targets `REJECTED` -> Advances to `MATH_REGENERATED`)
  - Task 2: `pedagogy` (Targets `MATH_PASSED` -> Advances to `PEDAGOGY_ADDED`)
  - Task 3: `format` (Targets `PEDAGOGY_ADDED` -> Advances to `APPROVED`)
  - Incorporates strict structural validation, exponential backoff retries (`tenacity`), and JSONL dry-run checkpointing to ensure zero token waste on API crashes.
- **The Healer (`ncert_recovery_extractor.py`)**: For rows that fail the Integrity Gate (due to botched legacy extraction), fall back to utilizing the 2-pass `ExtractionEngine` on the localized page PDF to safely re-extract the missing text/image.
- **The Judge**: Use `evaluator_engine.py` to route logic between stages (e.g. evaluating `MATH_REGENERATED` rows to promote them to `MATH_PASSED` so they can enter the pedagogy queue).

### 5.2 Phase 2: Fresh Extraction Unification 
- Stitch the new 2-pass `ExtractionEngine` directly into the `ncert_solution_pipeline` logic for net-new chapters.
- Ensure net-new uploaded chapters automatically flow through the `Solver -> Tutor -> Formatter` Assembly Line and land in `UNVERIFIED` state, bypassing the need for legacy heuristic checks entirely.
- Front-end APIs (`practiceQuestion.ts`) to eventually filter strictly by `review_status = 'APPROVED_GOLD'`.

---

## 🛑 Exceptions & Parked Scope
- Code/LLM logic to generate visual output (Chemistry structures, Math geometry, SVG diagramming) as part of the solution object is explicitly scoped out and parked for future platform iterations ("Live to die another day").
