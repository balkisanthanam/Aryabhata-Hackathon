"""Gemini extraction and embedding helpers for the NCERT Concept Index pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, List, Optional

from settings_loader import load_local_settings

load_local_settings()

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


LOGGER = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PIPELINE_DIR / "prompts"
MULTISTEP_DIR = (
    PIPELINE_DIR.parent
    / "ExtractionPipeline"
    / "SchoolDataExtraction"
    / "MultiStep"
)

if str(MULTISTEP_DIR) not in sys.path:
    sys.path.insert(0, str(MULTISTEP_DIR))

from blob_client import get_blob_client  # type: ignore  # noqa: E402
from config import GeminiModelConfig, PipelineConfig  # type: ignore  # noqa: E402
from gemini_client import CachedDocument, GeminiClient  # type: ignore  # noqa: E402

from google import genai as _genai  # noqa: E402  (for dedicated embed client)
from google.genai import types as _genai_types  # noqa: E402


VALID_CONTENT_TYPES = {
    "concept",
    "definition",
    "theorem",
    "formula",
    "worked_example",
    "data_table",
}

LTREE_LABEL_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Matches a bare backslash followed by any letter (the LaTeX command pattern).
# Used to double-escape LaTeX commands Gemini emits without proper JSON escaping.
# We protect already-doubled backslashes (\\) first, then double all \letter.
_LATEX_BACKSLASH_RE = re.compile(r"\\([A-Za-z])")


def _repair_json_escapes(raw: str) -> str:
    """Double-escape all LaTeX backslashes that Gemini emitted as bare \\X in JSON.

    Gemini sometimes returns LaTeX formulas inside JSON string values with
    single backslashes (e.g. \\phi, \\alpha, \\frac, \\theta) instead of the
    double-escaped form (\\\\phi) required by the JSON spec.

    Strategy:
      1. Temporarily protect already-correct \\\\ sequences with a placeholder.
      2. Double every remaining \\letter sequence (LaTeX command pattern).
      3. Restore the placeholder back to \\\\.

    This safely repairs both the "hard failures" (\\phi, \\alpha → invalid JSON
    escapes) and the "silent corruptions" (\\theta → tab, \\frac → form-feed)
    that the JSON parser accepts but mangles into control characters.
    """
    placeholder = "\x00\x01\x00"  # unlikely to appear in real content
    step1 = raw.replace("\\\\", placeholder)
    step2 = _LATEX_BACKSLASH_RE.sub(r"\\\\\1", step1)
    return step2.replace(placeholder, "\\\\")


def _parse_json_response(text: str) -> Any:
    """Parse Gemini's JSON response, repairing bare LaTeX backslashes if needed."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        LOGGER.debug("JSON parse failed; attempting LaTeX escape repair.")
        repaired = _repair_json_escapes(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            LOGGER.warning(
                "JSON still invalid after repair (first 500 chars of repaired): %s ...",
                repaired[:500],
            )
            raise exc


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the local prompts directory."""
    prompt_path = PROMPTS_DIR / name
    return prompt_path.read_text(encoding="utf-8")


def download_pdf(url: str, destination: Path) -> Dict[str, Any]:
    """Download a chapter PDF if it is not already present locally."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not destination.exists():
        LOGGER.info("Downloading chapter PDF from %s", url)
        destination.write_bytes(_download_url_bytes(url))

    pdf_bytes = destination.read_bytes()
    return {
        "local_path": str(destination),
        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "size_bytes": len(pdf_bytes),
        "source_url": url,
    }


def _download_url_bytes(url: str) -> bytes:
    """Download bytes from either Azure Blob Storage or a public URL."""
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc.endswith(".blob.core.windows.net"):
        return _download_blob_bytes(url)

    with urllib.request.urlopen(url) as response:
        return response.read()


def _download_blob_bytes(url: str) -> bytes:
    """Download blob bytes using Azure identity, with public URL fallback for signed/public blobs."""
    from azure.core.exceptions import AzureError
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient

    try:
        credential = DefaultAzureCredential()
        blob_client = BlobClient.from_blob_url(url, credential=credential)
        return blob_client.download_blob().readall()
    except AzureError as exc:
        LOGGER.warning("Azure-authenticated blob download failed for %s: %s", url, exc)
        with urllib.request.urlopen(url) as response:
            return response.read()


class ConceptGeminiExtractor:
    """Adapter around the shared MultiStep Gemini client for M2 extraction."""

    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        pipeline_config: Optional[PipelineConfig] = None,
    ) -> None:
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        config = pipeline_config or PipelineConfig.from_env()
        # ConceptIndex chapters can produce large JSON responses. 10 min per attempt
        # is enough headroom; our retry logic in gemini_client handles re-cache on
        # timeout. Override via CONCEPT_INDEX_API_TIMEOUT_SECONDS if needed.
        config.api_timeout_seconds = int(
            os.environ.get("CONCEPT_INDEX_API_TIMEOUT_SECONDS", 600)
        )
        self.pipeline_config = config
        self.client = GeminiClient(self.pipeline_config)
        self.blob_client = get_blob_client(use_managed_identity=True)

        # text-embedding-004 requires a regional Vertex AI endpoint (not 'global').
        # We build a dedicated embed client so the extraction client (often 'global')
        # and the embedding client remain independently configured.
        embed_location = os.environ.get("CONCEPT_INDEX_EMBED_LOCATION", "us-central1")
        embed_timeout_ms = int(os.environ.get("CONCEPT_INDEX_EMBED_TIMEOUT_SECONDS", 120)) * 1000
        self._embed_client = _genai.Client(
            vertexai=True,
            project=self.pipeline_config.project_id,
            location=embed_location,
            http_options=_genai_types.HttpOptions(timeout=embed_timeout_ms),
        )
        LOGGER.info("Embedding client initialised (location=%s)", embed_location)

    def get_extraction_model(self) -> GeminiModelConfig:
        """Build the Gemini model config used for concept extraction."""
        base_model = self.pipeline_config.solver_model
        model_id = os.environ.get(
            "CONCEPT_INDEX_EXTRACTION_MODEL",
            base_model.model_id,
        )
        return GeminiModelConfig(
            model_id=model_id,
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=65535,
            response_mime_type="application/json",
        )

    def build_extraction_prompt(self, chapter: Dict[str, Any]) -> str:
        """Build the concrete chapter-specific extraction prompt."""
        user_prompt = load_prompt_template("concept_extraction_user.txt")
        guidance = load_prompt_template("embedding_text_guidance.txt")
        return "\n\n".join(
            [
                user_prompt,
                "Chapter metadata:",
                json.dumps(
                    {
                        "chapter_id": chapter["chapter_id"],
                        "class": int(chapter["class_level"]),
                        "subject": chapter["subject"],
                        "chapter_number": chapter["chapter_number"],
                        "chapter_title": chapter["chapter_title"],
                    },
                    ensure_ascii=True,
                ),
                guidance,
            ]
        )

    def build_system_instruction(self) -> str:
        """Load the system instruction for extraction."""
        return load_prompt_template("concept_extraction_system.txt")

    def cache_document(self, chapter: Dict[str, Any], pdf_path: Path) -> CachedDocument:
        """Create or reuse a Gemini cached document for a chapter PDF."""
        extraction_model = self.get_extraction_model()
        return self.client.cache_document(
            document_path=pdf_path,
            model_id=extraction_model.model_id,
            display_name=f"concept_index_chapter_{chapter['chapter_id']}",
        )

    def extract_concepts(
        self,
        chapter: Dict[str, Any],
        pdf_path: Path,
        cached_doc: Optional[CachedDocument] = None,
    ) -> Dict[str, Any]:
        """Extract the concept hierarchy JSON from a chapter PDF."""
        prompt = self.build_extraction_prompt(chapter)
        system_instruction = self.build_system_instruction()
        model_config = self.get_extraction_model()

        if cached_doc:
            response = self.client.generate_with_cache(
                model_config=model_config,
                prompt=prompt,
                cached_doc=cached_doc,
                system_instruction=system_instruction,
            )
        else:
            response = self.client.generate(
                model_config=model_config,
                prompt=prompt,
                document_path=pdf_path,
                system_instruction=system_instruction,
            )

        payload = _parse_json_response(response.text)
        if isinstance(payload, list):
            payload = {"nodes": payload}
        if not isinstance(payload, dict):
            raise ValueError("Gemini extraction response must be a JSON object or array.")
        if "nodes" not in payload or not isinstance(payload["nodes"], list):
            raise ValueError("Gemini extraction response must include a top-level 'nodes' array.")
        return payload

    def normalize_nodes(
        self,
        chapter: Dict[str, Any],
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Normalize and validate extracted concept nodes."""
        nodes: List[Dict[str, Any]] = []
        resolved_paths = self._resolve_node_paths(raw_payload.get("nodes", []))

        for index, item in enumerate(raw_payload.get("nodes", []), start=1):
            raw_node_key = self._require_text(item.get("node_key"), "node_key", f"node_{index}")
            parent_key = self._clean_optional_text(item.get("parent_node_key"))
            node_key = resolved_paths[raw_node_key]
            parent_path = resolved_paths[parent_key] if parent_key else None

            content_type = item["content_type"].strip()
            if content_type not in VALID_CONTENT_TYPES:
                raise ValueError(f"Unsupported content_type '{content_type}' for node {node_key}.")

            embedding_text = self._require_text(item.get("embedding_text"), "embedding_text", node_key)
            description = self._clean_optional_text(item.get("description"))
            formulas_value = item.get("key_formulas")
            key_formulas = self._normalize_formula_field(formulas_value)
            solved_example = self._clean_optional_text(item.get("ncert_solved_example"))
            has_figure = bool(item.get("has_figure", False))

            if has_figure and "figure" not in embedding_text.lower() and "diagram" not in embedding_text.lower():
                embedding_text = (
                    f"{embedding_text} The figure or diagram for this concept should be described in plain English."
                ).strip()

            chunk_text = self._build_chunk_text(
                concept_title=self._require_text(item.get("concept_title"), "concept_title", node_key),
                description=description,
                embedding_text=embedding_text,
                ncert_solved_example=solved_example,
                explicit_chunk=self._clean_optional_text(item.get("chunk_text")),
            )

            chunk_index = item.get("chunk_index", index)
            if not isinstance(chunk_index, int):
                raise ValueError(f"chunk_index must be an integer for node {node_key}.")

            nodes.append(
                {
                    "chapter_id": chapter["chapter_id"],
                    "path": node_key,
                    "parent_path": parent_path,
                    "concept_title": self._require_text(item.get("concept_title"), "concept_title", node_key),
                    "description": description,
                    "key_formulas": key_formulas,
                    "embedding_text": embedding_text,
                    "ncert_solved_example": solved_example,
                    "content_type": content_type,
                    "chunk_text": chunk_text,
                    "chunk_index": chunk_index,
                    "has_figure": has_figure,
                    "figure_url": None,
                    "class": int(chapter["class_level"]),
                    "subject": str(chapter["subject"]),
                }
            )

        self._assert_parent_paths_exist(nodes)
        self._assert_paths_follow_hierarchy(nodes)
        self._assert_acyclic(nodes)
        return sorted(nodes, key=lambda node: (node["path"].count("."), node["path"]))

    def build_embed_text(self, chapter: Dict[str, Any], node: Dict[str, Any]) -> str:
        """Build the exact composite string used for hashing and embedding."""
        return "\n".join(
            filter(
                None,
                [
                    f"Subject: {chapter['subject']}",
                    f"Chapter: {chapter['chapter_title']}",
                    f"Concept: {node['concept_title']}",
                    f"Description: {node.get('description')}",
                    f"Semantic description: {node['embedding_text']}",
                    f"Solved example: {node.get('ncert_solved_example')}",
                ],
            )
        )

    def build_embed_hash(self, chapter: Dict[str, Any], node: Dict[str, Any]) -> str:
        """Hash the exact composite string that is sent to the embedding model."""
        embed_text = self.build_embed_text(chapter, node)
        return hashlib.sha256(embed_text.encode("utf-8")).hexdigest()

    def embed_text(
        self,
        text: str,
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        output_dimensionality: int = 768,
        model: str = "text-embedding-004",
    ) -> List[float]:
        """Create an embedding using a regional Vertex AI client.

        Uses self._embed_client (us-central1 by default) rather than the
        shared extraction client because text-embedding-004 is not available
        in the 'global' Vertex AI location.
        """
        def _api_call() -> Any:
            return self._embed_client.models.embed_content(
                model=model,
                contents=text,
                config=_genai_types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=output_dimensionality,
                ),
            )

        response = self.client._retry_with_backoff(_api_call)
        values = self._extract_embedding_values(response)
        if len(values) != output_dimensionality:
            raise ValueError(
                f"Expected embedding dimension {output_dimensionality}, got {len(values)}."
            )
        return values

    def embed_texts_batch(
        self,
        texts: List[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        output_dimensionality: int = 768,
        model: str = "text-embedding-004",
        batch_size: int = 20,
    ) -> List[List[float]]:
        """Embed multiple texts with batched Vertex AI calls.

        Splits `texts` into chunks of `batch_size` and sends each chunk as a
        single `embed_content` call (Vertex AI supports list-valued `contents`).
        Returns a flat list of vectors in the same order as `texts`.
        """
        all_vectors: List[List[float]] = []
        config = _genai_types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=output_dimensionality,
        )
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            def _api_call(b: List[str] = batch) -> Any:
                return self._embed_client.models.embed_content(
                    model=model,
                    contents=b,
                    config=config,
                )

            response = self.client._retry_with_backoff(_api_call)
            for emb in response.embeddings:
                values = list(emb.values)
                if len(values) != output_dimensionality:
                    raise ValueError(
                        f"Expected embedding dimension {output_dimensionality}, got {len(values)}."
                    )
                all_vectors.append(values)

        return all_vectors

    def serialize_cached_doc(self, cached_doc: CachedDocument) -> Dict[str, Any]:
        """Serialize Gemini cache metadata into checkpoint-friendly JSON."""
        return {
            "cache_name": cached_doc.cache_name,
            "display_name": cached_doc.display_name,
            "file_uri": cached_doc.file_uri,
            "created_at": cached_doc.created_at.isoformat(),
            "expires_at": cached_doc.expires_at.isoformat(),
            "valid": not cached_doc.is_expired,
        }

    def restore_cached_doc(self, payload: Dict[str, Any]) -> CachedDocument:
        """Rebuild a CachedDocument from checkpoint JSON."""
        from datetime import datetime

        return CachedDocument(
            cache_name=payload["cache_name"],
            display_name=payload["display_name"],
            file_uri=payload["file_uri"],
            created_at=datetime.fromisoformat(payload["created_at"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
        )

    def _extract_embedding_values(self, response: Any) -> List[float]:
        """Extract embedding values from Gemini SDK responses across shapes."""
        if hasattr(response, "embeddings") and response.embeddings:
            first = response.embeddings[0]
            if hasattr(first, "values"):
                return list(first.values)
            if isinstance(first, dict) and "values" in first:
                return list(first["values"])

        if hasattr(response, "embedding") and response.embedding:
            embedding = response.embedding
            if hasattr(embedding, "values"):
                return list(embedding.values)
            if isinstance(embedding, dict) and "values" in embedding:
                return list(embedding["values"])

        raise ValueError("Could not extract embedding values from Gemini response.")

    def _resolve_node_paths(self, items: List[Dict[str, Any]]) -> Dict[str, str]:
        """Resolve raw node keys into valid dotted ltree paths using parent relationships when needed."""
        items_by_key: Dict[str, Dict[str, Any]] = {}
        for index, item in enumerate(items, start=1):
            raw_key = self._require_text(item.get("node_key"), "node_key", f"node_{index}")
            if raw_key in items_by_key:
                raise ValueError(f"Duplicate node_key '{raw_key}' in Gemini extraction response.")
            items_by_key[raw_key] = item

        resolved: Dict[str, str] = {}
        resolving: Dict[str, bool] = {}

        def resolve(raw_key: str) -> str:
            if raw_key in resolved:
                return resolved[raw_key]
            if raw_key not in items_by_key:
                raise ValueError(f"parent_node_key '{raw_key}' does not reference an existing node_key.")
            if resolving.get(raw_key):
                raise ValueError(f"Cycle detected while resolving node_key '{raw_key}'.")

            resolving[raw_key] = True
            item = items_by_key[raw_key]
            raw_parent_key = self._clean_optional_text(item.get("parent_node_key"))

            if raw_parent_key:
                parent_path = resolve(raw_parent_key)
                normalized_key: Optional[str] = None
                if "." in raw_key:
                    try:
                        normalized_key = self._normalize_path(raw_key)
                    except ValueError:
                        normalized_key = None

                if normalized_key and normalized_key.startswith(f"{parent_path}."):
                    path = normalized_key
                else:
                    child_label = self._derive_child_label_from_flat_key(raw_key, raw_parent_key)
                    path = self._normalize_path(f"{parent_path}.{child_label}")
            else:
                path = self._normalize_path(raw_key)

            resolved[raw_key] = path
            resolving.pop(raw_key, None)
            return path

        for raw_key in items_by_key:
            resolve(raw_key)

        return resolved

    def _derive_child_label_from_flat_key(self, raw_key: str, raw_parent_key: str) -> str:
        """Derive a child ltree label when Gemini flattens hierarchy levels with underscores."""
        raw_segments = [segment.strip() for segment in raw_key.replace(".", "_").split("_") if segment.strip()]
        parent_segments = [
            segment.strip()
            for segment in raw_parent_key.replace(".", "_").split("_")
            if segment.strip()
        ]

        common_length = 0
        while (
            common_length < len(raw_segments)
            and common_length < len(parent_segments)
            and raw_segments[common_length] == parent_segments[common_length]
        ):
            common_length += 1

        child_segments = raw_segments[common_length:]
        if not child_segments:
            raise ValueError(
                f"Could not derive a child path label from node_key '{raw_key}' and "
                f"parent_node_key '{raw_parent_key}'."
            )

        child_label = "_".join(child_segments)
        if not LTREE_LABEL_RE.match(child_label):
            raise ValueError(
                f"Derived child label '{child_label}' from node_key '{raw_key}' is not ltree-safe."
            )
        return child_label

    def _normalize_path(self, value: str) -> str:
        """Normalize a node key into a valid ltree-style dotted path."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("node_key must be a non-empty string.")

        labels = [label.strip() for label in value.split(".")]
        for label in labels:
            if not LTREE_LABEL_RE.match(label):
                raise ValueError(
                    f"Invalid node_key label '{label}'. Expected regex [A-Za-z0-9_]+."
                )
        return ".".join(labels)

    def _require_text(self, value: Any, field_name: str, node_key: str) -> str:
        """Require a non-empty string field."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Node {node_key} is missing required field '{field_name}'.")
        return value.strip()

    def _clean_optional_text(self, value: Any) -> Optional[str]:
        """Normalize optional text fields."""
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None

    def _normalize_formula_field(self, value: Any) -> Optional[str]:
        """Normalize key_formulas into a single DB-friendly string field.

        Gemini may return:
          - null               → None
          - a JSON array       → one formula per line
          - a single string    → kept as-is
          - a string with LaTeX line-break separators (\\) → split into one per line
        """
        if value is None:
            return None
        if isinstance(value, list):
            formulas = [str(item).strip() for item in value if str(item).strip()]
            return "\n".join(formulas) or None
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            # LaTeX uses \\ as a line-break; Gemini sometimes concatenates multiple
            # equations with this separator instead of returning an array.
            if "\\\\" in cleaned:
                parts = [p.strip() for p in cleaned.split("\\\\") if p.strip()]
                return "\n".join(parts) or None
            return cleaned
        return str(value).strip() or None

    def _build_chunk_text(
        self,
        *,
        concept_title: str,
        description: Optional[str],
        embedding_text: str,
        ncert_solved_example: Optional[str],
        explicit_chunk: Optional[str],
    ) -> str:
        """Build chunk_text or reuse the extracted one when present."""
        if explicit_chunk:
            return explicit_chunk

        return "\n".join(
            filter(
                None,
                [
                    f"Concept: {concept_title}",
                    description,
                    embedding_text,
                    ncert_solved_example,
                ],
            )
        )

    def _assert_parent_paths_exist(self, nodes: List[Dict[str, Any]]) -> None:
        """Ensure every non-root node references an existing parent path."""
        paths = {node["path"] for node in nodes}
        for node in nodes:
            parent_path = node["parent_path"]
            if parent_path and parent_path not in paths:
                raise ValueError(
                    f"Node {node['path']} references missing parent path {parent_path}."
                )

    def _assert_paths_follow_hierarchy(self, nodes: List[Dict[str, Any]]) -> None:
        """Ensure each child path is a dotted descendant of its parent path."""
        for node in nodes:
            parent_path = node["parent_path"]
            if parent_path and not node["path"].startswith(f"{parent_path}."):
                raise ValueError(
                    f"Node path {node['path']} is not a descendant of parent path {parent_path}."
                )

    def _assert_acyclic(self, nodes: List[Dict[str, Any]]) -> None:
        """Detect cycles in the extracted parent-path graph."""
        node_map = {node["path"]: node for node in nodes}
        visited: Dict[str, str] = {}

        def visit(path: str) -> None:
            state = visited.get(path)
            if state == "visiting":
                raise ValueError(f"Cycle detected at node {path}.")
            if state == "done":
                return

            visited[path] = "visiting"
            parent_path = node_map[path]["parent_path"]
            if parent_path:
                visit(parent_path)
            visited[path] = "done"

        for path in node_map:
            visit(path)
