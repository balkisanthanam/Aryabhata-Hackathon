# Feasibility Analysis: Replacing Full-PDF with Vector Index Context in Solution Feedback

**Date:** 2026-03-30
**Scope:** Student Evaluation Pipeline (`pipelines/AzureFunctions/StudentEvaluationFunction/`)
**Prerequisite:** Read alongside `ConceptIndex_DesignReview.md` for index gap analysis

---

## 1. How the Pipeline Uses the PDF Today

The evaluation pipeline has 7 orchestrated steps. Only **one step** uses the chapter PDF:

| Step | Activity | Uses PDF? | What it does |
|------|----------|-----------|-------------|
| 1 | `read_evaluation` | No | DB lookup, status update |
| 2 | `fetch_student_images` | No | Download student handwriting from blob |
| 2B | `fetch_student_images` | No | Download optional textbook page images |
| 3 | `parse_text_ref` | No | Parse "13.8-13.10" → structured problem list (Gemini Flash-lite) |
| 4 | `validate_inputs` | No | DB lookup for chapter, subject validation |
| 5 | `get_chapter_pdf` | **Fetches** | Looks up `PDFFileURL` from `chapterdata`, downloads full PDF bytes to verify accessibility |
| **6** | **`evaluate_batch`** | **YES** | **Sends full PDF as `[REFERENCE MATERIAL PDF]` to Gemini alongside student pages** |
| 7 | `update_evaluation` | No | Write feedback_json to DB |

### What Gemini uses the PDF for (in `evaluate_batch`)

The evaluation prompt (`Evaluation.txt`) instructs the model to:
1. **Find the correct answer** — "Use chapter PDF to verify correct answer or solve yourself"
2. **Ground the solution** — reference textbook formulas, tables, and methods
3. **Generate full_solution** — provide the complete step-by-step solution for each problem

The PDF is appended as the last content part:
```python
content_parts.append("\n[REFERENCE MATERIAL PDF]")
content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})
```

### Token cost of the PDF per evaluation

| Component | Estimated tokens | Per-batch? |
|-----------|-----------------|------------|
| Full chapter PDF | 15,000–25,000 | YES — sent in every batch |
| Student pages (2 images) | 6,000–10,000 | YES |
| Textbook pages (optional, 1 image) | 3,000–5,000 | YES |
| Evaluation prompt | ~2,000 | YES |
| Model response | ~3,000–5,000 | YES |
| **Total per batch** | **~29,000–47,000** | |

For a typical evaluation (6 problems, batch_size=3 → 2 batches):
- **PDF contributes 30,000–50,000 tokens** (sent twice, once per batch)
- **This is 50–60% of total input tokens**

**Critical difference from the extraction pipeline:** There is **NO caching** here. The PDF is fetched fresh from blob storage and sent raw in every `evaluate_batch` call. Unlike the extraction pipeline which uses Gemini's Content Caching API (1-hour TTL), the evaluation pipeline re-uploads the entire PDF for each batch. This makes PDF replacement significantly more impactful for cost.

---

## 2. The Two Evaluation Scenarios

### Scenario A: NCERT Exercise Questions (text reference)

**Student says:** "13.8, 13.9, 13.10" with context `{subject: Physics, chapter: Oscillations}`

**What the model needs to evaluate:**
1. The question text (what was the student asked?)
2. The correct answer/solution (what should the student have done?)
3. Domain knowledge to assess the student's approach

**What we already have in the database:**
- `questiondata.content` (JSONB) — the extracted question text, visual_required flag, image URLs
- `questiondata.solution` (JSONB) — the AI-generated step-by-step solution with hints, formulas, final answer
- These were populated by the NCERT extraction pipeline (Stage 1 + Stage 2)

**Key insight:** For NCERT questions, we have BOTH the question and the reference solution already stored. The model does not need to "find the question in the PDF" or "solve it from scratch using the PDF." It can be given the pre-extracted question + solution directly.

### Scenario B: Non-NCERT / Bring-Your-Own Questions

**Student says:** "My coaching worksheet problem 5" and uploads problem images + solution images

**What the model needs:**
1. The question (from uploaded problem images — already handled)
2. Domain knowledge to evaluate (this is where the PDF or concept index helps)
3. No pre-stored solution exists

---

## 3. Replacement Strategy: What Can Replace the PDF

### For Scenario A (NCERT Questions) — **FULL REPLACEMENT IS VIABLE**

