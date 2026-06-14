"""Dip-test the 0.85 threshold.

Samples three buckets of (question, chapter) pairs and prints them so the user can
eyeball precision/drop-correctness:

  A. KEPT    — pair where score >= 0.85 (what the frontend will show).
               Primary check: is the question really about that chapter?
  B. DROPPED — pair where 0.80 < score < 0.85 (what threshold removes).
               Primary check: was the drop correct (question not really about that chapter)?
  C. ORPHAN  — questions whose MAX score is 0.80 (invisible without fallback).
               Primary check: where SHOULD the question live?
"""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


SAMPLE_N = 20


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            print("\n" + "=" * 80)
            print(f"A. KEPT (score >= 0.85) — precision check. Sample {SAMPLE_N}.")
            print("=" * 80)
            cur.execute(f"""
                SELECT q.id, q.subject,
                       cd.class AS cls, cd.chaptertitle AS chapter,
                       nch.concept_title, t.similarity_score,
                       LEFT(q.question_content->>'raw_text', 120) AS preview
                FROM jee_question_tags t
                JOIN jee_question_bank q ON q.id = t.question_id
                JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
                WHERE t.similarity_score >= 0.85
                ORDER BY random()
                LIMIT {SAMPLE_N}
            """)
            for r in cur.fetchall():
                preview = r['preview'].replace(chr(10), ' ')
                print(f"  id={r['id']:<5} [{r['subject']:<11}] Class {r['cls']} {r['chapter']}")
                print(f"    tag: {r['concept_title']} (score={float(r['similarity_score']):.2f})")
                print(f"    Q: {preview}")
                print()

            print("\n" + "=" * 80)
            print(f"B. DROPPED (0.80 tags, threshold drops) — drop-correctness check. Sample {SAMPLE_N}.")
            print("=" * 80)
            cur.execute(f"""
                SELECT q.id, q.subject,
                       cd.class AS cls, cd.chaptertitle AS chapter,
                       nch.concept_title, t.similarity_score,
                       (SELECT MAX(t2.similarity_score) FROM jee_question_tags t2
                        WHERE t2.question_id = q.id) AS question_max_sim,
                       LEFT(q.question_content->>'raw_text', 120) AS preview
                FROM jee_question_tags t
                JOIN jee_question_bank q ON q.id = t.question_id
                JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
                WHERE t.similarity_score = 0.80
                ORDER BY random()
                LIMIT {SAMPLE_N}
            """)
            for r in cur.fetchall():
                preview = r['preview'].replace(chr(10), ' ')
                max_str = f"(q has a stronger {r['question_max_sim']:.2f} tag elsewhere)" \
                    if r['question_max_sim'] > 0.80 else "(this 0.80 IS the q's top tag — ORPHAN)"
                print(f"  id={r['id']:<5} [{r['subject']:<11}] Class {r['cls']} {r['chapter']}")
                print(f"    dropped tag: {r['concept_title']} (score=0.80)  {max_str}")
                print(f"    Q: {preview}")
                print()

            print("\n" + "=" * 80)
            print("C. ORPHANS — every row whose MAX tag score is 0.80 (7 total)")
            print("=" * 80)
            cur.execute("""
                SELECT q.id, q.subject,
                       (SELECT MAX(t.similarity_score) FROM jee_question_tags t WHERE t.question_id = q.id) AS max_sim,
                       LEFT(q.question_content->>'raw_text', 160) AS preview
                FROM jee_question_bank q
                WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
                  AND NOT EXISTS (SELECT 1 FROM jee_question_tags t
                                  WHERE t.question_id = q.id AND t.similarity_score >= 0.85)
                ORDER BY q.id
            """)
            rows = list(cur.fetchall())
            for r in rows:
                preview = (r['preview'] or '').replace(chr(10), ' ')
                # show all tags for orphan
                cur.execute("""
                    SELECT nch.concept_title, cd.chaptertitle AS chapter,
                           t.similarity_score
                    FROM jee_question_tags t
                    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
                    LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
                    WHERE t.question_id = %s
                    ORDER BY t.similarity_score DESC
                """, (r['id'],))
                tags = cur.fetchall()
                print(f"  id={r['id']:<5} [{r['subject']:<11}] max={r['max_sim']:.2f}")
                for t in tags:
                    print(f"    {t['chapter']}  ::  {t['concept_title']} ({float(t['similarity_score']):.2f})")
                print(f"    Q: {preview}")
                print()


if __name__ == "__main__":
    main()
