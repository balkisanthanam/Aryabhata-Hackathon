# Design Note: Reviewing NCERT Solution Pipeline against Assembly Line Pattern

**Date:** May 2026
**Context:** The JEE Ascent Pipeline recently shifted away from a dense, multi-instruction single-pass LLM approach ("Solve this accurately AND use Socratic pedagogy AND output strict JSON schema all at once") and moved towards the **"Assembly Line Pattern"**. In an Assembly Line, models handle atomic sub-tasks sequentially (e.g., Step 1: Raw Math Solver -> Step 2: Socratic Rewriter -> Step 3: Schema Formatter). This mitigates LLM *Attention Dilution* (the model dropping pedagogical constraints when math logic becomes too complex).

## Opportunity 

The current **NCERT Data Extraction MultiStep Pipeline** (`pipelines\ExtractionPipeline\SchoolDataExtraction\MultiStep\main.py` -> `gemini_client.py` -> `solver_engine.py`) heavily utilizes the `GoldenGenerator` framework for evaluating and creating JSON. It asks the model (via Gemini) to do multiple distinct conceptual leaps in a single pass. 

Applying the Assembly Line pattern to NCERT extraction could drastically reduce output inconsistencies, schema failures, and hallucination artifacts in the NCERT pipeline.

## Current NCERT Extraction Loop:
Presently, NCERT images/crops are sent directly to the model, and we prompt it to:
1. Recognize the OCR text boundaries.
2. Determine if it's part of a conceptual chapter, exercise, or literal question.
3. Solve the question.
4. Output the structured JSON.

## Proposed "Assembly Line" Mapping for NCERT:

1. **The OCR / Layout Specialist (Pass 1)**
   * **Input:** Raw textbook image slice.
   * **Task:** Pure text/latex transcription & bounding box identification. Strip out irrelevant watermarks. 
   * **Output:** Clean Markdown text block (No JSON schema requested).

2. **The Sub-Agent Router (Pass 2 - Logic / Routing)**
   * **Input:** The clean Markdown text block.
   * **Task:** Identify is this *expository concept text*, an *exercise header*, or a *question*? 

3. **The Solver & Socratic Generator (Pass 3 - The Pedagogical layer)**
   * **Input:** ONLY if it is classified as a Question.
   * **Task:** Generate the underlying logical steps separately, then rewrite them defensively using Socratic Nudge pedagogy (as validated in the JEE pipeline).

4. **The Schema Formatter (Pass 4)**
   * **Input:** The accumulated outputs.
   * **Task:** Package everything faithfully into the strict `JSONB` properties required by the DB (`chapterdata`, `exercisedata`, `questiondata` formats).

## Benefits:
* **Cost Efficiency:** Cheaper tier models (like Gemini Flash) can handle the schema formatting and OCR phases. We only pay the premium for Gemini Pro on the heavy logical solver phase.
* **Granular Observability:** If parsing fails, we know exactly *which* agent in the line failed (OCR error vs Math logic error vs Schema JSON trailing commas).
* **Code Reusability:** The Socratic Agent prompt used in JEE can be cleanly imported into the NCERT pipeline for unified platform pedagogy.

***UPDATE (May 2026): Practical Implementation in Retrofit Pipeline***
*We successfully implemented the Assembly Line principle for the "Retrofit/Cleanse" stage of legacy NCERT data. Rather than the complex MultiStep solver doing it all, we now have `ncert_pipeline_orchestrator.py` which abstracts the LLM processing into three distinct passes via a database-backed state machine. See `NCERT_Pipeline_Handover.md` for the exact state progression (MATH_REGENERATED -> PEDAGOGY_ADDED -> APPROVED).*

## Technical Gotchas and Fixes (From Empirical Testing)
When migrating to this pattern, two critical integration fixes emerged during evaluation scaling:

1. **LaTeX vs JSON Decoding Collisions:**
   - **Issue:** The Formatter (Pass 4) outputs raw LaTeX math equations like `\times` and `\frac`. Native `json.loads` in Python treats `\t` and `\f` as illegal escape sequences and crashes.
   - **Fix:** A dedicated `_sanitize_json_escapes()` function must be applied immediately before decoding the LLM output to double-escape LaTeX slashes back to literal backslashes (`\\t`, `\\f`, `\\r`, `\\n`).

2. **Smart Context Leaking in Pass 3 (Pedagogical Layer):**
   - **Issue:** If Pass 1 is fed "Smart Context" (direct textbook theorem text) to ground its physics/math accuracy, the LLM derivation becomes heavily academic. Without override instructions, Pass 3 (Pedagogical Layer) gets lazy and echoes those textbook sentences directly (e.g. "By using Le Chatelier's...") instead of maintaining Socratic distance.
   - **Fix:** Pass 3 requires a hard-overridden prompt rule: *If the derivation quotes a specific rule or formula, do not state it. Ask the student "How would you apply X law here?"*