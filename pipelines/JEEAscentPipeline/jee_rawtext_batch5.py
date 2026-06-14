"""Batch 5 — Extraction-artefact + literal-escape repair in jee_question_bank.

Handles two repair classes discovered after Batches 1 and 2:

  Class A  Extraction artefacts (inner-monologue, embedded JSON fragment,
           ```json fence, preceded `|thought|` / `|continued|` tokens). The
           real question is buried in a JSON body that Gemini Flash wrote into
           `raw_text` instead of just the text.
           Fix: strip the leading reasoning, locate the `"raw_text": "..."`
           body, and replace the field with the extracted clean text + options.

  Class D  Literal `\\_` (backslash-underscore) sequences that appear OUTSIDE
           `$...$` math regions. The frontend renderer shows them verbatim
           instead of rendering a fill-in-blank.
           Fix: split raw_text by `$...$` regions; replace `\\_` with `_`
           ONLY in non-math regions; leave math mode untouched.

Untouched deliberately:
  - Unbalanced `$` delimiters (bucket E): ambiguous — some are currency, some
    are real LaTeX issues; not amenable to a blanket fix.
  - Rows where raw_text starts mid-expression (e.g. id=392 "1}{2} \\sin ...")
    — these need re-extraction via the Pro pipeline, not string repair.

Usage:
    python jee_rawtext_batch5.py --dry-run --year 2024
    python jee_rawtext_batch5.py --apply --year 2024 --yes
    python jee_rawtext_batch5.py --apply --year 2023 --yes
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402
from jee_jsonleak_repair import parse_leak, _tolerant_unescape  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOGGER = logging.getLogger("rawtext_batch5")


# ── Class A: extraction artefacts ────────────────────────────────────────────

_INNER_MONOLOGUE_PREFIXES = re.compile(
    r'^\s*(?:\|(?:thought|continued|video_summary_\d+)\|'
    r'|```(?:json)?'
    r'|thought(?=\s*\{)'      # bare "thought" or "continued" keyword before JSON
    r'|continued(?=\s*\{)'
    r')\s*\n?',
    re.IGNORECASE,
)

# Direct regex to pull out the `"raw_text": "..."` value from a string even if
# not wrapped in `{ ... }`. Escape handling done by _tolerant_unescape.
_RAW_TEXT_KEY_RE = re.compile(
    r'"raw_text"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL
)

_REASONING_PHRASES = [
    "Wait,", "Actually,", "Let me", "I need to", "I'll ",
    "Final check", "Final JSON", "Okay,", "One more",
]


def _find_last_json_obj(text: str) -> Optional[str]:
    """Locate the last `{ "raw_text": ... }` block in the text.

    Some rows look like: 'Actually, ...reasoning... Final JSON: { "raw_text": ... }'
    We want the last such block.
    """
    # Naive but effective: find the last `"raw_text":` and the enclosing `{ ... }`.
    last = text.rfind('"raw_text"')
    if last < 0:
        return None
    # Walk back to the opening brace.
    i = last
    while i >= 0 and text[i] != '{':
        i -= 1
    if i < 0:
        return None
    return text[i:]


def repair_artefact_row(raw: str) -> Optional[Dict[str, Any]]:
    """Try to recover a clean {raw_text, options, has_figure, figure_description}
    from a row whose raw_text is polluted with extraction reasoning."""
    # Strip leading |thought| / ```json / etc.
    body = _INNER_MONOLOGUE_PREFIXES.sub('', raw).lstrip()

    # If it already looks like a JSON body, hand to parse_leak directly.
    if body.lstrip().startswith('{') and '"raw_text"' in body[:300]:
        return parse_leak(body)

    # Else, find the last `{ "raw_text": ... }` block anywhere in the text.
    chunk = _find_last_json_obj(body)
    if chunk:
        parsed = parse_leak(chunk)
        if parsed and parsed.get("raw_text"):
            return parsed

    # Fallback: if raw_text contains ```json fence, try to strip everything
    # before the fence and retry.
    m = re.search(r'```(?:json)?\s*\n?(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        return parse_leak(m.group(1))

    # Strip backticks around "raw_text" (some rows wrap the JSON key-value
    # pair in markdown backticks: `"raw_text": "..."`).
    body_nb = body.replace('`', '')
    if '"raw_text"' in body_nb:
        chunk = _find_last_json_obj(body_nb)
        if chunk:
            parsed = parse_leak(chunk)
            if parsed and parsed.get("raw_text"):
                return parsed

    # Last-resort: direct regex extract of `"raw_text": "..."` even if the
    # enclosing `{...}` is missing (truncated prefix).
    m = _RAW_TEXT_KEY_RE.search(body_nb)
    if m:
        return {
            "raw_text": _tolerant_unescape(m.group(1)),
            "options": [],
            "has_figure": False,
            "figure_description": None,
        }

    return None


# ── Class D: literal \_ outside math mode ────────────────────────────────────

def fix_literal_backslash_underscore(text: str) -> Tuple[str, bool]:
    """Replace `\\_` with `_` only outside `$...$` math regions.

    Returns (new_text, changed).
    """
    parts = re.split(r'(\$[^$]*\$)', text)
    changed = False
    out: List[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            new_part = part.replace('\\_', '_')
            if new_part != part:
                changed = True
            out.append(new_part)
        else:
            out.append(part)
    return ''.join(out), changed


# ── detection predicates (mirror diagnose_rawtext_quality.py) ────────────────

ARTEFACT_PREDICATE = (
    # bucket A: leading fence
    "LTRIM(question_content->>'raw_text') ILIKE '|thought|%%' "
    " OR LTRIM(question_content->>'raw_text') ILIKE '|continued|%%' "
    " OR LTRIM(question_content->>'raw_text') ILIKE '|video_summary_%%' "
    " OR LTRIM(question_content->>'raw_text') ILIKE '```json%%' "
    " OR LTRIM(question_content->>'raw_text') ILIKE '\\begin{json}%%' "
    # bucket B: embedded "raw_text": mid-string
    " OR (question_content->>'raw_text' LIKE '%%\"raw_text\"%%' "
    "     AND LTRIM(question_content->>'raw_text') NOT LIKE '{%%\"raw_text\"%%') "
    # bucket C: reasoning prose prefix
    " OR question_content->>'raw_text' ILIKE 'Wait,%%' "
    " OR question_content->>'raw_text' ILIKE 'Actually,%%' "
    " OR question_content->>'raw_text' ILIKE 'Let me%%' "
    " OR question_content->>'raw_text' ILIKE 'Final check%%' "
    " OR question_content->>'raw_text' ILIKE 'Option %%' "
    # bucket F: standalone fence
    " OR question_content->>'raw_text' LIKE '%%```%%' "
    # bucket G: starts with close brace/bracket
    " OR LTRIM(question_content->>'raw_text') LIKE '}%%' "
    " OR LTRIM(question_content->>'raw_text') LIKE ']%%'"
)

LITERAL_ESCAPE_PREDICATE = "question_content->>'raw_text' ~ E'\\\\\\\\_'"


# ── fetch ────────────────────────────────────────────────────────────────────

def fetch_rows(db: JEEExtractionDBWriter, year: Optional[int],
               predicate: str) -> List[Dict[str, Any]]:
    clauses = [predicate]
    params: List[Any] = []
    if year is not None:
        clauses.append("year = %s")
        params.append(year)
    query = f"""
        SELECT id, year, subject, question_content
        FROM jee_question_bank
        WHERE {' AND '.join(clauses)}
        ORDER BY year, id
    """
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


# ── apply ────────────────────────────────────────────────────────────────────

def apply_artefact_fixes(db: JEEExtractionDBWriter, rows: List[Dict[str, Any]]
                         ) -> Dict[str, int]:
    """For each row, repair raw_text/options, clear tags+embeddings (re-tag later)."""
    stats = {"repaired": 0, "skipped_unparseable": 0, "tags_deleted": 0,
             "embeddings_deleted": 0}
    for r in rows:
        raw = (r["question_content"] or {}).get("raw_text", "")
        cleaned = repair_artefact_row(raw)
        if cleaned is None:
            stats["skipped_unparseable"] += 1
            LOGGER.warning("id=%d: unparseable — manual fix needed", r["id"])
            continue
        new_content = {**(r["question_content"] or {}), **cleaned}
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jee_question_bank "
                    "SET question_content = %s, "
                    "    difficulty = NULL, difficulty_confidence = NULL, "
                    "    pattern_label = NULL "
                    "WHERE id = %s",
                    (json.dumps(new_content), r["id"]),
                )
                cur.execute(
                    "DELETE FROM jee_question_tags WHERE question_id = %s",
                    (r["id"],),
                )
                stats["tags_deleted"] += cur.rowcount
                cur.execute(
                    "DELETE FROM jee_question_embeddings WHERE question_id = %s",
                    (r["id"],),
                )
                stats["embeddings_deleted"] += cur.rowcount
        stats["repaired"] += 1
    return stats


def apply_escape_fixes(db: JEEExtractionDBWriter, rows: List[Dict[str, Any]]
                       ) -> Dict[str, int]:
    """Literal `\\_` fix outside $...$. No tag/embedding invalidation — semantic
    meaning of the text doesn't change enough to require re-tagging."""
    stats = {"updated": 0, "unchanged": 0}
    for r in rows:
        qc = r["question_content"] or {}
        raw = qc.get("raw_text") or ""
        new_raw, changed = fix_literal_backslash_underscore(raw)
        if not changed:
            stats["unchanged"] += 1
            continue
        new_content = {**qc, "raw_text": new_raw}
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jee_question_bank SET question_content = %s WHERE id = %s",
                    (json.dumps(new_content), r["id"]),
                )
        stats["updated"] += 1
    return stats


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--class", dest="cls", choices=["artefact", "escape", "both"],
                        default="both", help="Which repair class to run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--sample", type=int, default=10)
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("specify --dry-run or --apply")

    db = JEEExtractionDBWriter()

    # ── Class A: extraction artefacts
    if args.cls in ("artefact", "both"):
        LOGGER.info("Fetching extraction-artefact rows (year=%s)...", args.year)
        artefact_rows = fetch_rows(db, args.year, ARTEFACT_PREDICATE)
        LOGGER.info("Found %d artefact rows.", len(artefact_rows))

        print("\n" + "=" * 80)
        print(f"CLASS A — Extraction artefacts ({len(artefact_rows)} rows)")
        print("=" * 80)
        parseable = 0
        unparseable_ids: List[int] = []
        for r in artefact_rows:
            raw = (r["question_content"] or {}).get("raw_text", "")
            cleaned = repair_artefact_row(raw)
            if cleaned:
                parseable += 1
            else:
                unparseable_ids.append(r["id"])
        print(f"  Will repair:            {parseable}")
        print(f"  Unparseable (skipped):  {len(unparseable_ids)}  ids={unparseable_ids[:20]}")

        if args.apply:
            if not args.yes and artefact_rows:
                print(f"\nAbout to repair {parseable} rows "
                      f"(will clear their tags + embeddings for re-tagging).")
                print("Press Enter or Ctrl+C.")
                input()
            r_stats = apply_artefact_fixes(db, artefact_rows)
            print("\n  REPAIR APPLIED:")
            for k, v in r_stats.items():
                print(f"    {k}: {v}")

    # ── Class D: literal \_ escape
    if args.cls in ("escape", "both"):
        LOGGER.info("Fetching literal-\\_ rows (year=%s)...", args.year)
        escape_rows = fetch_rows(db, args.year, LITERAL_ESCAPE_PREDICATE)
        LOGGER.info("Found %d literal-\\_ rows.", len(escape_rows))

        print("\n" + "=" * 80)
        print(f"CLASS D — Literal backslash-underscore ({len(escape_rows)} rows)")
        print("=" * 80)

        # Preview: how many will actually change?
        will_update = 0
        unchanged = 0
        for r in escape_rows:
            raw = (r["question_content"] or {}).get("raw_text") or ""
            _, changed = fix_literal_backslash_underscore(raw)
            if changed:
                will_update += 1
            else:
                unchanged += 1
        print(f"  Will update:            {will_update}")
        print(f"  All `\\_` inside math mode (no-op): {unchanged}")

        # Show a few before/after samples
        shown = 0
        for r in escape_rows[: args.sample]:
            raw = (r["question_content"] or {}).get("raw_text") or ""
            new_raw, changed = fix_literal_backslash_underscore(raw)
            if not changed:
                continue
            shown += 1
            print(f"\n  id={r['id']} year={r['year']} subj={r['subject']}")
            print(f"    BEFORE: {raw[:200]}")
            print(f"    AFTER : {new_raw[:200]}")

        if args.apply:
            if not args.yes and will_update > 0:
                print(f"\nAbout to update {will_update} rows. Press Enter or Ctrl+C.")
                input()
            e_stats = apply_escape_fixes(db, escape_rows)
            print("\n  ESCAPE FIX APPLIED:")
            for k, v in e_stats.items():
                print(f"    {k}: {v}")

    if args.dry_run:
        print("\n(dry-run — no changes applied)")


if __name__ == "__main__":
    main()
