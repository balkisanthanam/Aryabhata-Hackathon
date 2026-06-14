"""Batch 1 — JSON-leak repair + subject re-classification.

Target: rows in `jee_question_bank` whose `raw_text` starts with `{ "raw_text":`
or `\\begin{json}`. The Gemini Flash response was stored verbatim because
`json.loads()` failed in `jee_crop_pipeline.py`'s fallback path.

Per-row pipeline:
  1. Strip `\\begin{json}` / `\\end{json}` fences.
  2. Fix illegal JSON escapes (LaTeX single-backslashes like `\\sqrt`, `\\alpha`)
     by doubling any `\\` not followed by a valid JSON escape char.
  3. `json.loads()` → recover `raw_text`, `options`, `has_figure`, `figure_description`.
  4. If parse still fails, regex-extract `raw_text` and `options` directly.
  5. Batch LLM-classify the cleaned `raw_text` to predict the subject.
  6. If predicted subject != stored subject:
       UPDATE jee_question_bank.subject
       DELETE jee_question_tags WHERE question_id = id  (embeddings cascade via FK)
       DELETE jee_question_embeddings WHERE question_id = id
       Clear difficulty / difficulty_confidence / pattern_label
     Always: UPDATE question_content with the cleaned JSON.

Usage:
    python jee_jsonleak_repair.py --dry-run                   # report for all years
    python jee_jsonleak_repair.py --dry-run --year 2024 --limit 10
    python jee_jsonleak_repair.py --apply --year 2024 --yes
    python jee_jsonleak_repair.py --apply --year 2023 --yes

--dry-run: prints a per-row plan and the subject diff; no DB writes.
--apply:   writes updates + subject fixes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── path setup (mirrors subject_auditor.py) ──────────────────────────────────
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
LOGGER = logging.getLogger("jsonleak_repair")

VALID_SUBJECTS = {"Physics", "Chemistry", "Mathematics"}


# ── parsing helpers ──────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("\\begin{json}"):
        t = t[len("\\begin{json}"):].lstrip()
    if t.endswith("\\end{json}"):
        t = t[:-len("\\end{json}")].rstrip()
    # also accept ```json ... ``` fences just in case
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl >= 0:
            t = t[first_nl + 1 :]
    if t.endswith("```"):
        t = t[:-3].rstrip()
    return t


def _tolerant_unescape(s: str) -> str:
    """Un-escape only `\\\\` → `\\` and `\\"` → `"`. Preserve any other `\\X` (LaTeX).

    We cannot use `json.loads` because the source treats `\\t`, `\\n`, etc. as LaTeX
    commands (e.g. `\\to`, `\\nu`, `\\frac`) — JSON would turn them into tab/newline
    and destroy the math notation.
    """
    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
            if nxt == '"':
                out.append('"')
                i += 2
                continue
            # preserve LaTeX escape (`\sqrt`, `\frac`, etc.)
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_RAW_TEXT_RE = re.compile(r'"raw_text"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
_OPTIONS_RE = re.compile(r'"options"\s*:\s*\[([^\]]*)\]', re.DOTALL)
_STRING_ITEM_RE = re.compile(r'"((?:[^"\\]|\\.)*)"', re.DOTALL)
_HAS_FIGURE_RE = re.compile(r'"has_figure"\s*:\s*(true|false)')
_FIGURE_DESC_RE = re.compile(
    r'"figure_description"\s*:\s*(?:null|"((?:[^"\\]|\\.)*)")', re.DOTALL,
)


def parse_leak(raw: str) -> Optional[Dict[str, Any]]:
    """Return {raw_text, options, has_figure, figure_description} or None.

    We never call `json.loads` on the corrupted body — a valid-looking `\\t` or
    `\\n` inside raw_text would be interpreted as a JSON escape (tab/newline)
    and silently corrupt LaTeX commands like `\\to`, `\\nu`, `\\frac`.
    """
    body = _strip_fences(raw)

    rt_match = _RAW_TEXT_RE.search(body)
    if not rt_match:
        return None
    raw_text = _tolerant_unescape(rt_match.group(1))

    options: List[Dict[str, Any]] = []
    opt_match = _OPTIONS_RE.search(body)
    if opt_match:
        for m in _STRING_ITEM_RE.finditer(opt_match.group(1)):
            options.append({"nta_option_id": None,
                            "text": _tolerant_unescape(m.group(1))})

    has_figure = False
    hf = _HAS_FIGURE_RE.search(body)
    if hf:
        has_figure = hf.group(1) == "true"

    figure_description = None
    fd = _FIGURE_DESC_RE.search(body)
    if fd and fd.group(1) is not None:
        figure_description = _tolerant_unescape(fd.group(1))

    return {
        "raw_text": raw_text,
        "options": options,
        "has_figure": has_figure,
        "figure_description": figure_description,
    }


# ── data loading ─────────────────────────────────────────────────────────────

def fetch_leak_rows(db: JEEExtractionDBWriter, year: Optional[int],
                    limit: Optional[int]) -> List[Dict[str, Any]]:
    clauses = ["(LTRIM(question_content->>'raw_text') LIKE '{%%\"raw_text\"%%'"
               " OR LTRIM(question_content->>'raw_text') LIKE '\\begin{json}%%')"]
    params: List[Any] = []
    if year is not None:
        clauses.append("year = %s")
        params.append(year)

    query = f"""
        SELECT id, year, dateofexam::text AS dateofexam, shift, subject,
               nta_question_id, section, answer_key,
               question_content
        FROM jee_question_bank
        WHERE {' AND '.join(clauses)}
        ORDER BY year, dateofexam, shift, id
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


