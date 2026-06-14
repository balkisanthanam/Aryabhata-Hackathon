"""M3 — JEE Question Tagger.

Tags each row in jee_question_bank with NCERT concept IDs, generates a 768-dim
embedding per question, and writes difficulty / pattern_label metadata.

Usage:
    python question_tagger.py [--subject Physics|Chemistry|Mathematics]
                              [--batch-size 10] [--dry-run]
                              [--year 2024] [--limit 50]
                              [--skip-embeddings]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── path setup ───────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
MULTI_STEP_DIR = (
    SCRIPT_DIR.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
)
CONCEPT_INDEX_DIR = SCRIPT_DIR.parent / "ConceptIndex"

# Add shared lib directories (lower priority — SCRIPT_DIR must stay at front)
for p in [str(MULTI_STEP_DIR), str(CONCEPT_INDEX_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Force SCRIPT_DIR to position 0 so local db_writer.py takes priority over ConceptIndex's
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
from gemini_extractor import ConceptGeminiExtractor  # type: ignore  # noqa: E402
from db_writer import JEEExtractionDBWriter  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
LOGGER = logging.getLogger("question_tagger")

# ── constants ─────────────────────────────────────────────────────────────────
PROMPTS_DIR = SCRIPT_DIR / "prompts"

# jee_question_bank.subject → ncert_concept_hierarchy.subject
SUBJECT_MAP = {
    "Physics": "Physics",
    "Chemistry": "Chemistry",
    "Mathematics": "Maths",
}

VALID_DIFFICULTIES = {"EASY", "MEDIUM", "HARD"}

_LATEX_BACKSLASH_RE = re.compile(r"\\([A-Za-z])")


def _repair_latex_json(raw: str) -> str:
    """Double-escape bare LaTeX backslashes Gemini emits without proper JSON escaping.

    Identical strategy to M2's gemini_extractor._repair_json_escapes():
      1. Protect already-correct \\\\ with a placeholder.
      2. Double every remaining \\letter.
      3. Restore the placeholder.
    """
    placeholder = "\x00DBLSLASH\x00"
    s = raw.replace("\\\\", placeholder)
    s = _LATEX_BACKSLASH_RE.sub(lambda m: f"\\\\{m.group(1)}", s)
    return s.replace(placeholder, "\\\\")

# Process subjects in this order (smallest vocabulary first for easier debugging)
SUBJECT_ORDER = ["Physics", "Chemistry", "Mathematics"]

# Simple LaTeX stripping for hybrid retrieval embeddings
_LATEX_STRIP_RE = re.compile(r"\\(?:frac|text|mathrm|mathbf|textbf|sqrt)\{([^}]*)\}")
_LATEX_DELIM_RE = re.compile(r"\$\$?|\\[(\[\])]")


# ─────────────────────────────────────────────────────────────────────────────
class QuestionTaggerPipeline:
    """Main M3 pipeline: load vocabulary → batch LLM tag → embed → write DB."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        extractor: ConceptGeminiExtractor,
        db: JEEExtractionDBWriter,
        pipeline_config: PipelineConfig,
    ) -> None:
        self.client = gemini_client
        self.extractor = extractor
        self.db = db
        self.pipeline_config = pipeline_config

        self._system_prompt = (PROMPTS_DIR / "question_tagger_system.txt").read_text(
            encoding="utf-8"
        )
        self._user_template = (PROMPTS_DIR / "question_tagger_user.txt").read_text(
            encoding="utf-8"
        )

        self._tagger_model = GeminiModelConfig(
            model_id=os.environ.get("M3_TAGGER_MODEL", "gemini-3-flash-preview"),
            temperature=0.1,
            max_output_tokens=8192,
            response_mime_type="application/json",
        )

    # ── public ────────────────────────────────────────────────────────────────

    def run(
        self,
        subjects: List[str],
        *,
        mode: str = "hybrid",
        batch_size: int = 5,
        top_k: int = 25,
        dry_run: bool = False,
        year: Optional[int] = None,
        dateofexam: Optional[str] = None,
        shift: Optional[str] = None,
        limit: Optional[int] = None,
        skip_embeddings: bool = False,
        workers: int = 4,
    ) -> Dict[str, Any]:
        """Run M3 tagging for the given subjects. Returns summary stats."""
        total_tagged = 0
        total_embedded = 0
        total_failed_batches = 0
        total_questions = 0

        self.db.open_connection_pool(minconn=2, maxconn=workers + 2)
        try:
            for jee_subject in subjects:
                ncert_subject = SUBJECT_MAP[jee_subject]

                vocab_rows: Optional[List[Dict[str, Any]]] = None
                vocab_block: Optional[str] = None
                valid_ids: Optional[Set[int]] = None

                if mode == "full":
                    LOGGER.info("Loading full vocabulary for %s (ncert subject: %s)…", jee_subject, ncert_subject)
                    vocab_rows, valid_ids = self._load_vocabulary(ncert_subject)
                    LOGGER.info("  %d concept nodes loaded.", len(vocab_rows))
                    vocab_block = self._format_vocabulary_block(vocab_rows)

                # Refresh token once per subject before concurrent work begins
                self.db.refresh_token()

                LOGGER.info("Fetching untagged questions for %s…", jee_subject)
                questions = self.db.fetch_untagged_questions(
                    subject=jee_subject,
                    year=year,
                    dateofexam=dateofexam,
                    shift=shift,
                    limit=limit,
                )
                LOGGER.info("  %d untagged questions found.", len(questions))

                if not questions:
                    LOGGER.info("  Nothing to do for %s.", jee_subject)
                    continue

                total_questions += len(questions)

                batches = [
                    questions[i : i + batch_size]
                    for i in range(0, len(questions), batch_size)
                ]
                total_batches = len(batches)
                LOGGER.info(
                    "Processing %d batches for %s with %d worker(s)…",
                    total_batches, jee_subject, workers,
                )

                dry_run_sample_printed = False
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_num = {
                        executor.submit(
                            self._process_single_batch,
                            batch, ncert_subject, jee_subject,
                            top_k, mode, vocab_block, valid_ids, skip_embeddings,
                        ): (i + 1, batch)
                        for i, batch in enumerate(batches)
                    }

                    for future in as_completed(future_to_num):
                        batch_num, batch = future_to_num[future]
                        try:
                            result = future.result()
                        except Exception as exc:
                            LOGGER.error("  Batch %d/%d failed: %s — skipping.", batch_num, total_batches, exc)
                            total_failed_batches += 1
                            continue

                        tagged = result["tagged"]
                        embeddings = result["embeddings"]

                        LOGGER.info(
                            "[%s %s] Batch %d/%d — %d tagged, %d embedded.",
                            jee_subject, mode, batch_num, total_batches, len(tagged), len(embeddings),
                        )

                        if dry_run:
                            LOGGER.info("  [DRY-RUN] Would write %d tags, %d embeddings.", len(tagged), len(embeddings))
                            if not dry_run_sample_printed and tagged:
                                sample_vocab = result.get("sample_vocab") or vocab_rows or []
                                self._print_dry_run_sample(tagged, sample_vocab)
                                dry_run_sample_printed = True
                            continue

                        if not tagged:
                            continue

                        # Write tags
                        tag_rows = [
                            {"question_id": t["question_id"], "concept_id": c["concept_id"], "similarity_score": c["relevance_score"]}
                            for t in tagged
                            for c in t["tagged_concepts"]
                        ]
                        written = self.db.bulk_upsert_question_tags(tag_rows)
                        total_tagged += written
                        LOGGER.info("  Wrote %d tag rows.", written)

                        # Write embeddings
                        if embeddings:
                            emb_written = self.db.bulk_upsert_question_embeddings(embeddings)
                            total_embedded += emb_written
                            LOGGER.info("  Wrote %d embedding rows.", emb_written)

                        # Write metadata
                        meta_rows = [
                            {
                                "question_id": t["question_id"],
                                "difficulty": t["difficulty"],
                                "difficulty_confidence": t["difficulty_confidence"],
                                "pattern_label": t["pattern_label"],
                            }
                            for t in tagged
                        ]
                        self.db.bulk_update_question_metadata(meta_rows)

        finally:
            self.db.close_connection_pool()

        summary = {
            "mode": mode,
            "questions_processed": total_questions,
            "tag_rows_written": total_tagged,
            "embedding_rows_written": total_embedded,
            "failed_batches": total_failed_batches,
            "dry_run": dry_run,
        }
        LOGGER.info("M3 complete: %s", summary)
        return summary

    def compare(
        self,
        subjects: List[str],
        *,
        top_k: int = 25,
        batch_size: int = 15,
        year: Optional[int] = None,
        dateofexam: Optional[str] = None,
        shift: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        """Compare hybrid tagging against existing full-mode tags."""
        for jee_subject in subjects:
            ncert_subject = SUBJECT_MAP[jee_subject]

            LOGGER.info("Fetching already-tagged questions for %s…", jee_subject)
            questions = self.db.fetch_tagged_questions(
                subject=jee_subject,
                year=year,
                dateofexam=dateofexam,
                shift=shift,
                limit=limit,
            )
            if not questions:
                LOGGER.info("  No tagged questions found for %s.", jee_subject)
                continue

            LOGGER.info("  %d tagged questions found.", len(questions))

            # Fetch existing tags
            qids = [q["id"] for q in questions]
            existing_tags = self.db.fetch_existing_tags(qids)

            # Track retrieval hit rate and tagging comparison
            total_existing_concepts = 0
            retrieval_hits = 0
            tag_matches = 0
            tag_total = 0
            difficulty_matches = 0
            questions_perfect_recall = 0
            questions_with_extras = 0

            for batch_start in range(0, len(questions), batch_size):
                batch = questions[batch_start : batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                total_batches = (len(questions) + batch_size - 1) // batch_size
                # Refresh Azure token every 20 batches to avoid mid-run expiry
                if batch_num == 1 or batch_num % 20 == 0:
                    self.db.refresh_token()

                LOGGER.info(
                    "[%s compare] Batch %d/%d (%d questions)…",
                    jee_subject, batch_num, total_batches, len(batch),
                )

                # Hybrid retrieval
                batch_vocab, batch_valid_ids = self._retrieve_candidates_hybrid(
                    batch, ncert_subject, top_k,
                )

                # Check retrieval hit rate — are existing concepts in the candidates?
                for q in batch:
                    q_existing = existing_tags.get(q["id"], [])
                    existing_cids = {t["concept_id"] for t in q_existing}
                    total_existing_concepts += len(existing_cids)
                    hits = len(existing_cids & batch_valid_ids)
                    retrieval_hits += hits

                # Tag with hybrid
                try:
                    batch_vocab_block = self._format_vocabulary_block(batch_vocab)
                    hybrid_tagged = self._tag_batch(batch, batch_vocab_block, batch_valid_ids, jee_subject)
                except Exception as exc:
                    LOGGER.error("  Batch %d tagging failed: %s", batch_num, exc)
                    continue

                # Compare per question
                for t in hybrid_tagged:
                    qid = t["question_id"]
                    q_existing = existing_tags.get(qid, [])
                    existing_cids = {et["concept_id"] for et in q_existing}
                    hybrid_cids = {c["concept_id"] for c in t["tagged_concepts"]}

                    matched = existing_cids & hybrid_cids
                    extra = hybrid_cids - existing_cids
                    tag_matches += len(matched)
                    tag_total += len(existing_cids)

                    if matched == existing_cids:
                        questions_perfect_recall += 1
                    if extra:
                        questions_with_extras += 1

                    # Difficulty check
                    # Fetch existing difficulty from the question's DB row
                    q_row = next((q for q in batch if q["id"] == qid), None)
                    if q_row:
                        existing_diff = None
                        # Difficulty is in jee_question_bank — need to fetch it
                        # For simplicity, compare hybrid difficulty only
                        pass

                    # Print per-question detail
                    existing_labels = [
                        f"[{et['concept_id']}] {et['concept_title']} ({et['similarity_score']:.2f})"
                        for et in q_existing
                    ]
                    hybrid_labels = [
                        f"[{c['concept_id']}] (score={c['relevance_score']:.2f})"
                        for c in t["tagged_concepts"]
                    ]
                    recall_pct = (len(matched) / len(existing_cids) * 100) if existing_cids else 100
                    print(f"\n  Q{qid}:")
                    print(f"    Full-mode:  {', '.join(existing_labels)}")
                    print(f"    Hybrid:     {', '.join(hybrid_labels)}")
                    print(f"    Recall: {len(matched)}/{len(existing_cids)} ({recall_pct:.0f}%)  Extra: {len(extra)}")

                time.sleep(0.5)

            # Summary
            n_questions = len(questions)
            print(f"\n{'=' * 60}")
            print(f"COMPARE SUMMARY — {jee_subject}")
            print(f"{'=' * 60}")
            print(f"  Questions compared:      {n_questions}")
            print(f"  Retrieval hit rate:       {retrieval_hits}/{total_existing_concepts}"
                  f" ({retrieval_hits / total_existing_concepts * 100:.1f}%)" if total_existing_concepts else "")
            print(f"  Tag recall:              {tag_matches}/{tag_total}"
                  f" ({tag_matches / tag_total * 100:.1f}%)" if tag_total else "")
            print(f"  Perfect recall (100%):   {questions_perfect_recall}/{n_questions}")
            print(f"  Questions with extras:   {questions_with_extras}/{n_questions}")
            print(f"{'=' * 60}")

    # ── private ───────────────────────────────────────────────────────────────

    def _process_single_batch(
        self,
        batch: List[Dict[str, Any]],
        ncert_subject: str,
        jee_subject: str,
        top_k: int,
        mode: str,
        vocab_block: Optional[str],
        valid_ids: Optional[Set[int]],
        skip_embeddings: bool,
    ) -> Dict[str, Any]:
        """Retrieve candidates, tag, and embed one batch. Thread-safe. No DB writes.

        Returns dict with keys: tagged, embeddings, sample_vocab.
        """
        sample_vocab: Optional[List[Dict[str, Any]]] = None

        if mode == "hybrid":
            batch_vocab, batch_valid_ids = self._retrieve_candidates_hybrid(
                batch, ncert_subject, top_k,
            )
            batch_vocab_block = self._format_vocabulary_block(batch_vocab)
            tagged = self._tag_batch(batch, batch_vocab_block, batch_valid_ids, jee_subject)
            sample_vocab = batch_vocab
        else:
            tagged = self._tag_batch(batch, vocab_block, valid_ids, jee_subject)

        embeddings: List[Dict[str, Any]] = []
        if not skip_embeddings and tagged:
            embed_texts = [t["embed_text"] for t in tagged]
            try:
                vectors = self.extractor.embed_texts_batch(embed_texts)
                for t, vec in zip(tagged, vectors):
                    embeddings.append({
                        "question_id": t["question_id"],
                        "embedding": vec,
                        "embed_text": t["embed_text"],
                    })
            except Exception as exc:
                LOGGER.warning("Embedding failed: %s — continuing without vectors.", exc)

        time.sleep(1)  # Gemini rate limit breather
        return {"tagged": tagged, "embeddings": embeddings, "sample_vocab": sample_vocab}

    # ── hybrid retrieval ───────────────────────────────────────────────────

    @staticmethod
    def _strip_latex_for_embed(text: str) -> str:
        """Strip LaTeX markup from question text for retrieval embedding."""
        if not text:
            return ""
        # Replace \frac{a}{b} → a/b, \text{X} → X, etc.
        s = _LATEX_STRIP_RE.sub(r"\1", text)
        # Remove remaining LaTeX commands like \alpha, \times
        s = re.sub(r"\\[A-Za-z]+", " ", s)
        # Remove $ delimiters
        s = _LATEX_DELIM_RE.sub("", s)
        # Collapse whitespace
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _retrieve_candidates_hybrid(
        self,
        batch: List[Dict[str, Any]],
        ncert_subject: str,
        top_k: int,
    ) -> Tuple[List[Dict[str, Any]], Set[int]]:
        """Embed questions, query pgvector for top-K candidates, return union."""
        # Build plain text for embedding
        embed_texts = []
        for q in batch:
            content = q.get("question_content") or {}
            raw = content.get("raw_text", "")
            # Include options for MCQ context
            opts = content.get("options") or []
            opt_text = " ".join(o.get("text", "") for o in opts)
            combined = f"{raw} {opt_text}".strip()
            cleaned = self._strip_latex_for_embed(combined)
            # Fallback for figure-only questions with no/empty text
            embed_texts.append(cleaned if cleaned.strip() else f"{q.get('subject', 'Physics')} question {q.get('id', '')}")

        # Embed all questions in batch
        vectors = self.extractor.embed_texts_batch(embed_texts)

        # Query pgvector for each question, union the results
        seen: Dict[int, Dict[str, Any]] = {}  # concept_id → row (keep best score)
        for vec in vectors:
            candidates = self.db.fetch_concept_candidates_vector(
                vec, ncert_subject, top_k,
            )
            for c in candidates:
                cid = c["concept_id"]
                if cid not in seen or c["vector_score"] > seen[cid].get("vector_score", 0):
                    seen[cid] = c

        vocab_rows = list(seen.values())
        valid_ids = set(seen.keys())
        LOGGER.info("  Hybrid retrieval: %d unique candidates from %d questions × top-%d",
                     len(vocab_rows), len(batch), top_k)
        return vocab_rows, valid_ids

    # ── vocabulary ───────────────────────────────────────────────────────────

    def _load_vocabulary(self, ncert_subject: str) -> Tuple[List[Dict[str, Any]], Set[int]]:
        rows = self.db.load_concept_vocabulary(ncert_subject)
        valid_ids: Set[int] = {r["concept_id"] for r in rows}
        return rows, valid_ids

    def _format_vocabulary_block(self, vocab_rows: List[Dict[str, Any]]) -> str:
        lines = []
        for r in vocab_rows:
            formula_part = f" | formula: {r['key_formulas']}" if r.get("key_formulas") else ""
            lines.append(
                f"[{r['concept_id']}] {r['concept_title']} | {r['content_type']} | chapter: {r['chapter_title']}{formula_part}"
            )
        return "\n".join(lines)

    def _format_questions_block(self, questions: List[Dict[str, Any]]) -> str:
        lines = []
        for i, q in enumerate(questions, 1):
            content = q.get("question_content") or {}
            raw_text = content.get("raw_text", "").strip()
            section = q.get("section", "MCQ")
            qid = q["id"]
            # Include figure description if present
            fig_desc = content.get("figure_description")
            fig_note = f" [Figure: {fig_desc}]" if fig_desc else ""
            lines.append(f"Q{i} (id={qid}, section={section}): {raw_text}{fig_note}")
        return "\n\n".join(lines)

    def _tag_batch(
        self,
        batch: List[Dict[str, Any]],
        vocab_block: str,
        valid_ids: Set[int],
        subject: str,
    ) -> List[Dict[str, Any]]:
        """Call the tagger LLM for one batch; parse, validate, and return results."""
        vocab_rows_count = vocab_block.count("\n") + 1
        questions_block = self._format_questions_block(batch)
        expected_question_ids = {q["id"] for q in batch}

        user_prompt = self._user_template.format(
            subject=subject,
            n_concepts=vocab_rows_count,
            vocabulary_block=vocab_block,
            n_questions=len(batch),
            questions_block=questions_block,
        )

        result = self.client.generate(
            model_config=self._tagger_model,
            prompt=user_prompt,
            system_instruction=self._system_prompt,
        )
        raw_response = result.text.strip()

        return self._parse_and_validate(raw_response, valid_ids, expected_question_ids)

    def _parse_and_validate(
        self,
        raw_response: str,
        valid_ids: Set[int],
        expected_question_ids: Set[int],
    ) -> List[Dict[str, Any]]:
        """Parse LLM JSON response and validate concept IDs, dropping invalid ones."""
        # Strip markdown code fences if present
        text = raw_response
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        # Repair bare LaTeX backslashes Gemini sometimes emits (same fix as M2)
        text = _repair_latex_json(text)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error: {exc}\nRaw (first 1500 chars): {raw_response[:1500]}") from exc

        results = parsed.get("results")
        if not isinstance(results, list):
            raise ValueError(f"Expected 'results' array in response, got: {type(results)}")

        validated: List[Dict[str, Any]] = []
        for item in results:
            qid = item.get("question_id")
            if qid not in expected_question_ids:
                LOGGER.warning("  Unexpected question_id %s in response — skipping.", qid)
                continue

            # Validate concept IDs
            raw_concepts = item.get("tagged_concepts", [])
            good_concepts = []
            for c in raw_concepts:
                cid = c.get("concept_id")
                score = float(c.get("relevance_score", 0.0))
                if cid not in valid_ids:
                    LOGGER.warning("  Hallucinated concept_id %s for question %s — dropped.", cid, qid)
                    continue
                if score < 0.5:
                    continue
                good_concepts.append({"concept_id": cid, "relevance_score": round(score, 3)})

            if not good_concepts:
                LOGGER.warning("  No valid concepts for question %s — skipping question.", qid)
                continue

            difficulty = item.get("difficulty", "MEDIUM").upper()
            if difficulty not in VALID_DIFFICULTIES:
                difficulty = "MEDIUM"

            difficulty_confidence = float(item.get("difficulty_confidence", 0.5))
            difficulty_confidence = max(0.0, min(1.0, difficulty_confidence))

            pattern_label = str(item.get("pattern_label", "general")).lower().replace(" ", "_")[:64]
            embed_text = str(item.get("embed_text", "")).strip()

            validated.append({
                "question_id": qid,
                "tagged_concepts": good_concepts,
                "difficulty": difficulty,
                "difficulty_confidence": difficulty_confidence,
                "pattern_label": pattern_label,
                "embed_text": embed_text,
            })

        return validated

    def _print_dry_run_sample(
        self, tagged: List[Dict[str, Any]], vocab_rows: List[Dict[str, Any]]
    ) -> None:
        """Print a human-readable dry-run sample of the first 3 tagged questions."""
        id_to_title = {r["concept_id"]: r["concept_title"] for r in vocab_rows}
        print("\n" + "=" * 60)
        print("DRY-RUN SAMPLE (first 3 questions)")
        print("=" * 60)
        for t in tagged[:3]:
            print(f"\nQuestion ID: {t['question_id']}")
            print(f"  Difficulty:    {t['difficulty']} (conf={t['difficulty_confidence']:.2f})")
            print(f"  Pattern:       {t['pattern_label']}")
            print(f"  Embed text:    {t['embed_text']}")
            print(f"  Concepts ({len(t['tagged_concepts'])}):")
            for c in t["tagged_concepts"]:
                title = id_to_title.get(c["concept_id"], "?")
                print(f"    [{c['concept_id']}] {title} — score={c['relevance_score']}")
        print("=" * 60 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
def _build_pipeline() -> QuestionTaggerPipeline:
    pipeline_config = PipelineConfig()
    gemini_client = GeminiClient(pipeline_config)
    extractor = ConceptGeminiExtractor(pipeline_config=pipeline_config)
    db = JEEExtractionDBWriter()
    return QuestionTaggerPipeline(gemini_client, extractor, db, pipeline_config)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M3 JEE Question Tagger — tags jee_question_bank with NCERT concept IDs"
    )
    parser.add_argument(
        "--subject",
        choices=list(SUBJECT_MAP.keys()),
        default=None,
        help="Process only this subject (default: all in order Physics→Chemistry→Mathematics)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "hybrid"],
        default="hybrid",
        help="Tagging mode: 'full' sends entire vocabulary, 'hybrid' uses vector retrieval (default: hybrid)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        metavar="N",
        help="Questions per LLM call (default: 15 for hybrid, 5 for full)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=25,
        metavar="K",
        help="Candidates per question for hybrid retrieval (default: 25)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare hybrid vs existing full-mode tags (no DB writes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run tagging but skip all DB writes; print first batch results",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        metavar="Y",
        help="Filter questions by exam year (e.g. 2024)",
    )
    parser.add_argument(
        "--date",
        dest="dateofexam",
        default=None,
        metavar="YYYY-MM-DD",
        help="Filter to a single paper date (e.g. 2024-04-08)",
    )
    parser.add_argument(
        "--shift",
        default=None,
        metavar="S",
        help="Filter to a single shift (e.g. '1' or '2')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum questions to process (useful for testing)",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Tag only; skip embedding generation and jee_question_embeddings writes",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        metavar="N",
        help="Concurrent batch workers (default: 4; use 1 to disable concurrency)",
    )
    args = parser.parse_args()

    subjects = [args.subject] if args.subject else SUBJECT_ORDER

    # Default batch size depends on mode
    batch_size = args.batch_size
    if batch_size is None:
        batch_size = 15 if args.mode == "hybrid" else 5

    pipeline = _build_pipeline()

    if args.compare:
        pipeline.compare(
            subjects=subjects,
            top_k=args.top_k,
            batch_size=batch_size,
            year=args.year,
            dateofexam=args.dateofexam,
            shift=args.shift,
            limit=args.limit,
        )
    else:
        pipeline.run(
            subjects=subjects,
            mode=args.mode,
            batch_size=batch_size,
            top_k=args.top_k,
            dry_run=args.dry_run,
            year=args.year,
            dateofexam=args.dateofexam,
            shift=args.shift,
            limit=args.limit,
            skip_embeddings=args.skip_embeddings,
            workers=args.workers,
        )


if __name__ == "__main__":
    main()
