"""Quantify duplicate rows in jee_question_bank.

Hypothesis: extraction ran multiple times per paper, creating duplicate rows with
different stored subjects (and in turn, different tagged chapters on the frontend).

This script reports:
  1. Overall row counts vs unique NTA question IDs per year
  2. Distribution of duplicate-group sizes
  3. How many duplicate groups contain conflicting subjects
  4. Tag-count comparison within duplicate groups (tagged vs untagged)
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def run_query(cur, sql: str):
    cur.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            print("=" * 80)
            print("1. Rows vs unique (dateofexam, shift, nta_question_id) per year")
            print("=" * 80)
            rows = run_query(cur, """
                SELECT
                    year,
                    COUNT(*) AS rows,
                    COUNT(DISTINCT (dateofexam, shift, nta_question_id)) AS unique_keys,
                    COUNT(*) - COUNT(DISTINCT (dateofexam, shift, nta_question_id)) AS duplicate_rows
                FROM jee_question_bank
                GROUP BY year ORDER BY year;
            """)
            for r in rows:
                print(f"  {r['year']}: rows={r['rows']:>6}  unique={r['unique_keys']:>6}  "
                      f"duplicate_rows={r['duplicate_rows']:>6}")

            print()
            print("=" * 80)
            print("2. Distribution of duplicate-group sizes (2024)")
            print("=" * 80)
            rows = run_query(cur, """
                SELECT group_size, COUNT(*) AS num_groups
                FROM (
                    SELECT COUNT(*) AS group_size
                    FROM jee_question_bank
                    WHERE year = 2024
                    GROUP BY dateofexam, shift, nta_question_id
                ) s
                GROUP BY group_size ORDER BY group_size;
            """)
            for r in rows:
                print(f"  {r['group_size']} rows/group : {r['num_groups']:>6} groups")

            print()
            print("=" * 80)
            print("3. Duplicate groups with SUBJECT CONFLICT (2024)")
            print("=" * 80)
            rows = run_query(cur, """
                SELECT
                    COUNT(*) AS groups_with_conflict,
                    SUM(cnt) AS total_rows_in_conflicting_groups
                FROM (
                    SELECT COUNT(*) AS cnt, COUNT(DISTINCT subject) AS subj_count
                    FROM jee_question_bank
                    WHERE year = 2024
                    GROUP BY dateofexam, shift, nta_question_id
                    HAVING COUNT(*) > 1 AND COUNT(DISTINCT subject) > 1
                ) s;
            """)
            for r in rows:
                print(f"  groups_with_conflict={r['groups_with_conflict']}  "
                      f"total_rows_in_conflicting_groups={r['total_rows_in_conflicting_groups']}")

            print()
            print("=" * 80)
            print("4. Tag coverage within duplicate groups (2024, top 5 groups sample)")
            print("=" * 80)
            rows = run_query(cur, """
                WITH dups AS (
                    SELECT dateofexam, shift, nta_question_id
                    FROM jee_question_bank
                    WHERE year = 2024
                    GROUP BY dateofexam, shift, nta_question_id
                    HAVING COUNT(*) > 1
                    LIMIT 5
                )
                SELECT q.id, q.dateofexam::text AS dateofexam, q.shift, q.nta_question_id,
                       q.subject,
                       (SELECT COUNT(*) FROM jee_question_tags t WHERE t.question_id = q.id) AS tag_count,
                       LEFT(q.question_content->>'raw_text', 80) AS preview
                FROM jee_question_bank q
                JOIN dups ON q.dateofexam = dups.dateofexam
                         AND q.shift = dups.shift
                         AND q.nta_question_id = dups.nta_question_id
                WHERE q.year = 2024
                ORDER BY q.dateofexam, q.shift, q.nta_question_id, q.id;
            """)
            prev_key = None
            for r in rows:
                key = (r['dateofexam'], r['shift'], r['nta_question_id'])
                if key != prev_key:
                    print(f"\n  Group: {r['dateofexam']} shift={r['shift']} nta={r['nta_question_id']}")
                    prev_key = key
                print(f"    id={r['id']:>5}  subject={r['subject']:<12}  tags={r['tag_count']}  "
                      f"preview={r['preview'][:60]}")

            print()
            print("=" * 80)
            print("5. Per-year tagged count breakdown (tagged vs duplicate-inflated)")
            print("=" * 80)
            rows = run_query(cur, """
                SELECT year,
                    COUNT(DISTINCT q.id) AS total_rows,
                    COUNT(DISTINCT q.id) FILTER (
                        WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
                    ) AS tagged_rows,
                    COUNT(DISTINCT (dateofexam, shift, nta_question_id)) AS unique_questions
                FROM jee_question_bank q
                GROUP BY year ORDER BY year;
            """)
            for r in rows:
                print(f"  {r['year']}: total={r['total_rows']:>6}  tagged={r['tagged_rows']:>6}  "
                      f"unique={r['unique_questions']:>6}")


if __name__ == "__main__":
    main()
