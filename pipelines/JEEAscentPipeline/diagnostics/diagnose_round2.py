"""Diagnose the second round of user-flagged questions (post-dedup)."""

from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

# (label, ilike pattern)
FLAGGED = [
    ("candela Q13 (expect Physics Units/Measurement)",
        "%candela%luminous intensity%"),
    ("Q6 rational function inequality (Complex Numbers chapter?)",
        "%set of postive integral values of a for which%"),
    ("Q7 inverse sin alpha+beta+gamma=pi",
        "%sin^{-1} %alpha%sin^{-1} %beta%sin^{-1} %gamma%pi%"),
    ("Q9 (sqrt3+sqrt2)^x + (sqrt3-sqrt2)^x = 10",
        "%\\sqrt{3} + \\sqrt{2}%\\sqrt{3} - \\sqrt{2}%10%"),
    ("Q11 distinct roots + sequence a_n=alpha^n+beta^n",
        "%be the distinct roots of the equation%minimum value%"),
    ("Q12 4x^4 + 8x^3 - 17x^2 ...",
        "%4x^4 + 8x^3 - 17x^2%125%"),
    ("Q10 JSON leak + begin{json}",
        "%begin{json}%"),
    ("Q5 Physics Waves tuning fork + literal underscores",
        "%tuning fork%sonometer%frequency%"),
    ("Q20 Physics Kinetic Theory mean free path",
        "%number density%mean free path%"),
    ("12 Chem Q2 galvanic cell H2 + AgCl",
        "%H_{2}(g)%AgCl%galvanic cell%"),
    ("12 Chem Q3 silver displaced 5600 mL O2",
        "%mass of silver%5600%O%S.T.P%"),
]

# Alternative simpler patterns
FALLBACKS = {
    "Q7 inverse sin alpha+beta+gamma=pi":
        "%3\\alpha\\beta%",
    "Q9 (sqrt3+sqrt2)^x + (sqrt3-sqrt2)^x = 10":
        "%sqrt{3}%sqrt{2}%10%",
    "Q12 4x^4 + 8x^3 - 17x^2 ...":
        "%4x^4%17x^2%",
    "Q5 Physics Waves tuning fork + literal underscores":
        "%tuning fork resonates%",
    "12 Chem Q2 galvanic cell H2 + AgCl":
        "%AgCl%galvanic cell%",
}


def find(cur, pattern):
    cur.execute("""
        SELECT id, year, dateofexam::text AS dateofexam, shift, subject,
               (question_content->>'question_number')::int AS q_num,
               LEFT(question_content->>'raw_text', 170) AS preview
        FROM jee_question_bank
        WHERE question_content->>'raw_text' ILIKE %s
        ORDER BY dateofexam, shift, (question_content->>'question_number')::int
        LIMIT 3
    """, (pattern,))
    return [dict(r) for r in cur.fetchall()]


def tags_of(cur, qid):
    cur.execute("""
        SELECT nch.subject, cd.class AS cls, cd.chaptertitle AS chapter,
               nch.concept_title, t.similarity_score
        FROM jee_question_tags t
        JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
        LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
        WHERE t.question_id = %s
        ORDER BY t.similarity_score DESC
    """, (qid,))
    return [dict(r) for r in cur.fetchall()]


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for label, pat in FLAGGED:
                rows = find(cur, pat)
                if not rows and label in FALLBACKS:
                    rows = find(cur, FALLBACKS[label])
                print(f"\n{'=' * 80}\n{label}\n{'=' * 80}")
                if not rows:
                    print(f"  NOT FOUND (pattern {pat})")
                    continue
                for r in rows:
                    print(f"  id={r['id']}  {r['dateofexam']} s{r['shift']}  Q{r['q_num']}  subject={r['subject']}")
                    print(f"  preview: {r['preview']}")
                    ts = tags_of(cur, r["id"])
                    for t in ts[:4]:
                        print(f"    tag -> [{t['subject']}] Class {t['cls']} {t['chapter']} :: {t['concept_title']} ({t['similarity_score']:.2f})")


if __name__ == "__main__":
    main()
