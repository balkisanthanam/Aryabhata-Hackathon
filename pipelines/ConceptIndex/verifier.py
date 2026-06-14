"""Post-chapter consistency verifier for the NCERT Concept Index pipeline.

Usage (standalone):
    python verifier.py --chapter-id 66

Or import and call:
    from verifier import verify_chapter
    result = verify_chapter(chapter_id, checkpoint, db_writer)
    if not result.is_ok:
        print(result.failed)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from db_writer import ConceptIndexDBWriter

LOGGER = logging.getLogger(__name__)
CHECKPOINT_DIR = PIPELINE_DIR / "checkpoints"

MIN_EXPECTED_NODES = 5
MAX_EXPECTED_NODES = 200
EXPECTED_EMBEDDING_DIMS = 768


@dataclass
class VerificationResult:
    chapter_id: int
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return len(self.failed) == 0

    def summary_line(self) -> str:
        status = "PASS" if self.is_ok else "FAIL"
        warn_suffix = f" ({len(self.warnings)} warnings)" if self.warnings else ""
        total = len(self.passed) + len(self.failed)
        return f"ch{self.chapter_id}: {status} — {len(self.passed)}/{total} checks passed{warn_suffix}"


def _check_tier1(
    checkpoint: Dict[str, Any],
    result: VerificationResult,
) -> int:
    """Tier 1 — checkpoint-only checks. Returns node count (0 on hard failure)."""
    nodes = checkpoint.get("nodes", {})

    if not nodes:
        result.failed.append("Tier1-NodeCount: checkpoint has no nodes")
        return 0

    node_count = len(nodes)
    result.passed.append(f"Tier1-NodeCount: {node_count} nodes present in checkpoint")

    missing_hier = [p for p, s in nodes.items() if not s.get("hierarchy_written")]
    if missing_hier:
        result.failed.append(
            f"Tier1-HierarchyWritten: {len(missing_hier)} node(s) not written "
            f"({', '.join(missing_hier[:3])}{'...' if len(missing_hier) > 3 else ''})"
        )
    else:
        result.passed.append("Tier1-HierarchyWritten: all nodes marked hierarchy_written")

    missing_ids = [p for p, s in nodes.items() if not s.get("concept_id")]
    if missing_ids:
        result.failed.append(
            f"Tier1-ConceptIds: {len(missing_ids)} node(s) missing concept_id "
            f"({', '.join(missing_ids[:3])}{'...' if len(missing_ids) > 3 else ''})"
        )
    else:
        result.passed.append("Tier1-ConceptIds: all nodes have concept_id")

    missing_emb = [p for p, s in nodes.items() if not s.get("embedding_written")]
    if missing_emb:
        result.failed.append(
            f"Tier1-EmbeddingWritten: {len(missing_emb)} node(s) not embedded "
            f"({', '.join(missing_emb[:3])}{'...' if len(missing_emb) > 3 else ''})"
        )
    else:
        result.passed.append("Tier1-EmbeddingWritten: all nodes marked embedding_written")

    return node_count


def _check_tier2_consistency(
    chapter_id: int,
    expected_count: int,
    db_writer: ConceptIndexDBWriter,
    result: VerificationResult,
) -> Optional[int]:
    """Tier 2 — DB consistency checks. Returns DB hier_count or None on query failure."""

    # --- Bulk counts ---
    counts_sql = """
        SELECT
            (SELECT COUNT(*)
             FROM ncert_concept_hierarchy
             WHERE chapter_id = %s) AS hier_count,

            (SELECT COUNT(*)
             FROM ncert_concept_embeddings e
             JOIN ncert_concept_hierarchy h ON h.id = e.concept_id
             WHERE h.chapter_id = %s) AS emb_count,

            (SELECT COUNT(*)
             FROM ncert_concept_hierarchy
             WHERE chapter_id = %s AND path IS NULL) AS null_paths,

            (SELECT COUNT(*) - COUNT(DISTINCT path::text)
             FROM ncert_concept_hierarchy
             WHERE chapter_id = %s) AS dup_paths,

            (SELECT COUNT(*)
             FROM ncert_concept_hierarchy
             WHERE chapter_id = %s
               AND parent_id IS NULL
               AND path::text LIKE '%%.%%') AS orphan_non_root
    """

    try:
        row = db_writer.fetch_one(
            counts_sql,
            [chapter_id, chapter_id, chapter_id, chapter_id, chapter_id],
        )
    except Exception as exc:
        result.failed.append(f"Tier2-DBQuery: could not query DB: {exc}")
        return None

    hier_count = row["hier_count"]
    emb_count = row["emb_count"]
    null_paths = row["null_paths"]
    dup_paths = row["dup_paths"]
    orphan_non_root = row["orphan_non_root"]

    # Check 1: hierarchy row count matches checkpoint
    if hier_count == expected_count:
        result.passed.append(
            f"Tier2-HierCount: DB={hier_count} rows matches checkpoint={expected_count}"
        )
    else:
        result.failed.append(
            f"Tier2-HierCount: DB={hier_count} rows but checkpoint expects {expected_count}"
        )

    # Check 2: embedding count matches hierarchy count
    if emb_count == hier_count:
        result.passed.append(f"Tier2-EmbCount: {emb_count} embeddings match {hier_count} hierarchy rows")
    else:
        result.failed.append(
            f"Tier2-EmbCount: {emb_count} embeddings != {hier_count} hierarchy rows"
        )

    # Check 3: no null ltree paths
    if null_paths == 0:
        result.passed.append("Tier2-NoNullPaths: all hierarchy rows have a non-null path")
    else:
        result.failed.append(f"Tier2-NoNullPaths: {null_paths} row(s) have NULL path")

    # Check 4: no duplicate (chapter_id, path) pairs
    if dup_paths == 0:
        result.passed.append("Tier2-NoDuplicatePaths: no duplicate paths for this chapter")
    else:
        result.failed.append(f"Tier2-NoDuplicatePaths: {dup_paths} duplicate path row(s)")

    # Check 5: non-root nodes should have parent_id
    if orphan_non_root == 0:
        result.passed.append("Tier2-OrphanNonRoot: all non-root nodes have parent_id")
    else:
        result.failed.append(
            f"Tier2-OrphanNonRoot: {orphan_non_root} non-root node(s) have NULL parent_id"
        )

    # Check 6: all parent_ids actually exist in this chapter
    dangling_sql = """
        SELECT COUNT(*) AS dangling
        FROM ncert_concept_hierarchy child
        LEFT JOIN ncert_concept_hierarchy parent ON parent.id = child.parent_id
        WHERE child.chapter_id = %s
          AND child.parent_id IS NOT NULL
          AND parent.id IS NULL
    """
    try:
        row2 = db_writer.fetch_one(dangling_sql, [chapter_id])
        dangling = row2["dangling"]
        if dangling == 0:
            result.passed.append("Tier2-DanglingParents: all parent_ids resolve to real rows")
        else:
            result.failed.append(f"Tier2-DanglingParents: {dangling} node(s) have non-existent parent_id")
    except Exception as exc:
        result.warnings.append(f"Tier2-DanglingParents: query failed ({exc})")

    # Check 7: embedding dimensions are correct
    dim_sql = """
        SELECT COUNT(*) AS wrong_dim
        FROM ncert_concept_embeddings e
        JOIN ncert_concept_hierarchy h ON h.id = e.concept_id
        WHERE h.chapter_id = %s
          AND vector_dims(e.embedding) != %s
    """
    try:
        row3 = db_writer.fetch_one(dim_sql, [chapter_id, EXPECTED_EMBEDDING_DIMS])
        wrong_dim = row3["wrong_dim"]
        if wrong_dim == 0:
            result.passed.append(
                f"Tier2-EmbeddingDims: all embeddings are {EXPECTED_EMBEDDING_DIMS}-dimensional"
            )
        else:
            result.failed.append(
                f"Tier2-EmbeddingDims: {wrong_dim} embedding(s) have wrong dimensions "
                f"(expected {EXPECTED_EMBEDDING_DIMS})"
            )
    except Exception as exc:
        result.warnings.append(f"Tier2-EmbeddingDims: query failed ({exc})")

    return hier_count


def _check_tier2_data_quality(
    chapter_id: int,
    db_writer: ConceptIndexDBWriter,
    node_count: int,
    result: VerificationResult,
) -> None:
    """Tier 2 — data quality checks (WARN only, never FAIL)."""

    quality_sql = """
        SELECT
            COUNT(CASE WHEN embedding_text IS NULL OR embedding_text = '' THEN 1 END) AS empty_embed_text,
            COUNT(CASE WHEN concept_title IS NULL OR concept_title = '' THEN 1 END) AS empty_titles
        FROM ncert_concept_hierarchy
        WHERE chapter_id = %s
    """
    try:
        row = db_writer.fetch_one(quality_sql, [chapter_id])
        if row["empty_embed_text"] > 0:
            result.warnings.append(
                f"DataQuality-EmbeddingText: {row['empty_embed_text']} node(s) have empty embedding_text"
            )
        if row["empty_titles"] > 0:
            result.warnings.append(
                f"DataQuality-ConceptTitle: {row['empty_titles']} node(s) have empty concept_title"
            )
    except Exception as exc:
        result.warnings.append(f"DataQuality-TextFields: query failed ({exc})")

    if node_count < MIN_EXPECTED_NODES:
        result.warnings.append(
            f"DataQuality-NodeCount: {node_count} nodes is suspiciously low "
            f"(expected >= {MIN_EXPECTED_NODES})"
        )
    elif node_count > MAX_EXPECTED_NODES:
        result.warnings.append(
            f"DataQuality-NodeCount: {node_count} nodes is unusually high "
            f"(expected <= {MAX_EXPECTED_NODES})"
        )


def verify_chapter(
    chapter_id: int,
    checkpoint: Dict[str, Any],
    db_writer: Optional[ConceptIndexDBWriter] = None,
    *,
    skip_db: bool = False,
) -> VerificationResult:
    """Run all verification checks for one chapter.

    Args:
        chapter_id: The DB chapter ID.
        checkpoint: The loaded checkpoint dict for this chapter.
        db_writer: Active DB writer. Required unless skip_db=True.
        skip_db: Only run Tier 1 (checkpoint) checks.

    Returns:
        VerificationResult with passed/failed/warnings lists.
    """
    result = VerificationResult(chapter_id=chapter_id)
    node_count = _check_tier1(checkpoint, result)

    if skip_db or db_writer is None:
        return result

    if node_count == 0:
        result.failed.append("Tier2-Skipped: skipping DB checks because node_count == 0")
        return result

    hier_count = _check_tier2_consistency(chapter_id, node_count, db_writer, result)
    _check_tier2_data_quality(chapter_id, db_writer, node_count, result)

    return result


def _load_checkpoint(chapter_id: int) -> Optional[Dict[str, Any]]:
    path = CHECKPOINT_DIR / f"chapter_{chapter_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """Standalone CLI for verifying a single chapter."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Verify a single chapter's concept index data.")
    parser.add_argument("--chapter-id", type=int, required=True, help="Chapter ID to verify")
    parser.add_argument("--skip-db", action="store_true", help="Only run checkpoint checks, no DB queries")
    args = parser.parse_args()

    checkpoint = _load_checkpoint(args.chapter_id)
    if checkpoint is None:
        LOGGER.error("No checkpoint found for chapter %s.", args.chapter_id)
        sys.exit(1)

    db_writer = None if args.skip_db else ConceptIndexDBWriter()
    result = verify_chapter(args.chapter_id, checkpoint, db_writer, skip_db=args.skip_db)

    print(f"\n{result.summary_line()}\n")

    if result.passed:
        print("PASSED:")
        for p in result.passed:
            print(f"  ✓  {p}")

    if result.failed:
        print("\nFAILED:")
        for f in result.failed:
            print(f"  ✗  {f}")

    if result.warnings:
        print("\nWARNINGS:")
        for w in result.warnings:
            print(f"  ⚠  {w}")

    sys.exit(0 if result.is_ok else 1)


if __name__ == "__main__":
    main()
