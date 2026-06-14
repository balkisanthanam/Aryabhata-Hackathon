"""One-shot: add the missing unique constraint to jee_question_bank.

Safe-guard against future duplicates from re-running the extraction pipeline.
Idempotent — skips if the constraint already exists.
"""

from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1
                FROM pg_constraint con
                JOIN pg_class cls ON cls.oid = con.conrelid
                WHERE cls.relname = 'jee_question_bank'
                  AND con.conname = 'uq_jee_qbank_paper_nta'
            """)
            if cur.fetchone():
                print("Constraint uq_jee_qbank_paper_nta already exists — nothing to do.")
                return

            print("Adding UNIQUE constraint uq_jee_qbank_paper_nta "
                  "ON jee_question_bank (exam_paper_id, nta_question_id)...")
            cur.execute("""
                ALTER TABLE jee_question_bank
                ADD CONSTRAINT uq_jee_qbank_paper_nta
                UNIQUE (exam_paper_id, nta_question_id)
            """)
            print("OK — constraint added.")


if __name__ == "__main__":
    main()
