# NCERT Data Cleanse & Generation: Pipeline Handover

## 1. Objective
Transition from the JEE Ascent pipeline to digitizing and cleaning NCERT textbooks. 
Because the legacy `MultiStep` pipeline has known extraction flaws (hallucinating structures, missing context, mismatching answers), we are using a **Hybrid Assembly Line** approach. 

We process the legacy outputs through an LLM accuracy gate before rewriting bad solutions and applying strict AryaBhatta KaTeX formatting to the good ones.

---

## 2. Current State & Achievements
* **Database State:** The `questiondata` (or target NCERT table) now tracks state via a `review_status` column. Pre-existing rows were initialized to `LEGACY`.
* **Accuracy Gate Completed:** We wrote and ran `evaluate_ncert_baseline.py`. 
    * It pulls `LEGACY` rows.
    * It uses Vertex AI (Gemini) to evaluate the math/physics/chemistry logic strictly (zero-shot, using diagrams where needed).
    * Passed rows are updated to `MATH_PASSED`.
    * Failed rows are updated to `REJECTED`, and the exact failure reason is stored in a JSON log for the next stage.
* **Batch Results:** We ran 50-item batches across Class 11 & 12 (Physics, Chemistry, Maths) successfully. Pass rates were extraordinarily high (76% - 100%), proving the logic gate works effectively without just blindly comparing to answer keys.

---

## 3. The Unified Assembly Line Plan & State Machine

To enforce proper separation of concerns (LLMs hallucinate if asked to do intensive math, pedagogy, and formatting all at once), we have a unified `ncert_pipeline_orchestrator.py` that processes rows according to the following strict state progression:

1. **Extraction:** `LEGACY`
2. **Accuracy Gate:** `LEGACY` → `MATH_PASSED` or `REJECTED` (via `evaluate_ncert_baseline.py`)
3. **Regenerator:** `REJECTED` → `MATH_REGENERATED` (Must loop back to Gate to become PASSED).
4. **Pedagogy Injector:** `MATH_PASSED` → `PEDAGOGY_ADDED` (Adds Socratic `nudge_hints`).
5. **Formatter:** `PEDAGOGY_ADDED` → `APPROVED` (Applies strict KaTeX. Ready for App-serving).
6. **Final Validation:** `APPROVED` → `APPROVED_GOLD` (Only granted after successful 3D evaluation/Human logic checks. Used for model training).

### The Orchestrator (`ncert_pipeline_orchestrator.py`)
This script contains three targeted functions driven by CLI flags:
*   `--task regenerate`: Ignores formatting. Rewrites only the core math/physics logic for `REJECTED` rows. Updates to `MATH_REGENERATED`.
*   `--task pedagogy`: Assumes math is perfect. Injects Socratic questioning. Targets `MATH_PASSED` → `PEDAGOGY_ADDED`.
*   `--task format`: Assumes math and pedagogy are perfect. Enforces KaTeX restrictions. Targets `PEDAGOGY_ADDED` → `APPROVED`.

---

## 4. Run Commands for Handoff

**To run the baseline evaluator (Gate):**
```bash
python evaluate_ncert_baseline.py --class 12 --subject Physics --limit 50 --mode accuracy_only --update-db
```

**To regenerate the math for exactly those that failed:**
```bash
python ncert_pipeline_orchestrator.py --class 12 --subject Physics --task regenerate --limit 50 --update-db
```

**To inject pedagogy into the math-passed rows:**
```bash
python ncert_pipeline_orchestrator.py --class 12 --subject Physics --task pedagogy --limit 50 --update-db
```

**To format and approve them for the app:**
```bash
python ncert_pipeline_orchestrator.py --class 12 --subject Physics --task format --limit 50 --update-db
```

---

## 5. Next Immediate Action for AI
1. We just created `ncert_pipeline_orchestrator.py` which unifies these distinct operations. 
2. Test the `--task regenerate` path on the ~13 rejected rows in Chemistry/Physics.
3. Once generated, run those through `evaluate_ncert_baseline.py` again to ensure they upgraded to `MATH_PASSED`.
4. Proceed to test `--task pedagogy` and `--task format`.