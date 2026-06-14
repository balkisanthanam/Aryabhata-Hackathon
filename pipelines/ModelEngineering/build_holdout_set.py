"""
build_holdout_set.py — Phase A of the M3 Tuning Loop.

Constructs a frozen 100-record held-out evaluation set spanning NCERT and JEE,
balanced ~17/17/16 per subject within each source, with deliberate figure-bearing
sampling and a reserved `never_distill` final-exam slice. Writes
`holdout_eval_set.json` next to this script.

Design contract (see `Design/Architecture/M3_TuningLoop_Plan.md`, Phase A):
- 50 JEE (from `jee_question_bank.review_status='PENDING'`, answer_key present)
- 50 NCERT (from `questiondata`; prefer `MATH_PASSED`, back-fill from `LEGACY`)
- Subjects balanced per source (Maths/Physics/Chemistry — NCERT uses 'Maths',
  JEE uses 'Mathematics'; canonicalized to 'Maths' in the output).
- `has_figure` tagged per record (true if any problem-attached image URL exists).
- ~35% figure-bearing target (Physics drives most of this naturally).
- ~20 records flagged `never_distill: true` — the final-exam slice excluded
  from any future distillation loop (loop-correctness — keeps the final
  ship/no-ship decision honest).
- Zero overlap with `APPROVED_GOLD` ids in either table (asserted defensively
  after SQL filtering).
- Reproducible via `--seed` (default 42) + deterministic SQL ORDER BY.

CLI:
    python build_holdout_set.py --jee 50 --ncert 50
    python build_holdout_set.py --force            # overwrite existing file
"""

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

# Path setup mirrors batch_evaluator.py / jsonl_exporter.py so the shared
# `JEEExtractionDBWriter` + `build_user_payload` imports just work.
cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
jee_dir = project_root / "pipelines" / "JEEAscentPipeline"
for p in (extraction_dir, jee_dir, cwd):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from db_writer import JEEExtractionDBWriter  # noqa: E402
from jsonl_exporter import build_user_payload  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("build_holdout")

# NCERT stores subject as 'Maths'; JEE stores it as 'Mathematics'. Collapse to
# one canonical bucket so per-subject metrics aggregate cleanly across sources.
SUBJECT_CANONICAL = {
    "Maths": "Maths",
    "Mathematics": "Maths",
    "Physics": "Physics",
    "Chemistry": "Chemistry",
}

# Base per-subject split summing to 50; scaled to actual targets via _scale_targets.
SUBJECT_SPLIT_BASE = {"Maths": 17, "Physics": 17, "Chemistry": 16}


# ---------------------------------------------------------------------------
# Image-URL extractors + figure-presence detectors
#
# IMPORTANT (2026-05-23): URL presence and figure presence are NOT the same.
# JEE extraction records `has_figure=true` for figure-dependent problems but
# never populates `figure_url` / `option_figure_urls` — those are deferred.
# Surveyed across all jee_question_bank rows: 100% have NULL `figure_url`,
# while ~18% have `has_figure=true`. See E2E plan "Known Gaps" section.
#
# Consequence for the holdout:
#   - `has_figure` (broad): use for figure-DEPENDENT classification — what the
#     model sees in production. Drives stratified sampling and the per-figure
#     breakdown in batch_evaluator.
#   - `image_urls_present` (strict): use to know whether we can actually inline
#     an image part at inference. Today: ~100% of NCERT figure rows, ~0% JEE.
#     Recorded per-record so the figure-dependent / image-inlined split can be
#     analyzed downstream.
# ---------------------------------------------------------------------------

def _extract_ncert_image_urls(content) -> list:
    """NCERT figure URLs live under `content.figure_info[*].url` (per db_client.py:343)."""
    if not isinstance(content, dict):
        return []
    urls = []
    fi = content.get("figure_info") or []
    if isinstance(fi, list):
        for entry in fi:
            if isinstance(entry, dict):
                u = entry.get("url")
                if u:
                    urls.append(u)
    return urls


def _extract_jee_image_urls(content) -> list:
    """JEE figure URLs (when present) sit at top-level. Survey shows the entire
    jee_question_bank table has NULL `figure_url` today — see Known Gaps."""
    if not isinstance(content, dict):
        return []
    urls = []
    if content.get("figure_url"):
        urls.append(content["figure_url"])
    opt_urls = content.get("option_figure_urls") or []
    if isinstance(opt_urls, list):
        urls.extend(u for u in opt_urls if u)
    return urls


