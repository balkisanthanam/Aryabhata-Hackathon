"""Inspect sample rows from each raw_text quality bucket to design the repair."""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


BUCKETS = [
    ("A", "starts with |continued|/|thought|/```json",
     "LTRIM(question_content->>'raw_text') ILIKE '|continued|%%' "
     "OR LTRIM(question_content->>'raw_text') ILIKE '|thought|%%' "
     "OR LTRIM(question_content->>'raw_text') ILIKE '```json%%'"),
    ("B", "embedded \"raw_text\": mid-string",
     "question_content->>'raw_text' LIKE '%%\"raw_text\"%%' "
     "AND LTRIM(question_content->>'raw_text') NOT LIKE '{%%\"raw_text\"%%'"),
    ("C", "starts with reasoning prose",
     "question_content->>'raw_text' ILIKE 'Wait,%%' "
     "OR question_content->>'raw_text' ILIKE 'Actually,%%' "
     "OR question_content->>'raw_text' ILIKE 'Let me%%' "
     "OR question_content->>'raw_text' ILIKE 'Final check%%' "
     "OR question_content->>'raw_text' ILIKE 'Option %%'"),
    ("D", "literal \\_ escape",
     "question_content->>'raw_text' LIKE '%%\\_\\_%%'"),
    ("F", "contains ```",
     "question_content->>'raw_text' LIKE '%%```%%'"),
    ("G", "starts with close brace/bracket",
     "LTRIM(question_content->>'raw_text') LIKE '}%%' "
     "OR LTRIM(question_content->>'raw_text') LIKE ']%%'"),
]


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for code, label, pred in BUCKETS:
                print("\n" + "=" * 80)
                print(f"BUCKET {code}: {label}")
                print("=" * 80)
                cur.execute(f"""
                    SELECT id, year, subject,
                           LEFT(question_content->>'raw_text', 350) AS preview,
                           LENGTH(question_content->>'raw_text') AS total_len
                    FROM jee_question_bank
                    WHERE {pred}
                    ORDER BY random()
                    LIMIT 5
                """)
                for r in cur.fetchall():
                    print(f"\n  id={r['id']} year={r['year']} subj={r['subject']} len={r['total_len']}")
                    preview = (r['preview'] or '').replace(chr(10), '\\n')
                    print(f"  RAW: {preview}")


if __name__ == "__main__":
    main()
