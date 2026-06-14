"""Quantify the impact of the >= 0.85 similarity-score threshold on accentSession results."""
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
            print("Impact of jqt.similarity_score >= 0.85 threshold")
            print("=" * 80)

            cur.execute("""
                WITH before_filter AS (
                    SELECT t.question_id, COUNT(DISTINCT nch.chapter_id) AS n_chapters
                    FROM jee_question_tags t
                    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                    GROUP BY t.question_id
                ),
                after_filter AS (
                    SELECT t.question_id, COUNT(DISTINCT nch.chapter_id) AS n_chapters
                    FROM jee_question_tags t
                    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                    WHERE t.similarity_score >= 0.85
                    GROUP BY t.question_id
                )
                SELECT
                    (SELECT COUNT(*) FROM before_filter) AS qs_in_any_chapter_before,
                    (SELECT COUNT(*) FROM after_filter)  AS qs_in_any_chapter_after,
                    (SELECT COUNT(*) FROM before_filter WHERE n_chapters > 1) AS cross_listed_before,
                    (SELECT COUNT(*) FROM after_filter  WHERE n_chapters > 1) AS cross_listed_after
            """)
            r = dict(cur.fetchone())
            print(f"  Questions in >=1 chapter BEFORE threshold:  {r['qs_in_any_chapter_before']}")
            print(f"  Questions in >=1 chapter AFTER threshold:   {r['qs_in_any_chapter_after']}")
            print(f"  Dropped from ALL chapters (orphaned):      {r['qs_in_any_chapter_before'] - r['qs_in_any_chapter_after']}")
            print(f"  Cross-listed (>=2 chapters) BEFORE:         {r['cross_listed_before']}")
            print(f"  Cross-listed (>=2 chapters) AFTER:          {r['cross_listed_after']}")

            print()
            print("Per-chapter question counts BEFORE vs AFTER (top 20 by before-count):")
            cur.execute("""
                SELECT cd.class, cd.subject AS cs, cd.chaptertitle AS chapter,
                       COUNT(DISTINCT jqt.question_id) AS before_n,
                       COUNT(DISTINCT CASE WHEN jqt.similarity_score >= 0.85
                                           THEN jqt.question_id END) AS after_n
                FROM jee_question_tags jqt
                JOIN ncert_concept_hierarchy nch ON nch.id = jqt.concept_id
                JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
                GROUP BY cd.class, cd.subject, cd.chaptertitle
                ORDER BY before_n DESC
                LIMIT 20
            """)
            for r in cur.fetchall():
                delta = r['before_n'] - r['after_n']
                marker = " <<<" if delta >= 20 else ""
                print(f"  {r['before_n']:>4}->{r['after_n']:>4}  (-{delta:>3})  "
                      f"Class {r['class']} {r['cs']:10}  {r['chapter']}{marker}")

            print()
            print("Orphaned questions — have tags but none >= 0.85 (sample 10):")
            cur.execute("""
                SELECT q.id, q.year, q.subject,
                       (SELECT MAX(similarity_score) FROM jee_question_tags t WHERE t.question_id = q.id) AS max_sim,
                       LEFT(q.question_content->>'raw_text', 90) AS preview
                FROM jee_question_bank q
                WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
                  AND NOT EXISTS (SELECT 1 FROM jee_question_tags t
                                  WHERE t.question_id = q.id AND t.similarity_score >= 0.85)
                ORDER BY random()
                LIMIT 10
            """)
            for r in cur.fetchall():
                print(f"  id={r['id']} year={r['year']} subj={r['subject']:<12} max_sim={r['max_sim']:.2f}")
                print(f"    '{r['preview']}'")


if __name__ == "__main__":
    main()
