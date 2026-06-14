"""Round 2 diagnostic: pull the questions the user flagged after Batch 5 cleanup.

Groups them by (likely) category so we can triage:
  - mapping doubts
  - rendering issues
  - incomplete questions (new class)

For each flagged question we look up:
  - chapter_title via top-ranked tag's concept -> chapterdata.chaptertitle
  - stored subject + raw_text + options + has_figure + figure_blob_url
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


# (user-visible label, chapter keyword (ILIKE), q_number, hint)
FLAGGED = [
    # -- 11 Math
    ("11 Math Complex Numbers Q22",   "Complex",       22, "mapping?"),
    ("11 Math Complex Numbers Q18",   "Complex",       18, "mapping? z+2"),
    ("11 Math Trig Functions Q3",     "Trigonometric", 3,  "rendering (C1 residual)"),
    ("11 Math Trig Functions Q17",    "Trigonometric", 17, "mapping? inscribed circle"),
    # -- 11 Physics
    ("11 Physics Kinetic Theory Q10", "Kinetic",       10, "mapping? He/O2"),
    # -- 12 Chem Organic / GOC
    ("12 Chem Organic Q1",             "Organic",      1,  "mapping? phosphorous"),
    ("12 Chem Organic Q2",             "Organic",      2,  "mapping? Kjeldahl"),
    ("12 Chem Organic Q8",             "Organic",      8,  "incomplete? polar molecule"),
    ("12 Chem Organic Q11",            "Organic",      11, "incomplete — [Figure:] only"),
    ("12 Chem Organic Q18",            "Organic",      18, "rendering — TLC Rf blank"),
    ("12 Chem Organic Q19",            "Organic",      19, "mapping? solubility"),
    ("12 Chem Organic Q69",            "Organic",      69, "multiple — resonance"),
]


def subject_for(label):
    if "Math" in label:
        return "Mathematics"
    if "Physics" in label:
        return "Physics"
    return "Chemistry"


def fetch_rows(cur, subject, chap_kw, q_number):
    """All 2024 questions with the given q_number whose any tag sits under a chapter
    matching chap_kw."""
    cur.execute(
        """
        SELECT DISTINCT ON (q.id)
               q.id, q.year, q.dateofexam::text AS dateofexam, q.shift, q.subject,
               (q.question_content->>'question_number')::int AS q_num,
               q.question_content->>'raw_text' AS raw_text,
               q.question_content->'options' AS options,
               q.question_content->>'has_figure' AS has_figure,
               q.question_content->>'figure_blob_url' AS figure_blob_url,
               q.answer_key,
               q.difficulty, q.pattern_label
        FROM jee_question_bank q
        JOIN jee_question_tags t ON t.question_id = q.id
        JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
        LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
        WHERE q.year = 2024
          AND q.subject = %s
          AND (q.question_content->>'question_number')::int = %s
          AND cd.chaptertitle ILIKE %s
        ORDER BY q.id, q.dateofexam, q.shift
        LIMIT 8
        """,
        (subject, q_number, f"%{chap_kw}%"),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_tags(cur, qid):
    cur.execute(
        """
        SELECT nch.subject, cd.chaptertitle, cd.class AS cls,
               nch.concept_title, nch.content_type, t.similarity_score
        FROM jee_question_tags t
        JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
        LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
        WHERE t.question_id = %s
        ORDER BY t.similarity_score DESC
        """,
        (qid,),
    )
    return [dict(r) for r in cur.fetchall()]


def short(s, n=300):
    if s is None:
        return ""
    return s.replace("\n", " ")[:n]


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for label, chap_kw, qn, hint in FLAGGED:
                subj = subject_for(label)
                print("=" * 100)
                print(f"[{label}]   hint: {hint}")
                print("=" * 100)
                rows = fetch_rows(cur, subj, chap_kw, qn)
                if not rows:
                    print(f"  (no matches for subj={subj}, chapter LIKE %{chap_kw}%, Q{qn})")
                    continue
                for r in rows:
                    raw = r["raw_text"] or ""
                    raw_len = len(raw)
                    print(
                        f"\n  id={r['id']}  {r['dateofexam']} S{r['shift']}  "
                        f"subj={r['subject']}  ans={r['answer_key']}  "
                        f"fig={r['has_figure']}  diff={r['difficulty']}  "
                        f"raw_len={raw_len}"
                    )
                    if r.get("figure_blob_url"):
                        print(f"    figure_blob_url: {r['figure_blob_url']}")
                    print(f"    RAW: {short(raw, 360)}")
                    opts = r["options"] or []
                    for i, o in enumerate(opts):
                        t = short(o.get("text") or "", 140)
                        print(f"    [{chr(65+i)}] {t}")
                    for t in fetch_tags(cur, r["id"])[:5]:
                        print(
                            f"      {t['similarity_score']:.2f}  "
                            f"[{t['subject']} Cls {t['cls']}] {t['chaptertitle']}  >  "
                            f"{t['concept_title']}  ({t['content_type']})"
                        )
                print()


if __name__ == "__main__":
    main()
