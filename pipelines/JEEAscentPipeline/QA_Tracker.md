# JEE Ascent — QA Issue Tracker

> Started: 2026-04-17
> Purpose: Track issues surfaced by frontend smoke-testing of M8 (AccentSession). Fix one category at a time.

## 2026-05-25 — KI-4: Tutor Socratic regression on harder rows [PRIORITY: HIGH]

Surfaced during M3 Phase A Pro-Assembly holdout run (`pipelines/ModelEngineering/runs/Experiment_Run_20260523_231104.md`, N=100). Pro 3-pass Assembly Line scored 4.63 average Pedagogy — driven by ~14 rows where the judge issued the same verbatim complaint:

> *"the `nudge_hint` fields are direct statements / instructions / give away the next step, rather than Socratic guiding questions"*

Same failure mode as Phase 1 "Pedagogical Leakage" (Variants A/B/C). The Assembly Line was supposed to fix it; Variants E/F validated at N=10/25. N=100 was the first sample large enough to expose the regression on harder rows.

**Evidence — pattern is universal, NOT figure-related:**

| Bucket | N | AvgPed | Ped<4 |
|---|---|---|---|
| NCERT figure-bearing (image inlined ✓) | 10 | **4.00** | 4/10 |
| JEE figure-bearing (image NULL — KI-3) | 13 | 4.38 | 3/13 |
| NCERT non-figure | 40 | 4.80 | 1/40 |
| JEE non-figure | 37 | 4.70 | 4/37 |

NCERT figure-bearing scored WORSE on Pedagogy than JEE figure-bearing despite having images inlined to the solver. Disproves the figure-handicap hypothesis as the dominant cause.

**Affected sample rows (judge verdicts archived in `Experiment_Run_20260523_231104_RAW.json`):**
- NCERT Physics: 680, 721, 811, 780, 1131
- JEE: 953, 2516, 3568, 2216, 3332, 1036, 2420, 3455, 3395, 1730 (across all subjects)