def _ncert_has_figure(content) -> bool:
    """Figure-DEPENDENT classification (broad). True if extraction flagged a
    figure OR any figure_info entry exists, even with a NULL URL."""
    if not isinstance(content, dict):
        return False
    if content.get("has_figure"):
        return True
    fi = content.get("figure_info") or []
    if isinstance(fi, list) and any(isinstance(e, dict) for e in fi):
        return True
    return False


def _jee_has_figure(content) -> bool:
    """Figure-DEPENDENT classification (broad). The `has_figure` flag is the
    primary signal because `figure_url` extraction is deferred (Known Gaps)."""
    if not isinstance(content, dict):
        return False
    if content.get("has_figure"):
        return True
    if content.get("figure_url") or content.get("option_figure_urls"):
        return True
    return False


# ---------------------------------------------------------------------------
# Candidate-pool fetchers
# ---------------------------------------------------------------------------

def fetch_ncert_candidates(db: JEEExtractionDBWriter) -> list:
    """All NCERT rows eligible for the holdout: MATH_PASSED preferred, LEGACY back-fill.

    APPROVED_GOLD is excluded by the IN clause (defense in depth — the gold-overlap
    assertion at the end catches anything we missed).
    """
    query = """
        SELECT q.questionid, q.content, q.solution, q.answer_key, q.review_status,
               c.subject, c.class
        FROM questiondata q
        JOIN exercisedata e ON q.exerciseid = e.exerciseid
        JOIN chapterdata c ON e.chapterid = c.chapterid
        WHERE c.class IN ('11', '12')
          AND c.subject IN ('Maths', 'Physics', 'Chemistry')
          AND q.solution IS NOT NULL
          AND q.review_status IN ('MATH_PASSED', 'LEGACY')
        ORDER BY
          CASE q.review_status WHEN 'MATH_PASSED' THEN 0 WHEN 'LEGACY' THEN 1 END,
          q.questionid
    """
    rows = []
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if isinstance(row.get("content"), str):
                    try:
                        row["content"] = json.loads(row["content"])
                    except Exception:
                        row["content"] = {}
                rows.append(row)
    LOGGER.info(
        f"NCERT pool: {len(rows)} rows "
        f"(MATH_PASSED first, LEGACY back-fill, APPROVED_GOLD excluded)."
    )
    return rows


def fetch_jee_candidates(db: JEEExtractionDBWriter) -> list:
    """JEE PENDING rows with reliable answer keys (disjoint from the 102 APPROVED_GOLD)."""
    query = """
        SELECT q.id, q.question_content, q.solution, q.answer_key, q.subject, q.review_status
        FROM jee_question_bank q
        WHERE q.subject IN ('Mathematics', 'Physics', 'Chemistry')
          AND q.answer_key IS NOT NULL
          AND q.question_content IS NOT NULL
          AND q.review_status = 'PENDING'
        ORDER BY q.id
    """
    rows = []
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if isinstance(row.get("question_content"), str):
                    try:
                        row["question_content"] = json.loads(row["question_content"])
                    except Exception:
                        row["question_content"] = {}
                rows.append(row)
    LOGGER.info(
        f"JEE pool: {len(rows)} rows "
        f"(PENDING with answer_key, APPROVED_GOLD disjoint)."
    )
    return rows


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _scale_targets(base: dict, total: int) -> dict:
    """Scale a per-subject split (summing to anything) to exactly `total`."""
    base_sum = sum(base.values())
    scaled = {k: max(1, int(round(v * total / base_sum))) for k, v in base.items()}
    drift = total - sum(scaled.values())
    if drift:
        keys = sorted(scaled.keys())
        step = 1 if drift > 0 else -1
        i = 0
        while drift:
            scaled[keys[i % len(keys)]] += step
            drift -= step
            i += 1
    return scaled


