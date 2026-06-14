# ConceptIndex Design Review & Architecture Improvements

**Date:** 2026-03-30
**Scope:** `ncert_concept_hierarchy` + `ncert_concept_embeddings` — schema, extraction, embedding, and retrieval design
**Purpose:** Identify gaps and propose improvements to support multi-concept / multi-discipline retrieval (M3 JEE Question Tagging and beyond)

---

## 1. Current State Summary

### What Exists

| Component | Status | Notes |
|-----------|--------|-------|
| Schema (hierarchy + embeddings) | Complete | ltree, VECTOR(768), GIN, HNSW indexes |
| Extraction prompts | Complete | 5 content types, exhaustive rules |
| Embedding pipeline | Complete | text-embedding-004, 768-dim, batch support |
| DB writer (insert/upsert) | Complete | Topological ordering, checkpoint-resumable |
| Verification | Complete | Tier 1 (checkpoint) + Tier 2 (DB consistency) |
| **Retrieval / Search API** | **Not implemented** | Only a SQL comment in migration file |
| **Cross-chapter search** | **Not implemented** | All queries scoped to single chapter_id |

### Corpus Statistics (74 chapters, all Class 11 + 12)

| Metric | Value |
|--------|-------|
| Total nodes | 2,432 |
| By subject | Maths: 958, Chemistry: 815, Physics: 659 |
| By content_type | concept: 867, worked_example: 917, formula: 431, definition: 151, theorem: 66 |
| Nodes with figures | 571 (23.5%) |
| Nodes with solved examples | 923 (38.0%) |
| Nodes with key_formulas | 942 (38.7%) |
| Avg nodes/chapter | 32.9 |
| Range | 12 (Motion in a Straight Line) to 81 (Hydrocarbons) |

---

## 2. Gap Analysis: What the Index Does NOT Capture

### Gap 1: Reference Data Tables

**Severity: HIGH for JEE question solving**

NCERT chapters contain structured reference data that questions directly depend on:

- **Standard Reduction Potentials** (Electrochemistry, Table 2.1) — ~30 half-cell reactions with E values
- **Ionic Conductivities at Infinite Dilution** (Electrochemistry, Table 2.2) — values for ~20 ions
- **Bond Enthalpies** (Chemical Bonding, Table 4.5) — values for ~30 bond types
- **Atomic/Ionic Radii** (Periodicity, Table 3.6) — values for all main-group elements
- **Physical Constants** (Physics, scattered) — g, c, h, k_B, N_A, etc.
- **Thermodynamic Data Tables** (Chemistry Thermo, Table 5.x) — standard enthalpies of formation
- **Dielectric Constants** (Capacitance) — values for common materials

**Current situation:** These tables are not captured as nodes. The extraction prompt says "transcribed to Markdown, not cropped" for Stage 1 (question extraction), but the ConceptIndex extraction prompt has no guidance for handling data tables. The model either absorbs table values into the embedding_text of a parent concept (lossy) or ignores them entirely.

**Evidence:** The Electrochemistry chapter (29 nodes) has no node for standard electrode potential data. The "Measurement of Electrode Potential" concept node mentions SHE in embedding_text but does not contain the actual E values that students need to solve Nernst equation problems. When a JEE question asks "Calculate the EMF of a cell with Zn|Zn2+ and Cu|Cu2+", the model needs E(Zn2+/Zn) = -0.76V and E(Cu2+/Cu) = +0.34V — these values are not in any node.

---

### Gap 2: Missing Content Type — `data_table`

**Severity: HIGH**

The current 5 content types (`concept`, `definition`, `theorem`, `formula`, `worked_example`) do not have a type for structured reference data. A `data_table` content type would allow:

1. **Differentiated retrieval** — when a query involves numeric lookup, boost `data_table` nodes
2. **Structured storage** — the `description` field could hold a Markdown table or JSON structure
3. **Targeted embedding** — embedding_text for a data table can list all entries verbally for broad semantic matching

