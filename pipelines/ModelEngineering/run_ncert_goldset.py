"""
NCERT Gold Set scale-runner (R2 scale).

Drives the 6 class x subject combos through the orchestrator's pedagogy + format
stages, then runs the GOLD gate over every resulting APPROVED row.

  Phase 1 (pedagogy): 6 combos run in PARALLEL — one subprocess each.   MATH_PASSED   -> PEDAGOGY_ADDED
  Phase 2 (format):   6 combos run in PARALLEL — one subprocess each.   PEDAGOGY_ADDED -> APPROVED
  Phase 3 (gate):     one sequential pass, strict 5/5/5.                APPROVED       -> APPROVED_GOLD

Verbose per-combo output goes to TempLocal/scale_*.log — the console stays quiet.
Every step is status-driven, so the run is resumable: use --start-phase to resume.

NOTE on re-runs: --limit means "process up to N rows currently in the source status".
If a phase completes and you re-run it, it will process ANOTHER batch of N rows
(more gold — harmless). To resume cleanly after a mid-run stop, use --start-phase.

Usage:
  python run_ncert_goldset.py --per-combo 25                # full run, ~150 new rows
  python run_ncert_goldset.py --start-phase format          # resume (Phase 1 already done)
  python run_ncert_goldset.py --start-phase gate            # just gate existing APPROVED rows
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

CWD = Path(__file__).resolve().parent
PROJECT_ROOT = CWD.parent.parent
ORCH = CWD / "ncert_pipeline_orchestrator.py"
GATE = CWD / "evaluator_engine.py"
LOG_DIR = PROJECT_ROOT / "TempLocal"

COMBOS = [
    ("11", "Physics"), ("11", "Chemistry"), ("11", "Maths"),
    ("12", "Physics"), ("12", "Chemistry"), ("12", "Maths"),
]


def run_parallel(task: str, per_combo: int):
    """Launch one orchestrator subprocess per combo for `task`; wait for all."""
    procs = []
    for cls, subj in COMBOS:
        log_path = LOG_DIR / f"scale_{task}_{cls}_{subj}.log"
        fh = open(log_path, "w", encoding="utf-8")
        cmd = [sys.executable, str(ORCH), "--class", cls, "--subject", subj,
               "--task", task, "--limit", str(per_combo), "--update-db"]
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        procs.append((cls, subj, p, fh))
        print(f"  launched {task:9s} Class {cls} {subj:<10} -> {log_path.name}")

    print(f"  waiting for {len(procs)} {task} workers ...")
    failed = 0
    for cls, subj, p, fh in procs:
        rc = p.wait()
        fh.close()
        status = "ok" if rc == 0 else f"EXIT {rc}"
        if rc != 0:
            failed += 1
        print(f"    {task:9s} Class {cls} {subj:<10} {status}")
    if failed:
        print(f"  WARNING: {failed} {task} worker(s) exited non-zero — check the scale_{task}_*.log files.")


def main():
    ap = argparse.ArgumentParser(description="NCERT Gold Set scale-runner")
    ap.add_argument("--per-combo", type=int, default=25,
                    help="MATH_PASSED rows to process per class x subject combo (default 25 -> ~150 new rows)")
    ap.add_argument("--gate-limit", type=int, default=500,
                    help="Max APPROVED rows the GOLD gate evaluates (default 500)")
    ap.add_argument("--start-phase", choices=["pedagogy", "format", "gate"], default="pedagogy",
                    help="Resume from this phase (default: pedagogy = full run)")
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    phases = ["pedagogy", "format", "gate"]
    start = phases.index(args.start_phase)
    t0 = time.time()

    if start <= 0:
        print(f"\n=== PHASE 1: pedagogy — 6 combos x {args.per_combo}, parallel ===")
        run_parallel("pedagogy", args.per_combo)

    if start <= 1:
        # Format drains ALL PEDAGOGY_ADDED rows (including any backlog from a prior run),
        # so the per-combo limit is intentionally high — not tied to --per-combo.
        print(f"\n=== PHASE 2: format — drain all PEDAGOGY_ADDED, 6 combos parallel ===")
        run_parallel("format", 500)

    if start <= 2:
        print(f"\n=== PHASE 3: GOLD gate — strict 5/5/5 over all APPROVED rows ===")
        gate_log = LOG_DIR / "scale_gate.log"
        cmd = [sys.executable, str(GATE), "--source", "ncert",
               "--target-status", "APPROVED", "--limit", str(args.gate_limit)]
        with open(gate_log, "w", encoding="utf-8") as fh:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
        print(f"  gate complete -> {gate_log.name} (verdict JSONL: TempLocal/gate_ncert_APPROVED_*.jsonl)")

    print(f"\n=== Done in {(time.time() - t0) / 60:.1f} min ===")


if __name__ == "__main__":
    main()
