"""Smoke test: verify uq_jee_qbank_paper_nta blocks a duplicate insert, and
that bulk_insert_questions now silently skips duplicates via the new ON CONFLICT target."""

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
            cur.execute("""
                SELECT q.id, q.exam_paper_id, q.nta_question_id, q.subject, q.year,
                       q.dateofexam::text AS dateofexam, q.shift, q.answer_key,
                       q.question_content
                FROM jee_question_bank q
                LIMIT 1
            """)
            sample = dict(cur.fetchone())
            print(f"Sample row: id={sample['id']} paper={sample['exam_paper_id']} "
                  f"nta={sample['nta_question_id']}")

    fake_paper = {
        "id": sample["exam_paper_id"],
        "year": sample["year"],
        "dateofexam": sample["dateofexam"],
        "shift": sample["shift"],
    }
    fake_q = {
        "nta_question_id": sample["nta_question_id"],
        "subject": sample["subject"],
        "section": "MCQ",
        "question_content": sample["question_content"],
        "answer_key": sample["answer_key"],
    }

    before_count = _count(db, sample["exam_paper_id"])
    print(f"Rows for paper {sample['exam_paper_id']} BEFORE insert attempt: {before_count}")

    inserted = db.bulk_insert_questions([fake_q], fake_paper)
    print(f"bulk_insert_questions returned (rowcount): {inserted}")

    after_count = _count(db, sample["exam_paper_id"])
    print(f"Rows for paper {sample['exam_paper_id']} AFTER insert attempt:  {after_count}")

    if after_count == before_count:
        print("\nOK — constraint is blocking duplicates cleanly.")
    else:
        print("\nFAIL — row count changed! constraint or ON CONFLICT target is wrong.")


def _count(db, paper_id):
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jee_question_bank WHERE exam_paper_id = %s", (paper_id,))
            return cur.fetchone()[0]


if __name__ == "__main__":
    main()
