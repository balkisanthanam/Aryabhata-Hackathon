"""
Phase F.1 of M3 Ship Plan — diff JEE Maths non-fig failures between v1 (Phase A)
and v2 (Phase B) to classify the regression.

Hypotheses to distinguish:
  (a) Capacity displacement — v2 lost rows that v1 got right (real LoRA capacity issue).
  (b) Sampling noise — v2 failed on DIFFERENT rows than v1 (no net regression in same row).
  (c) Judge non-determinism — same rows fail/pass inconsistently across runs.

Reads:
  - runs/Experiment_Run_20260526_193008.md's RAW JSON  (v1 + Phase A)
  - runs/Experiment_Run_20260527_131515.md's RAW JSON  (v2)

Writes:
  - runs/_JEE_MATHS_REGRESSION_DIFF_v1_vs_v2.md
"""
import json
import sys
from pathlib import Path

CWD = Path(__file__).resolve().parent
V1_RAW = CWD / "runs" / "Experiment_Run_20260526_193008_RAW.json"
V2_RAW = CWD / "runs" / "Experiment_Run_20260527_131515_RAW.json"
OUT = CWD / "runs" / "_JEE_MATHS_REGRESSION_DIFF_v1_vs_v2.md"


def load_jee_maths_nonfig(raw_path: Path) -> dict:
    with raw_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for r in data["details"]:
        if r.get("source") == "jee" and r.get("subject") == "Maths" and not r.get("has_figure"):
            out[r["id"]] = r
    return out


def main() -> int:
    if not V1_RAW.exists() or not V2_RAW.exists():
        print(f"ERROR: one of the RAW files missing", file=sys.stderr)
        return 2

    v1 = load_jee_maths_nonfig(V1_RAW)
    v2 = load_jee_maths_nonfig(V2_RAW)

    ids = sorted(set(v1) | set(v2))
    classifications = {"v1_pass_v2_fail": [], "v1_fail_v2_pass": [], "both_fail": [], "both_pass": []}

    rows = []
    for qid in ids:
        r1 = v1.get(qid)
        r2 = v2.get(qid)
        s1 = r1.get("scores") if r1 else None
        s2 = r2.get("scores") if r2 else None
        acc1 = s1.get("accuracy_score") if s1 else None
        acc2 = s2.get("accuracy_score") if s2 else None
        pass1 = (acc1 == 5) if acc1 is not None else None
        pass2 = (acc2 == 5) if acc2 is not None else None

        if pass1 is None or pass2 is None:
            bucket = "missing"
        elif pass1 and pass2:
            bucket = "both_pass"
        elif pass1 and not pass2:
            bucket = "v1_pass_v2_fail"  # REGRESSION
        elif not pass1 and pass2:
            bucket = "v1_fail_v2_pass"
        else:
            bucket = "both_fail"

        if bucket in classifications:
            classifications[bucket].append(qid)
        rows.append({"qid": qid, "v1_acc": acc1, "v2_acc": acc2, "bucket": bucket,
                     "v1_fb": (s1 or {}).get("feedback_notes", "") if s1 else "",
                     "v2_fb": (s2 or {}).get("feedback_notes", "") if s2 else ""})

    lines = []
    lines.append("# JEE Maths Non-Figure Regression Diff — v1 (Phase A) vs v2 (Phase B)")
    lines.append("")
    lines.append(f"**v1 source:** `{V1_RAW.name}` (Phase A: v1 endpoint + schema + extended router)")
    lines.append(f"**v2 source:** `{V2_RAW.name}` (Phase B: v2 endpoint + schema + extended router)")
    lines.append("")
    lines.append(f"**Total JEE Maths non-fig rows:** {len(ids)}")
    lines.append("")
    lines.append("## Bucket counts")
    lines.append("")
    lines.append("| Bucket | Count | Interpretation |")
    lines.append("|---|---:|---|")
    lines.append(f"| both_pass | {len(classifications['both_pass'])} | Stable wins (no concern) |")
    lines.append(f"| both_fail | {len(classifications['both_fail'])} | Stable losses (hard rows — not v2 regression) |")
    lines.append(f"| v1_fail_v2_pass | {len(classifications['v1_fail_v2_pass'])} | **v2 improved** on these |")
    lines.append(f"| **v1_pass_v2_fail** | **{len(classifications['v1_pass_v2_fail'])}** | **REAL REGRESSION — v2 lost rows v1 got right** |")
    lines.append("")
    lines.append("## Classification verdict")
    lines.append("")
    n_reg = len(classifications["v1_pass_v2_fail"])
    n_improve = len(classifications["v1_fail_v2_pass"])
    if n_reg > 0 and n_reg > n_improve:
        verdict = "**(a) Real capacity displacement.** v2 lost more rows than it gained on this bucket — LoRA capacity hypothesis supported."
    elif n_reg > 0 and n_reg == n_improve:
        verdict = "**(b/c) Sampling-noise or judge-non-determinism.** Net is wash; row IDs shifted but no net regression."
    elif n_reg == 0:
        verdict = "**No regression — judge noise or eval artifact.** Same rows pass; numbers shifted due to other buckets."
    else:
        verdict = f"**Mixed.** {n_reg} regressed, {n_improve} improved — net change small, dominant effect may be sampling."
    lines.append(verdict)
    lines.append("")
    lines.append("## Per-row detail")
    lines.append("")
    lines.append("| qid | v1 Acc | v2 Acc | Bucket | v1 feedback (first 180) | v2 feedback (first 180) |")
    lines.append("|---|---:|---:|---|---|---|")
    for r in rows:
        fb1 = (r["v1_fb"] or "").replace("|", "/").replace("\n", " ")[:180]
        fb2 = (r["v2_fb"] or "").replace("|", "/").replace("\n", " ")[:180]
        lines.append(f"| {r['qid']} | {r['v1_acc']} | {r['v2_acc']} | {r['bucket']} | {fb1} | {fb2} |")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: wrote {OUT}")
    print(f"  v1_pass_v2_fail (REGRESSIONS): {len(classifications['v1_pass_v2_fail'])}")
    print(f"  v1_fail_v2_pass (improvements): {len(classifications['v1_fail_v2_pass'])}")
    print(f"  both_pass: {len(classifications['both_pass'])}")
    print(f"  both_fail: {len(classifications['both_fail'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