Examples of what would be `data_table` nodes:
- Standard electrode potentials (E values for half-cells)
- Bond dissociation enthalpies
- Ionization energies and electron affinities
- Standard enthalpies of formation
- Dielectric constants of materials
- Wavelengths/frequencies of electromagnetic spectrum bands

---

### Gap 3: Missing Content Type — `law` / `principle`

**Severity: MEDIUM**

Physical laws (Newton's Laws, Faraday's Laws, Kirchhoff's Laws) and chemical principles (Le Chatelier's Principle, Aufbau Principle) are currently split between `theorem` and `concept` with no consistent rule. The extraction prompt says "Lemmas, corollaries, and axioms should use content_type theorem" — but fundamental laws like F = ma are tagged as `formula` while Zeroth Law of Thermodynamics is `theorem`.

This inconsistency matters for retrieval: a JEE question asking about "application of Lenz's law" should preferentially retrieve the law node, not a formula node for EMF that happens to mention Lenz's law.

---

### Gap 4: No Cross-Chapter Concept Linking

**Severity: HIGH for multi-concept JEE problems**

JEE questions frequently require concepts from multiple chapters and sometimes multiple subjects:
- An Electrochemistry problem may need Thermodynamics (Gibbs energy) + Chemical Kinetics (rate constant)
- A Rotational Mechanics problem needs Linear Mechanics (Newton's laws) + Calculus (integration)
- An Organic Chemistry mechanism question needs Bonding (hybridization) + General Organic (inductive/mesomeric effects) + specific reaction chapter

**Current situation:** Each node is isolated within its chapter. There is no link between "Gibbs Energy" in Chemistry Thermodynamics and "Gibbs Energy" in Electrochemistry, even though they are the same concept applied in different contexts. The hybrid search can only query within one chapter at a time (the documented query pattern includes `AND nch.chapter_id = X`).

**What's needed:** A mechanism to identify and link semantically equivalent or prerequisite concepts across chapters. This could be:
- A `concept_links` junction table (concept_id_a, concept_id_b, link_type: 'equivalent' | 'prerequisite' | 'extends')
- Or simply removing the chapter_id filter from cross-chapter searches (requires testing retrieval quality)

---

### Gap 5: Embedding Text Quality Inconsistencies

**Severity: MEDIUM**

The embedding is built from a composite of 5 fields:
```
Subject: {subject}
Chapter: {chapter_title}
Concept: {concept_title}
Description: {description}
Semantic description: {embedding_text}
Solved example: {ncert_solved_example}
```

Issues observed:
1. **Redundancy:** For worked_example nodes, embedding_text often paraphrases the ncert_solved_example. Both get embedded, inflating the vector with duplicate signal.
2. **Missing discriminative terms:** For formula nodes, the embedding_text describes the formula verbally but often omits the physical scenario where it applies. E.g., "Nernst equation relates electrode potential to concentration" — this embeds well for "Nernst equation" queries but poorly for "calculate EMF of a zinc-copper cell" queries.
3. **No query-side awareness:** Embedding uses `RETRIEVAL_DOCUMENT` task type. The retrieval query should use `RETRIEVAL_QUERY` task type for asymmetric search. If this isn't done at query time, the cosine scores will be sub-optimal (text-embedding-004 is trained for asymmetric retrieval with distinct task types).

---

### Gap 6: Chunk Text Only Indexes `chunk_text` for BM25

**Severity: MEDIUM**

The trigger `fn_ncert_concept_tsv` builds the tsvector from `chunk_text` alone:
```sql
NEW.tsv_content := to_tsvector('english', COALESCE(NEW.chunk_text, ''));
```

But `chunk_text` is a 2–4 sentence summary — it deliberately omits detailed formula names, specific chemical compound names, and worked example specifics. A BM25 query for "Kohlrausch law potassium chloride molar conductivity" might miss the Kohlrausch node if `chunk_text` only says "limiting molar conductivity can be decomposed into ionic contributions."

**Improvement:** The tsvector should be built from a concatenation of `concept_title`, `chunk_text`, `description`, and `embedding_text`. This gives BM25 a much richer lexical surface.

---

### Gap 7: No Stored Embed Text for Audit/Re-embedding

**Severity: LOW (operational)**

The composite text that was embedded is computed at pipeline time and never stored. Only the 768-dim vector is persisted. If the embedding model changes (e.g., text-embedding-005 or a fine-tuned model), there is no way to re-embed without re-running extraction.

---

## 3. Retrieval Design: Current vs Required

### Current (Reference Only — Not Implemented)

```sql
SELECT nch.chunk_text,
  0.7 * (1 - (nce.embedding <=> query_vec::vector)) +
  0.3 * ts_rank(nch.tsv_content, plainto_tsquery('english', 'query'))
  AS combined_score
FROM ncert_concept_hierarchy nch
JOIN ncert_concept_embeddings nce ON nce.concept_id = nch.id
WHERE nch.class = 11 AND nch.subject = 'physics'
  AND nch.chapter_id = X
ORDER BY combined_score DESC LIMIT 5;
```

**Limitations for multi-concept retrieval:**

| Limitation | Impact |
|-----------|--------|
| Single chapter_id filter | Cannot retrieve concepts from multiple chapters |
| Fixed 70/30 weighting | No way to boost formula vs concept vs worked_example |
| LIMIT 5 | May miss the 6th concept needed for a 3-concept synthesis problem |
| No content_type filtering | Retrieves definitions when you need formulas, or vice versa |
| `plainto_tsquery` only | No phrase matching, no proximity, no prefix search |
| No re-ranking | Single-pass scoring — no cross-encoder or LLM rerank step |
| No parent/child expansion | Retrieves a leaf node but not its parent context |

### What Multi-Concept JEE Retrieval Requires

A JEE question like:

> *"A galvanic cell has E_cell = 1.1V. Calculate the equilibrium constant at 298K."*

Requires retrieving:
1. **Nernst Equation** (Electrochemistry) — the formula
2. **Equilibrium Constant from Nernst Equation** (Electrochemistry) — the derived relationship
3. **Gibbs Energy and Spontaneity** (Chemistry Thermodynamics) — for ΔG = -nFE
4. **Standard electrode potential values** (Electrochemistry) — the actual E values *(currently missing)*

This is a 2-chapter, 4-node retrieval across Chemistry Electrochemistry and Chemistry Thermodynamics. The current design cannot do this.

---

## 4. Proposed Improvements

### Improvement 1: Add `data_table` Content Type

**Schema change:**
```sql
ALTER TABLE ncert_concept_hierarchy
DROP CONSTRAINT IF EXISTS ncert_concept_hierarchy_content_type_check;

ALTER TABLE ncert_concept_hierarchy
ADD CONSTRAINT ncert_concept_hierarchy_content_type_check
CHECK (content_type IN ('definition', 'theorem', 'formula', 'worked_example', 'concept', 'data_table'));
```

**Extraction prompt addition:**
```
- Data Tables: When the chapter contains a reference data table (standard electrode potentials,
  bond enthalpies, ionization energies, dielectric constants, physical constants, etc.),
  create a node with content_type: data_table. Place the full table data in description
  as a Markdown table. In embedding_text, list ALL entries verbally so they are
  semantically searchable. In key_formulas, place any formula used to derive table values.
  Example: "Standard reduction potential of zinc ion zinc is negative zero point seven six
  volts, copper two plus copper is positive zero point three four volts..." etc.
```

**Impact:** Enables targeted retrieval of numeric reference data. A search for "EMF zinc copper cell" would now match the data_table node containing E values.

**Re-extraction scope:** Only chapters with significant reference tables need re-extraction. Estimated: ~15 chapters (Electrochemistry, Thermodynamics, Periodicity, Chemical Bonding, Electromagnetic Spectrum, Capacitance, Semiconductors, etc.)

---

### Improvement 2: Enrich the tsvector Source

**Schema change (trigger function):**
```sql
CREATE OR REPLACE FUNCTION fn_ncert_concept_tsv()
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_content := to_tsvector('english',
        COALESCE(NEW.concept_title, '') || ' ' ||
        COALESCE(NEW.chunk_text, '')    || ' ' ||
        COALESCE(NEW.description, '')   || ' ' ||
        COALESCE(NEW.embedding_text, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**Impact:** BM25 component now matches against concept titles, descriptions, and embedding text — not just the 2-sentence chunk summary. A query for "Kohlrausch law limiting molar conductivity potassium chloride" now has a much higher chance of matching.

**Migration:** Run `UPDATE ncert_concept_hierarchy SET chunk_text = chunk_text` to trigger re-computation for all rows.

---

### Improvement 3: Multi-Chapter Hybrid Search

The retrieval function should support cross-chapter search with optional chapter scoping:

```sql
-- Cross-chapter search (subject-scoped)
SELECT nch.id, nch.concept_title, nch.chunk_text, nch.content_type,
       nch.chapter_id, nch.path, nch.key_formulas,
  0.7 * (1 - (nce.embedding <=> $1::vector)) +
  0.3 * ts_rank(nch.tsv_content, websearch_to_tsquery('english', $2))
  AS combined_score
FROM ncert_concept_hierarchy nch
JOIN ncert_concept_embeddings nce ON nce.concept_id = nch.id
WHERE nch.class = $3
  AND nch.subject = ANY($4)            -- array of subjects, not single value
  -- chapter_id filter is OPTIONAL:
  AND ($5::int[] IS NULL OR nch.chapter_id = ANY($5))
ORDER BY combined_score DESC
LIMIT $6;
```

Key changes from the reference pattern:
- `subject = ANY($4)` — allows cross-subject search (Physics + Maths for mechanics problems)
- `chapter_id = ANY($5)` — optional array filter; NULL means search all chapters in subject
- `websearch_to_tsquery` instead of `plainto_tsquery` — supports quoted phrases and boolean operators
- Parameterized LIMIT — caller decides how many results

---

### Improvement 4: Content-Type Boosting

Different retrieval scenarios need different content types. A formula-lookup query should boost `formula` + `data_table` nodes. A conceptual-understanding query should boost `concept` + `definition` nodes.

```sql
-- Add a content_type boost factor
SELECT ...,
  (0.7 * (1 - (nce.embedding <=> $1::vector)) +
   0.3 * ts_rank(nch.tsv_content, websearch_to_tsquery('english', $2)))
  * CASE nch.content_type
      WHEN 'formula'        THEN $7  -- e.g., 1.2 for formula-heavy queries
      WHEN 'data_table'     THEN $8  -- e.g., 1.5 for data-lookup queries
      WHEN 'worked_example' THEN $9  -- e.g., 1.3 for "how to solve" queries
      ELSE 1.0
    END
  AS boosted_score
...
ORDER BY boosted_score DESC
```

The caller (M3 tagger, M4 solver, etc.) decides the boost profile based on query intent.

---

### Improvement 5: Parent Context Expansion

When a leaf node is retrieved, its parent and grandparent provide essential framing context. Example: retrieving "Isothermal Process" (formula) without its parent "Thermodynamic Processes" (concept) loses the classification context.

**Post-retrieval expansion (application-side logic, not SQL):**
```
For each retrieved node:
  1. Walk up the ltree path to root
  2. Include parent node's description if not already in result set
  3. Deduplicate by concept_id
```

This is lightweight because the ltree path is already stored and ancestor queries are fast:
```sql
SELECT * FROM ncert_concept_hierarchy
WHERE id IN (
  SELECT parent_id FROM ncert_concept_hierarchy WHERE id = ANY($retrieved_ids)
);
```

---

### Improvement 6: Two-Stage Retrieval (Retrieve + Rerank)

For high-stakes retrieval (M3 question tagging), a single-pass hybrid score may not be sufficient. A two-stage approach:

1. **Stage 1 — Broad recall:** Run the hybrid query with a generous LIMIT (e.g., 20–30 nodes)
2. **Stage 2 — LLM rerank:** Send the top-N chunks + the original question to a lightweight model (Gemini Flash or a cross-encoder) and ask it to rank by relevance

This is especially important for multi-concept problems where the 5th-most-similar chunk might be the most critical one for solving the problem.

**Trade-off:** Adds latency and cost. Should be optional (configurable) — use single-pass for batch indexing, two-stage for student-facing retrieval.

---

### Improvement 7: Store Composite Embed Text

**Schema change:**
```sql
ALTER TABLE ncert_concept_embeddings ADD COLUMN IF NOT EXISTS embed_text TEXT;
```

Store the composite text that was actually embedded. Enables:
- Re-embedding with a new model without re-extraction
- Debugging retrieval misses (inspect what the vector actually represents)
- Computing embedding drift if the model changes

---

## 5. Priority Matrix

| # | Improvement | Effort | Impact | Priority |
|---|-----------|--------|--------|----------|
| 1 | Add `data_table` content type + re-extract ~15 chapters | Medium | High | **P0** — blocks accurate JEE question solving |
| 2 | Enrich tsvector source (trigger change + backfill) | Low | Medium | **P0** — one SQL migration, immediate BM25 quality boost |
| 3 | Multi-chapter hybrid search query | Low | High | **P0** — required for M3 cross-chapter tagging |
| 4 | Content-type boosting in search | Low | Medium | **P1** — parameterized scoring, caller-side flexibility |
| 5 | Parent context expansion | Low | Medium | **P1** — application-side logic, no schema change |
| 6 | Two-stage retrieve + rerank | Medium | High | **P1** — important for accuracy, not blocking |
| 7 | Store embed_text column | Low | Low | **P2** — operational convenience |

---

## 6. Answering the Four Questions

### Q1: Investigate the vector/BM25 index closely

**Finding:** The index infrastructure is sound — HNSW for vector, GIN for BM25, ltree for hierarchy. The schema supports hybrid search. However, **no retrieval function exists in code** — only a SQL comment. The 70/30 weighting is untested. The BM25 component is under-powered because it only indexes the 2–4 sentence `chunk_text`, missing concept titles, descriptions, and embedding text. The HNSW index has no tuning parameters specified (uses pgvector defaults: `m=16, ef_construction=64`), which may need adjustment as the corpus grows beyond NCERT to include JEE-specific content.

### Q2: How can search be improved for multi-concept retrieval?

**Finding:** Three changes are essential:

1. **Remove the single-chapter constraint.** The documented query pattern hard-codes `chapter_id = X`. Multi-concept JEE problems span 2–4 chapters. The search must support subject-scoped or fully open search across the corpus.

2. **Increase recall before precision.** LIMIT 5 is too aggressive for multi-concept problems. Retrieve 15–20 candidates, then rerank (either by score threshold or LLM reranker) to select the final 5–8.

3. **Content-type-aware boosting.** A numeric problem needs `formula` + `data_table` nodes. A conceptual problem needs `definition` + `concept` nodes. The scoring function should accept boost weights from the caller.

### Q3: What are the gaps with the existing index design?

**Finding:** The biggest gap is **missing content coverage**, not architecture:

1. **No `data_table` content type.** Reference data (electrode potentials, bond enthalpies, physical constants) is not captured as discrete, retrievable nodes. This makes the index useless for any problem requiring a numeric lookup from the textbook.

2. **Under-powered BM25.** The tsvector is built from `chunk_text` only — a 2–4 sentence summary. It should include `concept_title`, `description`, and `embedding_text` for richer lexical matching.

3. **No cross-chapter linking.** Identical concepts appearing in different chapters (Gibbs energy in Thermodynamics vs Electrochemistry) are isolated nodes with no link between them.

4. **Figures are text-only.** 571 nodes (23.5%) have `has_figure = true` but `figure_url = NULL`. For geometry, circuit diagrams, and organic structures, the textual description in embedding_text is a lossy proxy.

The 5-type content classification and the embedding model choice (text-embedding-004, 768-dim) are adequate. The embedding composite text construction is reasonable. These do not need fundamental redesign — the improvements are additive (new content type, richer tsvector, cross-chapter search).

### Q4: Does this design capture all types of concepts?

**Finding: NO.** Specifically:

| Content Category | Captured? | Notes |
|-----------------|-----------|-------|
| Definitions | Yes | 151 nodes |
| Theorems / Laws | Partially | 66 nodes; physical laws inconsistently tagged as `formula` or `theorem` |
| Formulas | Yes | 431 nodes |
| Worked Examples | Yes | 917 nodes — well covered |
| Conceptual Explanations | Yes | 867 nodes |
| **Data/Reference Tables** | **NO** | Standard potentials, bond enthalpies, physical constants — not extracted |
| **Numerical Constants** | **NO** | g = 9.8 m/s2, h = 6.626e-34 J.s, etc. — not discrete nodes |
| **Comparative Data** | **NO** | Trends in periodic properties (which element is larger) — embedded in concept text but not structured |
| **Reaction Mechanisms (step-by-step)** | **Partially** | Organic reactions are formula nodes; multi-step mechanisms may not have each step as a node |
| **Diagrams/Figures** | **Text-only** | 571 flagged but no actual image content stored |

The most impactful gap for JEE is the missing data tables. The second is the incomplete figure handling. Both are addressable without redesigning the core schema.

---

## 7. Architectural Framing: Taxonomy vs Search Engine

A critical design question: **is vector retrieval the right abstraction for this index?**

The answer depends on the downstream consumer. The concept index serves two distinct roles, and conflating them leads to over-investment in retrieval infrastructure.

### Role 1: Structured Taxonomy (primary value)

The most valuable thing the concept index provides is a **controlled vocabulary of verified concept nodes** — each with a stable DB ID, a position in a chapter hierarchy, typed content, and associated formulas. This is a taxonomy. Its value is:

- **Tagging:** Assigning NCERT concept IDs to JEE questions (M3)
- **Linking:** Connecting student performance to specific concepts (M6/M7 frontend)
- **UI rendering:** Showing concept trees, formula cards, prerequisite chains

For these use cases, the retrieval method (vector, BM25, or LLM-guided) is an implementation detail. The index's value is that the nodes exist and have stable identities.

### Role 2: Context Retrieval (secondary, use-case-dependent)

For some use cases, the index is a source of grounding context — retrieve relevant chunks and feed them to a model. This is where vector + BM25 hybrid search applies. But as analyzed in the Solution Feedback feasibility study, this role is often unnecessary:

- **NCERT evaluation (Scenario A):** `questiondata` already has the extracted question + solution. No retrieval needed.
- **Non-NCERT evaluation (Scenario B):** Concept retrieval is useful but requires the P0 improvements (data_table, multi-chapter search).
- **Extraction pipeline solver:** Content caching makes retrieval gains negligible (see prior analysis).

### Implication: Don't over-invest in retrieval before downstream modules clarify query patterns

The retrieval infrastructure (HNSW index, BM25 trigger, hybrid scoring) is already built and costs nothing to maintain. The P0 improvements (enriched tsvector, multi-chapter query, data_table type) are low-effort and worth doing. But complex additions like cross-encoder reranking or retrieval fine-tuning should wait until a specific module demonstrates that pure retrieval is insufficient.

---

## 8. M3 Architecture Recommendation: LLM-Driven Tagging with Index as Vocabulary

M3 (JEE Question Tagger) is the first major consumer of this index. The architectural choice here sets the pattern for downstream modules.

### Why pure retrieval is insufficient for M3

M3's task: given a JEE question, identify which NCERT concepts it tests. This is a **reasoning task**, not a similarity-search task.

Consider: *"A galvanic cell has E_cell = 1.1V. Calculate the equilibrium constant at 298K."*

Vector retrieval against the question text will surface "Nernst Equation" and "Galvanic Cells" — the obvious matches. But the question also requires "Gibbs Energy and Spontaneity" (from a different chapter) and the relationship `ΔG = -nFE = -RT ln K`. An LLM can reason about this chain; a vector similarity score cannot.

### Recommended pattern: LLM tags against index vocabulary

```
Input:  JEE question text + subject
Step 1: Load all concept nodes for the relevant subject(s) as a vocabulary list
        (concept_id, concept_title, content_type, chapter_title, key_formulas — lightweight)
Step 2: Ask LLM: "Which of these NCERT concepts does this JEE question test?
        Return concept_ids with relevance scores."
Step 3: Store the tagged concept_ids in jee_question_tags
```

**Why this works:**
- The LLM already knows NCERT Physics/Chemistry/Maths from training data — it can reason about concept dependencies
- The index provides a **constrained output vocabulary** — the LLM cannot hallucinate concept names that don't exist in the DB
- Cross-chapter reasoning happens naturally (the LLM sees concepts from all chapters in the vocabulary list)
- No vector retrieval needed — the LLM does the matching directly

**Why not pure retrieval:**
- Vector search finds semantically similar nodes but cannot reason about multi-step concept chains
- BM25 matches keywords but misses implicit prerequisites (a question about "equilibrium constant" doesn't contain the word "Gibbs")
- A retrieval miss silently omits a critical concept tag; an LLM can be prompted to think about prerequisites explicitly

**Corpus size is manageable:**
- Physics: 659 nodes → ~15K tokens as a vocabulary list (concept_title + content_type + chapter_title)
- Chemistry: 815 nodes → ~18K tokens
- Maths: 958 nodes → ~22K tokens
- All fit comfortably within Gemini's context window in a single call

**Hybrid option (if vocabulary list is too long):**
- Use vector retrieval as a pre-filter: retrieve top-30 candidate nodes
- Then ask the LLM to select + add any missing prerequisites from the full vocabulary
- This reduces context size while preserving reasoning quality

### Where vector search still adds value for M3

- **Bulk pre-filtering:** If tagging thousands of JEE questions, a first-pass vector similarity can narrow candidates before the LLM call, reducing cost
- **Confidence scoring:** The cosine similarity score provides a numeric confidence signal that complements the LLM's binary tag decision
- **Fallback:** If the LLM tags a concept that's borderline, the vector score helps decide whether to keep it

The index infrastructure (HNSW, BM25) is not wasted — it's a useful optimization layer. But it is not the primary tagging mechanism.

---

## 9. Recommended Next Steps

1. **Immediate (before M3):**
   - Update the tsvector trigger to include all text fields (Improvement 2) — low effort, immediate BM25 quality boost
   - Add `data_table` to the content_type CHECK constraint (Improvement 1 — schema part)
   - Build the multi-chapter search query as a reusable SQL function or Python utility (Improvement 3) — needed for both retrieval and as a fallback/scoring layer for M3

2. **During M3 development:**
   - Implement M3 as **LLM-driven tagging with index as constrained vocabulary** (Section 8) — the LLM reasons about concept dependencies; the index provides valid concept_ids
   - Use vector search as an optional pre-filter or confidence signal, not the primary tagging mechanism
   - Re-extract the ~15 chapters with significant data tables using an updated prompt
   - Validate tagging quality on a held-out set of JEE questions before batch run

3. **Post-M3 (before student-facing features):**
   - Implement content-type boosting in the search function for modules that do use retrieval (e.g., Solution Feedback Scenario B)
   - Populate figure_url for nodes where visual context is critical
   - Add embed_text column for operational auditability
   - Evaluate whether retrieval-based or LLM-based concept lookup works better for real-time student features (hint generation, concept cards) — let the use case decide the pattern