# ── LLM subject classification ───────────────────────────────────────────────

_CLASSIFY_PROMPT = """You are a JEE Main subject classifier.

For each question below, decide whether it is Physics, Chemistry, or Mathematics.
Return ONLY a JSON object mapping each key (q1, q2, ...) to one of:
  "Physics", "Chemistry", "Mathematics"

Questions:
{block}
"""


def classify_subjects(client: GeminiClient, model: GeminiModelConfig,
                      rows: List[Dict[str, Any]],
                      batch_size: int = 15) -> Dict[int, str]:
    """Return {row_id: predicted_subject}."""
    result: Dict[int, str] = {}
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        block = ""
        id_by_key: Dict[str, int] = {}
        for i, r in enumerate(batch, 1):
            key = f"q{i}"
            id_by_key[key] = r["id"]
            text = (r["_clean_raw_text"] or "").strip()[:500]
            block += f"{key}: {text}\n\n"

        prompt = _CLASSIFY_PROMPT.format(block=block)
        resp = client.generate(model_config=model, prompt=prompt)
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.warning("LLM classify: bad JSON in response: %s", raw[:300])
            continue
        for key, qid in id_by_key.items():
            pred = (parsed.get(key) or "").strip()
            if pred in VALID_SUBJECTS:
                result[qid] = pred
            else:
                LOGGER.warning("Row id=%d: unexpected prediction %r", qid, pred)
        time.sleep(0.5)
    return result


# ── apply ────────────────────────────────────────────────────────────────────

