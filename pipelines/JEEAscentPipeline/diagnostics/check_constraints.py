"""Check all indexes, constraints, and data anomalies on jee_question_bank.

We need to confirm whether a unique constraint like (exam_paper_id, nta_question_id)
was ever present and later dropped. If one exists today the dedup plan is unnecessary;
if not, we need to add it (after dedup).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            print("=" * 80)
            print("1. Indexes on jee_question_bank")
            print("=" * 80)
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'jee_question_bank'
                ORDER BY indexname;
            """)
            for r in cur.fetchall():
                print(f"  {r['indexname']}")
                print(f"    {r['indexdef']}")

            print()
            print("=" * 80)
            print("2. Constraints on jee_question_bank (from pg_constraint)")
            print("=" * 80)
            cur.execute("""
                SELECT con.conname AS constraint_name,
                       con.contype AS type_code,
                       pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con
                JOIN pg_class cls ON cls.oid = con.conrelid
                WHERE cls.relname = 'jee_question_bank'
                ORDER BY con.conname;
            """)
            for r in cur.fetchall():
                print(f"  {r['constraint_name']}  ({r['type_code']})")
                print(f"    {r['definition']}")

            print()
            print("=" * 80)
            print("3. NULL counts on proposed unique-key columns")
            print("=" * 80)
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE exam_paper_id IS NULL) AS null_paper,
                    COUNT(*) FILTER (WHERE nta_question_id IS NULL) AS null_nta,
                    COUNT(*) FILTER (WHERE exam_paper_id IS NULL OR nta_question_id IS NULL) AS null_any
                FROM jee_question_bank;
            """)
            for r in cur.fetchall():
                print(f"  total={r['total']}  null_paper={r['null_paper']}  "
                      f"null_nta={r['null_nta']}  null_either={r['null_any']}")

            print()
            print("=" * 80)
            print("4. Duplicate groups by (exam_paper_id, nta_question_id) vs "
                  "(dateofexam, shift, nta_question_id)")
            print("=" * 80)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE dup_by_paper > 1) AS groups_dup_by_paper,
                    COUNT(*) FILTER (WHERE dup_by_date > 1) AS groups_dup_by_date
                FROM (
                    SELECT
                        COUNT(*) FILTER (WHERE nta_question_id IS NOT NULL AND exam_paper_id IS NOT NULL) AS dup_by_paper_n,
                        COUNT(*)                                                                        AS dup_by_paper,
                        COUNT(*)                                                                        AS dup_by_date
                    FROM jee_question_bank
                    GROUP BY exam_paper_id, nta_question_id
                    HAVING COUNT(*) > 1
                ) s_p,
                LATERAL (
                    SELECT 1
                ) _;
            """)
            # Simpler counts — two separate queries
            cur.execute("""
                SELECT COUNT(*) AS groups
                FROM (
                    SELECT 1 FROM jee_question_bank
                    WHERE nta_question_id IS NOT NULL
                    GROUP BY exam_paper_id, nta_question_id
                    HAVING COUNT(*) > 1
                ) s;
            """)
            for r in cur.fetchall():
                print(f"  dup groups by (exam_paper_id, nta_question_id): {r['groups']}")

            cur.execute("""
                SELECT COUNT(*) AS groups
                FROM (
                    SELECT 1 FROM jee_question_bank
                    WHERE nta_question_id IS NOT NULL
                    GROUP BY dateofexam, shift, nta_question_id
                    HAVING COUNT(*) > 1
                ) s;
            """)
            for r in cur.fetchall():
                print(f"  dup groups by (dateofexam, shift, nta_question_id): {r['groups']}")

            print()
            print("=" * 80)
            print("5. Rows with NULL nta_question_id (cannot use as part of unique key)")
            print("=" * 80)
            cur.execute("""
                SELECT year, COUNT(*) AS null_nta_rows
                FROM jee_question_bank
                WHERE nta_question_id IS NULL
                GROUP BY year
                ORDER BY year;
            """)
            rows = cur.fetchall()
            if not rows:
                print("  (none)")
            else:
                for r in rows:
                    print(f"  year={r['year']}  null_nta_rows={r['null_nta_rows']}")


if __name__ == "__main__":
    main()
