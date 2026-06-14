"""Deduplicate jee_question_bank.

Root cause of duplicates
------------------------
1. `db_writer.bulk_insert_questions` uses `ON CONFLICT DO NOTHING` without any
   conflict target, and no UNIQUE constraint exists on the table, so the clause
   never skips anything.
2. `jee_crop_pipeline.py` calls `bulk_insert_questions` directly on every run,
   unlike `jee_extraction_pipeline.py` which pre-checks `count_existing_questions`.
Every re-run of the crop pipeline on an already-extracted paper adds a full set
of duplicate rows.

Dedup strategy
--------------
For each group of rows sharing (exam_paper_id, nta_question_id):

  1. Compute a quality score:
       - +100 * max(similarity_score) of the row's tags  (0 if untagged)
       - -1000 if raw_text is empty / only whitespace
       - -500  if raw_text starts with a JSON schema leak ('{' followed by '"raw_text"')
       - +5    if answer_key is not null
       - +3    if question_content->>'options' has >= 1 entry
  2. Keep the row with the highest score; on ties keep the lowest id.
  3. Re-point any user_accent_attempts.question_id on losers to the winner
     (FK has no CASCADE; we cannot just delete).
  4. DELETE losers — jee_question_tags / jee_question_embeddings /
     ncert_jee_similarity all cascade.

Usage
-----
    python dedup_jee_question_bank.py --dry-run        # report only
    python dedup_jee_question_bank.py --dry-run --year 2024
    python dedup_jee_question_bank.py --apply          # actually delete
    python dedup_jee_question_bank.py --apply --year 2024
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOGGER = logging.getLogger("dedup")


# ── scoring ──────────────────────────────────────────────────────────────────

def _is_json_leak(raw_text: Optional[str]) -> bool:
    """Detect when the extractor wrote the Gemini JSON schema into raw_text."""
    if not raw_text:
        return False
    stripped = raw_text.lstrip()
    return stripped.startswith('{') and '"raw_text"' in stripped[:200]


def score_row(row: Dict[str, Any]) -> float:
    score = 0.0

    max_sim = row.get("max_tag_sim")
    if max_sim is not None:
        score += 100.0 * float(max_sim)

    qc = row.get("question_content") or {}
    raw = (qc.get("raw_text") or "").strip()

    if not raw:
        score -= 1000.0
    elif _is_json_leak(raw):
        score -= 500.0

    if row.get("answer_key"):
        score += 5.0

    options = qc.get("options") or []
    if isinstance(options, list) and len(options) > 0:
        score += 3.0

    return score


# ── data loading ─────────────────────────────────────────────────────────────

def fetch_duplicate_groups(db: JEEExtractionDBWriter, year: Optional[int]) -> List[Dict[str, Any]]:
    """Fetch every row that participates in a duplicate group, plus its max tag sim.

    Returns rows ordered by (exam_paper_id, nta_question_id, id) so grouping is trivial.
    """
    year_clause = "WHERE q.year = %s" if year else ""
    params: Tuple[Any, ...] = (year,) if year else ()

    query = f"""
        WITH dup_keys AS (
            SELECT exam_paper_id, nta_question_id
            FROM jee_question_bank q
            {year_clause}
            GROUP BY exam_paper_id, nta_question_id
            HAVING COUNT(*) > 1
        )
        SELECT
            q.id,
            q.exam_paper_id,
            q.nta_question_id,
            q.year,
            q.dateofexam::text AS dateofexam,
            q.shift,
            q.subject,
            q.answer_key,
            q.question_content,
            (
                SELECT MAX(similarity_score)
                FROM jee_question_tags t
                WHERE t.question_id = q.id
            ) AS max_tag_sim,
            (
                SELECT COUNT(*)
                FROM jee_question_tags t
                WHERE t.question_id = q.id
            ) AS tag_count
        FROM jee_question_bank q
        JOIN dup_keys d
          ON d.exam_paper_id = q.exam_paper_id
         AND d.nta_question_id = q.nta_question_id
        ORDER BY q.exam_paper_id, q.nta_question_id, q.id
    """
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


def group_rows(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any], List[Dict[str, Any]]]:
    groups: Dict[Tuple[Any, Any], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["exam_paper_id"], r["nta_question_id"])].append(r)
    return groups


# ── planning ─────────────────────────────────────────────────────────────────

def plan_dedup(
    groups: Dict[Tuple[Any, Any], List[Dict[str, Any]]],
) -> Tuple[List[int], List[Tuple[int, int]], Dict[str, int]]:
    """Return (ids_to_delete, loser_to_winner_map, stats)."""
    ids_to_delete: List[int] = []
    repoint_map: List[Tuple[int, int]] = []  # (loser_id, winner_id)
    stats = {
        "groups": 0,
        "rows_total": 0,
        "rows_keep": 0,
        "rows_delete": 0,
        "groups_with_subject_conflict": 0,
    }

    for _, rows in groups.items():
        if len(rows) < 2:
            continue
        stats["groups"] += 1
        stats["rows_total"] += len(rows)

        scored = sorted(
            ((score_row(r), -r["id"], r) for r in rows),
            key=lambda t: (t[0], t[1]),
            reverse=True,
        )
        winner = scored[0][2]
        losers = [s[2] for s in scored[1:]]

        stats["rows_keep"] += 1
        stats["rows_delete"] += len(losers)

        subjects = {r.get("subject") for r in rows}
        if len(subjects) > 1:
            stats["groups_with_subject_conflict"] += 1

        for loser in losers:
            ids_to_delete.append(loser["id"])
            repoint_map.append((loser["id"], winner["id"]))

    return ids_to_delete, repoint_map, stats


# ── reporting ────────────────────────────────────────────────────────────────

def print_report(
    groups: Dict[Tuple[Any, Any], List[Dict[str, Any]]],
    ids_to_delete: List[int],
    stats: Dict[str, int],
    sample_size: int = 20,
) -> None:
    print("=" * 80)
    print("DEDUP PLAN")
    print("=" * 80)
    print(f"  duplicate groups:                      {stats['groups']}")
    print(f"  ... with subject conflict:             {stats['groups_with_subject_conflict']}")
    print(f"  total rows in these groups:            {stats['rows_total']}")
    print(f"  rows to KEEP (1 per group):            {stats['rows_keep']}")
    print(f"  rows to DELETE:                        {stats['rows_delete']}")
    print()

    keys = list(groups.keys())[:sample_size]
    print(f"Sample — first {len(keys)} groups with winner highlighted:")
    for key in keys:
        rows = groups[key]
        if len(rows) < 2:
            continue
        scored = sorted(
            ((score_row(r), -r["id"], r) for r in rows),
            key=lambda t: (t[0], t[1]),
            reverse=True,
        )
        winner_id = scored[0][2]["id"]
        paper_id, nta = key
        print(f"\n  paper_id={paper_id}  nta={nta}")
        for sc, _, r in scored:
            mark = "KEEP  " if r["id"] == winner_id else "DELETE"
            qc = r.get("question_content") or {}
            preview = (qc.get("raw_text") or "").strip()[:60].replace("\n", " ")
            sim = r.get("max_tag_sim")
            sim_str = f"{float(sim):.2f}" if sim is not None else "  - "
            print(
                f"    {mark}  id={r['id']:>5}  subj={r['subject']:<12}  "
                f"tags={r['tag_count']:<2}  max_sim={sim_str}  score={sc:>8.2f}  "
                f"'{preview}'"
            )


# ── apply ────────────────────────────────────────────────────────────────────

def apply_fixes(
    db: JEEExtractionDBWriter,
    ids_to_delete: List[int],
    repoint_map: List[Tuple[int, int]],
) -> Dict[str, int]:
    """Re-point user attempts, then delete losers. Returns counts."""
    result = {
        "repointed_attempts": 0,
        "deleted_rows": 0,
    }
    if not ids_to_delete:
        return result

    with db.connection() as conn:
        with conn.cursor() as cur:
            # 1. Re-point user_accent_attempts from losers to winners.
            cur.executemany(
                """
                UPDATE user_accent_attempts
                SET question_id = %s
                WHERE question_id = %s
                """,
                [(winner, loser) for (loser, winner) in repoint_map],
            )
            result["repointed_attempts"] = cur.rowcount if cur.rowcount is not None else 0

            # 2. Delete loser rows in one shot (cascades handle tags, embeddings,
            #    ncert_jee_similarity).
            cur.execute(
                "DELETE FROM jee_question_bank WHERE id = ANY(%s::int[])",
                (ids_to_delete,),
            )
            result["deleted_rows"] = cur.rowcount

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate jee_question_bank")
    parser.add_argument("--year", type=int, default=None, help="Restrict to a specific year")
    parser.add_argument("--dry-run", action="store_true", help="Report only; no DB writes")
    parser.add_argument("--apply", action="store_true", help="Actually apply the dedup")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation on --apply")
    parser.add_argument(
        "--sample", type=int, default=20,
        help="Number of duplicate groups to print as sample (default 20)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("specify either --dry-run or --apply")

    db = JEEExtractionDBWriter()

    LOGGER.info("Fetching duplicate groups (year=%s)...", args.year or "ALL")
    rows = fetch_duplicate_groups(db, year=args.year)
    groups = group_rows(rows)
    LOGGER.info("Found %d rows across %d groups.", len(rows), len(groups))

    ids_to_delete, repoint_map, stats = plan_dedup(groups)
    print_report(groups, ids_to_delete, stats, sample_size=args.sample)

    if args.dry_run:
        print("\n(dry-run — no changes applied)")
        return

    # --apply path
    print()
    print(f"About to delete {len(ids_to_delete)} rows and re-point attempts.")
    if not args.yes:
        print("Press Enter to proceed or Ctrl+C to abort.")
        input()

    result = apply_fixes(db, ids_to_delete, repoint_map)
    print()
    print("=" * 80)
    print("DEDUP APPLIED")
    print("=" * 80)
    print(f"  user_accent_attempts re-pointed: {result['repointed_attempts']}")
    print(f"  rows deleted (cascaded tags+embeddings): {result['deleted_rows']}")


if __name__ == "__main__":
    main()