The current flow sends the PDF so Gemini can find the question and solve it. But we already have:

| Need | Current Source | Replacement Source | Already Available? |
|------|---------------|-------------------|-------------------|
| Question text | Gemini finds it in PDF | `questiondata.content` | YES |
| Question images | Gemini finds it in PDF | `questiondata.content.visual_data.blob_url` | YES |
| Correct solution | Gemini solves from PDF | `questiondata.solution` (steps, formulas, final_answer) | YES |
| Domain formulas | PDF chapter theory | `ncert_concept_hierarchy` (top-K chunks) | YES (with caveats from ConceptIndex_DesignReview.md) |
| Reference data tables | PDF tables | `ncert_concept_hierarchy` | **NO — gap identified in DesignReview** |

**Proposed replacement context for Scenario A:**

Instead of the ~20,000-token PDF, send:
```
[REFERENCE QUESTION]
Question 13.9: {questiondata.content.question_text}
{questiondata.content.visual_data image if present}

[REFERENCE SOLUTION]
{questiondata.solution — steps, formulas, final_answer}

[RELEVANT CONCEPTS]  (optional, from vector index)
{Top 3-5 concept chunks from ncert_concept_hierarchy, retrieved by question text}
```

**Estimated token cost of replacement:**
- Question text: ~200 tokens
- Reference solution: ~500–1,000 tokens
- Concept chunks (5 nodes): ~1,000–2,000 tokens
- **Total: ~1,700–3,200 tokens** vs 15,000–25,000 for the PDF

**Token savings: 80–90% of the PDF input per batch.**

### For Scenario B (Non-NCERT Questions) — **PARTIAL REPLACEMENT IS VIABLE**

There is no pre-stored question or solution. The model must evaluate from domain knowledge alone.

| Need | Current Source | Replacement Source |
|------|---------------|-------------------|
| Question text/image | Student-uploaded problem images | Same (no change) |
| Correct solution | Model solves from PDF | Model solves from concept chunks |
| Domain formulas | PDF chapter theory | `ncert_concept_hierarchy` (top-K chunks) |

This is the same trade-off analyzed in `ConceptIndex_DesignReview.md` for the extraction pipeline solver. The concept index can provide targeted formulas and definitions, but:
- Lacks data tables (Gap 1 in DesignReview)
- May miss multi-concept dependencies
- No figure content (figure_url = NULL)

**Recommendation for Scenario B:** Use concept chunks as primary context. If the student specifies a chapter, also retrieve the chapter's worked examples from the concept index (content_type = 'worked_example'). This provides pedagogical grounding without the full PDF.

**Risk:** For problems requiring specific numeric data (bond enthalpies, electrode potentials), the concept index lacks data_table nodes. This gap must be addressed (P0 from DesignReview) before Scenario B can fully drop the PDF.

---

## 4. Will the ConceptIndex DesignReview Improvements Help?

| DesignReview Improvement | Impact on Solution Feedback |
|--------------------------|---------------------------|
| **P0: Add `data_table` content type** | **HIGH** — Enables Scenario B (non-NCERT) to work without PDF for numeric-lookup problems |
| **P0: Enrich tsvector source** | **MEDIUM** — Better BM25 matching means more accurate concept retrieval for evaluation context |
| **P0: Multi-chapter hybrid search** | **HIGH** — Student problems may span concepts from multiple chapters (e.g., Electro-chemistry problem needing Thermodynamics concepts) |
| **P1: Content-type boosting** | **MEDIUM** — Evaluation context should prefer `formula` and `worked_example` nodes over `definition` nodes |
| **P1: Parent context expansion** | **LOW** — Less critical here since we have the pre-extracted solution as primary grounding |
| **P1: Two-stage retrieve+rerank** | **LOW** — Evaluation is already latency-heavy (3-5 min); a rerank step adds negligible overhead but limited value since Scenario A doesn't need retrieval |

**Key finding:** For Scenario A (NCERT), the DesignReview improvements are largely irrelevant — we don't need the concept index at all because we have the extracted question + solution. For Scenario B (non-NCERT), the P0 improvements (data_table, multi-chapter search) are prerequisites.

---

## 5. Impact on Latency and Cost

### Cost Analysis

**Current cost per evaluation (6 problems, 2 batches):**

