# Gold Set Generation — Execution Tracker

> Living tracker for the Gold Set work. Plan of record: planning session 2026-05-21.
> Goal: ~100 JEE + ~100 NCERT solutions at strict **5/5/5**, marked `APPROVED_GOLD`,
> exported as ChatML JSONL for Gemini 3 Flash SFT.

---

## Work Items

| ID | Item | Status |
|----|------|--------|
| W0 | Verify live DB state + reconcile | ✅ Done (verification) · CHECK constraint SQL written, apply pending approval |
| W1 | Fix `evaluator_engine.py` + build unified GOLD gate | ✅ Done — gate smoke-tested (JEE id=56 dry-run) |
| W2 | Orchestrator cost + schema fixes | ✅ Done — pedagogy→tutor_model, format→Flash, schema pinned, escape-sanitize retry |
| W3 | Wire Smart Context into NCERT `regenerate` | ✅ Done — pgvector retrieval wired into `regenerate_core_math` |
| W4 | Fix `jsonl_exporter.py` NCERT path | ✅ Done — NCERT filters `APPROVED_GOLD`; `build_user_payload` strips answer_key |

## Run Log

| ID | Run | Date | Scope | Result |
|----|-----|------|-------|--------|
| R1 | JEE filter (free analysis) | 2026-05-21 | 98 existing APPROVED_GOLD | 89 are genuine 5/5/5; 9 fall short; ~11 short of 100 |
| R1 | JEE demote + top-up | 2026-05-22 | demote 9 + generate 15 + gate | **102 JEE APPROVED_GOLD** (89 kept + 13 new; gate scored 13/16) |
| R2 | NCERT verify — Physics | 2026-05-22 | 10 rows, C11 Physics | 9/10 5/5/5 (1 miss = accuracy rounding nitpick) |
| R2 | NCERT verify — Chem+Maths | 2026-05-22 | 8 + 8 rows, C12 | Maths 8/8 ✓ · Chemistry 4/8 — all 4 misses = mhchem formatting |
| R2 | NCERT scale — run 1 | 2026-05-22 | 6 combos parallel | crashed mid-loop (DB connection drop); **40 gold banked**, 43 rows in-flight |
| R2 | NCERT scale — run 2 | 2026-05-22 | format-drain + gate | **153 NCERT APPROVED_GOLD** (target 150 ✓) — C11 Chem16/Maths23/Phys32, C12 Chem29/Maths28/Phys25 |
| R3 | Export training JSONL | 2026-05-22 | `jsonl_exporter --source all` | **255 examples** → `gold_sft_dataset.jsonl` (153 NCERT + 102 JEE), ChatML, verified well-formed |

**✅ GOLD SET COMPLETE (2026-05-22): 255 training examples — 153 NCERT + 102 JEE — at strict 5/5/5.**
Next phase: Vertex AI SFT (separate model-approach discussion).

---

## W0 — Verified DB state (2026-05-21, read-only via `verify_db_state.py`)

**`questiondata` (NCERT):** all 4 state-machine columns present; `review_status`
default = `'LEGACY'` → the `Retrofit` migration is live (not the conflicting
`UNVERIFIED` one). **No backfill needed.** No CHECK constraint present.

review_status distribution — 899 rows with a solution:

| Status | Count |
|--------|------:|
| LEGACY | 619 |
| MATH_PASSED | 262 |
| REJECTED | 20 |
| MATH_REGENERATED | 1 |

`MATH_PASSED` is already diverse across all 6 class×subject combos
(C11: Chem 38 / Maths 50 / Phys 43 — C12: Chem 49 / Maths 50 / Phys 32).
**R2 can draw entirely from this pool — no need to touch the 619 LEGACY rows.**

**`jee_question_bank` (JEE):**

| Status | Count |
|--------|------:|
| PENDING | 2480 |
| APPROVED_GOLD | 98 |
| APPROVED | 3 |
| UNVERIFIED | 3 |

