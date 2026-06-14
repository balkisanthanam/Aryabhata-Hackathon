"""Subject Auditor — verifies that crop-pipeline subject assignments are correct.

Samples 1 question per (paper, subject), asks Gemini Flash Lite to classify,
and reports mismatches with ready-to-run fix SQL.

Usage:
    python subject_auditor.py              # audit all papers, print report
    python subject_auditor.py --fix        # audit + apply subject fixes
    python subject_auditor.py --year 2024  # filter to one year
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── path setup (mirrors question_tagger.py) ──────────────────────────────────
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
LOGGER = logging.getLogger("subject_auditor")

VALID_SUBJECTS = {"Physics", "Chemistry", "Mathematics"}

# ── sampling ──────────────────────────────────────────────────────────────────

SAMPLE_QUERY = """
    SELECT DISTINCT ON (dateofexam, shift, subject)
        id,
        dateofexam::text AS dateofexam,
        shift,
        subject,
        LEFT(question_content->>'raw_text', 400) AS sample_text
    FROM jee_question_bank
    {where}
    ORDER BY dateofexam, shift, subject, id
"""


def fetch_samples(db: JEEExtractionDBWriter, year: Optional[int] = None) -> List[Dict[str, Any]]:
    from psycopg2.extras import RealDictCursor

    where = f"WHERE year = {int(year)}" if year else ""
    query = SAMPLE_QUERY.format(where=where)

    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            return [dict(r) for r in cur.fetchall()]


def group_by_paper(samples: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group samples by (dateofexam, shift) key."""
    papers: Dict[str, List[Dict[str, Any]]] = {}
    for s in samples:
        key = f"{s['dateofexam']}|{s['shift']}"
        papers.setdefault(key, []).append(s)
    return papers


# ── LLM classification ───────────────────────────────────────────────────────

CLASSIFY_PROMPT = """Classify each JEE Main question into its subject.
Reply ONLY with a JSON object like: {{"q1": "Physics", "q2": "Chemistry", "q3": "Mathematics"}}
Use exactly one of: Physics, Chemistry, Mathematics.

{questions_block}"""