| Component | Tokens (input) | Tokens (output) |
|-----------|----------------|-----------------|
| PDF (×2 batches) | 30,000–50,000 | — |
| Student images (×2 batches) | 12,000–20,000 | — |
| Prompts (×2 batches) | 4,000 | — |
| Responses (×2 batches) | — | 6,000–10,000 |
| **Total** | **46,000–74,000** | **6,000–10,000** |

**With replacement (Scenario A, 6 NCERT problems, 2 batches):**

| Component | Tokens (input) | Tokens (output) |
|-----------|----------------|-----------------|
| Question text + solution (×2 batches) | 3,400–6,400 | — |
| Concept chunks (optional, ×2) | 2,000–4,000 | — |
| Student images (×2 batches) | 12,000–20,000 | — |
| Prompts (×2 batches) | 4,000 | — |
| Responses (×2 batches) | — | 6,000–10,000 |
| **Total** | **21,400–34,400** | **6,000–10,000** |

**Input token reduction: 50–55% for NCERT evaluations.**

At Gemini pricing, this is a meaningful per-evaluation saving. Over hundreds of student submissions, it compounds.

### Latency Analysis

**Current latency contributors:**

| Step | Latency | Notes |
|------|---------|-------|
| `get_chapter_pdf` (blob download) | 1–3s | Downloads full PDF bytes to verify, then sends URL |
| `evaluate_batch` (PDF upload to Gemini) | 2–5s per batch | PDF bytes sent as content_part |
| `evaluate_batch` (Gemini processing) | 15–30s per batch | Model processes ~35K tokens input |
| **Total PDF-attributable** | **~5–13s per batch** | |

**With replacement:**

| Step | Latency | Notes |
|------|---------|-------|
| DB query for question + solution | 50–200ms | Simple indexed lookup by question_ref + exercise_id |
| Concept index query (optional) | 100–300ms | Hybrid search — HNSW + GIN |
| `evaluate_batch` (no PDF upload) | 0s | Eliminated |
| `evaluate_batch` (Gemini processing) | 8–15s per batch | Model processes ~15K tokens input |
| **Total** | **~8–16s per batch** | |

**Latency improvement: 7–15 seconds per batch, or 15–30 seconds for a typical 2-batch evaluation.**

For a pipeline that currently takes 3–5 minutes end-to-end, this could reduce total time by 15–25%. The improvement is not transformative but is noticeable — and it comes essentially free alongside the cost savings.

### Can this make the solution faster?

**Yes, measurably faster, for two reasons:**

1. **Reduced context = faster Gemini inference.** Gemini's generation time scales with input context length. Halving the input tokens reduces time-to-first-token and total generation time. For a 15K-token context vs 35K-token context, expect ~40% faster inference on the evaluation call.

2. **Eliminated blob download.** The `get_chapter_pdf` step currently downloads the full PDF from Azure Blob Storage to verify accessibility, then the `evaluate_batch` step downloads it again (via `fetch_blob_content`). Replacing the PDF with a DB query eliminates both downloads.

**The pipeline step `get_chapter_pdf` can be either simplified or removed entirely** for NCERT evaluations. For non-NCERT evaluations where concept chunks are used, it's replaced by a concept index query.

---

## 6. Implementation Approach

### Phase 1: NCERT Question Replacement (Scenario A) — No Index Changes Needed

This phase requires NO changes to the ConceptIndex. It uses existing data.

**New activity: `fetch_reference_material`**

Replaces `get_chapter_pdf` for NCERT evaluations:
1. Parse the problem list (from `parse_text_ref` output)
2. For each problem_id + chapter_id, query `questiondata` via `exercisedata`:
   ```sql
   SELECT q.content, q.solution
   FROM questiondata q
   JOIN exercisedata e ON q.exerciseid = e.exerciseid
   WHERE e.chapterid = {chapter_id}
     AND q.question_ref = {problem_id}
   ```
3. Return structured context: `{problem_id, question_text, question_images, solution_steps, final_answer}`

**Modified `evaluate_batch`:**
- Accept `reference_materials` (list of question+solution dicts) instead of `pdf_url`
- Build context as `[REFERENCE QUESTION]` + `[REFERENCE SOLUTION]` text blocks
- Remove PDF download logic

**Modified orchestrator:**
- After `validate_inputs`, check: is this an NCERT chapter with extracted questions?
  - YES → call `fetch_reference_material` instead of `get_chapter_pdf`
  - NO → fall back to current `get_chapter_pdf` (PDF flow preserved)

