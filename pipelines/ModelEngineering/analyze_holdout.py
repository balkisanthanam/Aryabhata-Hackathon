"""Compact holdout-result analyzer — prints a ~15-line summary so runs can be reviewed
without pasting full logs. Reads a batch_evaluator checkpoint (.jsonl, one row_result per
line) OR a *_RAW.json (dict with 'details'). Excludes corrupt_key holdout rows (KI-6) from
the headline. Pro-share is inferred from has_figure (the router sends figure rows to Pro).

Usage:
  python analyze_holdout.py runs/_checkpoint_A3_Untuned_schema_router.jsonl --label "A3 single-call"
  python analyze_holdout.py runs/Experiment_Run_<ts>_RAW.json --label "A3.5 flash-assembly"
"""
import argparse
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

CWD = Path(__file__).resolve().parent


def load_rows(path: Path):
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["details"] if isinstance(data, dict) and "details" in data else data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    path = Path(args.path)
    if not path.is_absolute():
        path = CWD / path
    rows = load_rows(path)

    # corrupt_key ids from the holdout (KI-6) — excluded from the headline
    hold = json.loads((CWD / "holdout_eval_set.json").read_text(encoding="utf-8"))["records"]
    corrupt_ids = {(r["source"], r["id"]) for r in hold if r.get("corrupt_key")}

    errors = [r for r in rows if not r.get("scores")]
    scored = [r for r in rows if r.get("scores")]
    clean = [r for r in scored if (r["source"], r["id"]) not in corrupt_ids]

    def s(r, k):
        return r["scores"].get(k)

    n = len(clean)
    acc5 = sum(1 for r in clean if s(r, "accuracy_score") == 5)
    full = sum(1 for r in clean if s(r, "is_pass"))
    figure = sum(1 for r in clean if r.get("has_figure"))

    print(f"=== {args.label or path.name} ===")
    print(f"rows: {len(rows)} total | {len(scored)} scored | {len(errors)} errors | {len(clean)} clean (excl {len(scored)-len(clean)} corrupt)")
    if errors:
        print(f"  !! {len(errors)} generator_errors (network/empty) -> prune+resume to fix")
    print(f"Acc-routable: {acc5}/{n} = {100*acc5/n:.1f}%   Full-pass: {full}/{n} = {100*full/n:.1f}%")
    print("Avg Acc/Ped/Fmt: %.2f / %.2f / %.2f" % (
        st.mean(s(r, "accuracy_score") for r in clean),
        st.mean(s(r, "pedagogy_score") for r in clean),
        st.mean(s(r, "formatting_score") for r in clean)))
    print(f"Pro-share (figure rows routed): {figure}/{n} = {100*figure/n:.0f}%")
    ped = Counter(s(r, "pedagogy_score") for r in clean)
    print("Ped dist:", {k: ped[k] for k in sorted(ped)})
    # accuracy misses + pedagogy misses (ids, for targeted follow-up)
    accfail = [(r["source"], r["id"], r["subject"]) for r in clean if s(r, "accuracy_score") != 5]
    pedfail = [(r["source"], r["id"], r["subject"]) for r in clean if s(r, "pedagogy_score") < 4]
    print(f"Acc misses ({len(accfail)}):", accfail[:12])
    print(f"Ped<4 ({len(pedfail)}):", pedfail[:14])
    # per source x figure
    print("By source x figure (acc-routable / full-pass / avgPed):")
    bk = defaultdict(list)
    for r in clean:
        bk[(r["source"], "fig" if r.get("has_figure") else "nofig")].append(r)
    for k in sorted(bk):
        g = bk[k]
        print("  %-12s n=%-3d acc=%3.0f%% full=%3.0f%% ped=%.2f" % (
            f"{k[0]}/{k[1]}", len(g),
            100*sum(1 for r in g if s(r, "accuracy_score") == 5)/len(g),
            100*sum(1 for r in g if s(r, "is_pass"))/len(g),
            st.mean(s(r, "pedagogy_score") for r in g)))


if __name__ == "__main__":
    main()