def stratified_sample(
    candidates: list,
    get_subject,
    get_has_figure,
    target_per_subject: dict,
    target_figure_share: float,
    rng: random.Random,
) -> list:
    """Pick `sum(target_per_subject.values())` records, balanced by subject and tilted
    toward `target_figure_share` figure-bearing within each subject. Back-fills from
    the opposite figure-bucket if a pool is short."""
    by_subj_fig = {}
    for r in candidates:
        subj = SUBJECT_CANONICAL.get(get_subject(r))
        if subj is None:
            continue
        fig = bool(get_has_figure(r))
        by_subj_fig.setdefault((subj, fig), []).append(r)

    picked = []
    for subj, target in target_per_subject.items():
        fig_target = max(1, int(round(target * target_figure_share)))
        nofig_target = target - fig_target

        fig_pool = list(by_subj_fig.get((subj, True), []))
        nofig_pool = list(by_subj_fig.get((subj, False), []))

        fig_take = rng.sample(fig_pool, min(fig_target, len(fig_pool)))
        nofig_take = rng.sample(nofig_pool, min(nofig_target, len(nofig_pool)))

        # Back-fill if either bucket was short
        deficit = target - len(fig_take) - len(nofig_take)
        if deficit > 0:
            picked_ids = {id(x) for x in fig_take + nofig_take}
            spare = [r for r in (fig_pool + nofig_pool) if id(r) not in picked_ids]
            rng.shuffle(spare)
            fig_take.extend(spare[:deficit])  # bucket assignment doesn't matter past target

        picked.extend(fig_take + nofig_take)
        LOGGER.info(
            f"  {subj}: picked {len(fig_take) + len(nofig_take)}/{target} "
            f"(figure-bearing: {sum(1 for r in fig_take if get_has_figure(r))}, "
            f"non-figure: {sum(1 for r in nofig_take if not get_has_figure(r))})"
        )

    return picked


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------

def record_from_ncert(row: dict) -> dict:
    image_urls = _extract_ncert_image_urls(row["content"])
    return {
        "source": "ncert",
        "id": row["questionid"],
        "subject": SUBJECT_CANONICAL.get(row["subject"], row["subject"]),
        "class": row.get("class"),
        "problem_payload": json.loads(build_user_payload(row["content"])),
        "answer_key": row.get("answer_key"),
        "image_urls": image_urls,
        "has_figure": _ncert_has_figure(row["content"]),
        "image_urls_present": bool(image_urls),
        "review_status_at_pick": row.get("review_status"),
    }


def record_from_jee(row: dict) -> dict:
    image_urls = _extract_jee_image_urls(row["question_content"])
    return {
        "source": "jee",
        "id": row["id"],
        "subject": SUBJECT_CANONICAL.get(row["subject"], row["subject"]),
        "class": None,
        "problem_payload": json.loads(build_user_payload(row["question_content"])),
        "answer_key": row.get("answer_key"),
        "image_urls": image_urls,
        "has_figure": _jee_has_figure(row["question_content"]),
        "image_urls_present": bool(image_urls),
        "review_status_at_pick": row.get("review_status"),
    }


# ---------------------------------------------------------------------------
# Defensive checks
# ---------------------------------------------------------------------------

