"""Main pipeline entrypoint for Module M2: NCERT Concept Index."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from db_writer import ConceptIndexDBWriter
from gemini_extractor import ConceptGeminiExtractor, download_pdf


PIPELINE_DIR = Path(__file__).resolve().parent
CHECKPOINT_DIR = PIPELINE_DIR / "checkpoints"
LOG_DIR = PIPELINE_DIR / "logs"
PROMPTS_DIR = PIPELINE_DIR / "prompts"
TEMP_DIR = PIPELINE_DIR / "temp"

LOGGER = logging.getLogger(__name__)


def ensure_runtime_dirs() -> None:
    """Create runtime directories needed by the pipeline."""
    for path in (CHECKPOINT_DIR, LOG_DIR, PROMPTS_DIR, TEMP_DIR):
        path.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    """Configure console and file logging."""
    ensure_runtime_dirs()
    log_path = LOG_DIR / f"concept_index_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for parameterized chapter runs."""
    parser = argparse.ArgumentParser(description="Build the NCERT Concept Index (Module M2).")
    parser.add_argument(
        "--chapter-ids",
        help="Comma-separated chapter IDs to process, e.g. 5,12,23",
    )
    parser.add_argument(
        "--subject",
        help="Only process one subject, e.g. physics",
    )
    parser.add_argument(
        "--class",
        dest="class_level",
        type=int,
        help="Only process one class, e.g. 11",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and validate only; do not write hierarchy or embeddings to the DB.",
    )
    return parser.parse_args()


def parse_chapter_ids(value: Optional[str]) -> Optional[List[int]]:
    """Parse comma-separated chapter IDs from the CLI."""
    if not value:
        return None
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def checkpoint_path(chapter_id: int) -> Path:
    """Return the checkpoint path for a chapter."""
    return CHECKPOINT_DIR / f"chapter_{chapter_id}.json"


def new_checkpoint(chapter: Dict[str, Any]) -> Dict[str, Any]:
    """Create the initial checkpoint structure for a chapter."""
    return {
        "chapter": {
            "chapter_id": chapter["chapter_id"],
            "class": int(chapter["class_level"]),
            "subject": chapter["subject"],
            "chapter_number": chapter["chapter_number"],
            "chapter_title": chapter["chapter_title"],
        },
        "stages": {
            "pdf_acquired": False,
            "pdf_cached": False,
            "concepts_extracted": False,
            "concepts_normalized": False,
            "hierarchy_written": False,
            "embeddings_written": False,
            "completed": False,
        },
        "pdf": {},
        "cache": {},
        "raw_extraction": None,
        "nodes": {},
        "errors": [],
        "summary": {},
        "updated_at": utcnow(),
    }


def load_checkpoint(chapter: Dict[str, Any], db_writer: ConceptIndexDBWriter) -> Dict[str, Any]:
    """Load a checkpoint or rebuild minimal state from the DB when possible."""
    path = checkpoint_path(chapter["chapter_id"])
    if path.exists():
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        checkpoint.setdefault("nodes", {})
        checkpoint.setdefault("errors", [])
        checkpoint.setdefault("summary", {})
        return checkpoint

    checkpoint = new_checkpoint(chapter)
    existing_nodes = db_writer.rebuild_checkpoint_nodes(chapter["chapter_id"])
    if existing_nodes:
        checkpoint["nodes"] = existing_nodes
    return checkpoint


def save_checkpoint(checkpoint: Dict[str, Any]) -> None:
    """Persist checkpoint JSON to disk."""
    checkpoint["updated_at"] = utcnow()
    path = checkpoint_path(int(checkpoint["chapter"]["chapter_id"]))
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def save_checkpoint_nonfatal(checkpoint: Dict[str, Any]) -> None:
    """Persist checkpoint state without aborting the pipeline on disk-write failures."""
    try:
        save_checkpoint(checkpoint)
    except Exception as exc:
        LOGGER.warning("Checkpoint save failed (non-fatal): %s", exc)


