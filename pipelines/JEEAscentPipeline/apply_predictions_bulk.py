"""Apply saved subject predictions in bulk (skips remaining rows after a partial run).

Reads a JSON dump from subject_auditor_perq.py's --save-predictions flag and applies
any not-yet-applied subject changes using bulk SQL (one UPDATE per target subject,
one DELETE for tags/embeddings via ANY(%s)).

Usage:
    python apply_predictions_bulk.py --predictions logs/audit_2023_preds.json --yes
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    preds = json.load(open(args.predictions, encoding="utf-8"))
    expected = [p for p in preds if p["predicted"] and p["stored"] != p["predicted"]]
    print(f"Expected subject changes in file: {len(expected)}")

    db = JEEExtractionDBWriter()
    # Re-read current subjects to find rows that haven't been applied yet.
    ids = [p["id"] for p in expected]
    preds_by_id = {p["id"]: p["predicted"] for p in expected}

    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, subject FROM jee_question_bank WHERE id = ANY(%s::int[])",
                (ids,),
            )
            current = {r["id"]: r["subject"] for r in cur.fetchall()}

    remaining = [
        {"id": qid, "predicted": preds_by_id[qid]}
        for qid in ids
        if current.get(qid) != preds_by_id[qid]
    ]
    print(f"Remaining not-yet-applied: {len(remaining)}")
    if not remaining:
        print("Nothing to do — everything already applied.")
        return

    if not args.yes:
        print("Press Enter to apply or Ctrl+C to abort.")
        input()

    # Bulk apply.
    by_subject: Dict[str, List[int]] = {}
    for r in remaining:
        by_subject.setdefault(r["predicted"], []).append(r["id"])
    all_ids = [r["id"] for r in remaining]

    stats = {"subject_changed": 0, "tags_deleted": 0, "embeddings_deleted": 0}
    with db.connection() as conn:
        with conn.cursor() as cur:
            for subj, id_list in by_subject.items():
                cur.execute(
                    "UPDATE jee_question_bank "
                    "SET subject = %s, difficulty = NULL, "
                    "    difficulty_confidence = NULL, pattern_label = NULL "
                    "WHERE id = ANY(%s::int[])",
                    (subj, id_list),
                )
                stats["subject_changed"] += cur.rowcount
            cur.execute(
                "DELETE FROM jee_question_tags WHERE question_id = ANY(%s::int[])",
                (all_ids,),
            )
            stats["tags_deleted"] = cur.rowcount
            cur.execute(
                "DELETE FROM jee_question_embeddings WHERE question_id = ANY(%s::int[])",
                (all_ids,),
            )
            stats["embeddings_deleted"] = cur.rowcount

    print("Applied:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
