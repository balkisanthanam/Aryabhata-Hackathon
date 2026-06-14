"""M3 Tag Verifier — local HTTP server for manual verification of question tags.

Usage:
    python tag_verifier_server.py [port]

Opens http://localhost:8099 (or custom port) with a UI to review
(question, concept) tag pairs and mark them correct/wrong/can-be-better.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import OrderedDict
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── path setup (mirrors question_tagger.py) ──────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from settings_loader import load_local_settings  # noqa: E402

load_local_settings()

from db_writer import JEEExtractionDBWriter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
LOGGER = logging.getLogger("tag_verifier")

HTML_PATH = SCRIPT_DIR / "tag_verifier.html"


# ── SQL queries ───────────────────────────────────────────────────────────────

FILTERS_QUERIES = {
    "years": """
        SELECT DISTINCT q.year FROM jee_question_bank q
        WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
        ORDER BY q.year
    """,
    "dates": """
        SELECT DISTINCT q.dateofexam::text AS dateofexam FROM jee_question_bank q
        WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
        ORDER BY dateofexam
    """,
    "shifts": """
        SELECT DISTINCT q.shift FROM jee_question_bank q
        WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
        ORDER BY q.shift
    """,
    "subjects": """
        SELECT DISTINCT q.subject FROM jee_question_bank q
        WHERE EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)
        ORDER BY q.subject
    """,
}

QUESTIONS_QUERY = """
    SELECT
        q.id              AS question_id,
        q.nta_question_id,
        q.subject,
        q.section,
        q.year,
        q.dateofexam::text AS dateofexam,
        q.shift,
        q.answer_key,
        q.question_content,
        q.difficulty,
        q.pattern_label,
        t.concept_id,
        t.similarity_score,
        nch.concept_title,
        nch.content_type,
        nch.key_formulas,
        nch.description,
        nch.ncert_solved_example,
        cd.chaptertitle   AS chapter_title
    FROM jee_question_bank q
    JOIN jee_question_tags t ON t.question_id = q.id
    JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
    JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
    WHERE {where}
    ORDER BY q.id, t.similarity_score DESC
"""


def _group_rows(rows):
    """Group flat SQL rows into questions with nested concepts."""
    questions = OrderedDict()
    for r in rows:
        qid = r["question_id"]
        if qid not in questions:
            qc = r["question_content"]
            if isinstance(qc, str):
                qc = json.loads(qc)
            questions[qid] = {
                "question_id": qid,
                "nta_question_id": r["nta_question_id"],
                "subject": r["subject"],
                "section": r["section"],
                "year": r["year"],
                "dateofexam": r["dateofexam"],
                "shift": r["shift"],
                "answer_key": r["answer_key"],
                "difficulty": r["difficulty"],
                "pattern_label": r["pattern_label"],
                "question_content": qc,
                "concepts": [],
            }
        questions[qid]["concepts"].append({
            "concept_id": r["concept_id"],
            "concept_title": r["concept_title"],
            "chapter_title": r["chapter_title"],
            "content_type": r["content_type"],
            "similarity_score": float(r["similarity_score"]) if r["similarity_score"] else 0,
            "key_formulas": r["key_formulas"],
            "description": r["description"],
            "ncert_solved_example": r["ncert_solved_example"],
        })
    result = list(questions.values())
    return {"questions": result, "count": len(result)}


# ── HTTP handler ──────────────────────────────────────────────────────────────

class VerifierHandler(BaseHTTPRequestHandler):
    db = JEEExtractionDBWriter()

    def log_message(self, format, *args):
        LOGGER.info(format, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_html()
        elif parsed.path == "/api/filters":
            self._serve_filters()
        elif parsed.path == "/api/questions":
            self._serve_questions(parse_qs(parsed.query))
        else:
            self.send_error(404)

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        content = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content)

    def _serve_filters(self):
        from psycopg2.extras import RealDictCursor

        result = {}
        with self.db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                for key, query in FILTERS_QUERIES.items():
                    cur.execute(query)
                    rows = cur.fetchall()
                    # Each query returns a single column — extract values
                    if rows:
                        col = list(rows[0].keys())[0]
                        result[key] = [r[col] for r in rows]
                    else:
                        result[key] = []
        self._send_json(result)

    def _serve_questions(self, params):
        clauses = []
        values = []

        year = params.get("year", [None])[0]
        date = params.get("date", [None])[0]
        shift = params.get("shift", [None])[0]
        subject = params.get("subject", [None])[0]

        if year:
            clauses.append("q.year = %s")
            values.append(int(year))
        if date:
            clauses.append("q.dateofexam = %s")
            values.append(date)
        if shift:
            clauses.append("q.shift = %s")
            values.append(shift)
        if subject:
            clauses.append("q.subject = %s")
            values.append(subject)

        if not clauses:
            self._send_json({"error": "Provide at least one filter (year, date, shift, subject)"}, 400)
            return

        where = " AND ".join(clauses)
        query = QUESTIONS_QUERY.format(where=where)

        from psycopg2.extras import RealDictCursor

        with self.db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, values)
                rows = [dict(r) for r in cur.fetchall()]

        self._send_json(_group_rows(rows))


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    server = HTTPServer(("127.0.0.1", port), VerifierHandler)
    LOGGER.info("Tag Verifier running at http://localhost:%d", port)
    LOGGER.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down.")
        server.server_close()
