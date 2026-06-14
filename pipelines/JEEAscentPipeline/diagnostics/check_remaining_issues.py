"""Post-dedup: scan remaining problems that dedup alone can't fix.

Targets:
  - A4: sp2 hybridization question (expected Chemistry)
  - A9/A10: Physics Kinetic Theory chapter — Q20-26 ordering issue
  - Questions with JSON leak pattern still in raw_text
  - Empty raw_text rows
  - Per-chapter counts post-dedup for top chapters
"""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            section("A4 — sp2 hybridization — broader pattern")
            cur.execute("""
                SELECT q.id, q.subject, q.year, q.dateofexam::text AS dateofexam, q.shift,
                       LEFT(q.question_content->>'raw_text', 160) AS preview
                FROM jee_question_bank q
                WHERE q.year = 2024
                  AND (q.question_content->>'raw_text') ILIKE '%sp^2%hybrid%'
                  AND (q.question_content->>'raw_text') ILIKE '%central atom%'
                LIMIT 5
            """)
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                print(f"  id={r['id']}  {r['dateofexam']} s{r['shift']}  subject={r['subject']}")
                print(f"  preview: {r['preview']}")

            section("JSON-leak rows still in DB (2024)")
            cur.execute("""
                SELECT COUNT(*) AS leaked
                FROM jee_question_bank
                WHERE year = 2024
                  AND LTRIM(question_content->>'raw_text') LIKE '{%"raw_text"%'
            """)
            for r in cur.fetchall():
                print(f"  rows with raw_text starting with JSON schema: {r['leaked']}")

            cur.execute("""
                SELECT q.id, q.subject, q.year, q.dateofexam::text AS dateofexam, q.shift,
                       LEFT(q.question_content->>'raw_text', 100) AS preview
                FROM jee_question_bank q
                WHERE q.year = 2024
                  AND LTRIM(q.question_content->>'raw_text') LIKE '{%"raw_text"%'
                ORDER BY q.id
                LIMIT 10
            """)
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                print(f"  id={r['id']} {r['dateofexam']} s{r['shift']} subject={r['subject']}")
                print(f"    {r['preview']}")

            section("Empty raw_text rows (2024)")
            cur.execute("""
                SELECT COUNT(*) AS empty
                FROM jee_question_bank
                WHERE year = 2024
                  AND (question_content->>'raw_text' IS NULL
                    OR TRIM(question_content->>'raw_text') = '')
            """)
            for r in cur.fetchall():
                print(f"  rows with empty raw_text: {r['empty']}")

            section("Per-chapter question counts (2024, top 15 by volume)")
            cur.execute("""
                SELECT cd.class, cd.subject AS chapter_subject, cd.chaptertitle,
                       COUNT(DISTINCT jqt.question_id) AS question_count
                FROM jee_question_tags jqt
                JOIN ncert_concept_hierarchy nch ON nch.id = jqt.concept_id
                JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
                JOIN jee_question_bank q ON q.id = jqt.question_id
                WHERE q.year = 2024
                GROUP BY cd.class, cd.subject, cd.chaptertitle
                ORDER BY question_count DESC
                LIMIT 15
            """)
            for r in cur.fetchall():
                print(f"  {r['question_count']:>4}  Class {r['class']} {r['chapter_subject']:10} - {r['chaptertitle']}")

            section("Physics Kinetic Theory — 2024 questions currently tagged there")
            cur.execute("""
                SELECT q.id, q.subject, q.dateofexam::text AS dateofexam, q.shift,
                       (q.question_content->>'question_number')::int AS q_num,
                       LEFT(q.question_content->>'raw_text', 100) AS preview
                FROM jee_question_bank q
                JOIN jee_question_tags jqt ON jqt.question_id = q.id
                JOIN ncert_concept_hierarchy nch ON nch.id = jqt.concept_id
                JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
                WHERE q.year = 2024
                  AND cd.chaptertitle ILIKE '%Kinetic Theory%'
                GROUP BY q.id, q.subject, q.dateofexam, q.shift,
                         q.question_content
                ORDER BY q.id
                LIMIT 40
            """)
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                preview = r['preview'].replace("\n", " ") if r['preview'] else ''
                print(f"  id={r['id']}  {r['dateofexam']} s{r['shift']} Q{r['q_num']}  "
                      f"subject={r['subject']}  '{preview[:80]}'")


if __name__ == "__main__":
    main()
