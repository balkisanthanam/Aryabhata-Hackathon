# Model Engineering History

This document serves as the chronological log for prompt engineering, architectural variations, and experimental milestones used to evaluate AI pipelines across projects (JEE, NCERT, etc.).

## JEE Solution Generation

### Phase 1: Prototype Variations (Variants A - D)
We conducted an initial round of structured evaluations attempting to format and generate Socratic steps directly via varying single-pass or basic two-pass systems.
- **Goal:** Determine the baseline capability for generating Socratic (tutor-like) mathematical and scientific proofs for JEE questions.
- **Results:**
  - **Variant A (Original Mono, N=10):** Pass Rate 90.0% | Acc: 4.70 | Ped: 4.70 | Fmt: 5.00
  - **Variant B (Expert Author Mono, N=10):** Pass Rate 100.0% | Acc: 5.00 | Ped: 4.50 | Fmt: 5.00
  - **Variant C (Author + Smart Context, N=10):** Pass Rate 100.0% | Acc: 5.00 | Ped: 4.30 | Fmt: 5.00
  - **Variant D (3-pass Assembly Baseline, N=8):** Pass Rate 100.0% | Acc: 5.00 | Ped: 4.88 | Fmt: 5.00
- **Major Challenges Encountered:**
  - **Pedagogical Leakage:** The model would frequently give away the final answer or critical execution steps too early in the hint structure instead of gently nudging the student (seen by Pedagogy scores dropping to ~4.3-4.5).
  - **JSON Serialisation Errors:** Formatting breaks caused by LaTeX collisions (e.g., standard backslash escaping where `\times` collided with JSON `\t` escaping).

### Phase 2: Decoupled Assembly Line (Variant E - Re-Tuning)
To resolve the leakage and formatting constraints, we introduced the **Socratic Decoupled Assembly Line**.
- **Architecture:** 3-Pass Pipeline.
  1. **Server:** Solves the problem outright (raw mathematical phase).
  2. **Tutor:** Transforms the solved mathematical steps into Socratic instructional steps.
  3. **Formatter:** Strict JSON/Markdown enforcement.
- **Experimental Tuning results (Variant E - Assembly + Smart Context):**
  - Iteration 1 (N=5): Pass Rate 80.0% | Acc: 4.20 | Ped: 3.80 | Fmt: 5.00
  - Iteration 2 (N=8): Pass Rate 87.5% | Acc: 4.88 | Ped: 4.62 | Fmt: 4.75
- **Final Result (Variant E - Re-tuning):** Hit a strict **100% Pass Rate** (10/10) with a flawless **5.0/5.0 Average Pedagogy** score in a 10-sample sandbox test.
- **Key Breakthrough:** Splitting the context and keeping the AI from being "conceptually overloaded" solved the pedagogy leak definitively.

### Phase 3: Golden Validation (Variant F)
Prior to committing the architecture to production, we ran a broader 25-sample validation to stress-test the Socratic and JSON stability.
- **Key Addition:** Integrated **Smart Context** (injecting RAG conceptual context directly from the NCERT database schemas).
- **Result (Variant F - Golden Validation):** Maintained **100% Pass Rate (25/25)** | Acc: 5.00 | Ped: 4.96 | Fmt: 4.96
- **Status:** **APPROVED**. This formally locked in the Assembly Line Socratic schema ("Golden Generator").

### Phase 4: Production Integration & In-DB Verification (May 2026)
We ported the Variant F logic directly into the production DB ingestion pipeline (`pipelines/JEEAscentPipeline/jee_solution_pipeline.py`). We seeded an initial target batch of 100 Socratic solutions straight into `jee_question_bank` as `UNVERIFIED`.

To ensure the production port didn't introduce bugs, we created `evaluate_saved_generations.py` to pull a subset of the newly created database entries and score them against the Universal Evaluator.

**Final Scorecard (25 Random Samples):**
- **Pass Rate:** 100%
- **Accuracy:** 5.0 / 5.0
- **Pedagogy:** 4.96 / 5.0
- **Formatting:** 4.96 / 5.0

**Conclusion:** The production pipeline preserved the Golden logic flawlessly. The subset was auto-approved and we are now clear for large-scale DB dataset generation.
