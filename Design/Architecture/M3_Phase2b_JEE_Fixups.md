# M3 Phase 2b — JEE Wiring FIX-UPS (pre-CP3 review findings)

> **Read after `M3_Phase2b_JEE_Handoff.md`.** The build is correct except for the items below,
> found in the owner's pre-CP3 code review. Apply A + B + C, then hand back the CP3 command.
> **Still do not commit** until CP3 passes + owner sign-off. Default `--solver-tier pro` stays
> byte-identical — none of these touch the pro path.

---

## 🔴 FIX A — Router discriminator is dead for JEE (correctness bug)

**File:** `pipelines/JEEAscentPipeline/jee_solution_pipeline.py`

**Problem:** `:249` passes `has_figure=bool(image_urls)`. `image_urls` comes from
`qc['figure_url']` / `option_figure_urls`, but **KI-3: `figure_url` is NULL on 100% of
`jee_question_bank` rows** → `image_urls` is always empty → `has_figure` always `False` →
`select_mode_for_record` **never routes any JEE row to Pro.** D4 is silently violated; every
figure row goes to Flash.

**Why the content flag is correct:** the ~170 figure rows carry `question_content.has_figure=true`
even though no crop exists. That missing crop is *exactly why* they must go to Pro (Flash is blind
without the image). So the router signal is the **content flag**, not the image list.

**Change:** after `image_urls` is built (~after line 226), add:
```python
row_has_figure = bool(qc.get('has_figure'))   # KI-3: figure_url NULL on all JEE rows;
                                              # the content flag (not bool(image_urls)) is the D4 router signal
```
Then use `row_has_figure` in **both** places that currently use `bool(image_urls)`:
- the log line at `:239`
- `has_figure=row_has_figure` in the `solve_with_gate(...)` call at `:249`

(Leave `image_urls` itself unchanged — it still passes any real images to the solver when present.)

---

## 🟡 FIX B — Gate the router→Pro path too, with a distinct status (owner-approved design call)

**File:** `pipelines/ExtractionPipeline/SchoolDataExtraction/MultiStep/gate.py`

**Problem:** the router→Pro branch (`:96-103`) returns `(sol, "UNVERIFIED")` **without gating**
Pro's answer. That silently stores a likely-wrong solution for a figure-dependent question and
labels it `UNVERIFIED` (= "looks fine"). We already gate the *fallback* Pro (`:128-134`) — there's
no reason to trust the *router* Pro more (it's solving figure-blind). The gate is free (string match).

**Decision (locked):** gate the router→Pro output, symmetric with the cascade bottom. On a real
miss, use a **distinct status `FIGURE_UNVERIFIED`** — NOT `GATE_FAILED` — so `GATE_FAILED` stays the
high-signal "two strong text attempts both missed → suspect key/solution" bucket, while
`FIGURE_UNVERIFIED` cleanly marks "KI-3-blocked, needs the figure." Corrupt keys still short-circuit
to `KEY_UNVERIFIED` via the existing `unknown` path.

**Change** the router branch (`gate.py:96-103`) to:
```python
    if mode == "pro-assembly":
        logger.info(f"gate: router→pro-assembly (source={source!r}, has_figure={has_figure})")
        sol = pro_generator.generate_assembly_line(
            prompt=prompt,
            system_prompt=system_prompt,
            image_urls=image_urls,
        )
        pro_answer = _parse_final_answer(sol.text, pro_generator)
        verdict = match(pro_answer, answer_key, options)
        logger.info(f"gate: router-Pro verdict={verdict!r} answer={pro_answer!r}")
        if verdict == "correct":
            return sol, "UNVERIFIED"
        if verdict == "unknown":
            return sol, "KEY_UNVERIFIED"
        return sol, "FIGURE_UNVERIFIED"   # figure-blind miss (KI-3) — distinct from non-figure GATE_FAILED
```
Also:
- Add `'FIGURE_UNVERIFIED'` to the status list in the module docstring (`:22`) and the
  `solve_with_gate` return-doc (`:84-87`).
- **Confirm `jee_question_bank.review_status` has no CHECK/enum constraint** that would reject a new
  string value (it already holds `UNVERIFIED`/`GATE_FAILED`/`GENERATION_FAILED`/`APPROVED_GOLD`, so a
  free varchar is expected — just verify, don't migrate).

**Caveat to keep in mind (no action):** on MCQ a key *match* is necessary-not-sufficient (~25% luck
floor), figure-blind or not — so a `UNVERIFIED` pass on a router→Pro row isn't proof of a correct
solution, only that the letter matched. Inherent gate limit; not a reason to change anything here.

---

## 🟡 FIX C — Verification query relies on a column we don't set

`update_solution_in_db` (`:86-90`) does **not** set `updated_at`, so the prior query's
`updated_at >= NOW() - INTERVAL '1 hour'` filter likely returns nothing. Scope by the run instead:
```sql
SELECT review_status, COUNT(*)
FROM jee_question_bank
WHERE year = 2024 AND is_generated = TRUE AND solution IS NOT NULL
GROUP BY review_status;
```

---

## CP3 — corrected command + what to confirm

**Pre-flight (locate a slice that actually contains figure rows, so the router fires):**
```sql
SELECT dateofexam, shift, COUNT(*) AS unsolved_with_figure
FROM jee_question_bank
WHERE year = 2024 AND solution IS NULL
  AND (question_content->>'has_figure')::boolean = TRUE
GROUP BY dateofexam, shift
ORDER BY unsolved_with_figure DESC
LIMIT 5;
```
Pick a `dateofexam`/`shift` with a handful of figure rows and target it so CP3 exercises the router.

**Run (note: drop `--use-assembly` — it's a no-op for the flash tier):**
```
cd pipelines/JEEAscentPipeline
python jee_solution_pipeline.py --solver-tier flash --year 2024 --exam-date <DATE> --shift <SHIFT> --limit 10
```

**Confirm (logs + the FIX-C query):**
1. Non-figure, Flash matches key → `UNVERIFIED`.
2. Non-figure, Flash mismatch → log `Flash miss → Pro re-solve`; Pro match → `UNVERIFIED`, Pro miss → `GATE_FAILED`.
3. **Figure row → log `router→pro-assembly`** (proves FIX A works); then `router-Pro verdict=...` →
   `UNVERIFIED` (match) / `FIGURE_UNVERIFIED` (miss) / `KEY_UNVERIFIED` (corrupt key).
4. Corrupt/≥9-digit key anywhere → `KEY_UNVERIFIED`, no Pro miss-flag.

**STOP, report the `review_status` spread + the gate log lines, wait for sign-off before commit.**
