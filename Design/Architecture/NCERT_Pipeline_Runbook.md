# NCERT Pipeline Execution Runbook

This runbook outlines the required sequence to safely pull legacy extracted DB rows through the 3-stage Assembly Line up to the `APPROVED_GOLD` standard using `ncert_pipeline_orchestrator.py` and `evaluator_engine.py`.

## State Machine Trajectory
`REJECTED` -> `MATH_REGENERATED` -> [Evaluator] -> `MATH_PASSED` -> `PEDAGOGY_ADDED` -> `APPROVED` -> [Evaluator] -> `APPROVED_GOLD`

---

### Step 1: Fix Core Mathematical Logic
Target any rows that failed initial legacy evaluations and are currently flagged as `REJECTED`. This stage completely ignores strict formatting and pedagogy to focus the LLM purely on hitting the Answer Key Truth.

```bash
cd pipelines/ModelEngineering
python ncert_pipeline_orchestrator.py --class 12 --subject Physics --task regenerate --limit 50 --update-db
```
*Result: Target rows are promoted to `MATH_REGENERATED`.*

### Step 2: Intermediate Evaluation Gate (The Math Check)
> **DEFERRED** — Steps 1–2 are the REJECTED-row rewrite loop. Per the Gold Set plan
> (2026-05-21) the rewrite loop is parked until the nimble model exists; the current
> run harvests only rows that already PASS accuracy. This step is kept for completeness.

Run the evaluator on the newly regenerated math before it proceeds to pedagogy, in
`accuracy_only` mode so scoring focuses solely on Accuracy.

```bash
python evaluator_engine.py --source ncert --target-status MATH_REGENERATED \
    --mode accuracy_only --pass-status MATH_PASSED --fail-status REJECTED
```
*Result: Rows scoring accuracy 5/5 are promoted to `MATH_PASSED`; the rest revert to `REJECTED`.*

### Step 3: Inject Pedagogy
Add Socratic nudges and conceptual hierarchy to mathematically verified rows without altering the core math equations.

```bash
python ncert_pipeline_orchestrator.py --class 12 --subject Physics --task pedagogy --limit 50 --update-db
```
*Result: Target rows are promoted to `PEDAGOGY_ADDED`.*

### Step 4: Strict KaTeX Formatting
Apply pedantic LaTeX formatting across the entire JSON payload, replacing bare unicode symbols with strict KaTeX.

```bash
python ncert_pipeline_orchestrator.py --class 12 --subject Physics --task format --limit 50 --update-db
```
*Result: Target rows are promoted to `APPROVED`.*

### Step 5: Final Golden Evaluation Gate
Run the ultimate evaluation checking all three pillars: Math Accuracy (5/5), Pedagogy
Quality (5/5), and Formatting adherence (5/5). Only a **strict 5/5/5** is promoted.

```bash
# --mode full and --pass-status APPROVED_GOLD are the defaults; --dry-run scores without writing.
python evaluator_engine.py --source ncert --target-status APPROVED --limit 50
```
*Result: Rows scoring a strict 5/5/5 are permanently promoted to `APPROVED_GOLD` and are
ready for App ingestion or Model Fine-Tuning datasets. Rows that fall short are left at
`APPROVED` (pass `--fail-status` to route them elsewhere). Verdicts are logged to
`TempLocal/gate_ncert_APPROVED_<runid>.jsonl`.*

The same gate serves the JEE table — `--source jee --target-status APPROVED` (or `UNVERIFIED`).