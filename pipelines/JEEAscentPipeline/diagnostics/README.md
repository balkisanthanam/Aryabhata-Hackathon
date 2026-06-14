# JEE Ascent Pipeline — Diagnostics

One-off investigation and verification scripts used during QA rounds 1–5 and the 2024 dedup / E2E validation push. Not part of the production pipeline — most are throwaway or batch-specific.

Kept for reproducibility when similar issues resurface (e.g., 2023 re-extract will likely hit comparable rawtext-quality and duplicate questions).

## Quick index

| Script | Purpose | Still useful for? |
|---|---|---|
| `check_audit_progress.py` | Poll how many rows have been audited by `subject_auditor_perq.py` | Any future auditor run |
| `check_constraints.py` | Inspect live DB constraints on `jee_question_bank` | Schema verification |
| `check_remaining_issues.py` | Summarise QA-round-tracked issues still open | Any new QA round |
| `check_threshold_impact.py` | Preview impact of raising `similarity_score` cutoff on tag counts | Future threshold tuning |
| `diagnose_broader.py` | Broad-net diagnostic for rawtext anomalies across subjects | Any new-year ingest |
| `diagnose_duplicates.py` | Identify dup rows by content hash + NTA ID | Dedup work on new years |
| `diagnose_flagged_questions.py` | Inspect rows flagged by the auditor | Round-N QA |
| `diagnose_rawtext_quality.py` | Heuristics for broken LaTeX / encoding drift | Any new-year ingest |
| `diagnose_round2.py` | Round 2 rawtext triage (2024-specific) | One-shot — likely obsolete |
| `diagnose_round2_flagged.py` | Round 2 flagged-subset details | One-shot |
| `diagnose_round2_incomplete.py` | Round 2 incomplete-row triage | One-shot |
| `diptest_threshold.py` | Hartigan's dip-test on similarity score distribution | Threshold tuning |
| `inspect_leaks.py` | Hunt LLM reasoning leaks in rawtext (KI-1 work) | Any new-year ingest |
| `inspect_rawtext_samples.py` | Pull random rawtext samples for manual review | Any new-year ingest |
| `sampling_matrix.py` | Pick representative 2024 questions per chapter for E2E | Future E2E campaigns |
| `smoketest_constraint.py` | Pre-flight check for the unique-constraint migration | Constraint work |
| `verify_dedup_plan.py` | Dry-run dedup plan before committing | Any future dedup |

## Running

All scripts assume the project's standard environment: `az login` active, `local.settings.local.json` present, and shared libs on `sys.path` via the pipeline's usual bootstrap. Most can be run as `python diagnostics/<script>.py` from the `pipelines/JEEAscentPipeline` folder.
