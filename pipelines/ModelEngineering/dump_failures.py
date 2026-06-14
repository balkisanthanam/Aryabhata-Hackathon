"""dump_failures.py — turn any eval/verify artifact into a queryable failures .md.

Reads either:
  (1) batch_evaluator RAW.json  — top-level dict with `details` list, each having
      {id, source, subject, has_figure, never_distill, scores{accuracy_score,
       pedagogy_score, formatting_score, total_score, feedback_notes, is_pass,
       is_gold}, generator_error}
  (2) Phase V verify checkpoint .jsonl — one flat record per line:
        JEE  : {id, subject, difficulty, has_figure, answer_key, final_answer, correct, error}
        NCERT: {id, subject, has_figure, accuracy_score, correct, error}

Emits runs/_FAILURES_<label>.md: a per-bucket summary count table followed by one
detail row per failure, sorted by (source, subject, has_figure). Every row carries the
question `id` so you can re-query the source row.

A "failure" is:
  - RAW.json  : scores.is_pass is False, OR generator_error set. Acc-miss flagged separately.
  - verify    : correct is False, OR error set.

Usage:
  python dump_failures.py runs/Experiment_Run_20260526_193008_RAW.json
  python dump_failures.py runs/_verify_solver_jee_ckpt.jsonl --source jee
  python dump_failures.py <artifact> --label MyLabel --out runs/_FAILURES_x.md
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone


def _load(path):
    """Return (records, kind) where kind in {'raw','verify'}."""
    if path.endswith(".jsonl"):
        recs = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
        return recs, "verify"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "details" in data:
        return data["details"], "raw"
    if isinstance(data, list):
        # bare list of detail dicts
        return data, "raw" if (data and "scores" in data[0]) else "verify"
    raise SystemExit(f"Unrecognized artifact shape: {path}")


def _norm(rec, kind, source_hint):
    """Normalize one record to a common dict; return None if it's a PASS."""
    if kind == "raw":
        sc = rec.get("scores") or {}
        gen_err = rec.get("generator_error")
        is_pass = sc.get("is_pass")
        if is_pass is None:  # no score + no error => can't classify; treat error as fail
            is_pass = gen_err is None
        if is_pass and not gen_err:
            return None
        return {
            "id": rec.get("id"),
            "source": rec.get("source", source_hint or "?"),
            "subject": rec.get("subject", "?"),
            "difficulty": rec.get("difficulty", ""),
            "has_figure": bool(rec.get("has_figure")),
            "acc": sc.get("accuracy_score"),
            "ped": sc.get("pedagogy_score"),
            "fmt": sc.get("formatting_score"),
            "answer_key": "",
            "final_answer": "",
            "note": (gen_err or sc.get("feedback_notes") or "").replace("\n", " ").strip(),
        }
    # verify
    err = rec.get("error")
    correct = rec.get("correct")
    if correct and not err:
        return None
    return {
        "id": rec.get("id"),
        "source": source_hint or "?",
        "subject": rec.get("subject", "?"),
        "difficulty": rec.get("difficulty", ""),
        "has_figure": bool(rec.get("has_figure")),
        "acc": rec.get("accuracy_score"),
        "ped": None,
        "fmt": None,
        "answer_key": str(rec.get("answer_key", "")).replace("\n", " ")[:60],
        "final_answer": str(rec.get("final_answer", "")).replace("\n", " ")[:60],
        "note": (err or "").replace("\n", " ").strip(),
    }


def _bucket(r):
    fig = "fig" if r["has_figure"] else "nofig"
    return f"{r['source']}/{r['subject']}/{fig}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--label", default=None, help="report label (default: artifact basename)")
    ap.add_argument("--source", default=None, help="source hint for verify ckpts (jee|ncert)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    label = args.label or os.path.splitext(os.path.basename(args.artifact))[0]
    recs, kind = _load(args.artifact)

    # infer source hint from filename for verify ckpts
    src_hint = args.source
    if src_hint is None and kind == "verify":
        lname = args.artifact.lower()
        src_hint = "jee" if "jee" in lname else ("ncert" if "ncert" in lname else None)

    total_by_bucket = defaultdict(int)
    fails = []
    for rec in recs:
        # bucket totals use source hint too
        src = rec.get("source", src_hint or "?")
        fig = "fig" if rec.get("has_figure") else "nofig"
        total_by_bucket[f"{src}/{rec.get('subject','?')}/{fig}"] += 1
        n = _norm(rec, kind, src_hint)
        if n is not None:
            fails.append(n)

    fails.sort(key=lambda r: (r["source"], r["subject"], not r["has_figure"], r["id"] or 0))
    fail_by_bucket = defaultdict(int)
    for r in fails:
        fail_by_bucket[_bucket(r)] += 1

    out = args.out or os.path.join("runs", f"_FAILURES_{label}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lines = []
    lines.append(f"# Failures — {label}")
    lines.append("")
    lines.append(f"> Source: `{args.artifact}` ({kind})  ·  generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"> Total records: {len(recs)}  ·  Failures: {len(fails)}")
    lines.append("")
    lines.append("## Per-bucket summary (failures / total)")
    lines.append("")
    lines.append("| bucket | fail | total | fail% |")
    lines.append("|---|---:|---:|---:|")
    for b in sorted(total_by_bucket):
        t = total_by_bucket[b]
        f = fail_by_bucket.get(b, 0)
        lines.append(f"| {b} | {f} | {t} | {100*f/t:.0f}% |")
    lines.append("")
    lines.append("## Failure detail")
    lines.append("")
    if kind == "raw":
        lines.append("| id | source | subject | fig | acc | ped | fmt | judge feedback |")
        lines.append("|---|---|---|---|---:|---:|---:|---|")
        for r in fails:
            lines.append(
                f"| {r['id']} | {r['source']} | {r['subject']} | {'Y' if r['has_figure'] else ''} "
                f"| {r['acc']} | {r['ped']} | {r['fmt']} | {r['note'][:300]} |"
            )
    else:
        lines.append("| id | source | subject | diff | fig | answer_key | model_answer | acc | note |")
        lines.append("|---|---|---|---|---|---|---|---:|---|")
        for r in fails:
            lines.append(
                f"| {r['id']} | {r['source']} | {r['subject']} | {r['difficulty']} "
                f"| {'Y' if r['has_figure'] else ''} | {r['answer_key']} | {r['final_answer']} "
                f"| {r['acc'] if r['acc'] is not None else ''} | {r['note'][:120]} |"
            )
    lines.append("")

    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Wrote {out}  ({len(fails)} failures / {len(recs)} records)")


if __name__ == "__main__":
    main()