The 98 `APPROVED_GOLD` rows (Chem 30 / Maths 40 / Phys 28, all `is_generated`)
were marked gold by the **old `is_pass` rule** (total ≥ 13 & accuracy = 5), *not*
strict 5/5/5 — they must be re-filtered against the 5/5/5 bar in R1.
`runs/DB_Evaluation_20260516_194904.json` already holds per-question 3-D scores
for 74 rows (avg acc 5.0 / ped 4.92 / fmt 4.93) — usable to filter for free.

**Reconciliation:** `Scripts/NCERT_StateMachine_Reconcile.sql` written (adds a
`CHECK` constraint enumerating valid statuses). Not yet applied — optional
hygiene, not on the critical path.

## R1 — JEE filter analysis (2026-05-21, zero API cost)

Cross-referenced `runs/DB_Evaluation_*.json` (99 distinct question_ids of real DB-row
evaluations) against the 98 `APPROVED_GOLD` rows. All 98 are covered:

- **89 confirmed strict 5/5/5** — genuine gold, keep.
- **9 fall short** — demote `APPROVED_GOLD → APPROVED` so the export stays clean:
  - 5/5/**4** (formatting): ids 44, 45, 60, 67, 89, 230
  - 5/**4**/5 (pedagogy): ids 102, 238
  - 5/**3**/5 (pedagogy): id 224
- 0 rows without eval data → no re-gating needed.

Result: 89 genuine JEE gold → **~11 short of the ~100 target**. Top up by generating
fresh solutions with `jee_solution_pipeline.py --use-assembly --use-smart-context`
(both flags mandatory — defaults are off), then gate them.

## Open items

- **14 NCERT formatting misses** (gate run 2): rows scored fmt 2–4, parked at `APPROVED`.
  Possibly the LOW-thinking formatter struggling on hard rows. Recoverable later by
  resetting to `PEDAGOGY_ADDED` and re-running format (consider MEDIUM thinking) if more
  NCERT gold is wanted. Not blocking — 153 gold already exceeds target.
- **2 pedagogy workers hung** in scale run 2 (~12 min on one Gemini call each) — transient
  `global`-endpoint stall. Sidestepped by resuming at `--start-phase format`.

## Notes / Decisions

- **DB connection-drop resilience (2026-05-22):** scale run 1 crashed — `psycopg2`
  `server closed the connection unexpectedly` after ~3.5 min / ~11 rows per worker.
  The orchestrator (and gate) held one connection across every slow LLM call;
  `DatabaseClient.connect()` reuses a cached handle whose `.closed` flag stays stale
  after a server-side drop. Fixed: added `execute_write()` to both — every write
  reconnects-and-retries on `OperationalError`/`InterfaceError`. Also: a DB-write
  failure no longer mis-flags the question as `NEEDS_HUMAN_REVIEW`.
- **Chemistry mhchem fix (2026-05-22):** Chemistry verify scored 4/8 — all 4 misses were
  formatting 4/5 because the formatter wrote chemical formulas as math subscripts
  (`$C_{6}H_{6}$`) instead of mhchem (`$\ce{C6H6}$`). Added a chemistry-notation rule to
  the format prompt. Frontend `LatexRenderer.tsx` already imports `katex/.../mhchem`, so
  `\ce{}` renders correctly. Accuracy/pedagogy were perfect — formatting-only fix.
- **Gemini 3 thinking latency (2026-05-22):** the format step was minutes/record because
  `gemini-3-flash-preview` is a thinking model and thinking was uncapped. Fixed by adding
  `thinking_level` to `GeminiModelConfig` and setting `formatter_model` to `LOW` (formatting
  is mechanical). `tutor_model`/`solver_model` keep full reasoning. Touches shared
  `config.py` + `gemini_client.py` — additive, other configs unaffected.

- The 98 `APPROVED_GOLD` were originally marked by the legacy `is_pass` rule
  (total ≥ 13 & acc = 5), which is why 9 sit below strict 5/5/5.
- `build_user_payload` (W4) **strips `answer_key`** from the SFT `user` message so the
  training input matches inference-time input. Flagged for the training-design review.
- The 3 existing `UNVERIFIED` JEE rows are single-pass (no assembly line) — e.g. id=56
  scored 5/2/5. Not gold-grade; exclude or regenerate.
