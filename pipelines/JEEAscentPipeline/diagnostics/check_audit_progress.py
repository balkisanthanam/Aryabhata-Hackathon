"""Peek at how many 2023 rows have changed subject so far."""
from __future__ import annotations
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def main():
    preds = json.load(open("logs/audit_2023_preds.json", encoding="utf-8"))
    expected_changes = [p for p in preds if p["stored"] != p["predicted"]]
    print(f"Expected total changes: {len(expected_changes)}")

    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Count how many of the expected-change rows ALREADY have the predicted subject
            ids = [p["id"] for p in expected_changes]
            preds_by_id = {p["id"]: p["predicted"] for p in expected_changes}
            cur.execute(
                "SELECT id, subject FROM jee_question_bank WHERE id = ANY(%s::int[])",
                (ids,),
            )
            applied = 0
            not_yet = 0
            for r in cur.fetchall():
                if r["subject"] == preds_by_id[r["id"]]:
                    applied += 1
                else:
                    not_yet += 1
            print(f"Already applied: {applied}")
            print(f"Not yet applied: {not_yet}")


if __name__ == "__main__":
    main()
