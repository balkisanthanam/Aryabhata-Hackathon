"""Batch 2 — Per-question subject auditor.

Catches rows whose `raw_text` is already clean but whose `subject` is wrong
(e.g. A11 candela id=3149; A13 2023 chem-as-maths rows; any other partial-paper
mismatch that the sample-based `subject_auditor.py` missed).

Per-row pipeline:
  1. Fetch rows (optionally filtered by --year, --max-tag-sim).
  2. Batch-LLM classify subject via Gemini Flash Lite.
  3. Where predicted != stored:
       UPDATE jee_question_bank SET subject = predicted, difficulty = NULL, ...
       DELETE FROM jee_question_tags WHERE question_id = id
       DELETE FROM jee_question_embeddings WHERE question_id = id
  4. Re-tagging picks these up via NOT EXISTS (Batch 3).

Usage:
    python subject_auditor_perq.py --dry-run --year 2023
    python subject_auditor_perq.py --dry-run --year 2024 --max-tag-sim 0.85
    python subject_auditor_perq.py --apply --year 2023 --yes
    python subject_auditor_perq.py --apply --year 2024 --max-tag-sim 0.85 --yes

Excludes rows already repaired by jee_jsonleak_repair.py (filters out rows whose
raw_text still starts with `{ "raw_text":` or `\\begin{json}` — that's Batch 1's
territory).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── path setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
MULTI_STEP_DIR = (
    SCRIPT_DIR.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
)
for p in [str(MULTI_STEP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from settings_loader import load_local_settings  # noqa: E402

load_local_settings()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import GeminiModelConfig, PipelineConfig  # type: ignore  # noqa: E402
from gemini_client import GeminiClient  # type: ignore  # noqa: E402
from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOGGER = logging.getLogger("subject_auditor_perq")

VALID_SUBJECTS = {"Physics", "Chemistry", "Mathematics"}


# ── fetch ────────────────────────────────────────────────────────────────────

def fetch_rows(
    db: JEEExtractionDBWriter,
    year: Optional[int],
    max_tag_sim: Optional[float],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    clauses = [
        # Skip rows whose raw_text is still leaked JSON — those are Batch 1's job.
        "LTRIM(question_content->>'raw_text') NOT LIKE '{%%\"raw_text\"%%'",
        "LTRIM(question_content->>'raw_text') NOT LIKE '\\begin{json}%%'",
        # Need actual content to classify.
        "COALESCE(question_content->>'raw_text', '') <> ''",
    ]
    params: List[Any] = []
    if year is not None:
        clauses.append("year = %s")
        params.append(year)

    select_cols = """
        q.id, q.year, q.dateofexam::text AS dateofexam, q.shift,
        q.subject, q.question_content->>'raw_text' AS raw_text
    """

    if max_tag_sim is not None:
        # Row's MAX tag score must be <= threshold (i.e., the tagger was not confident)
        query = f"""
            WITH row_sim AS (
                SELECT q.id, COALESCE(MAX(t.similarity_score), 0) AS max_sim
                FROM jee_question_bank q
                LEFT JOIN jee_question_tags t ON t.question_id = q.id
                WHERE {' AND '.join(clauses)}
                GROUP BY q.id
            )
            SELECT {select_cols}, rs.max_sim
            FROM jee_question_bank q
            JOIN row_sim rs ON rs.id = q.id
            WHERE rs.max_sim <= %s
            ORDER BY q.year, q.dateofexam, q.shift, q.id
        """
        params.append(max_tag_sim)
    else:
        query = f"""
            SELECT {select_cols}
            FROM jee_question_bank q
            WHERE {' AND '.join(clauses)}
            ORDER BY q.year, q.dateofexam, q.shift, q.id
        """

    if limit:
        query += f" LIMIT {int(limit)}"

    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


# ── LLM classify ─────────────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """You are a JEE Main subject classifier.

For each question below, decide whether it is Physics, Chemistry, or Mathematics.
Return ONLY a JSON object like: {{"q1": "Physics", "q2": "Chemistry"}}
Use exactly one of: Physics, Chemistry, Mathematics.