**Prompt modification (`Evaluation.txt`):**
- Replace "Use chapter PDF to verify correct answer" with "Use the provided reference question and solution to verify"
- The model still evaluates the student's work against the reference — the grounding source changes from PDF to structured text

### Phase 2: Non-NCERT Enhancement (Scenario B) — Requires DesignReview P0s

After the P0 improvements from `ConceptIndex_DesignReview.md` are implemented:
1. `data_table` content type added and ~15 chapters re-extracted
2. Multi-chapter hybrid search query built
3. Enriched tsvector trigger deployed

**Modified `fetch_reference_material` for non-NCERT:**
1. Embed the student's problem description (from problem images or text)
2. Run hybrid search against concept index (subject-scoped, cross-chapter)
3. Retrieve top 5–8 concept chunks (formulas, worked examples, data tables)
4. Return as `[RELEVANT CONCEPTS]` context block

---

## 7. Risk Assessment

### What could go wrong with NCERT replacement (Scenario A)?

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Extracted solution is wrong or incomplete | Low — solutions were generated by Gemini Pro with full PDF context | The model can still solve from its own knowledge; the reference solution is a hint, not the only source |
| Question text missing visual data | Low — extraction pipeline captures `has_figure` and uploads images | Check `visual_required` flag; if image URL is missing, fall back to PDF |
| Question not found in `questiondata` | Medium — some exercises may not have been extracted yet | Fall back to `get_chapter_pdf` for any problem_id that returns no DB match |
| Model evaluation quality degrades | Low — the reference solution provides stronger grounding than the PDF (explicit steps vs implicit chapter content) | A/B test on 20 evaluations before full rollout |

### What could go wrong with non-NCERT replacement (Scenario B)?

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Concept retrieval misses critical context | Medium — multi-concept problems | Retrieve more candidates (top-15), let model filter |
| Data table values not in index | High (until DesignReview P0 is done) | Do not deploy Phase 2 until `data_table` type is populated |
| No chapter context for non-NCERT problems | High — student may not specify a chapter | Use subject-wide search (no chapter filter) — acceptable because concept index is only ~1K nodes per subject |

---

## 8. Summary Finding

| Scenario | Verdict | Token Savings | Latency Savings | Prerequisites |
|----------|---------|--------------|-----------------|---------------|
| **A: NCERT Questions** | **YES — Full replacement** | **50–55% input tokens** | **15–30s per evaluation** | None — `questiondata` already populated |
| **B: Non-NCERT Questions** | **PARTIAL — After index improvements** | **40–50% input tokens** | **10–20s per evaluation** | DesignReview P0s (data_table, multi-chapter search) |

### Why this is different from the extraction pipeline conclusion

In the extraction pipeline analysis, we concluded "skip it" because:
1. Content caching already handled cost → **Not the case here. No caching exists.**
2. The quality gain was uncertain → **Here, Scenario A uses pre-verified question+solution, which is stronger grounding than the raw PDF.**
3. The only benefit was quality, not efficiency → **Here, the benefit is cost, latency, AND quality.**

**The Solution Feedback pipeline is the right place to adopt structured context replacement.** Start with Scenario A (NCERT), which requires zero index changes and delivers immediate measurable gains. Scenario B follows once the ConceptIndex P0 improvements land.

---

## 9. Recommended Next Steps

1. **Immediate:** Validate that `questiondata` coverage is complete for all NCERT chapters where Solution Feedback is used. Run a query:
   ```sql
   SELECT c.subject, c.chaptertitle, COUNT(q.questionid) as q_count
   FROM chapterdata c
   JOIN exercisedata e ON c.chapterid = e.chapterid
   JOIN questiondata q ON e.exerciseid = q.exerciseid
   WHERE q.solution IS NOT NULL
   GROUP BY c.subject, c.chaptertitle
   ORDER BY c.subject, c.chaptertitle;
   ```
   Any chapter with zero solutions needs the extraction pipeline run first.

2. **Phase 1 implementation:** Build `fetch_reference_material` activity, modify orchestrator with NCERT/non-NCERT branching, update evaluation prompt.

3. **A/B validation:** Run 10 NCERT evaluations with the new flow alongside the old flow. Compare: evaluation correctness, error_pinpoint accuracy, full_solution quality.

4. **Phase 2:** After ConceptIndex P0s are deployed, extend `fetch_reference_material` with hybrid search for non-NCERT problems.
