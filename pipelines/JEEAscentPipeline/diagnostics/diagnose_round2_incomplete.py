"""Round 2 follow-up: two lenses.

Lens A — find the specific flagged questions by content keyword (not q_number,
since the user's Q# is UI-positional within a chapter view, not NTA q_number).

Lens B — scan the whole 2024 corpus for the *incomplete question* class:
  (1) raw_text is very short (< 40 chars)
  (2) raw_text starts with "[Figure:" (figure description only — no question stem)
  (3) raw_text is only an options list / question ends in mid-formula
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


KEYWORD_FLAGS = [
    ("phosphorous (12 Chem Organic Q1)",      "%phosphorous%"),
    ("Kjeldahl (12 Chem Organic Q2)",         "%Kjeldahl%"),
    ("polar molecule (12 Chem Organic Q8)",   "%polar molecule%"),
    ("retardation factor / TLC Rf (Q18)",     "%retardation factor%"),
    ("solubility (12 Chem Organic Q19)",      "%solubility%"),
    ("resonance structures (12 Chem Q69)",    "%resonance structure%"),
    ("He/O2 kinetic theory (11 Phy Q10)",     "%He%O_2%"),
    ("He and O2 mass kinetic",                 "%Helium%oxygen%"),
]


def short(s, n=300):
    return (s or "").replace("\n", " ")[:n]


def print_row(r, tags):
    print(
        f"  id={r['id']}  {r['dateofexam']} S{r['shift']}  subj={r['subject']}  "
        f"q#={r['q_num']}  ans={r['answer_key']}  fig={r['has_figure']}  "
        f"raw_len={len(r['raw_text'] or '')}"
    )
    if r.get("figure_blob_url"):
        print(f"    figure_blob_url: {r['figure_blob_url']}")
    print(f"    RAW: {short(r['raw_text'], 320)}")
    opts = r["options"] or []
    for i, o in enumerate(opts):
        print(f"    [{chr(65+i)}] {short(o.get('text', ''), 140)}")
    for t in tags[:4]:
        print(
            f"      {t['similarity_score']:.2f}  "
            f"[{t['subject']} Cls {t['cls']}] {t['chaptertitle']}  >  "
            f"{t['concept_title']}"
        )


def fetch_tags(cur, qid):
    cur.execute(
        """
        SELECT nch.subject, cd.chaptertitle, cd.class AS cls, nch.concept_title,
               t.similarity_score
        FROM jee_question_tags t
        JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
        LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
        WHERE t.question_id = %s
        ORDER BY t.similarity_score DESC
        """,
        (qid,),
    )
    return [dict(r) for r in cur.fetchall()]


def search_keyword(cur, kw):
    cur.execute(
        """
        SELECT q.id, q.year, q.dateofexam::text AS dateofexam, q.shift, q.subject,
               (q.question_content->>'question_number')::int AS q_num,
               q.question_content->>'raw_text' AS raw_text,
               q.question_content->'options' AS options,
               q.question_content->>'has_figure' AS has_figure,
               q.question_content->>'figure_blob_url' AS figure_blob_url,
               q.answer_key
        FROM jee_question_bank q
        WHERE q.year = 2024
          AND q.question_content->>'raw_text' ILIKE %s
        ORDER BY q.dateofexam, q.shift, q_num
        LIMIT 6
        """,
        (kw,),
    )
    return [dict(r) for r in cur.fetchall()]


def scan_incomplete(cur):
    print("\n" + "=" * 100)
    print("LENS B: INCOMPLETE-QUESTION SCAN — 2024 corpus")
    print("=" * 100)

    buckets = [
        ("Very short raw_text (<40 chars) and fig=false",
         "LENGTH(q.question_content->>'raw_text') < 40 "
         "AND (q.question_content->>'has_figure')::text = 'false'"),
        ("Starts with '[Figure:' — figure-only extraction",
         "LTRIM(q.question_content->>'raw_text') LIKE '[Figure:%%'"),
        ("Raw_text ends mid-formula (last char is { or = or - or _ )",
         "RIGHT(RTRIM(q.question_content->>'raw_text'), 1) IN ('{', '=', '-', '_')"),
        ("raw_text ends with \\text{______} blank-hole",
         "q.question_content->>'raw_text' ILIKE '%%\\_\\_\\_\\_\\_\\_%%'"),
    ]
    for label, predicate in buckets:
        print(f"\n---- {label}")
        cur.execute(f"""
            SELECT q.id, q.year, q.dateofexam::text AS dateofexam, q.shift, q.subject,
                   (q.question_content->>'question_number')::int AS q_num,
                   q.question_content->>'raw_text' AS raw_text,
                   q.question_content->'options' AS options,
                   q.question_content->>'has_figure' AS has_figure,
                   q.question_content->>'figure_blob_url' AS figure_blob_url,
                   q.answer_key
            FROM jee_question_bank q
            WHERE q.year = 2024 AND ({predicate})
            ORDER BY q.subject, q.dateofexam, q.shift, q_num
            LIMIT 20
        """)
        rows = [dict(r) for r in cur.fetchall()]
        # also count
        cur.execute(f"""
            SELECT COUNT(*) AS n
            FROM jee_question_bank q
            WHERE q.year = 2024 AND ({predicate})
        """)
        total = cur.fetchone()["n"]
        print(f"  (showing first {min(len(rows),20)} of {total})")
        for r in rows:
            print_row(r, [])


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("=" * 100)
            print("LENS A: KEYWORD SEARCHES for user-flagged questions")
            print("=" * 100)
            for label, kw in KEYWORD_FLAGS:
                print("\n" + "-" * 100)
                print(f"[{label}]")
                print("-" * 100)
                rows = search_keyword(cur, kw)
                if not rows:
                    print(f"  (no matches for ILIKE {kw})")
                    continue
                for r in rows:
                    tags = fetch_tags(cur, r["id"])
                    print_row(r, tags)

            scan_incomplete(cur)


if __name__ == "__main__":
    main()
