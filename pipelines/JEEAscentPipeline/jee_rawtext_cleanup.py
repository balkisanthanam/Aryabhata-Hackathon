"""Pass 1 — JEE Raw-Text Cleanup.

Detects questions where Gemini's inner monologue leaked into `raw_text` during
M1b extraction, sends the corrupted text to Gemini Flash for clean extraction,
and UPDATEs `question_content` JSONB in `jee_question_bank`.

Usage:
    python jee_rawtext_cleanup.py [--dry-run] [--subject Physics] [--limit 10]
    python jee_rawtext_cleanup.py                        # fix all 47 leakage questions
    python jee_rawtext_cleanup.py --dry-run --limit 5   # preview without writing
    python jee_rawtext_cleanup.py --subject Mathematics  # one subject only

Pass 2 (bare LaTeX delimiters — 68 questions) is a separate script / decision.
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
from typing import Any, Dict, List, Optional

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

from gemini_client import GeminiClient  # type: ignore  # noqa: E402
from config import GeminiModelConfig, PipelineConfig  # type: ignore  # noqa: E402
from db_writer import JEEExtractionDBWriter  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)

# ── leakage detection ─────────────────────────────────────────────────────────
# Patterns that indicate Gemini reasoning leaked into raw_text.
# These phrases appear in Gemini's inner monologue but never in JEE questions.
LEAKAGE_PATTERNS = [
    # Strong signals — never appear in a JEE question stem
    r"\bwait\s*,",
    r"\bjust checking\b",
    r"\bthis matches\b",
    r"\bactually\s*,",
    r"\blet me\b",
    r"\bmatches option\b",
    r"\bI need to\b",
    r"\bI think\b",
    r"\bI'll\b",
    r"\bI am\b",
    r"\bI'm\b",
    r"\bthe answer is\b",
    r"\bthe correct answer is\b",  # avoid matching standard JEE ending "choose the correct answer from..."
    r"\bso the answer\b",
    r"\bthis is option\b",
    r"\bthe question asks\b",
    r"\bhm+\b",
    r"\bokay\b",
    r"\balright\b",
    r"\blet's\b",
]

LEAKAGE_RE = re.compile(
    "|".join(LEAKAGE_PATTERNS),
    re.IGNORECASE,
)


def has_leakage(raw_text: str) -> bool:
    return bool(LEAKAGE_RE.search(raw_text))


# ── Gemini prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a careful data cleaner for a JEE Main question bank.

The input is a `raw_text` field that was extracted from a JEE Main PDF exam paper by an AI model. \
Unfortunately, the AI model's internal reasoning ("Let me think...", "Actually,", "Wait,", \
"I think the answer is...", etc.) has leaked into the extracted text alongside the actual question text.

Your task:
1. Identify and remove ALL reasoning/commentary that does not belong to the original JEE question.
2. Return ONLY the clean question text as it would appear in the original NTA exam paper.
3. Preserve ALL mathematical notation exactly (LaTeX: $...$, \\frac, \\sqrt, etc.).
4. Preserve ALL option labels (A, B, C, D or (A), (B), (C), (D)) and their text.
5. Preserve paragraph/line structure of the question.
6. Do NOT add any explanation or commentary.
7. Return the cleaned text as plain text (not JSON, not markdown).

If the entire text is corrupted beyond recovery (impossible to identify the original question), \
return exactly: UNRECOVERABLE
"""

USER_PROMPT_TEMPLATE = """\
Clean the following corrupted JEE question raw_text. Remove all AI reasoning/commentary.

Question ID: {question_id}
Subject: {subject}
Section: {section}

--- CORRUPTED RAW TEXT START ---
{raw_text}
--- CORRUPTED RAW TEXT END ---

Return only the clean question text.
"""


def clean_raw_text(
    client: GeminiClient,
    model_config: GeminiModelConfig,
    question: Dict[str, Any],
    dry_run: bool = False,
) -> Optional[str]:
    """Send corrupted raw_text to Gemini Flash and return the cleaned version.

    Returns None if the response is UNRECOVERABLE or empty.
    """
    raw_text = (question.get("question_content") or {}).get("raw_text", "")
    if not raw_text:
        return None

    user_prompt = USER_PROMPT_TEMPLATE.format(
        question_id=question["id"],
        subject=question["subject"],
        section=question["section"],
        raw_text=raw_text,
    )

    if dry_run:
        LOGGER.info(
            "[DRY-RUN] Would send Q%d (%d chars) to Gemini for cleanup",
            question["id"],
            len(raw_text),
        )
        return None

    result = client.generate(
        model_config,
        user_prompt,
        system_instruction=SYSTEM_PROMPT,
    )

    cleaned = (result.text if result else "").strip()
    if not cleaned or cleaned.upper() == "UNRECOVERABLE":
        LOGGER.warning("Q%d — Gemini returned UNRECOVERABLE or empty", question["id"])
        return None

    return cleaned


