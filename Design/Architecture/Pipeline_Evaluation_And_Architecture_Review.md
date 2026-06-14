# Pipeline Architecture Review and Evaluation Strategy

## 1. Architectural Comparison: Monolithic JEE vs NCERT Multi-Step

We compared the current 1-pass JEE Generation Pipeline with the 3-pass NCERT Pipeline (`MultiStep`).

| Feature | JEE Pipeline (Current) | NCERT MultiStep Pipeline |
|---------|---------|---------|
| **Approach** | Single-pass monolithic prompt ("Expert Author") | 3-stage separation (Solution → Tutor → Format) |
| **Strengths** | Fast, token-efficient, single LLM call. Generates raw mathematical derivation effectively. | **Strong separation of concerns.** The Tutor step can focus entirely on pedagogical voice without diluting the raw mathematical derivation in the first step. Format step ensures strict schema compliance. |
| **Weaknesses** | Overloading a single prompt risks "lazy generation" (now mitigated by the new prompt) and makes it harder to isolate formatting bugs from logic bugs. | Higher latency and cost due to multi-pass LLM calls. |

**Recommendation:** For now, the 1-pass JEE approach is viable because the "Expert Author" prompt is generating strong math derivations. However, if we need to tune the "Tutor/Pedagogical" voice independently for the JEE solutions in the future, the NCERT 3-pass architecture is significantly more resilient for fine-tuning individual stages.

---

## 2. Review of "Smart Context" (RAG / Vector Indexing)

The NCERT extracting pipeline uses a **Smart Context** vector mechanism. Rather than solving in a vacuum, the pipeline queries the `ncert_concept_embeddings` and `ncert_concept_hierarchy` to fetch curriculum-specific text, formulas, and theorems before solving the question.

**Analysis & Recommendation:** 
This is an incredibly strong design pattern. Grounding the LLM via RAG limits scope hallucination and ensures the AI doesn't solve a Class 11 problem using a college-level theorem. We must ensure this mechanism is universally applied to the JEE generation pipeline as well, so JEE questions are solved using the specific NCERT theoretical boundaries defined in the Concept Index.

---

## 3. Batch Evaluation Wrapper & A/B Testing Strategy

To validate the improved JEE Prompt outputs (and future model tuning), we are designing a **Batch Evaluation Wrapper**.
Visual inspection of screenshots is subjective and does not scale. The A/B testing workflow will follow this design:

### The Architecture
1. **The Wrapper Script (`batch_evaluator.py`)** 
   - Takes a dataset subset (e.g., $N=50$ random JEE mathematics questions).
   - Generates the solutions under the "Current Prompt/Model" vs the "Test Prompt/Model".
2. **The Evaluator Engine Integration**
   - Feeds the outputs into the existing `evaluator_engine.py` (which scores on a 0-5 scale for Accuracy, Pedagogy, and Formatting).
3. **Cumulative State Aggregation**
   - Computes quantitative metrics: Pass Rate (%), Avg Accuracy Score (X.X/5), Avg Pedagogy Score, Avg Token Length.
4. **Markdown Export (Baselining)**
   - Emits an `Experiment_Run_[Timestamp].md` report containing:
     - Prompt version used.
     - Quantitative results table.
     - Top 3 fail-cases for qualitative review.

**Why this matters:** This creates an immutable "save state" for prompt engineering. If we change a math derivation rule in the prompt, we can instantly tell if "Accuracy" dipped across the 50-question baseline dataset compared to the previous run.

---

## 4. Current Status of JEE Solvers
- **Problem:** Previous generation was "lazy" with mathematical steps.
- **Fix Applied:** Deployed the `jee_solver_prompt_author.md` A/B testing prompt.
- **Result:** Visual inspection confirms a massive improvement in mathematical rigor and exhaustiveness.
## 5. Implementation Metrics Update

We implemented and baselined several pipeline variants using the `batch_evaluator.py`.

| Variant | Run Configuration | Pass Rate | Avg Accuracy (0-5) | Avg Pedagogy (0-5) | Avg Formatting (0-5) |
|---------|---------|---------|----------|----------|------------|
| **A** | Original Mono Prompt / Default Context | 90% (9/10) | 4.70 | 4.70 | 5.0 |
| **B** | Mono Prompt + Smart Context | 100% (5/5) | 5.0 | 4.60 | 4.60 |
| **C** | 3-Pass Assembly / Default Context | 100% (5/5) | 5.0 | 4.80 | 5.0 |
| **E** | 3-Pass Assembly + Smart Context | 87.5% (7/8) | 4.88 | 4.62 | 4.75 |
| **E (Retuned)** | **3-Pass Assembly + Smart Context + Pedagogy Fix + JSON Fix** | **100% (10/10)** | **5.00** | **5.00** | **5.00** |

**Crucial Learnings from Variant E (Retuning):**
1. **JSON Escaping for LaTeX:** The `GoldenGenerator` in Python must be patched with a `json.loads(self._sanitize_json_escapes(solution_text))` fallback. LaTeX commands like `\times` and `\frac` are generated as `\t` and `\f` which break Python's raw JSON decoder, crashing the pipeline.
2. **Socratic Decoupling:** Injecting direct textbook "Smart Context" to the Expert Solver inadvertently poisoned the pedagogical flow, causing the Tutor stage to blurt out direct laws (e.g. "Use Le Chatelier's...") instead of hinting. Fixed by adding a rigid system prompt rule in Stage 2 forcing the tutor to ask Socratic questions about laws rather than stating them.

This "Golden" generating setup (Variant E - Retuned) is pending final confirmation via a 25-sample run.