"""Repair raw_text rows where LaTeX escapes (\\t, \\f, \\r) were eaten during
JSON decode, leaving tab/formfeed/CR characters in place of the backslash.

Target rows: 7 confirmed bad rows identified by the 2026-04-21 diagnostic:
    380, 391, 840, 882, 1013, 1127, 1158

Patterns restored in `question_content.raw_text` (and in option texts):
    <TAB>ext{…}      → \\text{…}
    <TAB>imes        → \\times
    <FORMFEED>rac{…} → \\frac{…}
    <CR>ightarrow    → \\rightarrow

Only the tab/formfeed/CR *character* followed by the expected LaTeX tail is
replaced — so legitimate prose text containing "ext" or "imes" is never
touched.

Usage:
    python jee_latex_escape_repair.py --dry-run
    python jee_latex_escape_repair.py --apply --yes
    python jee_latex_escape_repair.py --apply --ids 380,391,840,882,1013,1127,1158 --yes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402

LOGGER = logging.getLogger(__name__)

TARGET_IDS_DEFAULT = [380, 391, 840, 882, 1013, 1127, 1158]

# (search, replace) — search uses the actual control character, which is what
# ended up stored in DB after the JSON decoder consumed `\\t`/`\\f`/`\\r`.
REPLACEMENTS: List[Tuple[str, str]] = [
    ("\text{", "\\text{"),        # \t eaten
    ("\textbf{", "\\textbf{"),    # \t eaten
    ("\textit{", "\\textit{"),    # \t eaten
    ("\times", "\\times"),        # \t eaten (no trailing {, use word boundary in practice)
    ("\frac{", "\\frac{"),        # \f eaten
    ("\rightarrow", "\\rightarrow"),  # \r eaten
    ("\rightharpoonup", "\\rightharpoonup"),  # \r eaten
]


def repair_string(text: str) -> Tuple[str, int]:
    """Return (repaired_text, total_replacements_count)."""
    if not text:
        return text, 0
    total = 0
    for search, replace in REPLACEMENTS:
        if search in text:
            n = text.count(search)
            text = text.replace(search, replace)
            total += n
    return text, total


def repair_question_content(qc: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Repair raw_text, figure_description, and each option's text."""
    qc = dict(qc)  # shallow copy
    total = 0

    raw = qc.get("raw_text")
    if isinstance(raw, str):
        new_raw, n = repair_string(raw)
        if n:
            qc["raw_text"] = new_raw
            total += n

    fig = qc.get("figure_description")
    if isinstance(fig, str):
        new_fig, n = repair_string(fig)
        if n:
            qc["figure_description"] = new_fig
            total += n

    opts = qc.get("options")
    if isinstance(opts, list):
        new_opts = []
        for opt in opts:
            if isinstance(opt, dict):
                o = dict(opt)
                if isinstance(o.get("text"), str):
                    new_text, n = repair_string(o["text"])
                    if n:
                        o["text"] = new_text
                        total += n
                new_opts.append(o)
            else:
                new_opts.append(opt)
        if opts != new_opts:
            qc["options"] = new_opts

    return qc, total


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    ap.add_argument("--apply", action="store_true", help="Write updates to DB.")
    ap.add_argument("--yes", action="store_true", help="Skip final confirmation.")
    ap.add_argument(
        "--ids",
        type=str,
        default=None,
        help=f"Comma-separated qids. Default: {','.join(str(i) for i in TARGET_IDS_DEFAULT)}",
    )
    return ap.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    if not args.dry_run and not args.apply:
        print("Specify either --dry-run or --apply.")
        return 2
    if args.dry_run and args.apply:
        print("Pass only one of --dry-run or --apply.")
        return 2

    ids: List[int] = (
        [int(x) for x in args.ids.split(",")] if args.ids else TARGET_IDS_DEFAULT
    )
    LOGGER.info("Target ids: %s", ids)

    writer = JEEExtractionDBWriter()
    repairs: List[Tuple[int, Dict[str, Any], int]] = []

    with writer.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, subject, year, question_content "
            "FROM jee_question_bank WHERE id = ANY(%s) ORDER BY id",
            (ids,),
        )
        rows = cur.fetchall()
        LOGGER.info("Fetched %d rows", len(rows))

        for qid, subj, year, qc in rows:
            # psycopg2 returns jsonb as dict already
            new_qc, n = repair_question_content(qc)
            if n == 0:
                LOGGER.info("id=%s (%s %s) — NOTHING TO REPAIR", qid, subj, year)
                continue
            LOGGER.info("id=%s (%s %s) — %d replacement(s)", qid, subj, year, n)
            # Show small before/after snippet
            before = qc.get("raw_text", "")[:200]
            after = new_qc.get("raw_text", "")[:200]
            if before != after:
                print(f"  BEFORE: {before!r}")
                print(f"  AFTER : {after!r}")
            repairs.append((qid, new_qc, n))

    if not repairs:
        print("\nNothing to repair.")
        return 0

    print(f"\n{len(repairs)} row(s) to update, total {sum(r[2] for r in repairs)} replacements.")

    if args.dry_run:
        print("DRY-RUN — no DB writes.")
        return 0

    if not args.yes:
        confirm = input("Type YES to apply: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return 1

    # Apply
    with writer.connection() as conn, conn.cursor() as cur:
        for qid, new_qc, _ in repairs:
            cur.execute(
                "UPDATE jee_question_bank SET question_content = %s::jsonb WHERE id = %s",
                (json.dumps(new_qc), qid),
            )
        conn.commit()
        LOGGER.info("Committed %d updates.", len(repairs))

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
