"""Prepare bad/incomplete 2024 rows for Pro-pipeline re-extraction.

Criteria for "bad":
  1. raw_text starts mid-formula (Class C1-style truncation)
     — known rep: id=392  ("1}{2} \\sin \\theta ...")
     — heuristic: first non-space char is '}' OR starts with a lowercase letter
                  followed quickly by '}'.
  2. raw_text starts with '[Figure:' — figure-only extraction, question stem missing.
  3. Very short raw_text (< 40 chars) AND no options AND no figure_blob_url.

Dry-run (default) prints a report grouped by exam_paper_id.
Run with --apply to actually:
  - DELETE the bad rows from jee_question_bank
  - UPDATE exam_papers.extraction_status back to 'PENDING' for affected papers
  - REMOVE the matching checkpoint JSON files so the pipeline re-runs them

After --apply, run:
  python jee_extraction_pipeline.py --paper-ids <comma-separated-list>
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


# Note: jsonb_array_length(options) = 0 captures "no options"
BAD_ROW_SQL = """
WITH candidates AS (
  SELECT q.id, q.exam_paper_id, q.year, q.dateofexam::text AS dateofexam,
         q.shift, q.subject,
         (q.question_content->>'question_number')::text AS question_number,
         q.question_content->>'raw_text' AS raw_text,
         COALESCE(jsonb_array_length(q.question_content->'options'), 0) AS n_opts,
         q.question_content->>'has_figure' AS has_figure,
         q.question_content->>'figure_blob_url' AS figure_blob_url
  FROM jee_question_bank q
  WHERE q.year = 2024
)
SELECT *, CASE
  WHEN LTRIM(raw_text) LIKE '[Figure:%%' THEN 'B_figure_only'
  WHEN LTRIM(raw_text) LIKE '}%%' THEN 'A_truncated_open_brace'
  WHEN raw_text ~ '^[a-z][})]' THEN 'A_truncated_mid_formula'
  WHEN LENGTH(raw_text) < 40
       AND n_opts = 0
       AND (figure_blob_url IS NULL OR figure_blob_url = '') THEN 'C_short_no_opts_no_fig'
  ELSE NULL END AS bucket
FROM candidates
WHERE
     LTRIM(raw_text) LIKE '[Figure:%%'
  OR LTRIM(raw_text) LIKE '}%%'
  OR raw_text ~ '^[a-z][})]'
  OR (LENGTH(raw_text) < 40
      AND n_opts = 0
      AND (figure_blob_url IS NULL OR figure_blob_url = ''))
ORDER BY exam_paper_id, dateofexam, shift, question_number NULLS LAST
"""


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="DANGER: actually delete rows, reset paper status, delete checkpoints")
    return p.parse_args()


def short(s, n=180):
    return (s or "").replace("\n", " ")[:n]


def main():
    args = parse_args()

    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(BAD_ROW_SQL)
            rows = [dict(r) for r in cur.fetchall()]

            if not rows:
                print("No bad rows found.")
                return

            # Group by paper + bucket
            by_paper = {}
            for r in rows:
                by_paper.setdefault(r["exam_paper_id"], []).append(r)

            print(f"Found {len(rows)} bad rows across {len(by_paper)} paper(s).\n")

            for pid in sorted(by_paper):
                group = by_paper[pid]
                g0 = group[0]
                print("-" * 90)
                print(
                    f"  paper_id={pid}  ({g0['dateofexam']} S{g0['shift']})  "
                    f"{len(group)} bad row(s)"
                )
                for r in group:
                    print(
                        f"    id={r['id']}  subj={r['subject']:<11}  "
                        f"q#={r['question_number']}  bucket={r['bucket']}  "
                        f"raw_len={len(r['raw_text'] or '')}  n_opts={r['n_opts']}"
                    )
                    print(f"      RAW: {short(r['raw_text'], 200)}")

            paper_ids = sorted(by_paper.keys())
            ids_csv = ",".join(str(p) for p in paper_ids)

            print("\n" + "=" * 90)
            print(f"Affected paper_ids: {ids_csv}")
            print("=" * 90)

            if not args.apply:
                print("\n(dry-run — no changes made. Re-run with --apply to execute.)")
                print("\nAfter --apply, run:")
                print(f"  python jee_extraction_pipeline.py --paper-ids {ids_csv}")
                return

            # ────────────────── APPLY ──────────────────
            print("\n>>> APPLYING changes ...")
            row_ids = [r["id"] for r in rows]

            # 1. Delete bad rows (tags + embeddings cascade via FK, but be explicit)
            cur.execute("DELETE FROM jee_question_tags WHERE question_id = ANY(%s)", (row_ids,))
            print(f"    deleted {cur.rowcount} tag rows")
            cur.execute("DELETE FROM jee_question_embeddings WHERE question_id = ANY(%s)", (row_ids,))
            print(f"    deleted {cur.rowcount} embedding rows")
            cur.execute("DELETE FROM jee_question_bank WHERE id = ANY(%s)", (row_ids,))
            print(f"    deleted {cur.rowcount} question_bank rows")

            # 2. Reset paper extraction_status to PENDING
            cur.execute(
                "UPDATE exam_papers SET extraction_status = 'PENDING' WHERE id = ANY(%s)",
                (paper_ids,),
            )
            print(f"    reset {cur.rowcount} exam_papers rows to PENDING")
            conn.commit()

            # 3. Delete checkpoint JSONs (Pro pipeline uses 'paper_<id>.json')
            checkpoint_dir = SCRIPT_DIR / "checkpoints"
            removed = 0
            for pid in paper_ids:
                cp = checkpoint_dir / f"paper_{pid}.json"
                if cp.exists():
                    cp.unlink()
                    removed += 1
            print(f"    removed {removed} checkpoint file(s)")

            print("\nDone. Now run:")
            print(f"  python jee_extraction_pipeline.py --paper-ids {ids_csv}")


if __name__ == "__main__":
    main()