# ── DB helpers ────────────────────────────────────────────────────────────────
def fetch_leaky_questions(
    db: JEEExtractionDBWriter,
    *,
    subject: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch all questions where raw_text matches leakage patterns."""
    from psycopg2.extras import RealDictCursor

    # SQL-level filter using the same patterns as the Python check.
    # This is a broad filter; Python-level has_leakage() is the authoritative check.
    sql_pattern = "|".join([
        "wait,",
        "just checking",
        "this matches",
        "actually,",
        "let me",
        "matches option",
        "I need to",
        "I think",
        "I'll",
        "I am ",
        "I'm",
        "the answer is",
        "the correct answer is",
        "so the answer",
        "this is option",
        "the question asks",
        "okay",
        "alright",
        "let's",
    ])

    clauses = [
        f"(question_content->>'raw_text') ~* %s"
    ]
    params: List[Any] = [sql_pattern]

    if subject:
        clauses.append("subject = %s")
        params.append(subject)

    limit_clause = f"LIMIT {int(limit)}" if limit else ""

    query = f"""
        SELECT id, subject, section, question_content
        FROM jee_question_bank
        WHERE {' AND '.join(clauses)}
        ORDER BY subject, id
        {limit_clause}
    """

    with db.connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]

    # Secondary Python-level filter to avoid false positives from the broad SQL regex
    return [r for r in rows if has_leakage((r.get("question_content") or {}).get("raw_text", ""))]


def update_raw_text(
    db: JEEExtractionDBWriter,
    question_id: int,
    cleaned_text: str,
) -> None:
    """UPDATE question_content JSONB to replace raw_text with the cleaned version."""
    query = """
        UPDATE jee_question_bank
        SET question_content = jsonb_set(
            question_content,
            '{raw_text}',
            %s::jsonb
        )
        WHERE id = %s
    """
    # jsonb_set expects a JSONB value — JSON-encode the string so it's a valid JSON string
    json_value = json.dumps(cleaned_text)

    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (json_value, question_id))


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pass 1 cleanup: remove LLM reasoning leakage from JEE raw_text fields."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect leakage and preview but skip all DB writes and Gemini calls.",
    )
    parser.add_argument(
        "--subject",
        choices=["Physics", "Chemistry", "Mathematics"],
        help="Process only questions for this subject.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Max questions to process (useful for testing).",
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Print the first 300 chars of each detected raw_text (for inspection).",
    )
    args = parser.parse_args()

    db = JEEExtractionDBWriter()

    # Set up Gemini client (Flash — cheap for single-question prompts)
    model_config = GeminiModelConfig(
        model_id=os.environ.get("CLEANUP_MODEL", "gemini-3-flash-preview"),
        temperature=0.1,
        max_output_tokens=4096,
    )
    pipeline_config = PipelineConfig()
    client = GeminiClient(pipeline_config)

    LOGGER.info("Fetching questions with LLM leakage patterns…")
    questions = fetch_leaky_questions(db, subject=args.subject, limit=args.limit)
    LOGGER.info("Found %d questions with leakage", len(questions))

    if not questions:
        LOGGER.info("Nothing to clean up.")
        return

    if args.dry_run:
        LOGGER.info("=== DRY-RUN MODE — no DB writes or Gemini calls ===")

    fixed = 0
    skipped = 0
    unrecoverable = 0

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        raw_text = (q.get("question_content") or {}).get("raw_text", "")

        LOGGER.info(
            "[%d/%d] Q%d (%s %s) — %d chars",
            i, len(questions), qid, q["subject"], q["section"], len(raw_text),
        )

        if args.show_text:
            LOGGER.info("  RAW: %s", raw_text[:300].replace("\n", " "))

        # Token refresh every 20 questions to prevent expiry
        if i % 20 == 1 and not args.dry_run:
            db.refresh_token()

        cleaned = clean_raw_text(client, model_config, q, dry_run=args.dry_run)

        if args.dry_run:
            skipped += 1
            continue

        if cleaned is None:
            unrecoverable += 1
            LOGGER.warning("  → SKIPPED (unrecoverable or empty response)")
            continue

        # Sanity: cleaned text should be shorter than input (we removed stuff)
        # and should not itself contain leakage patterns
        if has_leakage(cleaned):
            LOGGER.warning(
                "  → Q%d: cleaned text still has leakage patterns — skipping", qid
            )
            unrecoverable += 1
            continue

        if len(cleaned) > len(raw_text) * 1.1:
            LOGGER.warning(
                "  → Q%d: cleaned text is longer than original (%d > %d) — skipping",
                qid, len(cleaned), len(raw_text),
            )
            unrecoverable += 1
            continue

        update_raw_text(db, qid, cleaned)
        fixed += 1
        LOGGER.info(
            "  → FIXED (original %d chars → %d chars)",
            len(raw_text), len(cleaned),
        )

        # Brief pause to avoid Gemini rate-limiting
        time.sleep(0.5)

    LOGGER.info(
        "\n=== DONE ===\n  Fixed: %d\n  Skipped (dry-run): %d\n  Unrecoverable: %d\n  Total: %d",
        fixed, skipped, unrecoverable, len(questions),
    )


if __name__ == "__main__":
    main()