def classify_paper(
    client: GeminiClient,
    model_config: GeminiModelConfig,
    paper_samples: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Classify 3 samples from one paper. Returns {stored_subject: predicted_subject}."""
    questions_block = ""
    key_map = {}  # "q1" → stored_subject
    for i, s in enumerate(paper_samples, 1):
        label = f"q{i}"
        key_map[label] = s["subject"]
        text = (s["sample_text"] or "").strip()
        questions_block += f"{label}: {text}\n\n"

    prompt = CLASSIFY_PROMPT.format(questions_block=questions_block)

    result = client.generate(
        model_config=model_config,
        prompt=prompt,
    )
    raw = result.text.strip()

    # Parse JSON from response
    text = raw
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        LOGGER.error("Failed to parse LLM response: %s", raw[:500])
        return {}

    # Map back: stored_subject → predicted_subject
    predictions = {}
    for label, stored_subj in key_map.items():
        pred = (parsed.get(label) or "").strip()
        if pred in VALID_SUBJECTS:
            predictions[stored_subj] = pred
        else:
            LOGGER.warning("Invalid prediction '%s' for %s — skipping", pred, label)

    return predictions


# ── audit logic ───────────────────────────────────────────────────────────────

def audit_papers(
    db: JEEExtractionDBWriter,
    client: GeminiClient,
    model_config: GeminiModelConfig,
    year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Audit all papers. Returns list of paper results with mismatch info."""
    LOGGER.info("Fetching samples...")
    samples = fetch_samples(db, year)
    papers = group_by_paper(samples)
    LOGGER.info("Found %d papers to audit (%d samples).", len(papers), len(samples))

    results = []
    for i, (paper_key, paper_samples) in enumerate(sorted(papers.items()), 1):
        dateofexam, shift = paper_key.split("|")
        LOGGER.info("[%d/%d] Classifying %s shift %s...", i, len(papers), dateofexam, shift)

        predictions = classify_paper(client, model_config, paper_samples)

        mismatches = {}
        for stored, predicted in predictions.items():
            if stored != predicted:
                mismatches[stored] = predicted

        results.append({
            "dateofexam": dateofexam,
            "shift": shift,
            "predictions": predictions,
            "mismatches": mismatches,
            "ok": len(mismatches) == 0,
        })

        # Brief pause between papers
        if i < len(papers):
            time.sleep(0.5)

    return results


# ── reporting ─────────────────────────────────────────────────────────────────

def print_report(results: List[Dict[str, Any]]) -> None:
    ok_count = sum(1 for r in results if r["ok"])
    bad_count = len(results) - ok_count

    print("\n" + "=" * 70)
    print(f"SUBJECT AUDIT REPORT — {len(results)} papers ({ok_count} OK, {bad_count} mismatched)")
    print("=" * 70)

    for r in results:
        status = "OK" if r["ok"] else "MISMATCH"
        print(f"\nPaper {r['dateofexam']} shift {r['shift']}:  [{status}]")
        for subj in ["Physics", "Chemistry", "Mathematics"]:
            pred = r["predictions"].get(subj, "?")
            match = pred == subj
            mark = "+" if match else "X MISMATCH"
            print(f"  {subj:14s} -> LLM says: {pred:14s}  {mark}")

    if bad_count > 0:
        print("\n" + "=" * 70)
        print("FIX SQL STATEMENTS")
        print("=" * 70)
        for r in results:
            if r["ok"]:
                continue
            print(f"\n-- Fix paper {r['dateofexam']} shift {r['shift']}")
            print(_generate_fix_sql(r))
            print(_generate_cleanup_sql(r))


def _generate_fix_sql(result: Dict[str, Any]) -> str:
    """Generate UPDATE SQL to fix subject assignments."""
    mismatches = result["mismatches"]
    if not mismatches:
        return ""

    # Build CASE expression from mismatches
    # We need the full mapping (all 3 subjects), not just mismatched ones
    predictions = result["predictions"]
    case_parts = []
    for stored, predicted in predictions.items():
        if stored != predicted:
            case_parts.append(f"    WHEN subject = '{stored}' THEN '{predicted}'")

    if not case_parts:
        return ""

    case_block = "\n".join(case_parts)
    return (
        f"UPDATE jee_question_bank SET subject = CASE\n"
        f"{case_block}\n"
        f"    ELSE subject\n"
        f"END\n"
        f"WHERE dateofexam = '{result['dateofexam']}' AND shift = '{result['shift']}';"
    )


def _generate_cleanup_sql(result: Dict[str, Any]) -> str:
    """Generate cleanup SQL for M3 tags on mismatched papers."""
    date = result["dateofexam"]
    shift = result["shift"]
    filter_clause = f"SELECT id FROM jee_question_bank WHERE dateofexam = '{date}' AND shift = '{shift}'"
    return (
        f"\n-- Clean up M3 tags for {date} shift {shift}\n"
        f"DELETE FROM jee_question_tags WHERE question_id IN ({filter_clause});\n"
        f"DELETE FROM jee_question_embeddings WHERE question_id IN ({filter_clause});\n"
        f"UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, pattern_label = NULL\n"
        f"WHERE dateofexam = '{date}' AND shift = '{shift}';"
    )


# ── fix mode ──────────────────────────────────────────────────────────────────

def apply_fixes(db: JEEExtractionDBWriter, results: List[Dict[str, Any]]) -> None:
    """Apply subject fixes and clean up M3 tags for mismatched papers."""
    bad = [r for r in results if not r["ok"]]
    if not bad:
        print("\nNo mismatches to fix.")
        return

    print(f"\nApplying fixes for {len(bad)} papers...")

    for r in bad:
        date, shift = r["dateofexam"], r["shift"]
        predictions = r["predictions"]

        # Build the CASE mapping
        case_parts = []
        params = []
        for stored, predicted in predictions.items():
            if stored != predicted:
                case_parts.append(f"WHEN subject = %s THEN %s")
                params.extend([stored, predicted])

        if not case_parts:
            continue

        case_sql = " ".join(case_parts)
        update_query = (
            f"UPDATE jee_question_bank SET subject = CASE {case_sql} ELSE subject END "
            f"WHERE dateofexam = %s AND shift = %s"
        )
        params.extend([date, shift])

        filter_query_tags = (
            "DELETE FROM jee_question_tags WHERE question_id IN "
            "(SELECT id FROM jee_question_bank WHERE dateofexam = %s AND shift = %s)"
        )
        filter_query_embeds = (
            "DELETE FROM jee_question_embeddings WHERE question_id IN "
            "(SELECT id FROM jee_question_bank WHERE dateofexam = %s AND shift = %s)"
        )
        meta_query = (
            "UPDATE jee_question_bank SET difficulty = NULL, difficulty_confidence = NULL, "
            "pattern_label = NULL WHERE dateofexam = %s AND shift = %s"
        )

        with db.connection() as conn:
            with conn.cursor() as cur:
                # Clean up M3 data first
                cur.execute(filter_query_tags, (date, shift))
                tags_deleted = cur.rowcount
                cur.execute(filter_query_embeds, (date, shift))
                embeds_deleted = cur.rowcount
                cur.execute(meta_query, (date, shift))

                # Apply subject fix
                cur.execute(update_query, params)
                rows_fixed = cur.rowcount

        LOGGER.info(
            "Fixed %s shift %s: %d rows updated, %d tags deleted, %d embeddings deleted",
            date, shift, rows_fixed, tags_deleted, embeds_deleted,
        )

    print("All fixes applied.")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit subject assignments in jee_question_bank using Gemini Flash Lite"
    )
    parser.add_argument("--year", type=int, default=None, help="Filter to a specific year")
    parser.add_argument("--fix", action="store_true", help="Apply fixes for mismatched papers")
    args = parser.parse_args()

    pipeline_config = PipelineConfig()
    client = GeminiClient(pipeline_config)
    db = JEEExtractionDBWriter()

    model = GeminiModelConfig(
        model_id=os.environ.get("AUDITOR_MODEL", "gemini-3.1-flash-lite-preview"),
        temperature=0.0,
        max_output_tokens=256,
        response_mime_type="application/json",
    )

    results = audit_papers(db, client, model, year=args.year)
    print_report(results)

    if args.fix:
        bad = [r for r in results if not r["ok"]]
        if bad:
            print(f"\nAbout to fix {len(bad)} papers. Press Enter to continue or Ctrl+C to abort.")
            input()
            apply_fixes(db, results)
        else:
            print("\nNo fixes needed.")


if __name__ == "__main__":
    main()
