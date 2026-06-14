"""Build a focused NCERT figure-row eval set for the visual / router-shrink test.

Pulls every NCERT figure-bearing row (has_figure=True, images present) from BOTH the frozen
holdout and the NCERT solver-verify set, normalizes to the batch_evaluator record schema, and
writes `holdout_ncert_fig.json`. These are the rows where untuned Flash multi-stage CAN see the
image (unlike JEE figures, which are KI-3-blind). Used to test whether Flash multi-stage handles
NCERT visual well enough to route NCERT figures away from Pro.

Usage: python build_ncert_fig_subset.py
"""
import json
from pathlib import Path

CWD = Path(__file__).resolve().parent
OUT = CWD / "holdout_ncert_fig.json"
NEED = ("source", "id", "subject", "problem_payload", "answer_key", "image_urls", "has_figure")


def _records(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["records"] if isinstance(data, dict) and "records" in data else data


def main():
    pool = {}
    for fname, default_source in [("holdout_eval_set.json", None),
                                  ("solver_verifyset_ncert.json", "ncert")]:
        for r in _records(CWD / fname):
            src = r.get("source", default_source)
            if src != "ncert" or not r.get("has_figure"):
                continue
            imgs = r.get("image_urls") or []
            if not imgs:
                continue  # no image => not a usable visual test row
            rec = {k: r.get(k) for k in NEED}
            rec["source"] = "ncert"
            rec["never_distill"] = r.get("never_distill", False)
            pool[r["id"]] = rec  # dedup by id (verify set already excludes holdout ids)

    records = list(pool.values())
    OUT.write_text(json.dumps({"meta": {"n": len(records), "purpose": "NCERT visual test"},
                               "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    by = Counter(r["subject"] for r in records)
    print(f"Wrote {OUT.name}: {len(records)} NCERT figure rows (with images)")
    print("by subject:", dict(by))


if __name__ == "__main__":
    main()
