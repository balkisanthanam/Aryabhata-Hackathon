"""Build the E2E sampling matrix for JEE Ascent frontend validation.

Picks 2-3 chapters per subject (Physics / Maths / Chemistry) that have:
  - Enough questions to exercise the UI (>= 5 tagged rows, post-0.85 filter)
  - A mix of MCQ and Integer sections
  - At least one clean row and ideally no figure-required rows

Prints the chapter_id + a sample of 3-5 question ids per chapter so the user
can click through the frontend deterministically.
"""
from __future__ import annotations

import sys
from db_writer import JEEExtractionDBWriter


SAMPLE_SQL = """
WITH tagged AS (
    SELECT
        q.id              AS qid,
        q.subject,
        q.section,
        q.year,
        q.question_content->>'question_number' AS qnum,
        (q.question_content->>'has_figure')::boolean AS has_figure,
        q.question_content->>'figure_blob_url'      AS figure_url,
        t.concept_id,
        nch.chapter_id,
        cd.chaptertitle  AS chapter_title,
        cd.class         AS chapter_class,
        cd.chapternumber AS chapter_number,
        t.similarity_score
    FROM jee_question_bank q
    JOIN jee_question_tags t ON t.question_id = q.id
    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
    LEFT JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
    WHERE q.year = 2024
      AND t.similarity_score >= 0.85
),
chapter_stats AS (
    SELECT
        chapter_id,
        chapter_title,
        chapter_class,
        chapter_number,
        subject,
        COUNT(DISTINCT qid) AS total_qs,
        SUM(CASE WHEN section = 'MCQ'     THEN 1 ELSE 0 END) AS mcq_rows,
        SUM(CASE WHEN section = 'Integer' THEN 1 ELSE 0 END) AS int_rows,
        SUM(CASE WHEN has_figure         THEN 1 ELSE 0 END) AS fig_rows,
        SUM(CASE WHEN has_figure AND figure_url IS NULL THEN 1 ELSE 0 END) AS fig_missing
    FROM tagged
    GROUP BY chapter_id, chapter_title, chapter_class, chapter_number, subject
)
SELECT chapter_id, chapter_title, subject, total_qs, mcq_rows, int_rows, fig_rows, fig_missing, chapter_class, chapter_number
FROM chapter_stats
WHERE total_qs >= 5
ORDER BY subject, chapter_class, chapter_number;
"""


SAMPLE_QUESTIONS_SQL = """
SELECT DISTINCT ON (q.id)
    q.id,
    q.section,
    q.question_content->>'question_number' AS qnum,
    (q.question_content->>'has_figure')::boolean AS has_figure,
    LEFT(q.question_content->>'raw_text', 120) AS preview
FROM jee_question_bank q
JOIN jee_question_tags t ON t.question_id = q.id
JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
WHERE q.year = 2024
  AND nch.chapter_id = %s
  AND t.similarity_score >= 0.85
ORDER BY q.id, q.section
LIMIT 5;
"""


def main() -> None:
    writer = JEEExtractionDBWriter()
    with writer.connection() as conn, conn.cursor() as cur:
        cur.execute(SAMPLE_SQL)
        chapters = cur.fetchall()

        print(f"\n{'='*110}")
        print(f"{'Subj':<12} {'Cls':<4} {'Ch#':<4} {'ChId':<6} {'Title':<42} {'Total':>6} {'MCQ':>5} {'Int':>5} {'Fig':>5} {'FigMissing':>11}")
        print("="*110)

        best_by_subject: dict[str, list[tuple]] = {"Physics": [], "Mathematics": [], "Chemistry": []}
        for row in chapters:
            chapter_id, title, subject, total, mcq, integer, fig, fig_missing, cls, chnum = row
            print(
                f"{subject[:11]:<12} {str(cls or '?'):<4} {str(chnum or '?'):<4} {chapter_id:<6} {(title or '?')[:41]:<42} "
                f"{total:>6} {mcq:>5} {integer:>5} {fig:>5} {fig_missing:>11}"
            )
            if subject in best_by_subject:
                best_by_subject[subject].append(row)

        # Pick top-3 chapters per subject by mix quality: want both mcq + integer + few missing figures
        print(f"\n{'='*100}")
        print("RECOMMENDED SAMPLING CHAPTERS (clean mix, minimal figure-missing)")
        print("="*100)

        picks: list[tuple[str, int, str]] = []
        for subj, rows in best_by_subject.items():
            # Prefer chapters where int_rows > 0 AND fig_missing is low relative to total
            ranked = sorted(
                rows,
                key=lambda r: (
                    -(1 if r[5] > 0 else 0),   # has Integer rows
                    r[7],                       # fig_missing asc
                    -r[3],                      # total desc
                ),
            )
            for r in ranked[:2]:
                picks.append((r[2], r[0], r[1]))

        for subj, chapter_id, title in picks:
            print(f"\n[{subj}] chapter_id={chapter_id}  {title}")
            cur.execute(SAMPLE_QUESTIONS_SQL, (chapter_id,))
            for qid, section, qnum, has_fig, preview in cur.fetchall():
                fig_flag = "[FIG]" if has_fig else "     "
                print(f"  qid={qid:<6} sec={section:<8} q#={qnum or '?':<4} {fig_flag} {preview.strip()[:80]}")


if __name__ == "__main__":
    sys.exit(main() or 0)
