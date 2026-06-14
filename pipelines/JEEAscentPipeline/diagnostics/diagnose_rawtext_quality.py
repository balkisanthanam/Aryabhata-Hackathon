"""Quantify remaining raw_text quality issues after Batches 1-2.

Classes of damage we know about from user flags + Batch 2 sampling:
  - Inner-monologue markers: |continued|, |thought|, ```json  (Gemini reasoning fence)
  - Reasoning phrases: 'Wait,', 'Actually,', 'Let me', 'I need to', 'I\\'ll', etc.
  - Embedded JSON fragment mid-string: '"raw_text":' appearing not at the start
  - Starting with a stray quote or partial prose before the real text
  - Literal LaTeX escapes that won't render (\\_, $ ... $= ... $ broken, unbalanced $)
"""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


CHECKS = [
    ("A. Starts with inner-monologue fence  |continued|  |thought|  ```json",
     "LTRIM(raw_text) ILIKE '|continued|%%'"
     " OR LTRIM(raw_text) ILIKE '|thought|%%'"
     " OR LTRIM(raw_text) ILIKE '```json%%'"
     " OR LTRIM(raw_text) ILIKE '\\begin{json}%%'"),

    ("B. Contains '\"raw_text\"' mid-string (embedded JSON fragment)",
     "raw_text LIKE '%%\"raw_text\"%%'"
     " AND LTRIM(raw_text) NOT LIKE '{%%\"raw_text\"%%'"),

    ("C. Starts with a stray single quote then prose (Wait/Actually/Let me/Final/Option)",
     "(raw_text ILIKE '%%\"Wait,%%' OR raw_text ILIKE '%%Wait, I %%'"
     " OR raw_text ILIKE '%%\"Actually%%' OR raw_text ILIKE '%%\" Actually%%'"
     " OR raw_text ILIKE 'Wait,%%' OR raw_text ILIKE 'Actually,%%'"
     " OR raw_text ILIKE 'Let me%%' OR raw_text ILIKE 'I need to%%'"
     " OR raw_text ILIKE 'I think%%' OR raw_text ILIKE 'I''ll %%'"
     " OR raw_text ILIKE 'Final check%%' OR raw_text ILIKE '\" %%'"
     " OR raw_text ILIKE 'Option %%')"),

    ("D. Literal backslash-underscore sequence (\\_) outside $...$ math mode",
     "raw_text ~ E'\\\\\\\\_\\\\\\\\_'"),
    ("D2. Any literal backslash-underscore (\\_) anywhere in raw_text",
     "raw_text ~ E'\\\\\\\\_'"),

    ("E. Raw $ ... $= or $ ... $ without matching close (heuristic: odd count of $)",
     "MOD(LENGTH(raw_text) - LENGTH(REPLACE(raw_text, '$', '')), 2) = 1"),

    ("F. Contains standalone ```  fence anywhere",
     "raw_text LIKE '%%```%%'"),

    ("G. Starts with a close brace or bracket (truncated JSON)",
     "LTRIM(raw_text) LIKE '}%%' OR LTRIM(raw_text) LIKE ']%%'"),
]


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            print("=" * 80)
            print("Scope: rows with remaining raw_text quality issues (by year)")
            print("=" * 80)
            for label, predicate in CHECKS:
                cur.execute(f"""
                    SELECT year, COUNT(*) AS n
                    FROM (
                        SELECT year, question_content->>'raw_text' AS raw_text
                        FROM jee_question_bank
                    ) q
                    WHERE raw_text IS NOT NULL
                      AND ({predicate})
                    GROUP BY year ORDER BY year
                """)
                rows = list(cur.fetchall())
                total = sum(r["n"] for r in rows)
                print(f"\n  {label}")
                for r in rows:
                    print(f"    {r['year']}: {r['n']}")
                print(f"    TOTAL: {total}")

            print()
            print("=" * 80)
            print("Combined: rows matching ANY of A,B,C,D,F,G (not E — ambiguous)")
            print("=" * 80)
            # Build a combined OR of A-D,F,G
            combined = " OR ".join(p for _, p in CHECKS if _[0] not in ("E",))
            # Filter predicate list by label prefix
            parts = [p for l, p in CHECKS if not l.startswith("E.")]
            combined = " OR ".join(f"({p})" for p in parts)
            cur.execute(f"""
                SELECT year, subject, COUNT(*) AS n
                FROM (
                    SELECT year, subject, question_content->>'raw_text' AS raw_text
                    FROM jee_question_bank
                ) q
                WHERE raw_text IS NOT NULL
                  AND ({combined})
                GROUP BY year, subject ORDER BY year, subject
            """)
            rows = list(cur.fetchall())
            grand = 0
            for r in rows:
                print(f"  {r['year']}  {r['subject']:<12}  {r['n']}")
                grand += r["n"]
            print(f"  GRAND TOTAL: {grand}")

            print()
            print("=" * 80)
            print("Sample 10 rows from the combined set")
            print("=" * 80)
            cur.execute(f"""
                SELECT id, year, subject,
                       LEFT(question_content->>'raw_text', 200) AS preview
                FROM jee_question_bank
                WHERE question_content->>'raw_text' IS NOT NULL
                  AND ({combined})
                ORDER BY random()
                LIMIT 10
            """)
            for r in cur.fetchall():
                preview = (r['preview'] or '').replace(chr(10), ' ')
                print(f"  id={r['id']} year={r['year']} subj={r['subject']}")
                print(f"    {preview}")
                print()


if __name__ == "__main__":
    main()
