"""Database helpers for the JEE Ascent extraction pipeline (M1b)."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from settings_loader import load_local_settings

load_local_settings()

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor, execute_values


LOGGER = logging.getLogger(__name__)


class JEEExtractionDBWriter:
    """psycopg2-based reader/writer for M1b exam paper and question tables."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or os.environ.get("DATABASE_URL")
        self.connection_config = None if self.dsn else self._build_connection_config()
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

    # ──────────────────── connection pool (M3) ────────────────────

    def open_connection_pool(self, minconn: int = 2, maxconn: int = 8) -> None:
        """Create a ThreadedConnectionPool for concurrent use.

        Must be called before starting concurrent batch workers.
        """
        if self.dsn:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn, maxconn, self.dsn, connect_timeout=30
            )
        else:
            params = self._build_connection_params()
            params.setdefault("connect_timeout", 30)
            self._pool = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, **params)
        LOGGER.info("Connection pool opened (min=%d, max=%d).", minconn, maxconn)

    def close_connection_pool(self) -> None:
        """Close all pool connections and discard the pool."""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None
            LOGGER.info("Connection pool closed.")

    # ─────────────────────────── reads ────────────────────────────

    def fetch_pending_answer_keys(
        self,
        *,
        year: Optional[int] = None,
        session: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return exam_answer_keys rows that are PENDING, FINAL, and have a blob_url."""
        clauses = ["blob_url IS NOT NULL", "extraction_status = 'PENDING'", "key_type = 'FINAL'"]
        params: List[Any] = []

        if year is not None:
            clauses.append("year = %s")
            params.append(year)

        if session:
            clauses.append("session = %s")
            params.append(session)

        query = f"""
            SELECT id, title, year, session, key_type, blob_url, filename
            FROM exam_answer_keys
            WHERE {' AND '.join(clauses)}
            ORDER BY year, session
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]

    def fetch_pending_papers(
        self,
        *,
        paper_ids: Optional[List[int]] = None,
        year: Optional[int] = None,
        session: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return exam_papers rows that are PENDING and have a blob_url."""
        clauses = ["blob_url IS NOT NULL", "extraction_status = 'PENDING'"]
        params: List[Any] = []

        if paper_ids:
            clauses.append("id = ANY(%s)")
            params.append(paper_ids)

        if year is not None:
            clauses.append("year = %s")
            params.append(year)

        # session filter: exam_papers has no session column — filter by shift prefix
        if session:
            clauses.append("LOWER(shift) LIKE LOWER(%s)")
            params.append(f"{session}%")

        # Skip known bad rows: "JEE Main 2018" paper names
        clauses.append("LOWER(papername) NOT LIKE '%%2018%%'")

        # Skip 2023 Session 1 entirely (no valid AK, no papers)
        # 2023 S1 papers would have dateofexam between 2023-01-24 and 2023-02-01
        clauses.append(
            "NOT (year = 2023 AND dateofexam BETWEEN '2023-01-24' AND '2023-02-01')"
        )

        query = f"""
            SELECT
                id,
                examname,
                papername,
                year,
                dateofexam,
                shift,
                filename,
                blob_url,
                paper_format,
                extraction_status
            FROM exam_papers
            WHERE {' AND '.join(clauses)}
            ORDER BY year, dateofexam, shift
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]

    def fetch_papers_by_ids(self, paper_ids: List[int]) -> List[Dict[str, Any]]:
        """Return exam_papers rows for the given IDs regardless of extraction_status."""
        query = """
            SELECT
                id, examname, papername, year, dateofexam, shift,
                filename, blob_url, paper_format, extraction_status
            FROM exam_papers
            WHERE id = ANY(%s)
            ORDER BY year, dateofexam, shift
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (paper_ids,))
                return [dict(r) for r in cur.fetchall()]

    def answer_key_mappings_exist(self, source_key_id: int) -> bool:
        """Return True if jee_answer_mappings already has rows for this AK."""
        query = "SELECT 1 FROM jee_answer_mappings WHERE source_key_id = %s LIMIT 1"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (source_key_id,))
                return cur.fetchone() is not None

    def questions_exist_for_paper(self, exam_paper_id: int) -> bool:
        """Return True if jee_question_bank already has rows for this paper."""
        query = "SELECT 1 FROM jee_question_bank WHERE exam_paper_id = %s LIMIT 1"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (exam_paper_id,))
                return cur.fetchone() is not None

    def lookup_answer_key(self, nta_question_id: str) -> Optional[str]:
        """Look up the correct_option_id for an NTA question ID."""
        query = "SELECT correct_option_id FROM jee_answer_mappings WHERE nta_question_id = %s"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (nta_question_id,))
                row = cur.fetchone()
                return row[0] if row else None

    def lookup_answer_keys_bulk(self, nta_question_ids: List[str]) -> Dict[str, str]:
        """Fetch correct_option_id for all given NTA question IDs in one query.

        Returns a dict mapping nta_question_id → correct_option_id.
        """
        if not nta_question_ids:
            return {}
        query = "SELECT nta_question_id, correct_option_id FROM jee_answer_mappings WHERE nta_question_id = ANY(%s)"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (nta_question_ids,))
                return {row[0]: row[1] for row in cur.fetchall()}

    # ─────────────────────────── writes ───────────────────────────

    def bulk_insert_answer_mappings(
        self,
        mappings: List[Dict[str, Any]],
        source_key_id: int,
    ) -> int:
        """Insert Q-ID → option-ID pairs; skip conflicts. Returns inserted count."""
        if not mappings:
            return 0

        query = """
            INSERT INTO jee_answer_mappings (nta_question_id, correct_option_id, source_key_id)
            VALUES %s
            ON CONFLICT (nta_question_id) DO NOTHING
        """
        rows = [(m["nta_question_id"], m["correct_option_id"], source_key_id) for m in mappings]
        with self.connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, rows, page_size=500)
                return cur.rowcount

    def mark_answer_key_extracted(self, key_id: int) -> None:
        """Set extraction_status = 'EXTRACTED' on an exam_answer_keys row."""
        query = "UPDATE exam_answer_keys SET extraction_status = 'EXTRACTED' WHERE id = %s"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key_id,))

    def mark_answer_key_failed(self, key_id: int) -> None:
        """Set extraction_status = 'FAILED' on an exam_answer_keys row."""
        query = "UPDATE exam_answer_keys SET extraction_status = 'FAILED' WHERE id = %s"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key_id,))

    def update_paper_format(self, paper_id: int, paper_format: str) -> None:
        """Persist the detected paper format back to exam_papers."""
        query = "UPDATE exam_papers SET paper_format = %s WHERE id = %s"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (paper_format, paper_id))

    def bulk_insert_questions(self, questions: List[Dict[str, Any]], paper: Dict[str, Any]) -> int:
        """Insert extracted questions into jee_question_bank. Returns inserted count."""
        if not questions:
            return 0

        query = """
            INSERT INTO jee_question_bank (
                nta_question_id,
                exam_paper_id,
                year,
                dateofexam,
                shift,
                subject,
                section,
                tier,
                question_content,
                answer_key,
                is_generated,
                review_status,
                source
            ) VALUES %s
            ON CONFLICT ON CONSTRAINT uq_jee_qbank_paper_nta DO NOTHING
        """
        rows = [
            (
                q.get("nta_question_id"),
                paper["id"],
                paper["year"],
                paper.get("dateofexam"),
                paper.get("shift"),
                q.get("subject"),
                q.get("section"),
                3,
                json.dumps(q.get("question_content", {})),
                q.get("answer_key"),
                False,
                "APPROVED",
                "NTA_EXTRACTED",
            )
            for q in questions
        ]
        with self.connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, rows, page_size=100)
                return cur.rowcount

    def mark_paper_extracted(self, paper_id: int) -> None:
        """Set extraction_status = 'EXTRACTED' on an exam_papers row."""
        query = "UPDATE exam_papers SET extraction_status = 'EXTRACTED' WHERE id = %s"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (paper_id,))

    def mark_paper_failed(self, paper_id: int) -> None:
        """Set extraction_status = 'FAILED' on an exam_papers row."""
        query = "UPDATE exam_papers SET extraction_status = 'FAILED' WHERE id = %s"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (paper_id,))

    # ─────────────────────── connection helpers ────────────────────

    @contextmanager
    def connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Yield a psycopg2 connection with automatic commit/rollback.

        When a pool is open (concurrent mode), borrows from the pool and
        returns it after use. Otherwise opens and closes a single connection.
        On OperationalError (token expired / connection dropped), refreshes
        the Azure token and retries once before propagating the error.
        """
        if self._pool is not None:
            conn = self._pool.getconn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._pool.putconn(conn)
            return

        # Single-connection path (no pool active)
        if self.dsn:
            conn = psycopg2.connect(self.dsn, connect_timeout=30)
        else:
            try:
                params = self._build_connection_params()
                params.setdefault("connect_timeout", 30)
                conn = psycopg2.connect(**params)
            except psycopg2.OperationalError:
                LOGGER.warning("Connection failed — refreshing token and retrying…")
                self.refresh_token()
                params = self._build_connection_params()
                params.setdefault("connect_timeout", 30)
                conn = psycopg2.connect(**params)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _build_connection_config(self) -> Dict[str, Any]:
        host = os.environ.get("DB_HOST") or os.environ.get("AZURE_PG_HOST")
        name = os.environ.get("DB_NAME") or os.environ.get("AZURE_PG_DATABASE")
        user = os.environ.get("DB_USER") or os.environ.get("AZURE_PG_USER")
        port = os.environ.get("DB_PORT") or os.environ.get("AZURE_PG_PORT") or "5432"
        sslmode = os.environ.get("DB_SSLMODE", "require")

        if not all([host, name, user]):
            raise ValueError(
                "Database configuration not found. Set DATABASE_URL or DB_HOST/DB_NAME/DB_USER."
            )
        return {"host": host, "port": port, "dbname": name, "user": user, "sslmode": sslmode}

    def refresh_token(self) -> None:
        """Force-acquire a fresh Azure CLI token and cache it for this session.

        Call this once per subject (before concurrent batch workers start) to
        ensure the token is valid for the full run. If a pool is open, it is
        recreated so new connections pick up the fresh token.
        """
        LOGGER.info("Refreshing Azure DB access token...")
        self._cached_password = self._get_access_token()
        LOGGER.info("Azure DB token refreshed.")
        if self._pool is not None:
            minconn = self._pool.minconn
            maxconn = self._pool.maxconn
            self._pool.closeall()
            self._pool = None
            self.open_connection_pool(minconn=minconn, maxconn=maxconn)

    def _build_connection_params(self) -> Dict[str, Any]:
        params = dict(self.connection_config or self._build_connection_config())
        password = os.environ.get("DB_PASSWORD") or os.environ.get("AZURE_PG_PASSWORD")
        if password:
            params["password"] = password
            return params

        # Use cached token if available (refreshed once per paper via refresh_token()).
        # Fall back to acquiring a new token if not yet cached.
        if not hasattr(self, "_cached_password") or not self._cached_password:
            LOGGER.info("DB_PASSWORD not set; acquiring Azure token for PostgreSQL.")
            self._cached_password = self._get_access_token()

        params["password"] = self._cached_password
        return params

    # ─────────────── M3: Question Tagger ─────────────────────────

    def load_concept_vocabulary(self, subject: str) -> List[Dict[str, Any]]:
        """Return all concept nodes for *subject* (ncert_concept_hierarchy value,
        e.g. 'Maths' not 'Mathematics') joined with chapter title.

        Each row: {concept_id, concept_title, content_type, chapter_title, key_formulas}
        Sorted by chapter_id, path for deterministic vocabulary ordering.
        """
        query = """
            SELECT
                nch.id              AS concept_id,
                nch.concept_title,
                nch.content_type,
                nch.key_formulas,
                cd.chaptertitle     AS chapter_title
            FROM ncert_concept_hierarchy nch
            JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
            WHERE nch.subject = %s
            ORDER BY nch.chapter_id, nch.path
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (subject,))
                return [dict(r) for r in cur.fetchall()]

    def fetch_untagged_questions(
        self,
        *,
        subject: Optional[str] = None,
        year: Optional[int] = None,
        dateofexam: Optional[str] = None,
        shift: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return jee_question_bank rows that have no entry in jee_question_tags.

        Uses NOT EXISTS for idempotency — safe to restart without duplicates.
        Filter by subject / year / dateofexam / shift to target a single paper.
        Returns: id, nta_question_id, subject, section, answer_key, question_content.
        """
        clauses = [
            "NOT EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)"
        ]
        params: List[Any] = []

        if subject is not None:
            clauses.append("q.subject = %s")
            params.append(subject)

        if year is not None:
            clauses.append("q.year = %s")
            params.append(year)

        if dateofexam is not None:
            clauses.append("q.dateofexam = %s")
            params.append(dateofexam)

        if shift is not None:
            clauses.append("q.shift = %s")
            params.append(shift)

        limit_clause = f"LIMIT {int(limit)}" if limit else ""

        query = f"""
            SELECT
                q.id,
                q.nta_question_id,
                q.subject,
                q.section,
                q.answer_key,
                q.question_content
            FROM jee_question_bank q
            WHERE {' AND '.join(clauses)}
            ORDER BY q.subject, q.id
            {limit_clause}
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]

    def bulk_upsert_question_tags(self, rows: List[Dict[str, Any]]) -> int:
        """Upsert rows into jee_question_tags.

        Each row: {question_id, concept_id, similarity_score}
        ON CONFLICT updates similarity_score so re-runs are idempotent.
        Returns number of rows affected.
        """
        if not rows:
            return 0
        query = """
            INSERT INTO jee_question_tags (question_id, concept_id, similarity_score)
            VALUES %s
            ON CONFLICT (question_id, concept_id)
            DO UPDATE SET similarity_score = EXCLUDED.similarity_score
        """
        data = [(r["question_id"], r["concept_id"], r["similarity_score"]) for r in rows]
        with self.connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, data, page_size=500)
                return cur.rowcount

    def bulk_upsert_question_embeddings(self, rows: List[Dict[str, Any]]) -> int:
        """Upsert rows into jee_question_embeddings.

        Each row: {question_id, embedding (list[float]), embed_text}
        Returns number of rows affected.
        """
        if not rows:
            return 0
        query = """
            INSERT INTO jee_question_embeddings (question_id, embedding, embed_text)
            VALUES %s
            ON CONFLICT (question_id)
            DO UPDATE SET
                embedding  = EXCLUDED.embedding,
                embed_text = EXCLUDED.embed_text
        """
        import json as _json
        data = [
            (r["question_id"], str(r["embedding"]), r.get("embed_text"))
            for r in rows
        ]
        with self.connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, data, page_size=200)
                return cur.rowcount

    def bulk_update_question_metadata(self, rows: List[Dict[str, Any]]) -> int:
        """Update difficulty, difficulty_confidence, pattern_label on jee_question_bank.

        Each row: {question_id, difficulty, difficulty_confidence, pattern_label}
        Returns number of rows updated.
        """
        if not rows:
            return 0
        query = """
            UPDATE jee_question_bank AS q
            SET
                difficulty            = v.difficulty,
                difficulty_confidence = v.difficulty_confidence::float,
                pattern_label         = v.pattern_label
            FROM (VALUES %s) AS v(question_id, difficulty, difficulty_confidence, pattern_label)
            WHERE q.id = v.question_id::int
        """
        data = [
            (r["question_id"], r["difficulty"], r["difficulty_confidence"], r["pattern_label"])
            for r in rows
        ]
        with self.connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, data, page_size=200)
                return cur.rowcount

    # ─────────── M3 Hybrid: vector retrieval + compare ────────────

    @staticmethod
    def _vector_literal(embedding: List[float]) -> str:
        """Format a Python float list as a pgvector literal."""
        return "[" + ",".join(f"{v:.12f}" for v in embedding) + "]"

    def fetch_concept_candidates_vector(
        self,
        question_embedding: List[float],
        subject: str,
        top_k: int = 25,
    ) -> List[Dict[str, Any]]:
        """Return top-K concept candidates by cosine similarity using pgvector.

        Returns same columns as load_concept_vocabulary() plus vector_score.
        """
        vec_lit = self._vector_literal(question_embedding)
        query = """
            SELECT
                nch.id              AS concept_id,
                nch.concept_title,
                nch.content_type,
                nch.key_formulas,
                cd.chaptertitle     AS chapter_title,
                1 - (nce.embedding <=> %s::vector) AS vector_score
            FROM ncert_concept_hierarchy nch
            JOIN ncert_concept_embeddings nce ON nce.concept_id = nch.id
            JOIN chapterdata cd ON cd.chapterid = nch.chapter_id
            WHERE nch.subject = %s
            ORDER BY nce.embedding <=> %s::vector
            LIMIT %s
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (vec_lit, subject, vec_lit, top_k))
                return [dict(r) for r in cur.fetchall()]

    def fetch_tagged_questions(
        self,
        *,
        subject: Optional[str] = None,
        year: Optional[int] = None,
        dateofexam: Optional[str] = None,
        shift: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return jee_question_bank rows that HAVE entries in jee_question_tags.

        Opposite of fetch_untagged_questions — used for compare/evaluation mode.
        """
        clauses = [
            "EXISTS (SELECT 1 FROM jee_question_tags t WHERE t.question_id = q.id)"
        ]
        params: List[Any] = []

        if subject is not None:
            clauses.append("q.subject = %s")
            params.append(subject)
        if year is not None:
            clauses.append("q.year = %s")
            params.append(year)
        if dateofexam is not None:
            clauses.append("q.dateofexam = %s")
            params.append(dateofexam)
        if shift is not None:
            clauses.append("q.shift = %s")
            params.append(shift)

        limit_clause = f"LIMIT {int(limit)}" if limit else ""

        query = f"""
            SELECT
                q.id,
                q.nta_question_id,
                q.subject,
                q.section,
                q.answer_key,
                q.question_content
            FROM jee_question_bank q
            WHERE {' AND '.join(clauses)}
            ORDER BY q.subject, q.id
            {limit_clause}
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]

    def fetch_existing_tags(self, question_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        """Return existing tags grouped by question_id.

        Returns {question_id: [{concept_id, concept_title, similarity_score}, ...]}.
        """
        if not question_ids:
            return {}
        query = """
            SELECT t.question_id, t.concept_id, nch.concept_title, t.similarity_score
            FROM jee_question_tags t
            JOIN ncert_concept_hierarchy nch ON nch.id = t.concept_id
            WHERE t.question_id = ANY(%s)
            ORDER BY t.question_id, t.similarity_score DESC
        """
        result: Dict[int, List[Dict[str, Any]]] = {}
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (question_ids,))
                for row in cur.fetchall():
                    qid = row["question_id"]
                    result.setdefault(qid, []).append(dict(row))
        return result

    # ──────────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        from azure.identity import AzureCliCredential

        # Use AzureCliCredential directly (skips slow IMDS/ManagedIdentity probes).
        # Wrap in a thread with a 20s timeout so a stale CLI session fails fast
        # instead of hanging the pipeline indefinitely.
        credential = AzureCliCredential()

        def _get():
            return credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_get)
            try:
                return future.result(timeout=20)
            except FuturesTimeoutError:
                raise RuntimeError(
                    "Azure CLI token acquisition timed out after 20s. "
                    "Run `az account get-access-token` to refresh your CLI session."
                )
