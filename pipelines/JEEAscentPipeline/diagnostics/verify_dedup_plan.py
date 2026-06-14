"""Verify that the dedup plan keeps the user-flagged questions' correct-subject row."""

from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402
from dedup_jee_question_bank import score_row  # noqa: E402

FLAGGED_IDS_BY_LABEL = {
    "A1 silver/electricity": [292, 1373, 2274],
    "A2 decacarbonyldimanganese": [459, 1538, 2438],
    "A3 PF5/BrF5 hybridisation": [898, 1892, 2878],
    "A6 tetrahedral die": [1049, 2037, 3025],
    "A7 Diamagnetic Lanthanoid": [365, 1446, 2343],
    "A8/D1 fair die tossed": [2215],  # only 1 copy found earlier
    "B1 integral": [109],
    "C1 malformed LaTeX": [392],
}


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for label, ids in FLAGGED_IDS_BY_LABEL.items():
                print(f"\n{'=' * 70}\n{label} (ids={ids})\n{'=' * 70}")
                cur.execute(
                    """
                    SELECT
                        q.id, q.subject, q.answer_key, q.exam_paper_id, q.nta_question_id,
                        q.question_content,
                        (SELECT MAX(similarity_score) FROM jee_question_tags t WHERE t.question_id = q.id) AS max_tag_sim,
                        (SELECT COUNT(*) FROM jee_question_tags t WHERE t.question_id = q.id) AS tag_count
                    FROM jee_question_bank q
                    WHERE q.id = ANY(%s::int[])
                    ORDER BY q.id
                    """,
                    (ids,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    sc = score_row(r)
                    qc = r.get("question_content") or {}
                    preview = (qc.get("raw_text") or "")[:55].replace("\n", " ")
                    sim = r.get("max_tag_sim")
                    sim_str = f"{float(sim):.2f}" if sim is not None else "  - "
                    print(
                        f"  id={r['id']:>5}  subj={r['subject']:<12}  tags={r['tag_count']:<2}  "
                        f"max_sim={sim_str}  score={sc:>9.2f}  '{preview}'"
                    )
                if rows:
                    best = max(rows, key=lambda r: (score_row(r), -r["id"]))
                    print(f"  --> WINNER: id={best['id']} subj={best['subject']}")


if __name__ == "__main__":
    main()
