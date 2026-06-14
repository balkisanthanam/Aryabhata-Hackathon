"""
W0 — Read-only verification of the Gold Set state machine.

Inspects the live DB to settle the migration ambiguity before any pipeline run:
- Does `questiondata` carry the state-machine columns? What is review_status' default?
- review_status distribution on `questiondata` (NCERT) and `jee_question_bank` (JEE).
- Any CHECK constraint enumerating valid statuses.

ZERO writes. ZERO Gemini calls. Safe to run anytime.
"""

import sys
from pathlib import Path

cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
sys.path.insert(0, str(extraction_dir))

from db_client import DatabaseClient


def hr(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    db = DatabaseClient(use_managed_identity=True)
    with db.connect() as conn:
        with conn.cursor() as cur:

            hr("1. questiondata — state-machine columns")
            cur.execute(
                """
                SELECT column_name, data_type, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'questiondata'
                  AND column_name IN ('review_status','is_generated','retry_count','answer_key')
                ORDER BY column_name
                """
            )
            rows = cur.fetchall()
            if not rows:
                print("  (none present — NCERT migration NOT applied)")
            for c in rows:
                print(f"  {c[0]:<16} type={c[1]:<20} default={str(c[2]):<24} nullable={c[3]}")

            hr("2. questiondata — review_status distribution")
            try:
                cur.execute(
                    "SELECT COALESCE(review_status,'<NULL>'), COUNT(*) "
                    "FROM questiondata GROUP BY review_status ORDER BY 2 DESC"
                )
                for st, n in cur.fetchall():
                    print(f"  {st:<24} {n}")
            except Exception as e:
                conn.rollback()
                print(f"  (could not query: {e})")

            hr("2b. questiondata — rows with a non-NULL solution (cleanse pool)")
            cur.execute("SELECT COUNT(*) FROM questiondata WHERE solution IS NOT NULL")
            print(f"  solution IS NOT NULL: {cur.fetchone()[0]}")

            hr("3. jee_question_bank — review_status distribution")
            try:
                cur.execute(
                    "SELECT COALESCE(review_status,'<NULL>'), COUNT(*) "
                    "FROM jee_question_bank GROUP BY review_status ORDER BY 2 DESC"
                )
                for st, n in cur.fetchall():
                    print(f"  {st:<24} {n}")
            except Exception as e:
                conn.rollback()
                print(f"  (could not query: {e})")

            hr("3b. jee_question_bank — generated rows with a solution")
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM jee_question_bank "
                    "WHERE solution IS NOT NULL AND is_generated = TRUE"
                )
                print(f"  is_generated=TRUE AND solution IS NOT NULL: {cur.fetchone()[0]}")
            except Exception as e:
                conn.rollback()
                print(f"  (could not query: {e})")

            hr("4. CHECK constraints touching review_status")
            cur.execute(
                """
                SELECT con.conrelid::regclass AS tbl, con.conname, pg_get_constraintdef(con.oid)
                FROM pg_constraint con
                WHERE con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) ILIKE '%review_status%'
                """
            )
            chk = cur.fetchall()
            if not chk:
                print("  (no CHECK constraint on review_status — typos would pass silently)")
            for t, name, ddl in chk:
                print(f"  {t}.{name}: {ddl}")

    print("\nDone. (read-only — nothing was modified)")


if __name__ == "__main__":
    main()