Questions:
{block}
"""


def _classify_one_batch(
    client: GeminiClient,
    model: GeminiModelConfig,
    batch: List[Dict[str, Any]],
) -> Dict[int, str]:
    block = ""
    id_by_key: Dict[str, int] = {}
    for i, r in enumerate(batch, 1):
        key = f"q{i}"
        id_by_key[key] = r["id"]
        text = (r["raw_text"] or "").strip()[:500]
        block += f"{key}: {text}\n\n"

    prompt = _CLASSIFY_PROMPT.format(block=block)
    resp = client.generate(model_config=model, prompt=prompt)
    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]

    result: Dict[int, str] = {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("LLM classify: bad JSON: %s", raw[:300])
        return result

    for key, qid in id_by_key.items():
        pred = (parsed.get(key) or "").strip()
        if pred in VALID_SUBJECTS:
            result[qid] = pred
        else:
            LOGGER.warning("Row id=%d: unexpected prediction %r", qid, pred)
    return result


def classify_concurrent(
    rows: List[Dict[str, Any]],
    client: GeminiClient,
    model: GeminiModelConfig,
    batch_size: int,
    workers: int,
) -> Dict[int, str]:
    batches: List[List[Dict[str, Any]]] = []
    for i in range(0, len(rows), batch_size):
        batches.append(rows[i : i + batch_size])
    LOGGER.info("Classifying %d rows in %d batches across %d workers...",
                len(rows), len(batches), workers)

    predictions: Dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_classify_one_batch, client, model, b): i
            for i, b in enumerate(batches, 1)
        }
        done = 0
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                batch_result = fut.result()
                predictions.update(batch_result)
            except Exception as e:
                LOGGER.error("Batch %d failed: %s", idx, e)
            done += 1
            if done % 5 == 0 or done == len(batches):
                LOGGER.info("Progress: %d / %d batches", done, len(batches))
    return predictions


# ── apply ────────────────────────────────────────────────────────────────────

def apply_subject_fixes_bulk(
    db: JEEExtractionDBWriter,
    changes: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Apply all subject changes in a single connection.

    Groups updates by target subject so we can do one UPDATE per subject rather
    than one per row. Deletes tags/embeddings in two single queries using ANY(%s).
    """
    stats = {"subject_changed": 0, "tags_deleted": 0, "embeddings_deleted": 0}
    if not changes:
        return stats

    by_subject: Dict[str, List[int]] = {}
    for c in changes:
        by_subject.setdefault(c["predicted"], []).append(c["id"])

    all_ids = [c["id"] for c in changes]

    with db.connection() as conn:
        with conn.cursor() as cur:
            # Update subject + clear metadata, one statement per target subject.
            for subj, ids in by_subject.items():
                cur.execute(
                    "UPDATE jee_question_bank "
                    "SET subject = %s, difficulty = NULL, "
                    "    difficulty_confidence = NULL, pattern_label = NULL "
                    "WHERE id = ANY(%s::int[])",
                    (subj, ids),
                )
                stats["subject_changed"] += cur.rowcount
            # Clear stale tags and embeddings for all affected rows in one go.
            cur.execute(
                "DELETE FROM jee_question_tags WHERE question_id = ANY(%s::int[])",
                (all_ids,),
            )
            stats["tags_deleted"] = cur.rowcount
            cur.execute(
                "DELETE FROM jee_question_embeddings WHERE question_id = ANY(%s::int[])",
                (all_ids,),
            )
            stats["embeddings_deleted"] = cur.rowcount
    return stats


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--max-tag-sim", type=float, default=None,
                        help="Only audit rows with max tag similarity <= this (narrow scan)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--save-predictions", type=str, default=None,
                        help="Write all (id, stored_subject, predicted_subject, preview) to this path as JSON")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("specify either --dry-run or --apply")

    db = JEEExtractionDBWriter()
    LOGGER.info("Fetching rows (year=%s, max-tag-sim=%s, limit=%s)...",
                args.year, args.max_tag_sim, args.limit)
    rows = fetch_rows(db, args.year, args.max_tag_sim, args.limit)
    LOGGER.info("Fetched %d rows to audit.", len(rows))
    if not rows:
        return

    pipeline_config = PipelineConfig()
    client = GeminiClient(pipeline_config)
    model = GeminiModelConfig(
        model_id=os.environ.get("AUDITOR_MODEL", "gemini-3.1-flash-lite-preview"),
        temperature=0.0,
        max_output_tokens=2048,
        response_mime_type="application/json",
    )

    predictions = classify_concurrent(
        rows, client, model,
        batch_size=args.batch_size, workers=args.workers,
    )
    LOGGER.info("Got predictions for %d rows.", len(predictions))

    # Diff
    by_diff = {"same": 0, "changed": 0, "no_prediction": 0}
    changes: List[Dict[str, Any]] = []
    for r in rows:
        pred = predictions.get(r["id"])
        if pred is None:
            by_diff["no_prediction"] += 1
        elif pred == r["subject"]:
            by_diff["same"] += 1
        else:
            by_diff["changed"] += 1
            changes.append({**r, "predicted": pred})

    print()
    print("=" * 80)
    print("SUBJECT AUDITOR (PER-Q) — PLAN")
    print("=" * 80)
    print(f"  rows audited:          {len(rows)}")
    print(f"  subject unchanged:     {by_diff['same']}")
    print(f"  subject to be changed: {by_diff['changed']}")
    print(f"  no prediction:         {by_diff['no_prediction']}")
    print()
    if changes:
        print(f"Sample changes (first 20 of {len(changes)}):")
        for c in changes[:20]:
            preview = (c.get("raw_text") or "")[:70].replace("\n", " ")
            print(f"  id={c['id']:>5}  {c['dateofexam']} s{c['shift']}  "
                  f"{c['subject']:<12} -> {c['predicted']:<12}  '{preview}'")

    if args.save_predictions:
        dump = [{
            "id": r["id"],
            "year": r["year"],
            "dateofexam": r["dateofexam"],
            "shift": r["shift"],
            "stored": r["subject"],
            "predicted": predictions.get(r["id"]),
            "preview": (r.get("raw_text") or "")[:200],
        } for r in rows]
        Path(args.save_predictions).write_text(
            json.dumps(dump, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nSaved {len(dump)} predictions to {args.save_predictions}")

    if args.dry_run:
        print("\n(dry-run — no changes applied)")
        return

    if not args.yes:
        print(f"\nAbout to apply {by_diff['changed']} subject changes. "
              "Press Enter or Ctrl+C.")
        input()

    total = apply_subject_fixes_bulk(db, changes)

    print()
    print("=" * 80)
    print("SUBJECT AUDITOR — APPLIED")
    print("=" * 80)
    for k, v in total.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
