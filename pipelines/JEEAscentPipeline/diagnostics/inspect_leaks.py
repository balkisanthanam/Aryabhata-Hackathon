"""Inspect a sample of leaked rows in full to understand parse-ability."""
from __future__ import annotations
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def try_parse(text: str):
    """Try to json.loads; strip \\begin{json} fence if present."""
    t = text.strip()
    if t.startswith("\\begin{json}"):
        t = t[len("\\begin{json}"):].strip()
    if t.endswith("\\end{json}"):
        t = t[:-len("\\end{json}")].strip()
    try:
        return "OK", json.loads(t)
    except json.JSONDecodeError as e:
        return f"ERR {e.msg} col={e.colno}", None


def main():
    db = JEEExtractionDBWriter()
    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, year, subject,
                       question_content->>'raw_text' AS raw
                FROM jee_question_bank
                WHERE LTRIM(question_content->>'raw_text') LIKE '{%"raw_text"%'
                   OR LTRIM(question_content->>'raw_text') LIKE '\\begin{json}%'
                ORDER BY random()
                LIMIT 5
            """)
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                print("=" * 80)
                print(f"id={r['id']}  year={r['year']}  subject={r['subject']}")
                print(f"raw_text length: {len(r['raw'])}")
                print("-- first 400 chars --")
                print(r["raw"][:400])
                print("-- last 200 chars --")
                print(r["raw"][-200:])
                status, parsed = try_parse(r["raw"])
                print(f"\nparse: {status}")
                if parsed:
                    print(f"  keys: {list(parsed.keys())}")
                    rt = parsed.get("raw_text", "")
                    opts = parsed.get("options", [])
                    print(f"  clean raw_text len: {len(rt)}")
                    print(f"  clean raw_text[:180]: {rt[:180]}")
                    print(f"  options count: {len(opts) if isinstance(opts, list) else '?'}")
                print()


if __name__ == "__main__":
    main()
