# AryaBhatta Architecture Proposal: Evaluating & Fine-Tuning Pipeline

## Track A: JEE Solution Generation Pipeline (Bootstrap via Pro)

**1. Target & Purpose:**
Gemini 3.1 Pro (Preview) acting as the "Teacher" model to bootstrap a "Golden Set" of reference data and model solutions.

**2. Pipeline Design (Assembly Line Pattern):**
Decoupled DB-to-AI-to-DB loop ensuring high precision:
* **Ingestion:** Pull batches scoped by `--year`, `--shift`, `--subject` from `jee_question_bank`.
* **Step 1 (The Solver):** Gemini 3.1 Pro solves purely for mathematical/physics accuracy (dry, step-by-step logic).
* **Step 2 (The Tutor):** Gemini 3.1 Pro rewrites the dry logic into Socratic nudges.
* **Step 3 (The Formatter):** Fast model ensures LaTeX and JSON schema validity.
* **Persistence:** Writes `JSONB` solution back to DB with `review_status = 'UNVERIFIED'`.

**3. Verification & Grading Mechanism:**
* A separate offline job (`evaluator_engine.py`) grades `UNVERIFIED` solutions.
* Updates status to `APPROVED_GOLD` (>13/15) or `REJECTED_NEEDS_REWRITE`. Imperfect answers are kept in the DB for negative-example training data.

## Track B: Fine-Tuning & Dataset Infrastructure

**1. Target Model & Task:**
Fine-tuning a smaller, faster model (e.g., Gemini Flash) to act as our Production Evaluator of student math problems, capable of scoring on Precision, Pedagogy, and Tone.

**2. Creating the JSONL:**
Use `pipelines/ModelEngineering/jsonl_exporter.py` to extract high-quality evaluation data into ChatML format (`.jsonl`).

**3. JSONL Content Structure:**
* **System Role:** Evaluator persona instructions.
* **User Role:** Universal Question Payload + Student's uploaded solution.
* **Model Role:** Perfect Evaluation Feedback JSON (Must be 4/5 or 5/5 on all facets).

**4. Active Learning Flywheel:**
Iterative continuous evaluation. Flag low confidence or disputed evaluations, route them to Gemini 3.1 Pro to correct, append the correction to the dataset, and re-tune.

**5. Fixing Teacher Pedagogy:**
Before extracting data, update the Teacher Prompt to enforce Socratic methodology using the 4 specific baseline archetypes (Golden, Pedagogy Jumper, Confident Drift, Visual Hallucination). Re-run NCERT solutions to fix the current 1/5 and 2/5 pedagogy defaults.

## Pending Prompt Edits (`jee_solver_prompt.md`)
*   Remove `{{CLASS}}` and `{{BOARD}}` as JEE is board/class-agnostic.
*   Rewrite visual context instruction to accurately reflect Azure Blob URLs securely embedded within the Universal Payload JSON rather than raw cropped images.
*   Overhaul the "Step-by-step nudging" instruction block to aggressively mandate Socratic, hint-driven "mental leaps."
*   Create an explicit task to re-generate NCERT solutions with the improved Pedagogy instructions before treating them as "Golden".