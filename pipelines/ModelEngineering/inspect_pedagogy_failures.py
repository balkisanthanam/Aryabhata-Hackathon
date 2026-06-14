"""
Phase 0.1 of M3 v2 plan — inspect Pedagogy failures from Tuned v1.

Reads the Tuned v1 candidate eval RAW JSON, filters rows where
scores.pedagogy_score < 5, dumps the verbatim judge feedback, and
buckets the complaints by keyword pattern so we can see whether they
share a single failure mode (e.g. all "direct instruction" -- the
KI-4 pattern) or scatter across causes.

CLI:
  python inspect_pedagogy_failures.py
  python inspect_pedagogy_failures.py --raw runs/Experiment_Run_<ts>_RAW.json --out runs/_ped_failures_v1.md
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CWD = Path(__file__).resolve().parent
DEFAULT_RAW = CWD / "runs" / "Experiment_Run_20260526_105654_RAW.json"
DEFAULT_OUT = CWD / "runs" / "_ped_failures_v1.md"

# Rough keyword buckets tuned to the Pro KI-4 / Phase 1 failure modes.
# Each row may match multiple buckets; we record all matches.
PATTERNS = {
    "direct_instruction": re.compile(r"\b(direct|instruct|statement|tells|states|gives|reveals)\b", re.I),
    "not_socratic":       re.compile(r"\b(not\s+socratic|leading|prescriptive|guiding question)\b", re.I),
    "missing_hint":       re.compile(r"\b(missing|absent|no\s+nudge|empty|no\s+hint)\b", re.I),
    "shallow":            re.compile(r"\b(shallow|superficial|too\s+brief|inadequate)\b", re.I),
    "skip_step":          re.compile(r"\b(skips?|jumps?|omits?|misses?\s+step|gap)\b", re.I),
    "reveals_answer":     re.compile(r"\b(reveals\s+(the\s+)?answer|gives\s+(it\s+)?away|spoils?)\b", re.I),
    "hint_explanation_mismatch": re.compile(r"\b(disconnect|mismatch|inconsistent|hint.*explanation.*differ|aligned)\b", re.I),
}


def bucket(text: str) -> list[str]:
    return [name for name, pat in PATTERNS.items() if pat.search(text or "")]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", default=str(DEFAULT_RAW))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--threshold", type=int, default=5, help="Flag rows with pedagogy_score < this (default 5)")
    args = p.parse_args()

    raw_path = Path(args.raw)
    out_path = Path(args.out)

    if not raw_path.exists():
        print(f"ERROR: RAW not found: {raw_path}", file=sys.stderr)
        return 2

    with raw_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    details = data.get("details", [])

    failures = []
    for r in details:
        s = r.get("scores")
        if not s:
            continue
        if s.get("pedagogy_score", 5) < args.threshold:
            failures.append(r)

    if not failures:
        print(f"No Pedagogy failures below {args.threshold}.")
        return 0

    # Bucketize
    bucket_counts = defaultdict(int)
    bucket_examples = defaultdict(list)
    uncategorized = []
    for r in failures:
        fb = r["scores"].get("feedback_notes", "")
        tags = bucket(fb)
        if not tags:
            uncategorized.append(r)
        for t in tags:
            bucket_counts[t] += 1
            bucket_examples[t].append(r)

    # Render markdown report
    lines = []
    lines.append(f"# Pedagogy Failure Inspection — {data.get('label','?')}")
    lines.append(f"**Source:** `{raw_path.name}`  ")
    lines.append(f"**Threshold:** Ped < {args.threshold}  ")
    lines.append(f"**Failures found:** {len(failures)} of {len(details)} scored rows")
    lines.append("")
    lines.append("## Bucket distribution (keyword pattern match — multi-label, sums > total)")
    lines.append("")
    lines.append("| Bucket | Count | % of failures |")
    lines.append("|---|---:|---:|")
    for name in sorted(bucket_counts, key=bucket_counts.get, reverse=True):
        pct = 100 * bucket_counts[name] / len(failures)
        lines.append(f"| `{name}` | {bucket_counts[name]} | {pct:.0f}% |")
    if uncategorized:
        lines.append(f"| `(uncategorized)` | {len(uncategorized)} | {100*len(uncategorized)/len(failures):.0f}% |")
    lines.append("")
    lines.append("## Per-row detail")
    lines.append("")
    lines.append("| id | source | subject | Acc | Ped | Fmt | Buckets | Feedback (first 220 chars) |")
    lines.append("|---|---|---|---:|---:|---:|---|---|")
    for r in sorted(failures, key=lambda x: (x["source"], x["scores"]["pedagogy_score"])):
        s = r["scores"]
        fb = (s.get("feedback_notes") or "").replace("|", "/").replace("\n", " ")[:220]
        tags = ",".join(bucket(s.get("feedback_notes",""))) or "—"
        lines.append(f"| {r['id']} | {r['source']} | {r['subject']} | {s['accuracy_score']} | {s['pedagogy_score']} | {s['formatting_score']} | {tags} | {fb} |")

    if uncategorized:
        lines.append("")
        lines.append("## Uncategorized — full feedback dump")
        for r in uncategorized:
            lines.append("")
            lines.append(f"### {r['source']}/{r['id']} ({r['subject']}) — Ped {r['scores']['pedagogy_score']}")
            lines.append("")
            lines.append("> " + (r['scores'].get('feedback_notes') or '').replace("\n", "\n> "))

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {len(failures)} failures categorized -> {out_path}")
    print(f"Top buckets: {dict(sorted(bucket_counts.items(), key=lambda x: -x[1])[:3])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
