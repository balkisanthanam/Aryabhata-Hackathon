"""
Phase V.1 — build stratified solver-verification sets for untuned gemini-3-flash.

Two output files (holdout-compatible record schema so existing tooling can consume them):
  - solver_verifyset_jee.json   (~250 rows; subject x difficulty x figure stratified)
  - solver_verifyset_ncert.json (~150 rows; subject x figure stratified)

Both EXCLUDE the 100 frozen-holdout IDs AND all APPROVED_GOLD IDs (no train/test leak).

JEE rows carry a clean answer_key (MCQ letter / integer) → ARM 1 objective matching.
NCERT rows carry freeform answer_key → ARM 2 LLM-judge accuracy_only.

CLI:
  python build_solver_verifyset.py --jee 250 --ncert 150 [--seed 7] [--force]
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

CWD = Path(__file__).resolve().parent
sys.path.insert(0, str(CWD))
sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))
sys.path.insert(0, str(CWD.parent / "JEEAscentPipeline"))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from jsonl_exporter import build_user_payload  # noqa: E402
from build_holdout_set import _extract_ncert_image_urls  # noqa: E402

HOLDOUT = CWD / "holdout_eval_set.json"
OUT_JEE = CWD / "solver_verifyset_jee.json"
OUT_NCERT = CWD / "solver_verifyset_ncert.json"

# JEE subject names differ from NCERT ('Mathematics' vs 'Maths')
JEE_SUBJECTS = ["Mathematics", "Physics", "Chemistry"]
NCERT_SUBJECTS = ["Maths", "Physics", "Chemistry"]
DIFFICULTIES = ["EASY", "MEDIUM", "HARD"]


def load_excluded_ids():
    """Holdout IDs (per source) — gold is excluded at query time by status filter."""
    ho = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    jee_holdout = {r["id"] for r in ho["records"] if r["source"] == "jee"}
    ncert_holdout = {r["id"] for r in ho["records"] if r["source"] == "ncert"}
    return jee_holdout, ncert_holdout


def fetch_jee(db, exclude_ids: set) -> list:
    q = """
        SELECT id, subject, difficulty, question_content, answer_key,
               (question_content::json->>'has_figure') AS has_figure_flag
        FROM jee_question_bank
        WHERE subject IN ('Mathematics','Physics','Chemistry')
          AND review_status = 'PENDING'
          AND answer_key IS NOT NULL
          AND question_content IS NOT NULL
        ORDER BY id
    """
    out = []
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if row["id"] in exclude_ids:
                    continue
                content = row["question_content"]
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except Exception:
                        content = {}
                row["_content"] = content if isinstance(content, dict) else {}
                row["_has_figure"] = str(row.get("has_figure_flag")).lower() == "true"
                row["_difficulty"] = (row.get("difficulty") or "MEDIUM").upper()
                out.append(row)
    return out


def fetch_ncert(db, exclude_ids: set) -> list:
    q = """
        SELECT q.questionid AS id, c.subject, c.class, q.content, q.answer_key
        FROM questiondata q
        JOIN exercisedata e ON q.exerciseid = e.exerciseid
        JOIN chapterdata c ON e.chapterid = c.chapterid
        WHERE c.subject IN ('Maths','Physics','Chemistry')
          AND q.review_status <> 'APPROVED_GOLD'
          AND q.answer_key IS NOT NULL
          AND q.content IS NOT NULL
        ORDER BY q.questionid
    """
    out = []
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if row["id"] in exclude_ids:
                    continue
                content = row["content"]
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except Exception:
                        content = {}
                row["_content"] = content if isinstance(content, dict) else {}
                row["_has_figure"] = bool(row["_content"].get("has_figure"))
                out.append(row)
    return out


def stratify_jee(rows, total, rng):
    """subject x difficulty x figure, proportional with figure floor."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["subject"], r["_difficulty"], r["_has_figure"])].append(r)
    # Target: even split across subjects, within-subject even across difficulty,
    # and ensure figure-bearing get represented (cap ~25% since pool is figure-sparse).
    per_subject = total // len(JEE_SUBJECTS)
    picked = []
    for subj in JEE_SUBJECTS:
        per_diff = max(1, per_subject // len(DIFFICULTIES))
        for diff in DIFFICULTIES:
            fig_rows = buckets.get((subj, diff, True), [])
            nonfig_rows = buckets.get((subj, diff, False), [])
            rng.shuffle(fig_rows); rng.shuffle(nonfig_rows)
            # aim ~20% figure within each (subject,difficulty) cell, floor of available
            n_fig = min(len(fig_rows), max(0, round(per_diff * 0.20)))
            n_nonfig = min(len(nonfig_rows), per_diff - n_fig)
            picked.extend(fig_rows[:n_fig])
            picked.extend(nonfig_rows[:n_nonfig])
    rng.shuffle(picked)
    return picked


def stratify_ncert(rows, total, rng):
    """subject x figure (no difficulty labels for NCERT)."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["subject"], r["_has_figure"])].append(r)
    per_subject = total // len(NCERT_SUBJECTS)
    picked = []
    for subj in NCERT_SUBJECTS:
        fig_rows = buckets.get((subj, True), [])
        nonfig_rows = buckets.get((subj, False), [])
        rng.shuffle(fig_rows); rng.shuffle(nonfig_rows)
        # include ALL available figure rows (they're scarce + the interesting multimodal test), cap at ~40% of subject quota
        n_fig = min(len(fig_rows), max(1, round(per_subject * 0.40)))
        n_nonfig = min(len(nonfig_rows), per_subject - n_fig)
        picked.extend(fig_rows[:n_fig])
        picked.extend(nonfig_rows[:n_nonfig])
    rng.shuffle(picked)
    return picked


def to_record_jee(r) -> dict:
    return {
        "source": "jee",
        "id": r["id"],
        "subject": "Maths" if r["subject"] == "Mathematics" else r["subject"],
        "difficulty": r["_difficulty"],
        "problem_payload": json.loads(build_user_payload(r["_content"])),
        "answer_key": r["answer_key"],
        "image_urls": [],  # JEE figure_url is NULL (KI-3); nothing to pass
        "has_figure": r["_has_figure"],
    }


def to_record_ncert(r) -> dict:
    image_urls = _extract_ncert_image_urls(r["_content"]) if r["_has_figure"] else []
    return {
        "source": "ncert",
        "id": r["id"],
        "subject": r["subject"],
        "class": r.get("class"),
        "problem_payload": json.loads(build_user_payload(r["_content"])),
        "answer_key": r["answer_key"],
        "image_urls": image_urls,  # NCERT figure images EXIST — pass them (multimodal test)
        "has_figure": r["_has_figure"],
    }


def summarize(records, dims):
    counter = defaultdict(int)
    for rec in records:
        key = tuple(rec.get(d) for d in dims)
        counter[key] += 1
    for key in sorted(counter, key=lambda k: tuple(str(x) for x in k)):
        print(f"    {dict(zip(dims, key))}: {counter[key]}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jee", type=int, default=250)
    p.add_argument("--ncert", type=int, default=150)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    if (OUT_JEE.exists() or OUT_NCERT.exists()) and not args.force:
        print(f"ERROR: output exists; pass --force to overwrite.", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    jee_holdout, ncert_holdout = load_excluded_ids()
    db = JEEExtractionDBWriter()

    print("Fetching JEE pool...")
    jee_rows = fetch_jee(db, jee_holdout)
    print(f"  JEE candidates (PENDING, answer_key, excl holdout): {len(jee_rows)}")
    jee_picked = stratify_jee(jee_rows, args.jee, rng)
    jee_records = [to_record_jee(r) for r in jee_picked]

    print("Fetching NCERT pool...")
    ncert_rows = fetch_ncert(db, ncert_holdout)
    print(f"  NCERT candidates (non-gold, answer_key, excl holdout): {len(ncert_rows)}")
    ncert_picked = stratify_ncert(ncert_rows, args.ncert, rng)
    ncert_records = [to_record_ncert(r) for r in ncert_picked]

    OUT_JEE.write_text(json.dumps({"meta": {"seed": args.seed, "n": len(jee_records)}, "records": jee_records}, indent=2), encoding="utf-8")
    OUT_NCERT.write_text(json.dumps({"meta": {"seed": args.seed, "n": len(ncert_records)}, "records": ncert_records}, indent=2), encoding="utf-8")

    print(f"\nJEE verify set: {len(jee_records)} rows -> {OUT_JEE.name}")
    summarize(jee_records, ["subject", "difficulty", "has_figure"])
    print(f"\nNCERT verify set: {len(ncert_records)} rows -> {OUT_NCERT.name}")
    summarize(ncert_records, ["subject", "has_figure"])

    # Leak check
    jee_ids = {r["id"] for r in jee_records}
    ncert_ids = {r["id"] for r in ncert_records}
    assert not (jee_ids & jee_holdout), "LEAK: JEE verify overlaps holdout"
    assert not (ncert_ids & ncert_holdout), "LEAK: NCERT verify overlaps holdout"
    print("\nLeak check passed (zero holdout overlap).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
