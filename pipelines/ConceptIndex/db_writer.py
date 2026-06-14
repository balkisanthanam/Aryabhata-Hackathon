"""Database helpers for the NCERT Concept Index pipeline."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, List, Optional, TypeVar

_T = TypeVar("_T")

from settings_loader import load_local_settings

load_local_settings()

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor


LOGGER = logging.getLogger(__name__)


class ConceptIndexDBWriter:
    """Small psycopg2-based writer for M2 chapter reads and concept writes."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or os.environ.get("DATABASE_URL")
        self.connection_config = None if self.dsn else self._build_connection_config()
        self._cached_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def fetch_chapters(
        self,
        *,
        chapter_ids: Optional[List[int]] = None,
        subject: Optional[str] = None,
        class_level: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch chapter rows that are eligible for concept indexing."""
        clauses = ["pdffileurl IS NOT NULL"]
        params: List[Any] = []

        if chapter_ids:
            clauses.append("chapterid = ANY(%s)")
            params.append(chapter_ids)

        if subject:
            clauses.append("LOWER(subject) = LOWER(%s)")
            params.append(subject)

        if class_level is not None:
            clauses.append("class = %s")
            params.append(str(class_level))

        query = f"""
            SELECT
                chapterid AS chapter_id,
                class AS class_level,
                subject,
                chapternumber AS chapter_number,
                chaptertitle AS chapter_title,
                pdffileurl AS pdf_file_url
            FROM chapterdata
            WHERE {' AND '.join(clauses)}
            ORDER BY class, subject, chapternumber
        """

        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def fetch_existing_path_id_map(self, chapter_id: int) -> Dict[str, int]:
        """Load current `(chapter_id, path)` identities for resumable writes."""
        query = """
            SELECT id, path::text AS path
            FROM ncert_concept_hierarchy
            WHERE chapter_id = %s
              AND path IS NOT NULL
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (chapter_id,))
                rows = cursor.fetchall()
                return {row["path"]: row["id"] for row in rows}

    def rebuild_checkpoint_nodes(self, chapter_id: int) -> Dict[str, Dict[str, Any]]:
        """Rebuild minimal node state when checkpoint files are missing."""
        query = """
            SELECT
                h.id AS concept_id,
                h.path::text AS path,
                p.path::text AS parent_path,
                EXISTS (
                    SELECT 1
                    FROM ncert_concept_embeddings e
                    WHERE e.concept_id = h.id
                ) AS embedding_written
            FROM ncert_concept_hierarchy h
            LEFT JOIN ncert_concept_hierarchy p ON p.id = h.parent_id
            WHERE h.chapter_id = %s
              AND h.path IS NOT NULL
        """
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (chapter_id,))
                rows = cursor.fetchall()
                state: Dict[str, Dict[str, Any]] = {}
                for row in rows:
                    state[row["path"]] = {
                        "parent_path": row["parent_path"],
                        "concept_id": row["concept_id"],
                        "hierarchy_written": True,
                        "embedding_written": bool(row["embedding_written"]),
                        "figure_url": None,
                        "has_figure": False,
                        "embed_hash": None,
                    }
                return state

    def fetch_one(self, query: str, params: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
        """Fetch one row and return it as a plain dict."""
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params or [])
                row = cursor.fetchone()
                return dict(row) if row else None

    def upsert_hierarchy_row(
        self,
        *,
        chapter_id: int,
        path: str,
        parent_id: Optional[int],
        concept_title: str,
        description: Optional[str],
        key_formulas: Optional[str],
        embedding_text: str,
        ncert_solved_example: Optional[str],
        content_type: str,
        figure_url: Optional[str],
        chunk_text: Optional[str],
        chunk_index: Optional[int],
        class_value: Optional[int],
        subject: Optional[str],
    ) -> Dict[str, Any]:
        """Upsert one concept hierarchy row using `(chapter_id, path)` as the natural key."""
        select_sql = """
            SELECT id
            FROM ncert_concept_hierarchy
            WHERE chapter_id = %s
              AND path::text = %s
            LIMIT 1
        """
        insert_sql = """
            INSERT INTO ncert_concept_hierarchy (
                chapter_id,
                parent_id,
                concept_title,
                description,
                key_formulas,
                embedding_text,
                ncert_solved_example,
                content_type,
                path,
                figure_url,
                chunk_text,
                chunk_index,
                class,
                subject
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s::ltree, %s, %s, %s, %s, %s
            )
            RETURNING id
        """
        update_sql = """
            UPDATE ncert_concept_hierarchy
            SET
                parent_id = %s,
                concept_title = %s,
                description = %s,
                key_formulas = %s,
                embedding_text = %s,
                ncert_solved_example = %s,
                content_type = %s,
                figure_url = %s,
                chunk_text = %s,
                chunk_index = %s,
                class = %s,
                subject = %s
            WHERE id = %s
            RETURNING id
        """

        def _do() -> Dict[str, Any]:
            with self.connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(select_sql, (chapter_id, path))
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute(
                            update_sql,
                            (
                                parent_id,
                                concept_title,
                                description,
                                key_formulas,
                                embedding_text,
                                ncert_solved_example,
                                content_type,
                                figure_url,
                                chunk_text,
                                chunk_index,
                                class_value,
                                subject,
                                existing["id"],
                            ),
                        )
                        row = cursor.fetchone()
                    else:
                        cursor.execute(
                            insert_sql,
                            (
                                chapter_id,
                                parent_id,
                                concept_title,
                                description,
                                key_formulas,
                                embedding_text,
                                ncert_solved_example,
                                content_type,
                                path,
                                figure_url,
                                chunk_text,
                                chunk_index,
                                class_value,
                                subject,
                            ),
                        )
                        row = cursor.fetchone()

                    return dict(row)

        return self._retry_db_op(_do)

    def upsert_embedding_row(self, *, concept_id: int, embedding: List[float]) -> Dict[str, Any]:
        """Upsert the vector row for a concept using the schema's unique `concept_id`."""
        vector_literal = self._vector_literal(embedding)

        insert_sql = """
            INSERT INTO ncert_concept_embeddings (concept_id, embedding, created_at)
            VALUES (%s, %s::vector, NOW())
            ON CONFLICT (concept_id) DO UPDATE
            SET embedding = EXCLUDED.embedding
            RETURNING id
        """

        def _do() -> Dict[str, Any]:
            with self.connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(insert_sql, (concept_id, vector_literal))
                    row = cursor.fetchone()
                    return dict(row)

        return self._retry_db_op(_do)

    def bulk_upsert_hierarchy_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        initial_path_to_id: Optional[Dict[str, int]] = None,
    ) -> Dict[str, int]:
        """Write multiple hierarchy rows sequentially in a single connection.

        Each dict in `rows` must contain: chapter_id, path, parent_path,
        concept_title, description, key_formulas, embedding_text,
        ncert_solved_example, content_type, figure_url, chunk_text,
        chunk_index, class_value, subject.

        parent_id is resolved from `initial_path_to_id` (pre-existing rows from
        the checkpoint) and from nodes written earlier in this same batch —
        so rows must be in parent-before-child order (topological).

        Returns {path: concept_id} for every row written.
        """
        if not rows:
            return {}

        select_sql = """
            SELECT id FROM ncert_concept_hierarchy
            WHERE chapter_id = %s AND path::text = %s LIMIT 1
        """
        insert_sql = """
            INSERT INTO ncert_concept_hierarchy (
                chapter_id, parent_id, concept_title, description, key_formulas,
                embedding_text, ncert_solved_example, content_type, path,
                figure_url, chunk_text, chunk_index, class, subject
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::ltree, %s, %s, %s, %s, %s)
            RETURNING id
        """
        update_sql = """
            UPDATE ncert_concept_hierarchy SET
                parent_id=%s, concept_title=%s, description=%s, key_formulas=%s,
                embedding_text=%s, ncert_solved_example=%s, content_type=%s,
                figure_url=%s, chunk_text=%s, chunk_index=%s, class=%s, subject=%s
            WHERE id=%s RETURNING id
        """

        path_to_id: Dict[str, int] = dict(initial_path_to_id or {})

        def _do() -> Dict[str, int]:
            result: Dict[str, int] = {}
            with self.connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    for row in rows:
                        parent_id = (
                            path_to_id.get(row["parent_path"])
                            if row.get("parent_path")
                            else None
                        )
                        cursor.execute(select_sql, (row["chapter_id"], row["path"]))
                        existing = cursor.fetchone()
                        if existing:
                            cursor.execute(update_sql, (
                                parent_id, row["concept_title"], row["description"],
                                row["key_formulas"], row["embedding_text"],
                                row["ncert_solved_example"], row["content_type"],
                                row["figure_url"], row["chunk_text"], row["chunk_index"],
                                row["class_value"], row["subject"], existing["id"],
                            ))
                        else:
                            cursor.execute(insert_sql, (
                                row["chapter_id"], parent_id, row["concept_title"],
                                row["description"], row["key_formulas"],
                                row["embedding_text"], row["ncert_solved_example"],
                                row["content_type"], row["path"], row["figure_url"],
                                row["chunk_text"], row["chunk_index"],
                                row["class_value"], row["subject"],
                            ))
                        written_id = cursor.fetchone()["id"]
                        path_to_id[row["path"]] = written_id
                        result[row["path"]] = written_id
            return result

        return self._retry_db_op(_do)

    def bulk_upsert_embedding_rows(
        self,
        items: List[Dict[str, Any]],
    ) -> None:
        """Upsert multiple embedding rows in a single connection.

        Each dict in `items` must contain: concept_id (int), embedding (List[float]).
        """
        if not items:
            return

        insert_sql = """
            INSERT INTO ncert_concept_embeddings (concept_id, embedding, created_at)
            VALUES (%s, %s::vector, NOW())
            ON CONFLICT (concept_id) DO UPDATE SET embedding = EXCLUDED.embedding
        """

        def _do() -> None:
            with self.connection() as conn:
                with conn.cursor() as cursor:
                    for item in items:
                        cursor.execute(
                            insert_sql,
                            (item["concept_id"], self._vector_literal(item["embedding"])),
                        )

        self._retry_db_op(_do)

    @contextmanager
    def connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Open a new psycopg2 connection with automatic commit/rollback."""
        if self.dsn:
            conn = psycopg2.connect(self.dsn)
        else:
            conn = psycopg2.connect(**self._build_connection_params())
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass  # connection may already be dead — ignore secondary error
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _retry_db_op(self, func: Callable[[], _T], *, max_retries: int = 3) -> _T:
        """Retry a DB operation on transient connection errors with exponential back-off."""
        for attempt in range(max_retries):
            try:
                return func()
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                LOGGER.warning(
                    "Transient DB error (attempt %d/%d): %s. Retrying in %ds.",
                    attempt + 1, max_retries, exc, wait,
                )
                time.sleep(wait)

    def _build_connection_config(self) -> Dict[str, Any]:
        """Build base connection settings from repo-style environment variables."""
        host = os.environ.get("DB_HOST") or os.environ.get("AZURE_PG_HOST")
        name = os.environ.get("DB_NAME") or os.environ.get("AZURE_PG_DATABASE")
        user = os.environ.get("DB_USER") or os.environ.get("AZURE_PG_USER")
        port = os.environ.get("DB_PORT") or os.environ.get("AZURE_PG_PORT") or "5432"
        sslmode = os.environ.get("DB_SSLMODE", "require")

        if not all([host, name, user]):
            raise ValueError(
                "Database configuration not found. Set DATABASE_URL or DB_HOST/DB_NAME/DB_USER."
            )

        return {
            "host": host,
            "port": port,
            "dbname": name,
            "user": user,
            "sslmode": sslmode,
        }

    def _build_connection_params(self) -> Dict[str, Any]:
        """Build connection params, preferring password auth and falling back to Entra token auth."""
        params = dict(self.connection_config or self._build_connection_config())
        password = os.environ.get("DB_PASSWORD") or os.environ.get("AZURE_PG_PASSWORD")
        if password:
            params["password"] = password
            return params

        LOGGER.debug("DB_PASSWORD not set; using DefaultAzureCredential for PostgreSQL access.")
        params["password"] = self._get_access_token()
        return params

    def _get_access_token(self) -> str:
        """Return a cached Entra token for Azure PostgreSQL, refreshing only when near expiry."""
        now = datetime.now(timezone.utc)
        if self._cached_token and self._token_expiry and self._token_expiry > now:
            return self._cached_token

        from azure.identity import DefaultAzureCredential

        LOGGER.info("Fetching fresh Azure PostgreSQL token.")
        credential = DefaultAzureCredential()
        token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        self._cached_token = token.token
        # token.expires_on is a Unix timestamp int
        expiry = datetime.fromtimestamp(token.expires_on, tz=timezone.utc)
        # Refresh 5 minutes early to avoid using an about-to-expire token
        from datetime import timedelta
        self._token_expiry = expiry - timedelta(minutes=5)
        LOGGER.info("Token cached; valid until %s.", self._token_expiry.isoformat())
        return self._cached_token

    def _vector_literal(self, embedding: List[float]) -> str:
        """Format a pgvector literal accepted by PostgreSQL."""
        return "[" + ",".join(f"{value:.12f}" for value in embedding) + "]"
