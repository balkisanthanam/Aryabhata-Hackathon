"""One-shot diagnostic: find the 10 user-flagged questions in DB and print their state.

Hypothesis we're testing:
  Frontend chapter is determined by jee_question_tags -> ncert_concept_hierarchy.chapter_id.
  Tagger filters by q.subject. So if stored subject is wrong, tagger uses the wrong
  vocabulary, hallucinates tags, and the question lands under a wrong chapter.

This script matches each flagged question by a distinctive text substring, then prints
stored subject + tagged chapters side-by-side.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

# (label, text pattern to ILIKE match)
FLAGGED = [
    ("A1 silver/electricity (expect Chemistry)",
        "%silver%displaced by a quantity of electricity%"),
    ("A2 decacarbonyldimanganese (expect Chemistry)",
        "%decacarbonyldimanganese%"),
    ("A3 PF5/BrF5 hybridisation (expect Chemistry)",
        "%PF$_{5}$ and $BrF$_{5}$%"),  # alt patterns tried below
    ("A4 sp2 hybridization pair (expect Chemistry)",
        "%central atoms exhibit $sp^{2}$%"),
    ("A6/B2/F1 tetrahedral die quadratic (expect Maths Probability)",
        "%three independent rolls of a fair tetrahedral die%"),
    ("A7 Diamagnetic Lanthanoid (expect Chemistry)",
        "%Diamagnetic Lanthanoid ions%"),
    ("A8/D1 fair die tossed (expect Maths Probability)",
        "%fair die is tossed repeatedly until a six%"),
    ("B1 integral sqrt(e^x - 1) (expect Maths Integral+Quadratic)",
        "%\\\\sqrt{e^x - 1}%"),
    ("C1 malformed LaTeX sin theta (rendering)",
        "%1}{2} \\\\sin \\\\theta - \\\\frac{\\\\sqrt{3}}{2} \\\\cos%"),
]

# Fallback patterns (ILIKE-friendly, no backslash issues)
FALLBACKS = {
    "A3 PF5/BrF5 hybridisation (expect Chemistry)": "%PF%BrF%hybridisation%",
    "B1 integral sqrt(e^x - 1) (expect Maths Integral+Quadratic)": "%roots of the equation%e^%",
    "C1 malformed LaTeX sin theta (rendering)": "%sin %theta%cos %theta%",
}


def find_question(cur, pattern: str):
    cur.execute(
        """
        SELECT id, year, dateofexam::text AS dateofexam, shift, subject,
               (question_content->>'question_number')::int AS q_num,
               LEFT(question_content->>'raw_text', 180) AS preview
        FROM jee_question_bank
        WHERE question_content->>'raw_text' ILIKE %s
        ORDER BY dateofexam, shift, (question_content->>'question_number')::int
        LIMIT 5
        """,
        (pattern,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_tags(cur, qid: int):
    cur.execute(
        """
        SELECT nch.subject, cd.chaptertitle AS chapter_title, cd.class AS cls,
               nch.concept_title, t.similarity_score
        FROM jee_question_tags t
        JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
        LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
        WHERE t.question_id = %s
        ORDER BY t.similarity_score DESC
        """,
        (qid,),
    )
    return [dict(r) for r in cur.fetchall()]


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for label, pattern in FLAGGED:
                rows = find_question(cur, pattern)
                if not rows and label in FALLBACKS:
                    rows = find_question(cur, FALLBACKS[label])

                print(f"\n{'=' * 80}\n{label}\n{'=' * 80}")
                if not rows:
                    print(f"  NOT FOUND (pattern: {pattern})")
                    continue

                for q in rows:
                    print(
                        f"  id={q['id']}  {q['dateofexam']} shift={q['shift']}  "
                        f"Q{q['q_num']}  stored subject={q['subject']}"
                    )
                    print(f"  preview: {q['preview'][:150]}")
                    tags = fetch_tags(cur, q["id"])
                    if not tags:
                        print("    (no tags)")
                    else:
                        for t in tags[:4]:
                            print(
                                f"    tag -> [{t['subject']}] Class {t['cls']} {t['chapter_title']} :: "
                                f"{t['concept_title']} (score={t['similarity_score']:.2f})"
                            )


if __name__ == "__main__":
    main()