def _assert_no_gold_overlap(records: list, db: JEEExtractionDBWriter) -> None:
    """Belt-and-braces: confirm no picked id is APPROVED_GOLD in either table."""
    ncert_ids = [r["id"] for r in records if r["source"] == "ncert"]
    jee_ids = [r["id"] for r in records if r["source"] == "jee"]
    overlaps = []
    with db.connection() as conn:
        with conn.cursor() as cur:
            if ncert_ids:
                cur.execute(
                    "SELECT questionid FROM questiondata "
                    "WHERE questionid = ANY(%s) AND review_status = 'APPROVED_GOLD'",
                    (ncert_ids,),
                )
                overlaps.extend(("ncert", r[0]) for r in cur.fetchall())
            if jee_ids:
                cur.execute(
                    "SELECT id FROM jee_question_bank "
                    "WHERE id = ANY(%s) AND review_status = 'APPROVED_GOLD'",
                    (jee_ids,),
                )
                overlaps.extend(("jee", r[0]) for r in cur.fetchall())
    if overlaps:
        LOGGER.error(f"APPROVED_GOLD overlap detected (this should never happen): {overlaps}")
        sys.exit(3)
    LOGGER.info("Assertion ✓ — zero overlap with APPROVED_GOLD in either table.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build the M3 held-out evaluation set.")
    parser.add_argument("--jee", type=int, default=50, help="Number of JEE rows.")
    parser.add_argument("--ncert", type=int, default=50, help="Number of NCERT rows.")
    parser.add_argument(
        "--figure-share", type=float, default=0.35,
        help="Target fraction of records that are figure-bearing (~30-40%% per plan).",
    )
    parser.add_argument(
        "--never-distill", type=int, default=20,
        help="Records reserved as the never-distill final-exam slice.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (reproducibility).")
    parser.add_argument(
        "--output", type=str, default="holdout_eval_set.json",
        help="Output JSON file (relative to ModelEngineering folder).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite output if it exists.")
    args = parser.parse_args()

    out_path = cwd / args.output
    if out_path.exists() and not args.force:
        LOGGER.error(f"{out_path} already exists. Pass --force to overwrite.")
        sys.exit(2)

    rng = random.Random(args.seed)
    db = JEEExtractionDBWriter()

    # Fetch pools
    ncert_pool = fetch_ncert_candidates(db)
    jee_pool = fetch_jee_candidates(db)

    # Stratified sample per source
    LOGGER.info(f"Sampling {args.ncert} NCERT records...")
    ncert_picked = stratified_sample(
        ncert_pool,
        get_subject=lambda r: r["subject"],
        get_has_figure=lambda r: _ncert_has_figure(r["content"]),
        target_per_subject=_scale_targets(SUBJECT_SPLIT_BASE, args.ncert),
        target_figure_share=args.figure_share,
        rng=rng,
    )

    LOGGER.info(f"Sampling {args.jee} JEE records...")
    jee_picked = stratified_sample(
        jee_pool,
        get_subject=lambda r: r["subject"],
        get_has_figure=lambda r: _jee_has_figure(r["question_content"]),
        target_per_subject=_scale_targets(SUBJECT_SPLIT_BASE, args.jee),
        target_figure_share=args.figure_share,
        rng=rng,
    )

    # Construct output records
    records = [record_from_ncert(r) for r in ncert_picked] \
              + [record_from_jee(r) for r in jee_picked]

    # Defensive gold-overlap check (SQL already filters but trust nothing)
    _assert_no_gold_overlap(records, db)

    # Tag the never-distill final-exam slice
    n_never = min(args.never_distill, len(records))
    never_idx = set(rng.sample(range(len(records)), n_never))
    for i, rec in enumerate(records):
        rec["never_distill"] = i in never_idx

    # Summary metadata — distinguishes figure-DEPENDENT (has_figure) from
    # image-INLINED (image_urls_present). The gap between them is the JEE
    # figure-URL extraction debt (see E2E plan Known Gaps).
    fig_count = sum(1 for r in records if r["has_figure"])
    img_count = sum(1 for r in records if r["image_urls_present"])
    subj_breakdown = {}
    for r in records:
        key = (r["source"], r["subject"], r["has_figure"])
        subj_breakdown[key] = subj_breakdown.get(key, 0) + 1

    payload = {
        "meta": {
            "created_at": datetime.now().isoformat(),
            "seed": args.seed,
            "figure_share_target": args.figure_share,
            "ncert_count": sum(1 for r in records if r["source"] == "ncert"),
            "jee_count": sum(1 for r in records if r["source"] == "jee"),
            "figure_bearing_count": fig_count,
            "image_urls_present_count": img_count,
            "never_distill_count": n_never,
            "subject_breakdown": {f"{s}/{subj}/fig={fig}": n for (s, subj, fig), n in sorted(subj_breakdown.items())},
        },
        "records": records,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    LOGGER.info(f"Wrote {len(records)} records to {out_path}")
    LOGGER.info(f"  source: NCERT={payload['meta']['ncert_count']} / JEE={payload['meta']['jee_count']}")
    LOGGER.info(
        f"  figure-bearing: {fig_count}/{len(records)} "
        f"(target ~{int(args.figure_share * 100)}%)"
    )
    LOGGER.info(
        f"  image-inlined: {img_count}/{fig_count} of figure-bearing "
        f"(JEE figure-URL extraction is deferred — see Known Gaps)"
    )
    LOGGER.info(f"  never-distill (final-exam): {n_never}")
    LOGGER.info("Subject × figure breakdown:")
    for k, v in payload["meta"]["subject_breakdown"].items():
        LOGGER.info(f"    {k}: {v}")


if __name__ == "__main__":
    main()