def register_nodes(checkpoint: Dict[str, Any], nodes: List[Dict[str, Any]]) -> None:
    """Ensure every normalized node has a checkpoint entry."""
    for node in nodes:
        state = checkpoint["nodes"].setdefault(
            node["path"],
            {
                "parent_path": node["parent_path"],
                "concept_id": None,
                "hierarchy_written": False,
                "embedding_written": False,
                "figure_url": None,
                "has_figure": node["has_figure"],
                "embed_hash": None,
            },
        )
        state["parent_path"] = node["parent_path"]
        state["has_figure"] = node["has_figure"]


def apply_figure_state(checkpoint: Dict[str, Any], nodes: List[Dict[str, Any]]) -> None:
    """Persist figure handling state without uploading or embedding images."""
    for node in nodes:
        checkpoint["nodes"][node["path"]]["has_figure"] = node["has_figure"]
        checkpoint["nodes"][node["path"]]["figure_url"] = None
        node["figure_url"] = None


def process_chapter(
    chapter: Dict[str, Any],
    *,
    extractor: ConceptGeminiExtractor,
    db_writer: ConceptIndexDBWriter,
    dry_run: bool,
) -> Dict[str, Any]:
    """Process one chapter through extraction, validation, and optional DB writes."""
    checkpoint = load_checkpoint(chapter, db_writer)
    if checkpoint["stages"].get("completed"):
        LOGGER.info("Skipping chapter %s; checkpoint already complete.", chapter["chapter_id"])
        return checkpoint

    pdf_metadata = checkpoint.get("pdf") or {}
    pdf_path = Path(pdf_metadata.get("local_path", TEMP_DIR / f"chapter_{chapter['chapter_id']}.pdf"))
    if not checkpoint["stages"].get("pdf_acquired"):
        pdf_metadata = download_pdf(chapter["pdf_file_url"], pdf_path)
        checkpoint["pdf"] = pdf_metadata
        checkpoint["stages"]["pdf_acquired"] = True
        save_checkpoint_nonfatal(checkpoint)

    cached_doc = None
    if checkpoint["stages"].get("pdf_cached") and checkpoint.get("cache"):
        cached_doc = extractor.restore_cached_doc(checkpoint["cache"])
    else:
        cached_doc = extractor.cache_document(chapter, Path(checkpoint["pdf"]["local_path"]))
        checkpoint["cache"] = extractor.serialize_cached_doc(cached_doc)
        checkpoint["stages"]["pdf_cached"] = True
        save_checkpoint_nonfatal(checkpoint)

    if checkpoint["stages"].get("concepts_extracted") and checkpoint.get("raw_extraction"):
        raw_extraction = checkpoint["raw_extraction"]
    else:
        raw_extraction = extractor.extract_concepts(
            chapter=chapter,
            pdf_path=Path(checkpoint["pdf"]["local_path"]),
            cached_doc=cached_doc,
        )
        checkpoint["raw_extraction"] = raw_extraction
        checkpoint["stages"]["concepts_extracted"] = True
        save_checkpoint_nonfatal(checkpoint)

    nodes = extractor.normalize_nodes(chapter, raw_extraction)
    register_nodes(checkpoint, nodes)
    apply_figure_state(checkpoint, nodes)
    checkpoint["stages"]["concepts_normalized"] = True
    save_checkpoint_nonfatal(checkpoint)

    if dry_run:
        checkpoint["summary"] = {
            "mode": "dry-run",
            "node_count": len(nodes),
            "chapter_id": chapter["chapter_id"],
        }
        save_checkpoint_nonfatal(checkpoint)
        LOGGER.info("Dry run complete for chapter %s (%s nodes).", chapter["chapter_id"], len(nodes))
        return checkpoint

    # --- Hierarchy writes (single connection for entire chapter) ---
    initial_path_to_id = {
        path: state["concept_id"]
        for path, state in checkpoint["nodes"].items()
        if state.get("concept_id")
    }
    pending_hier = [
        {
            "chapter_id": node["chapter_id"],
            "path": node["path"],
            "parent_path": node["parent_path"],
            "concept_title": node["concept_title"],
            "description": node["description"],
            "key_formulas": node["key_formulas"],
            "embedding_text": node["embedding_text"],
            "ncert_solved_example": node["ncert_solved_example"],
            "content_type": node["content_type"],
            "figure_url": node["figure_url"],
            "chunk_text": node["chunk_text"],
            "chunk_index": node["chunk_index"],
            "class_value": node["class"],
            "subject": node["subject"],
        }
        for node in nodes
        if not (
            checkpoint["nodes"][node["path"]].get("hierarchy_written")
            and checkpoint["nodes"][node["path"]].get("concept_id")
        )
    ]

    if pending_hier:
        LOGGER.info("Writing %d hierarchy rows for chapter %s.", len(pending_hier), chapter["chapter_id"])
        new_ids = db_writer.bulk_upsert_hierarchy_rows(
            pending_hier, initial_path_to_id=initial_path_to_id
        )
        for path, concept_id in new_ids.items():
            state = checkpoint["nodes"][path]
            state["concept_id"] = concept_id
            state["hierarchy_written"] = True
        save_checkpoint_nonfatal(checkpoint)

    checkpoint["stages"]["hierarchy_written"] = True
    save_checkpoint_nonfatal(checkpoint)

    # --- Embedding writes (batched API calls + single connection per batch) ---
    EMBED_BATCH = 20
    pending_emb = [
        (node, extractor.build_embed_text(chapter, node), extractor.build_embed_hash(chapter, node))
        for node in nodes
        if checkpoint["nodes"][node["path"]].get("concept_id")
        and not (
            checkpoint["nodes"][node["path"]].get("embedding_written")
            and checkpoint["nodes"][node["path"]].get("embed_hash")
            == extractor.build_embed_hash(chapter, node)
        )
    ]

    if pending_emb:
        LOGGER.info("Embedding %d nodes for chapter %s.", len(pending_emb), chapter["chapter_id"])
        for batch_start in range(0, len(pending_emb), EMBED_BATCH):
            batch = pending_emb[batch_start : batch_start + EMBED_BATCH]
            texts = [t for _, t, _ in batch]
            vectors = extractor.embed_texts_batch(
                texts,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
                model="text-embedding-004",
                batch_size=EMBED_BATCH,
            )
            db_writer.bulk_upsert_embedding_rows([
                {"concept_id": checkpoint["nodes"][node["path"]]["concept_id"], "embedding": vec}
                for (node, _, _), vec in zip(batch, vectors)
            ])
            for (node, _, embed_hash), _ in zip(batch, vectors):
                state = checkpoint["nodes"][node["path"]]
                state["embed_hash"] = embed_hash
                state["embedding_written"] = True
            save_checkpoint_nonfatal(checkpoint)

    checkpoint["stages"]["embeddings_written"] = True
    checkpoint["stages"]["completed"] = True
    checkpoint["summary"] = {
        "mode": "full-run",
        "node_count": len(nodes),
        "chapter_id": chapter["chapter_id"],
    }
    save_checkpoint_nonfatal(checkpoint)
    LOGGER.info("Completed chapter %s (%s nodes).", chapter["chapter_id"], len(nodes))
    return checkpoint


def utcnow() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    """CLI entrypoint."""
    ensure_runtime_dirs()
    configure_logging()
    args = parse_args()

    db_writer = ConceptIndexDBWriter()
    extractor = ConceptGeminiExtractor()

    chapters = db_writer.fetch_chapters(
        chapter_ids=parse_chapter_ids(args.chapter_ids),
        subject=args.subject,
        class_level=args.class_level,
    )

    if not chapters:
        LOGGER.warning("No chapters matched the provided filters.")
        return

    for chapter in chapters:
        try:
            process_chapter(
                chapter,
                extractor=extractor,
                db_writer=db_writer,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            LOGGER.exception(
                "Failed processing chapter %s (%s).",
                chapter["chapter_id"],
                chapter["chapter_title"],
            )
            checkpoint = load_checkpoint(chapter, db_writer)
            checkpoint["errors"].append(
                {
                    "timestamp": utcnow(),
                    "message": str(exc),
                }
            )
            save_checkpoint_nonfatal(checkpoint)
            raise


if __name__ == "__main__":
    main()