**Sibling sub-bug (single row, same family):** id=3565 JEE Physics — nudge_hints systematically shifted by one step (Step 1 hint asks about Step 2's content, etc.). Pedagogy=2. Same root: Tutor positional discipline lapsing on hard rows.

**Why HIGH priority:** propagates to every newly generated solution from the Pro Assembly Line. The Gold Set is unaffected (strict 5/5/5 filter excluded all regression examples). But any hybrid-ship M3 path (Tuned Flash + Pro pedagogy post-pass) leaks the regression into production. Must land BEFORE any hybrid M3 ship.

**Likely root cause:** Tutor stage prompt doesn't enforce "MUST be a question, MUST NOT start with an imperative verb." Direct-instruction hints are easier to generate than Socratic ones — on harder rows, the model takes the easier path.

**Fix scope:**
1. Update `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/solver_engine.py::_stage_2_socratic_tutor` system prompt — add a hard rule + 2–3 negative examples ("Calculate X" → "What quantity does the formula give you here?"). Consider adding a self-check pass that rejects hints starting with imperative verbs or containing the numerical answer.
2. Re-run the 14 failing rows in `--dry-run` to verify the prompt fix recovers them.
3. Gold Set is unaffected (5/5/5 filter); no retroactive fix needed for `APPROVED_GOLD`.

**Status: OPEN — schedule for next sprint after Phase A closes.**

## 2026-05-25 — KI-5: Formatter LaTeX backslash escape regression [PRIORITY: HIGH]

Same holdout run. 2/100 rows had LaTeX commands written with single backslashes that JSON-escape into control characters at parse time:

- **id=721** NCERT Physics (Ped=3, **Fmt=3**): `\frac` → formfeed `\f`, `\text` → tab `\t`. Judge: *"backslashes are not properly escaped in LaTeX commands like '\frac' (which parses as a formfeed '\f') and '\text' (which parses as a tab '\t'), which will break the math rendering."*
- **id=953** JEE Maths (Ped=3, **Fmt=4**): `\frac{k(k+1)}{2}` rendered as `\le rac{k(k + 1)}{2}` — the `\f` from `\frac` was eaten as formfeed, leaving `le rac` as visible garbage.

Same problem class as Phase 1 "JSON Serialisation Errors". Formatter is supposed to double-escape these (`\\frac`) but isn't catching all `\f`/`\t`/`\n`/`\b` collision triplets (`\frac`/`\text`/`\nu`/`\beta`).

**Why HIGH priority:** if M3 ships hybrid-path (b) with a Pro post-format pass, every output runs through the broken formatter. Frontend renders garbage on affected rows. If M3 ships single-call (a) — Tuned Flash only, no post-format pass — KI-5 becomes moot for production output, but the legacy Pro pipeline still carries the bug for ongoing bulk NCERT/JEE runs until Tuned Flash fully takes over.

**Fix scope:** audit `solver_engine.py::_stage_3_json_formatter` prompt. Add explicit rule: *"When emitting LaTeX inside JSON, double-escape ALL backslashes (`\\frac`, `\\text`, `\\nu`, etc.). Single-backslash LaTeX is a JSON parsing bug."* Add a post-parse validation that detects formfeed/tab/null bytes inside `latex_formula` fields and either auto-repairs or fails loud.

**Status: OPEN — schedule alongside KI-4.**

## 2026-05-30 — KI-6: Corrupt MCQ answer keys in 2024 set (raw correct_option_id left in answer_key)

Surfaced during the M3 measurement sprint (`pipelines/ModelEngineering/dump_failures.py` over
the Phase V untuned-3-flash verify results). Several "solver misses" had a 9–12 digit number in
`answer_key` (e.g. `878270220533`, `68019157009`) instead of a letter — these are **NTA
correct_option_ids left unmapped**, not real answers.

**Scope (full-corpus scan):** **89 / 1491 (6.0%)** of non-null `jee_question_bank.answer_key`
rows are corrupt — ALL year 2024, ALL `section='MCQ'`. By subject: **Maths 38/502 (7.6%)**,
Chemistry 26/490 (5.3%), Physics 25/499 (5.0%). 2024 was previously believed clean — we tracked
AK *coverage* (99.1%), not *correctness*.

**Root cause:** per the extraction design (`JEEAscentPipeline/CLAUDE.md`), `answer_key` should
store the letter A/B/C/D (option array index 0–3). For these 89 rows the extractor left the raw
`correct_option_id` instead of mapping it to a letter.

**Recoverability:** NOT recoverable via SQL. The corrupt rows' `question_content.options[]` carry
`nta_option_id: null` (the per-question option-id ordering was never persisted), so the
correct_option_id → letter mapping is lost. `jee_answer_mappings` has all 89 nta_question_ids
(→ correct_option_id) but that's the same id we already have — still no letter. **Fix = re-extract
the affected papers** (crop pipeline repopulates option nta_option_ids, then remap), foldable into
the KI-2 re-extraction batch.

**Impact / interim handling:**
- All prior eval numbers (Phase V, holdout, verify sets) are deflated — every corrupt row scores
  as a miss even when the model is right. Re-scored clean: untuned-3-flash JEE non-fig **88.9% →
  94.7%**.
- M3 Tier-1 answer-key gate MUST validate key sanity (drop `^\d{9,}$`), apply numeric tolerance,
  resolve MCQ letter↔value — else it false-routes ~6% of correct rows to Pro.
- Program B rejection-sampling harvester would wrongly reject ~6% of good CoTs — clean keys first.
- Frozen sets affected: `holdout_eval_set.json` 3 corrupt rows; `solver_verifyset_jee.json` 7.
- Shared comparator: `pipelines/ModelEngineering/answer_match.py`. Findings:
  `pipelines/ModelEngineering/runs/_ANSWERKEY_DATAQUALITY_FINDING.md`.

**Status: OPEN — proper fix (re-extract 89 rows) deferred alongside KI-2; interim exclude +
key-validate in M3 sprint.**

## 2026-05-23 — KI-3: JEE figure-URL extraction gap (figure_url universally NULL)

Surfaced while building the M3 holdout (`pipelines/ModelEngineering/build_holdout_set.py`).
Initial detection used `figure_url` presence and returned **zero** figure-bearing JEE
rows across all 50 sampled (Maths/Physics/Chemistry × all `review_status` tiers).
A full-table survey confirmed the scope:

| review_status | subject | total | with figure_url | with has_figure=true | with option_figure_urls |
|---|---|---:|---:|---:|---:|
| APPROVED | Chemistry | 1 | 0 | 0 | 0 |
| APPROVED | Mathematics | 3 | 0 | 0 | 0 |
| APPROVED | Physics | 8 | 0 | 2 | 0 |
| APPROVED_GOLD | Chemistry | 29 | 0 | 4 | 0 |
| APPROVED_GOLD | Mathematics | 37 | 0 | 0 | 0 |
| APPROVED_GOLD | Physics | 36 | 0 | 5 | 0 |
| PENDING | Chemistry | 460 | 0 | 89 | 0 |
| PENDING | Mathematics | 462 | 0 | 1 | 0 |
| PENDING | Physics | 450 | 0 | 80 | 0 |
| UNVERIFIED | Physics | 5 | 0 | 0 | 0 |

**Findings:**
- `figure_url` is **NULL on every single row** of `jee_question_bank` (1,491 rows surveyed).
- `has_figure` is populated correctly — ~18% of PENDING Physics (80/450) and ~19% of PENDING Chemistry (89/460) are flagged as figure-dependent.
- `option_figure_urls` is empty everywhere — no per-option figures captured either.
- Even APPROVED_GOLD rows (used to build the 102 JEE training examples) have NULL figure_url despite 9 of them having `has_figure=true` — meaning the model was trained text-only on figure-dependent questions.

**Root cause:** `jee_paper_extractor.py` (Pro pipeline) and `jee_crop_pipeline.py` extract `has_figure` as a boolean classification but never crop or upload the actual figure image. The schema field exists; only the extractor step is missing. Noted as "Phase 2 enhancement" in `CLAUDE.md` (`question_content` JSONB schema section).

**Impact:**
- **Today's production:** Pro receives text like "In the given figure $R_1 = 10\Omega$…" without the figure for ~170 questions. Quality on those is degraded.
- **M3 baselines:** all three runs (Pro, untuned Flash, tuned Flash) inherit the same no-image handicap on JEE — comparison stays fair, but figure-dependent JEE Acc-routable % will be lower than non-figure across the board.
- **M3 holdout (fixed 2026-05-23):** now detects `has_figure` via flag; records also carry `image_urls_present` so the figure-dependent / image-inlined split is downstream-analyzable.
- **Training data:** 9 APPROVED_GOLD JEE rows that the model learned from are figure-dependent but were exported text-only by `jsonl_exporter.build_user_payload()`. Tuned Flash will mirror this limitation.

**Fix scope:** extend `jee_paper_extractor.py` / `jee_crop_pipeline.py` to crop figure regions during extraction, upload to blob storage (reuse `pipelines/.../blob_client.py`), and populate `question_content.figure_url`. Re-run extraction on the ~170 figure-bearing rows. Could be folded into the 2023 re-extraction batch (KI-2) so both pipelines pick up the figure-crop step at once. Not blocking M3.

**Status: OPEN — deferred to post-M3 (or alongside KI-2 re-extraction).**

## 2026-04-17 — Round 1 complete: Dedup

Root cause found for most of category A: `jee_question_bank` had 1,564 duplicate rows
(3,084 rows for 1,520 unique 2024 questions). Duplicates had conflicting subjects,
causing frontend to show wrong-subject variants under wrong chapters.

Fixes applied:
- **Dedup script** (`dedup_jee_question_bank.py`) removed 1,564 loser rows; kept the
  row whose tags had the highest max `similarity_score` in its group.
- **Unique constraint** `uq_jee_qbank_paper_nta UNIQUE (exam_paper_id, nta_question_id)`
  added to `jee_question_bank`.
- **`db_writer.bulk_insert_questions`** now uses `ON CONFLICT ON CONSTRAINT
  uq_jee_qbank_paper_nta DO NOTHING` (was a no-op before).
- **`jee_crop_pipeline.py`** now calls `questions_exist_for_paper()` before
  `bulk_insert_questions`, matching the Pro pipeline.
- Migration file `Scripts/JEEAscent_DB_Migration.sql` updated with the new constraint.

## 2026-04-20 — Round 3: 2023 systemic breakage + MVP decision

Frontend re-check of Kinetic Theory chapter (A9/A10) surfaced three things:

1. **A9/A10 cleared** — Kinetic Theory now shows 21 Physics questions (24 in DB, frontend `similarity_score >= 0.85` filter hides 3), no Maths/Chem cross-listings visible. **FIXED.**
2. **New bug (originally thought isolated):** id=4024 had PDF metadata header (`Question Number : 32 Question Id : 3666943142 Question Type : MCQ ...`) slurped into `raw_text`, with `options: []` and `answer_key: NULL`.
3. **Broader diagnostic revealed 2023 is systemically broken:**

| Symptom | Scope |
|---|---|
| 2023 rows total | 1,080 |
| Rows with `answer_key IS NULL` | **1,080 (100%)** |
| Rows with empty options (`[]`) | ~33 per paper × 12 = **396** |
| Rows matching ANY AK in `jee_answer_mappings` | **0** |
| NTA IDs in question bank | Perfectly sequential (`3666943111, 3666943112, …`) — hallucinated |
| NTA IDs in AK mappings | Different range (`3666941070, 3666941171, …`) — real |

**Root cause:** 2023 Pro-pipeline extraction generated sequential NTA IDs instead of reading real ones from the paper. Question content itself is fine (real JEE LaTeX), but the AK join is 0%, so no answer_keys and no "Check Answer" capability on the frontend.

**Decision (user, 2026-04-20):** Park 2023 wholesale. MVP on 2024 (1,504 tagged rows across all three subjects) is enough to build and demo the full pipeline. Re-extract 2023 post-MVP alongside 2021/2022/2025. Logged as **KI-2** under Known Issues.

## 2026-04-17 — Round 2: Broader scope discovered

After dedup, user re-tested on the frontend and flagged new issues. Diagnostic queries
across the whole corpus found the following, much larger scope:

| Scope item | Count |
|---|---|
| JSON-leak rows (raw_text starts with `{ "raw_text":` or `\begin{json}`) | **216** across 2023+2024 |
| → 2024: 28 Chem, 21 Math, 43 Phys | 92 |
| → 2023: 24 Chem, 28 Math, 72 Phys | 124 |
| Questions tagged to 2+ chapters (**cross-listing**) | **545 / 1,520 (35.8%)** |
| → still cross-listed if threshold `score ≥ 0.85` | 204 (13.4%) |
| 2023 rows labeled Mathematics but with Chemistry content (heuristic) | ≥ 20 |
| Partial-paper subject mismatches (single-row, no duplicate) | e.g. A11 (candela), A8 (fair die) |

## Status Legend
- **OPEN** — not yet investigated
- **TRIAGED** — root cause identified, fix not applied
- **FIXING** — fix in progress
- **FIXED** — verified on frontend

## Summary

| Category | Open | Fixed | Notes |
|---|---|---|---|
| A. Subject Mismatch | **2 known (2024) + all 2023 parked** | 11 | 2024: A8, A11 open; A9/A10 FIXED (verified 2026-04-20). 2023 issues (A12, A13) parked under KI-2. |
| B. Tagging Verification | 0 | 2 | Both original cases fixed by dedup |
| C. Rendering Issues | **2 (2024)** | 1 | C1 malformed LaTeX (id=392) and C2 `\begin{json}` (id=664) OPEN on 2024; C3 (id=711) FIXED by Batch 5 literal-`\_` cleanup; 2023 C-class issues rolled into KI-2 |
| D. Extraction Issues | 0 (2024) | 216 | Batch 1 repaired all 216 JSON-leak rows. 2023 hallucinated-NTA-ID breakage is a separate issue tracked under KI-2. |
| E. Empty Questions | 0 | 1 | Empty-`raw_text` count is 0 post-dedup |
| F. Uncategorised | 0 | 1 | Resolved by dedup |
| **G. Cross-listing** | 0 | 545 | Batch 4 applied `similarity_score >= 0.85` filter in `accentSession.ts` + `accentChapterMap.ts`; dropped cross-listing 626 → 258 |
| **KI-1 Image+text rows** | 10 | — | Parked 2026-04-20. Flash reasoning-leak on dense mixed text+image. Revisit on next-year ingest. |
| **KI-2 2023 systemic** | 1,080 | — | Parked 2026-04-20. Hallucinated NTA IDs → 100% null answer_keys. Full re-extract required. |
| **KI-3 JEE figure_url gap** | 1,491 | — | Parked 2026-05-23. `figure_url` NULL on 100% of JEE rows. Fix alongside KI-2 re-extract. |
| **KI-4 Tutor Socratic regression** | 14 (in N=100 sample) | — | **NEW 2026-05-25 — PRIORITY: HIGH.** Pro Tutor reverts to direct-instruction hints on harder rows. Must fix before any hybrid-ship M3 path. |
| **KI-5 Formatter LaTeX `\f`/`\t` escape** | 2 (in N=100 sample) | — | **NEW 2026-05-25 — PRIORITY: HIGH.** Single-backslash LaTeX collides with JSON escapes. Breaks frontend rendering. Must fix before hybrid-ship. |
| **KI-6 Corrupt 2024 MCQ answer keys** | 89 (6.0% of 1,491) | — | **NEW 2026-05-30.** Raw correct_option_id left in `answer_key` (all 2024 MCQ). Not SQL-recoverable (option ids null) → re-extract affected papers, defer alongside KI-2. Deflated all eval numbers; clean JEE non-fig 88.9%→94.7%. Interim: exclude + key-validate. |

---

## A. Subject Mismatch

Question appears under the wrong subject/chapter on the frontend. Likely root cause: `assign_subject_section()` in `jee_crop_pipeline.py` (position-based rotation) still misclassifying for these papers, or `subject_auditor.py` missed them.

| # | Status | Chapter (as shown) | Q# | Evidence | Expected | Resolution |
|---|--------|--------------------|----|----------|----------|------------|
| A1 | **FIXED** | 11th Maths, Trigonometric Functions | Q14 | silver / electrolysis | Chemistry — Electrochemistry | Dedup kept id=292 (Chemistry, tag score=1.00 on Faraday's Laws) |
| A2 | **FIXED** | 11th Maths, Trigonometric Functions | Q15 | decacarbonyldimanganese | Chemistry — Coordination Compounds | Dedup kept id=459 (Chemistry, Bonding in Metal Carbonyls score=1.00) |
| A3 | **FIXED** | 11th Maths, Trigonometric Functions | Q16 | PF₅/BrF₅ sp³d hybridisation | Chemistry — Chemical Bonding | Dedup kept id=898 (Chemistry, Hybridisation score=1.00) |
| A4 | **FIXED** | 11th Maths, Trigonometric Functions | Q17 | "sp² hybridization pair" | Chemistry — Chemical Bonding | Post-dedup id=1082 is Chemistry |
| A5 | **FIXED** | 11th Maths, Trigonometric Functions | Q19 | (empty card) | Chemistry (from neighbours) | Empty-raw_text count now 0; see E1 |
| A6 | **FIXED** | Maths, Complex Numbers & Quadratic | Q17 | tetrahedral die → ax²+bx+c real roots | Maths — Probability | Dedup kept id=1049 (Mathematics, Probability score=1.00) |
| A7 | **FIXED** | Maths, Complex Numbers & Quadratic | Q22 | Diamagnetic Lanthanoid ions | Chemistry — d and f Block | Dedup kept id=365 (Chemistry, Magnetic Properties score=1.00) |
| A8 | **OPEN** | Physics, Kinetic Theory | Q20 | fair die tossed | Maths — Probability | id=2215 — no correct duplicate existed; has JSON leak too (D category). Needs combined subject-fix + raw_text cleanup. |
| A9 | **PROBABLY FIXED** | Physics, Kinetic Theory | Q21–Q23 | "all Maths" | Maths | Post-dedup, Kinetic Theory chapter has only id=2215 as misclassified. Frontend positions 20–23 likely mapped from id=2215 and surrounding. **Needs user re-check on frontend.** |
| A10 | **PROBABLY FIXED** | Physics, Kinetic Theory | Q25–Q26 | "Chemistry" | Chemistry | Same: likely resolved by dedup cleanup of the chapter. **Needs user re-check.** |
| A11 | **OPEN** | 11th Maths, Trigonometric Functions | Q13 | "The candela is the luminous intensity… source that emits monochromatic radiation of frequency 'A' × 10¹² hertz" | Physics — Units & Measurement | id=3149 — single row, subject=Mathematics, tagged to Trig Functions :: Radian Measure (0.80). Partial-paper subject mismatch with clean raw_text. |
| A12 | **OPEN** | 12 Chem, Electrochemistry (potential) | Q2 | Galvanic cell ½H₂ + AgCl reaction | Chemistry — correct, but in 2023 paper it's wrongly labeled Math | id=3872 (2023-04-08 s1 Q62) subject=Mathematics. Will misroute after 2023 tagging. |
| A13 | **OPEN** | 2023 suspected | various | 20+ rows with Urea/galvanic/hybridisation/lanthanide/osmotic/molarity content labeled `subject=Mathematics` | Chemistry (most) | Sample: ids 3713, 3898, 3983, 4158, 4247, 4255, 4317, 4338, 4509, 4526, 4607, 4610, 4700. Fix BEFORE tagging 2023. |

**Investigation query template (run before fixing):**
```sql
SELECT id, year, dateofexam, shift, subject, question_number,
       LEFT(question_content->>'raw_text', 120) AS preview
FROM jee_question_bank
WHERE year = 2024
  AND question_number IN (14,15,16,17,19) -- adjust per row above
  -- AND dateofexam = 'YYYY-MM-DD' AND shift = '1'  -- narrow by paper if known
ORDER BY dateofexam, shift, question_number;
```

---

## B. Tagging Verification

Concept tags assigned by M3 are missing a clearly relevant concept, or include a wrong one.

| # | Status | Chapter | Q# | Evidence | Resolution |
|---|--------|---------|----|----------|------------|
| B1 | **FIXED** | Maths, Complex Numbers & Quadratic | Q2 | "Let ∫_α^(log_e 4) dx / √(e^x − 1) = π/6. Then e^α and e^−α are the roots" | id=109 is correctly tagged: `Integrals :: Evaluation of Definite Integrals by Substitution` (score 1.00) + Methods of Integration (0.80) + Complex Numbers/Quadratic (0.70). The user saw this under "Complex Numbers" chapter because a wrong duplicate existed — now dedup'd. |
| B2 | **FIXED** | Maths, Complex Numbers & Quadratic | Q17 | Dice probability → ax²+bx+c real roots | id=1049 correctly tagged: `Probability :: Probability` (1.00) + `Probabilities of equally likely outcomes` (0.90) + Quadratic (0.80). Wrong duplicates dedup'd. |

---

## C. Rendering Issues

LaTeX not rendering correctly on frontend. Raw `$…$` delimiters or literal `\frac{}{}` leaking into visible text.

| # | Status | Chapter | Q# | Evidence |
|---|--------|---------|----|----------|
| C1 | OPEN | 11th Maths, Trigonometric Functions | Q3 | id=392. Body reads: `1}{2} \sin \theta - \frac{\sqrt{3}}{2} \cos \theta + \sin \theta (-\frac{1}{2} \sin \theta - \frac{\sqrt{3}}{2} \cos \theta)$ = ... $= -\frac{3}{4} \sin^2 \theta -` — unbalanced `$` delimiters + stray literal braces. Malformed LaTeX stored in `question_content.raw_text`. |
| C2 | OPEN | 11 Maths, Complex Numbers & Quadratic | Q10 | id=664. Body shows literal `\begin{json}` followed by JSON schema keys (`"raw_text":`, `"options": [`). Same extraction failure mode as category D, but inside a Mathematics-subject row. Counted in D total as well. |
| C3 | OPEN | 11 Physics, Waves | Q5 | id=711. Integer-answer blank renders as literal `\_\_\_\_\_\_\_\_\_` instead of a proper fill-in. The raw_text stores `\_` (backslash-underscore) which the frontend LaTeX renderer doesn't unescape. Likely a Flash-crop transcription artifact — needs raw_text clean-up. |

---

## D. Extraction Issues

Raw LLM JSON schema leaked into `question_content.raw_text`.

**Scope widened 2026-04-17** — across all years: **216 rows** have `raw_text` starting with `{ "raw_text":` or `\begin{json}`. Breakdown:

| Year | Chemistry | Mathematics | Physics | Subtotal |
|---|---|---|---|---|
| 2024 | 28 | 21 | 43 | **92** |
| 2023 | 24 | 28 | 72 | **124** |
| **Total** | **52** | **49** | **115** | **216** |

Note: many (especially the Physics-labeled ones in 2024) have Maths content — the subject is wrong *and* the raw_text is corrupted. Fixing one without the other leaves the row broken.

| # | Status | Count | Evidence |
|---|--------|-------|----------|
| D1 | OPEN | 1 | Canonical example id=2215 (Physics Kinetic Theory Q20) — same row as A8. |
| D-bulk | OPEN | 215 | Every other row with raw_text starting with `{ "raw_text":` or `\begin{json}`. Mostly 2024-01-27 s1, 2024-01-30 s1, plus large blocks across 2023 papers. |

Root cause: Gemini Flash crop transcription returned a stringified JSON or `\begin{json}`-fenced blob. `jee_crop_pipeline.py`'s fallback path at line ~394 catches `json.JSONDecodeError` and stores the entire raw string as `raw_text`. The existing `jee_rawtext_cleanup.py` handles inner-monologue leakage, not JSON-schema leakage — a new repair script is needed.

---

## E. Empty Questions

| # | Status | Chapter | Q# | Evidence | Resolution |
|---|--------|---------|----|----------|------------|
| E1 | **FIXED** | 11th Maths, Trigonometric Functions | Q19 | Card renders only the `Q19` label + Check Answer/Skip | Post-dedup, the count of 2024 rows with empty `raw_text` is 0. The empty card was a duplicate row that got deleted. |

---

## F. Uncategorised

| # | Status | Chapter | Q# | Evidence | Resolution |
|---|--------|---------|----|----------|------------|
| F1 | **FIXED** | 11th Maths, Trigonometric Functions | Q17 | Tetrahedral die question with `m/n, gcd(m,n)=1` and no A–D options | Confirmed same question as A6 (id=1049). It's an integer-answer Section B question so correctly has no options. It was showing under "Trigonometric Functions" because a wrong-subject duplicate was tagged there. Dedup removed the duplicate. |

---

---

## G. Cross-listing (NEW — discovered round 2)

Questions show up under multiple NCERT chapters on the frontend because the M3 tagger
assigns 2–5 concept tags per question across different chapters, and `accentSession.ts`
has no similarity threshold — even weak tags (score 0.5–0.7) cause a question to appear
under that chapter.

**Concrete examples user flagged under "11 Maths, Complex Numbers & Quadratic":**

| id | Actual topic | Primary tag | Secondary tag (cross-list cause) |
|---|---|---|---|
| 109 | Definite Integration | Integrals :: Evaluation of Definite Integrals by Substitution (1.00) | Complex Numbers :: Complex Numbers and Quadratic Equations (0.70) |
| 498 | Inverse Trig | Inverse Trig Functions :: Miscellaneous Examples (1.00) | Complex Numbers :: Identities (0.70) |
| 661 | Exponential equation | Complex Numbers :: Complex Numbers and Quadratic Equations (0.90) | Sets :: Sets and their Representations (0.70) |
| 753 | Quadratic + sequences | Complex Numbers :: Miscellaneous Examples (1.00) | Application of Derivatives :: Maxima and Minima (0.90) |
| 766 | Polynomial roots | Complex Numbers :: Miscellaneous Examples (0.90) | Complex Numbers :: Identities (0.80) |

**Scope:** 545 of 1,520 tagged questions (35.8%) currently cross-listed. Threshold `score ≥ 0.85` drops this to 204 (13.4%) — preserves legitimate multi-topic tagging while dropping weak cross-chapter pollution.

| # | Status | Proposed fix |
|---|--------|--------------|
| G1 | **FIXED** | `accentSession.ts:62` and `accentChapterMap.ts:37` now filter `jqt.similarity_score >= 0.85`. Validated via dip test: precision 20/20 on kept, drop-correctness 19/20 on dropped. Cross-listing dropped from 626 → 258 questions. 7 orphans (0.46%) — most have genuinely-weak tags, candidates for targeted re-tagging in future. |

**Open observation** (not a bug, but worth tracking): JEE Main questions sometimes cover concepts *above* NCERT Class 11–12 depth. The orphan set may partially reflect genuine NCERT-vocabulary gaps rather than tagger failure. If orphan count grows meaningfully with the 2023 corpus, it's worth auditing whether we need to extend the concept vocabulary (maybe with JEE Advanced-tier concepts).

---

## Proposed Next Batches (Round 3+)

Order is by impact and by the fact that batches 1–3 share the same LLM-classify skeleton
(pattern-based execution is ~2× cheaper than category-by-category).

### Batch 1 — JSON-leak repair + subject re-classification ✅ DONE (2026-04-17)

**Result:**
- 2024: 92 rows repaired → 92 subjects corrected, 178 tags cleared, 91 embeddings cleared
- 2023: 124 rows repaired → 124 subjects corrected (2023 was untagged)
- All 216 LaTeX-preserving clean `raw_text` values written (via tolerant regex unescape — `json.loads` corrupted LaTeX escapes like `\to`, `\frac`)

Script `jee_jsonleak_repair.py`:
- For each row whose `raw_text` starts with `{ "raw_text":` or `\begin{json}`:
  1. Parse the leaked JSON (or `\begin{json}`-fenced block) to recover `raw_text`, `options`, `has_figure`, `figure_description`.
  2. If parse fails, send the corrupted text to Gemini Flash for clean re-extraction.
  3. LLM-classify the subject on the cleaned `raw_text`.
  4. If subject differs from stored: UPDATE `jee_question_bank.subject`, DELETE `jee_question_tags` + `jee_question_embeddings`, clear `difficulty` / `difficulty_confidence` / `pattern_label`.
  5. UPDATE `question_content` with the cleaned JSON.
- Run on 2024 (92 rows) first, verify sample, then 2023 (124 rows).
- Resolves: all of D, A8, A12 (partially), the hidden ~100 Maths-as-Physics rows in 2024, some of A13.

### Batch 2 — Per-question subject audit ✅ DONE (2026-04-17)

**Result:**
- 2023: 952 / 1,080 subjects corrected (**88% — systematic cyclic rotation** across most 2023 papers: Phys→Math, Chem→Phys, Math→Chem)
- 2024: 238 / 1,520 subjects corrected (partial-paper mismatches that subject_auditor.py missed)
- **Total: 1,190 subjects corrected, 438 bad tags + 235 embeddings cleared**
- Validated: 0 LLM false positives across 10 sampled "unchanged" rows + 7 Math→Physics edge cases (all were genuinely Physics: de Broglie, Bohr, photoelectric, black body)
- Also discovered **new extraction-artefact variant** inside audit preview output: inner-monologue leakage (`|continued|`, `|thought|`, `"Wait, I was typing..."`) — distinct from JSON-leak, counted as future Batch 5 work.

Script `subject_auditor_perq.py` (plus `apply_predictions_bulk.py` for resuming a partial run):
- For rows whose `raw_text` is clean but subject is suspicious — run LLM classify in batches of ~20.
- Focus sets in order:
  1. All 2023 rows (1,080 — BEFORE tagging 2023 to avoid wrong-vocab tagging).
  2. All 2024 rows post-batch-1 (re-audit for any residual wrong subjects).
- For mismatches: UPDATE subject + clear tags/embeddings/metadata (same cascade as batch 1).
- Resolves: A11 (candela id=3149), A13 (2023 chem-as-maths rows), and any other partial-paper single-row mismatches.

### Batch 3 — Re-tag affected rows

- `python question_tagger.py --year 2024` — NOT EXISTS filter picks up only the rows whose tags were cleared in batch 1 & 2.
- `python question_tagger.py --year 2023` — fresh tagging with now-correct subjects.
- Use full-mode fallback (`--mode full --batch-size 1`) for persistent hybrid failures as before.

### Batch 4 — Cross-listing filter (category G)

- One-line query change in `apps/functions/src/functions/accentSession.ts` and `accentChapterMap.ts`: add `AND jqt.similarity_score >= 0.85` to the JOIN.
- Also review `apps/functions/src/functions/accentQuestion.ts` for the single-question endpoint.
- No data migration; pure read-path change; can be rolled back cleanly.

### Batch 5 — Extraction artefacts + literal-escape cleanup ✅ DONE (2026-04-17)

**Result:**
- Class A (extraction artefacts — `|thought|`/`|continued|`/``` ```json ```/embedded JSON): **27 rows repaired** (25 from 2024 first run + 2 from enhanced-parser second pass)
- Class D (literal `\_` outside `$...$` math mode): **37 rows fixed** (15 in 2024 + 22 in 2023). `\_` inside math mode correctly left alone.
- 30 tags + 18 embeddings cleared for re-tagging.

**Script:** `jee_rawtext_batch5.py` (relies on `parse_leak` from `jee_jsonleak_repair.py`). Handles two repair classes in one pass.

**Remaining unfixable — 10 rows need manual re-extraction via Pro pipeline:**

Genuinely unfixable (question stem missing / content fragmented):
- 2023: id=3968, 4093, 4115, 4335, 4513
- 2024: id=347, 812, 1566, 1913, 2987

C1 flag: id=392 (unbalanced `$` + stray `1}{2}` prefix) — also a candidate for Pro pipeline re-extraction. Total: **11 manual re-extraction candidates.**

C3 flag: id=711 tuning fork — **FIXED** by Class D (literal `\_` → `_` in non-math).

**Post-batch residuals (from `diagnose_rawtext_quality.py`):**
| Pattern | Before | After |
|---|---|---|
| A (inner-monologue) | 6 | 0 |
| B (embedded `"raw_text"`) | 35 | 8 |
| C (reasoning prose) | 10 | 9 |
| D2 (any literal `\_`) | 58 | 21 (all inside `$...$`, correctly preserved) |
| F (``` fence) | 11 | 0 |
| G (truncated JSON) | 4 | 2 |

The ~10 residuals in B/C/G all overlap with the 10 unparseable rows flagged above.

---

## How to Use This Tracker

1. The batch numbering above is the execution order. Each batch produces a script, a log, and updated counts.
2. After each batch, re-run the diagnostic scripts (`diagnose_duplicates.py`, `diagnose_broader.py`) and record new counts in the Summary table.
3. For category-level reporting (A/B/C/D/E/F/G), flip rows to **FIXED** as the batches resolve them.
4. Keep the Summary counts in sync with each status change.

---

## Known Issues — PARKED (revisit on next-year ingest)

### KI-1 — Flash reasoning-leak on dense mixed text+image questions

**Status:** PARKED (2026-04-20). Non-blocking — 10 rows out of ~5,600 tagged questions (0.2% of corpus).

**Affected rows (10):**
| id | year | paper_id | date | shift | subject | Q# |
|---|---|---|---|---|---|---|
| 4093 | 2023 | 214 | 2023-04-10 | 2 | Mathematics | 9 |
| 4115 | 2023 | 214 | 2023-04-10 | 2 | Mathematics | 30 |
| 4335 | 2023 | 216 | 2023-04-11 | 2 | Chemistry | 76 |
| 4513 | 2023 | 218 | 2023-04-13 | 1 | Chemistry | 74 |
| 3968 | 2023 | 221 | 2023-04-08 | 2 | Chemistry | 69 |
| 2987 | 2024 | 2 | 2024-04-08 | 1 | Chemistry | 78 |
| 1913 | 2024 | 3 | 2024-04-06 | 2 | Chemistry | 85 |
| 812 | 2024 | 4 | 2024-04-06 | 1 | Chemistry | 63 |
| 347 | 2024 | 14 | 2024-01-30 | 1 | Physics | 50 |
| 392 | 2024 | 15 | 2024-01-30 | 2 | Mathematics | 3 |

(id=1566 from the original batch-5 "unfixable" list is already deleted and does not need action.)

**Root cause:** These questions have dense mixed text+image content — the stem is text but the critical content (organic-chemistry reagent schemes with multiple ring substitutions, detailed diagrams, or complex figures) is embedded as PNG inside the PDF. Gemini Flash's crop-based multimodal transcription became uncertain on how to notate the structures in LaTeX, entered a "thinking aloud" mode (`"I'll use these. Wait, the prompt says… Actually, let me use more descriptive LaTeX…"`), and **never produced a final JSON response**. The crop pipeline's parser fallback stored Flash's raw reasoning stream verbatim as `raw_text`.

**Evidence it's reasoning-leak, not truncation:** the affected raw_texts are short (363–943 chars), well below the 8192 `max_output_tokens` ceiling. Pure truncation would leave 30k+ char outputs cut mid-stream.

**Why Batch 5 couldn't auto-repair:** existing repair scripts (`jee_jsonleak_repair.py`, `jee_rawtext_batch5.py`) parse leaked JSON or strip known artefact patterns. For these 10, Flash never produced any parseable JSON — it's pure monologue. No structure to recover.

**Why the 2026-04-18 Pro-pipeline re-run didn't fix these:** `prep_reextract_bad_rows.py`'s `BAD_ROW_SQL` matches `[Figure:%`, `}%`, `^[a-z][})]`, and `<40 char` patterns — not monologue prefixes like `"thought{"`, `"Actually"`, `"One last check"`, `"I'll use"`. So the bad rows were never deleted before the Pro re-run, and `bulk_insert_questions` uses `ON CONFLICT DO NOTHING`, preserving them.

**Proposed fix (figure-blob approach):** the Prisma schema already has `question_content.figure_blob_url` (frontend renders it in AccentSession). Rather than trying to transcribe complex org-chem structures to LaTeX (lossy and fragile), the right solution is:

1. Crop the full question region (stem + all 4 options with embedded structures) from the PDF as one PNG per question.
2. Upload to Azure Blob (`stevaluationstorage/onlineresources/jee/figures/`).
3. Set `question_content.figure_blob_url` to the blob URL.
4. Set `question_content.raw_text` to just the textual prompt (e.g. *"Identify the major products A and B respectively in the following set of reactions."*).
5. Clear `jee_question_tags` + `jee_question_embeddings` so the row re-tags.
6. Re-run `question_tagger.py` — the minimal text stem will produce sensible tags.

**When to revisit:** Next-year ingestion (2021, 2022, 2025) OR a full re-tag sweep. At that point we'll encounter more instances of this failure mode on different papers, so it's worth building a reusable `fix_image_question.py` helper (takes `--id`, `--png`, `--raw-text`; does blob upload + DB update + tag clear in one call) and applying it to all residuals in a single pass.

**Also fix at that time:** `prep_reextract_bad_rows.py` `BAD_ROW_SQL` should include monologue-prefix patterns (`thought%`, `Actually%`, `One last check%`, `I'll use%`) so the next auto-reset catches these.

---

### KI-2 — 2023 systemic breakage (hallucinated NTA IDs)

**Status:** PARKED (2026-04-20). MVP will run on 2024 only. 2023 will be re-extracted wholesale post-MVP alongside 2021/2022/2025.

**Scope:** All 12 papers, all 1,080 rows of 2023 in `jee_question_bank`.

**Symptoms:**
- `answer_key IS NULL` on every single 2023 row (1,080 / 1,080)
- NTA IDs are perfectly sequential within each paper (`3666943111, 3666943112, 3666943113, …`) — a fingerprint of Gemini Pro generating them as a counter rather than reading them from the source
- The real AK NTA IDs (from `jee_answer_mappings`, extracted via PyMuPDF from AK PDFs) are in a different numeric range (`3666941070, …`). Zero overlap.
- ~33 rows per paper have `options: []` (empty); ~90% do have real options
- Question **text** looks correct — real JEE content in real LaTeX (not hallucinated)
- `question_number` is populated on 956 / 1,080 rows — so the ordinal position is usually recoverable

**Why the existing repair scripts couldn't fix it:** `jee_jsonleak_repair.py` and `jee_rawtext_batch5.py` repair content-level artefacts. This is a different failure class — the content is fine, it's the **identifier** that's fake. No local repair is possible without the source PDF.

**Why partial salvage won't work:**
- Can't re-join via `(paper_id, question_number)` because `jee_answer_mappings` / `exam_answer_keys` don't store `question_number`.
- Without answer_keys, "Check Answer" and progression-engine scoring are broken for the entire year.

**Proposed fix (post-MVP):**
1. Identify the 2023 paper_ids: 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224.
2. `DELETE FROM jee_question_bank WHERE year = 2023;`
3. `UPDATE exam_papers SET extraction_status = 'PENDING', paper_format = NULL WHERE id IN (213, …, 224);`
4. `rm pipelines/JEEAscentPipeline/checkpoints/paper_{213..224}.json` (and `crop_paper_*.json` if any).
5. Harden the Pro-pipeline system prompt to explicitly require reading NTA Question IDs *only* from the PDF (not generating them); add a sanity check that rejects sequential id patterns.
6. Alternative: use the crop pipeline (`jee_crop_pipeline.py`), which reads NTA IDs from the PDF text layer deterministically via regex — no LLM hallucination risk on the IDs themselves.
7. Re-run extraction, validate AK coverage ≥ 80% per paper, then run `question_tagger.py --year 2023`.

**Expected cost:** ~3 hours end-to-end (12 papers × ~15 min each for Pro, or faster via crop).

**Memory refs:** `MEMORY.md` M1b section must not say 2023 is "extracted + subject-corrected" — that reflected a broken state where the extraction returned rows but the IDs/AKs never joined. Updated 2026-04-20.