def apply_row_update(db: JEEExtractionDBWriter, row_id: int,
                     new_content: Dict[str, Any],
                     new_subject: Optional[str],
                     old_subject: str) -> Dict[str, int]:
    """UPDATE the row. If subject changes, cascade-clear tags/embeddings/metadata."""
    stats = {"tags_deleted": 0, "embeddings_deleted": 0}
    with db.connection() as conn:
        with conn.cursor() as cur:
            if new_subject and new_subject != old_subject:
                cur.execute(
                    "UPDATE jee_question_bank SET question_content = %s, subject = %s,"
                    "       difficulty = NULL, difficulty_confidence = NULL,"
                    "       pattern_label = NULL"
                    " WHERE id = %s",
                    (json.dumps(new_content), new_subject, row_id),
                )
                cur.execute(
                    "DELETE FROM jee_question_tags WHERE question_id = %s",
                    (row_id,),
                )
                stats["tags_deleted"] = cur.rowcount
                cur.execute(
                    "DELETE FROM jee_question_embeddings WHERE question_id = %s",
                    (row_id,),
                )
                stats["embeddings_deleted"] = cur.rowcount
            else:
                cur.execute(
                    "UPDATE jee_question_bank SET question_content = %s WHERE id = %s",
                    (json.dumps(new_content), row_id),
                )
    return stats


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None, help="Filter to a specific year")
    parser.add_argument("--limit", type=int, default=None, help="Cap rows processed")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    parser.add_argument("--apply", action="store_true", help="Actually apply writes")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation on --apply")
    parser.add_argument("--batch-size", type=int, default=15, help="LLM batch size for subject classification")
    parser.add_argument("--skip-classify", action="store_true",
                        help="Skip subject classification (only repair raw_text)")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("specify either --dry-run or --apply")

    db = JEEExtractionDBWriter()
    LOGGER.info("Fetching leaked rows (year=%s, limit=%s)...", args.year, args.limit)
    rows = fetch_leak_rows(db, year=args.year, limit=args.limit)
    LOGGER.info("Fetched %d rows to inspect.", len(rows))

    # Step 1 — repair raw_text
    repaired: List[Dict[str, Any]] = []
    parse_fail = 0
    for r in rows:
        raw = (r["question_content"] or {}).get("raw_text", "")
        cleaned = parse_leak(raw)
        if cleaned is None:
            parse_fail += 1
            LOGGER.warning("id=%d: parse failed, skipping", r["id"])
            continue
        r["_clean_content"] = cleaned
        r["_clean_raw_text"] = cleaned["raw_text"]
        repaired.append(r)

    LOGGER.info("Repaired raw_text for %d rows (%d parse failures).",
                len(repaired), parse_fail)
    if not repaired:
        return

    # Step 2 — LLM-classify subjects
    predictions: Dict[int, str] = {}
    if not args.skip_classify:
        pipeline_config = PipelineConfig()
        client = GeminiClient(pipeline_config)
        model = GeminiModelConfig(
            model_id=os.environ.get("JSONLEAK_MODEL", "gemini-3.1-flash-lite-preview"),
            temperature=0.0,
            max_output_tokens=1024,
            response_mime_type="application/json",
        )
        LOGGER.info("Classifying subjects for %d rows (batch=%d)...",
                    len(repaired), args.batch_size)
        predictions = classify_subjects(client, model, repaired, batch_size=args.batch_size)
        LOGGER.info("Got predictions for %d rows.", len(predictions))

    # Step 3 — report
    by_diff = {"same": 0, "changed": 0, "no_prediction": 0}
    sample_changes: List[str] = []
    for r in repaired:
        pred = predictions.get(r["id"])
        if pred is None:
            by_diff["no_prediction"] += 1
        elif pred == r["subject"]:
            by_diff["same"] += 1
        else:
            by_diff["changed"] += 1
            if len(sample_changes) < 15:
                sample_changes.append(
                    f"  id={r['id']:>5}  {r['dateofexam']} s{r['shift']}  "
                    f"{r['subject']:<12} -> {pred:<12}  "
                    f"'{r['_clean_raw_text'][:70]}'"
                )

    print()
    print("=" * 80)
    print("JSON-LEAK REPAIR PLAN")
    print("=" * 80)
    print(f"  rows with leaked raw_text:         {len(rows)}")
    print(f"  successfully parsed:               {len(repaired)}")
    print(f"  parse failures (will be skipped):  {parse_fail}")
    if not args.skip_classify:
        print(f"  subject unchanged:                 {by_diff['same']}")
        print(f"  subject to be changed:             {by_diff['changed']}")
        print(f"  no prediction from LLM:            {by_diff['no_prediction']}")
    print()
    if sample_changes:
        print("Sample subject changes (first 15):")
        for line in sample_changes:
            print(line)

    if args.dry_run:
        print("\n(dry-run — no changes applied)")
        return

    # Step 4 — apply
    if not args.yes:
        print(f"\nAbout to repair {len(repaired)} rows "
              f"({by_diff.get('changed', 0)} with subject changes). Press Enter or Ctrl+C.")
        input()

    total_stats = {"rows_updated": 0, "tags_deleted": 0, "embeddings_deleted": 0,
                   "subject_changed": 0}
    for r in repaired:
        pred = predictions.get(r["id"])
        s = apply_row_update(db, r["id"], r["_clean_content"], pred, r["subject"])
        total_stats["rows_updated"] += 1
        total_stats["tags_deleted"] += s["tags_deleted"]
        total_stats["embeddings_deleted"] += s["embeddings_deleted"]
        if pred and pred != r["subject"]:
            total_stats["subject_changed"] += 1

    print()
    print("=" * 80)
    print("JSON-LEAK REPAIR APPLIED")
    print("=" * 80)
    for k, v in total_stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
