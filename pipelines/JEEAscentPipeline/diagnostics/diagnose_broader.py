"""Quantify the broader scope of remaining issues.

1. All JSON-leak rows (all years, all subjects)
2. Multi-chapter question distribution (how many questions tagged to 2+ chapters)
3. 2023 rows by subject — what's the current state before tagging runs
4. Rows whose subject doesn't match their own top tag's subject (impossible, but worth checking)
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

            section("1. JSON-leak rows by year x subject")
            cur.execute("""
                SELECT year, subject, COUNT(*) AS n
                FROM jee_question_bank
                WHERE LTRIM(question_content->>'raw_text') LIKE '{%"raw_text"%'
                   OR LTRIM(question_content->>'raw_text') LIKE '\\begin{json}%'
                GROUP BY year, subject ORDER BY year, subject
            """)
            for r in cur.fetchall():
                print(f"  {r['year']}  {r['subject']:<12}  {r['n']}")

            section("2. Questions tagged to 2+ chapters (how much cross-listing)")
            cur.execute("""
                WITH q_chapter_count AS (
                    SELECT t.question_id, COUNT(DISTINCT nch.chapter_id) AS n_chapters
                    FROM jee_question_tags t
                    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                    GROUP BY t.question_id
                )
                SELECT n_chapters, COUNT(*) AS questions
                FROM q_chapter_count
                GROUP BY n_chapters
                ORDER BY n_chapters
            """)
            for r in cur.fetchall():
                print(f"  {r['n_chapters']} chapters per q  -> {r['questions']:>5} questions")

            section("3a. Cross-listing when top tag score is >= 0.85 per chapter (after threshold)")
            cur.execute("""
                WITH q_chapter_top AS (
                    SELECT t.question_id, nch.chapter_id, MAX(t.similarity_score) AS top_in_chapter
                    FROM jee_question_tags t
                    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                    GROUP BY t.question_id, nch.chapter_id
                ),
                q_included AS (
                    SELECT question_id, COUNT(*) AS n_chapters_kept
                    FROM q_chapter_top
                    WHERE top_in_chapter >= 0.85
                    GROUP BY question_id
                )
                SELECT n_chapters_kept, COUNT(*) AS questions
                FROM q_included
                GROUP BY n_chapters_kept
                ORDER BY n_chapters_kept
            """)
            for r in cur.fetchall():
                print(f"  {r['n_chapters_kept']} chapters (threshold 0.85)  -> {r['questions']:>5} questions")

            section("3b. Cross-listing when keeping top-1 chapter only (strictest)")
            cur.execute("""
                WITH q_chapter_top AS (
                    SELECT t.question_id, nch.chapter_id, MAX(t.similarity_score) AS top_in_chapter
                    FROM jee_question_tags t
                    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                    GROUP BY t.question_id, nch.chapter_id
                ),
                ranked AS (
                    SELECT question_id, chapter_id,
                           ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY top_in_chapter DESC) AS rnk
                    FROM q_chapter_top
                )
                SELECT COUNT(DISTINCT question_id) AS questions_with_only_1_chapter
                FROM ranked WHERE rnk = 1
            """)
            for r in cur.fetchall():
                print(f"  If we kept only top-chapter per question: {r['questions_with_only_1_chapter']} questions")

            section("4. 2023 rows by subject (pre-tagging)")
            cur.execute("""
                SELECT subject, COUNT(*) AS n FROM jee_question_bank
                WHERE year = 2023 GROUP BY subject ORDER BY subject
            """)
            for r in cur.fetchall():
                print(f"  {r['subject']:<12}  {r['n']}")

            section("5. Suspect 2023 rows: looks-like-chem content stored as Maths (heuristic scan)")
            cur.execute("""
                SELECT id, dateofexam::text AS dateofexam, shift, subject,
                       LEFT(question_content->>'raw_text', 110) AS preview
                FROM jee_question_bank
                WHERE year = 2023
                  AND subject = 'Mathematics'
                  AND (question_content->>'raw_text' ILIKE '%galvanic%'
                    OR question_content->>'raw_text' ILIKE '%electrochem%'
                    OR question_content->>'raw_text' ILIKE '%hybridisation%'
                    OR question_content->>'raw_text' ILIKE '%hybridization%'
                    OR question_content->>'raw_text' ILIKE '%lanthan%'
                    OR question_content->>'raw_text' ILIKE '%coordination geometry%'
                    OR question_content->>'raw_text' ILIKE '%sp^3%d%'
                    OR question_content->>'raw_text' ILIKE '%molar mass%')
                ORDER BY id
                LIMIT 20
            """)
            rows = list(cur.fetchall())
            if not rows:
                print("  (none matched heuristics)")
            for r in rows:
                print(f"  id={r['id']} {r['dateofexam']} s{r['shift']} subj={r['subject']}")
                print(f"    {r['preview']}")

            section("6. Physics-labeled Maths-content heuristic scan (2024, post-dedup)")
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM jee_question_bank
                WHERE year = 2024
                  AND subject = 'Physics'
                  AND (question_content->>'raw_text' ILIKE '%\\int%'
                    OR question_content->>'raw_text' ILIKE '%\\lim%'
                    OR question_content->>'raw_text' ILIKE '%\\sin^{-1}%'
                    OR question_content->>'raw_text' ILIKE '%matrix%'
                    OR question_content->>'raw_text' ILIKE '%derivative%'
                    OR question_content->>'raw_text' ILIKE '%orthocentre%'
                    OR question_content->>'raw_text' ILIKE '%probability%')
            """)
            for r in cur.fetchall():
                print(f"  rows: {r['n']}")


if __name__ == "__main__":
    main()
