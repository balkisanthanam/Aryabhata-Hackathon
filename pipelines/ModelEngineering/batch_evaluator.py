"""
Batch Evaluator — M2.4 + M3 baselining harness.

Runs a chosen generator (Pro assembly line / untuned Flash / tuned Flash) over a
fixed set of questions, scores each generation with the Universal Evaluator, and
exports a Markdown + JSON report with per-(source × subject × figure-bearing)
breakdowns plus the aggregate `Full-pass %` and `Accuracy-routable %` decision
metrics from `Design/Architecture/M3_TuningLoop_Plan.md`.

Usage:
    # Ad-hoc (random JEE sample, legacy behavior — kept for backwards compat)
    python batch_evaluator.py --limit 10 --use-assembly --label "ad-hoc"

    # M3.1 baselines — same frozen holdout for all three runs
    python batch_evaluator.py --model pro-assembly  --holdout-file holdout_eval_set.json \
        --use-smart-context --label "M3.1 Target Pro-Assembly"
    python batch_evaluator.py --model flash-untuned --holdout-file holdout_eval_set.json \
        --label "M3.1 Floor Flash-Untuned"

    # M3.2 candidate — once a tuned endpoint exists
    python batch_evaluator.py --model flash-tuned --tuned-endpoint "<endpoint>" \
        --holdout-file holdout_eval_set.json --label "M3.2 Candidate Flash-Tuned v1"
"""

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Path setup (matches the rest of pipelines/ModelEngineering)
cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
jee_dir = project_root / "pipelines" / "JEEAscentPipeline"

if str(extraction_dir) not in sys.path:
    sys.path.insert(0, str(extraction_dir))
if str(jee_dir) not in sys.path:
    sys.path.insert(0, str(jee_dir))

from gemini_client import GeminiClient  # noqa: E402
from config import PipelineConfig, GeminiModelConfig, flash_assembly_config  # noqa: E402
from solver_engine import GoldenGenerator  # noqa: E402
from router import select_mode_for_record  # noqa: E402
from evaluator_engine import UniversalEvaluator, EvaluationResult, get_evaluator  # noqa: E402
from db_writer import JEEExtractionDBWriter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("batch_evaluator")

# Vertex tuning requires byte-identical system instruction at train and inference time.
# `flash-untuned` and `flash-tuned` both load this file; `pro-assembly` uses a richer
# prompt via --prompt because that's what produced the gold-set outputs we're training on.
CANONICAL_SYS_PATH = cwd / "canonical_system_instruction.txt"

# Untuned Flash base model — the "Floor" comparison anchor.
UNTUNED_FLASH_MODEL_ID = "gemini-3-flash-preview"

# Canonical solution schema for Vertex response_schema enforcement.
# Per Phase 0 diagnostic (2026-05-26 — runs/_PED_REGRESSION_ANALYSIS_v1.md):
# Tuned Flash v1 was intermittently omitting step_type + nudge_hint fields from
# its JSON output, even on rows it was trained on. SFT did not override Gemini
# 2.5's bias toward stripped JSON. response_schema forces field presence at
# generation time. minLength: 1 prevents empty-string evasion.
CANONICAL_SOLUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "step_number": {"type": "integer", "minimum": 1},
                    "step_type": {"type": "string", "minLength": 1},
                    "nudge_hint": {"type": "string", "minLength": 1},
                    "explanation": {"type": "string", "minLength": 1},
                    "latex_formula": {"type": "string", "minLength": 1},
                },
                "required": ["step_number", "step_type", "nudge_hint", "explanation", "latex_formula"],
            },
        },
        "final_answer": {"type": "string", "minLength": 1},
    },
    "required": ["steps", "final_answer"],
}



# ---------------------------------------------------------------------------
# Test-set loading: frozen holdout (M3) OR ad-hoc random JEE batch (legacy)
# ---------------------------------------------------------------------------

def load_holdout(holdout_path: Path) -> list:
    """Read the frozen holdout file produced by `build_holdout_set.py`.

    Each record has `source`, `id`, `subject`, `problem_payload`, `answer_key`,
    `image_urls`, `has_figure`, `never_distill`. We pass these through as-is so
    the same harness scores NCERT and JEE without source-specific assumptions.
    """
    if not holdout_path.exists():
        LOGGER.error(f"Holdout file not found: {holdout_path}. Run build_holdout_set.py first.")
        sys.exit(1)
    payload = json.loads(holdout_path.read_text(encoding="utf-8"))
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    LOGGER.info(
        f"Loaded {len(records)} holdout records from {holdout_path.name} "
        f"(NCERT={sum(1 for r in records if r['source']=='ncert')}, "
        f"JEE={sum(1 for r in records if r['source']=='jee')}, "
        f"figure-bearing={sum(1 for r in records if r.get('has_figure'))})"
    )
    return records


def fetch_test_batch(db_writer: JEEExtractionDBWriter, limit: int = 10) -> list:
    """Legacy ad-hoc JEE random sample. Returned in holdout-record shape so the
    downstream loop is uniform regardless of the source mode."""
    query = """
        SELECT id, nta_question_id, subject, question_content, answer_key
        FROM jee_question_bank
        WHERE answer_key IS NOT NULL AND question_content IS NOT NULL
        ORDER BY RANDOM()
        LIMIT %s
    """
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    records = []
    for r in rows:
        qc = r.get("question_content") or {}
        if isinstance(qc, str):
            try:
                qc = json.loads(qc)
            except Exception:
                qc = {}
        image_urls = []
        if qc.get("figure_url"):
            image_urls.append(qc["figure_url"])
        if qc.get("option_figure_urls"):
            image_urls.extend([u for u in qc["option_figure_urls"] if u])
        records.append({
            "source": "jee",
            "id": r["id"],
            "subject": r.get("subject", "Unknown"),
            "problem_payload": {
                "problem_text": qc.get("raw_text", ""),
                "options": qc.get("options", []),
            },
            "answer_key": r.get("answer_key"),
            "image_urls": image_urls,
            "has_figure": bool(image_urls),
            "never_distill": False,
        })
    return records


# ---------------------------------------------------------------------------
# Smart-Context retrieval (Pro-assembly only — Flash modes mirror training data)
# ---------------------------------------------------------------------------

def build_smart_context_payload(q_id: int, source: str, db_writer: JEEExtractionDBWriter) -> str:
    """NCERT theory pulled from `jee_question_tags` joined to `ncert_concept_hierarchy`.
    Only meaningful for JEE rows (NCERT-side smart context is wired inside the NCERT
    orchestrator). For mixed-source holdouts, this is a no-op on NCERT rows."""
    if source != "jee":
        return ""
    query = """
        SELECT nch.concept_title, nch.embedding_text, nch.key_formulas, nch.ncert_solved_example
        FROM jee_question_tags jqt
        JOIN ncert_concept_hierarchy nch ON jqt.concept_id = nch.id
        WHERE jqt.question_id = %s
        ORDER BY jqt.similarity_score DESC
        LIMIT 5
    """
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (q_id,))
            rows = cur.fetchall()
    if not rows:
        return ""
    blocks = []
    for title, emb_txt, formulas, example in rows:
        block = f"### Concept: {title}\n"
        if emb_txt:
            block += f"**Theory**: {emb_txt}\n"
        if formulas:
            block += f"**Formulas**: {formulas}\n"
        if example:
            block += f"**Example**: {example}\n"
        blocks.append(block)
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# Generation dispatch — one of three modes
# ---------------------------------------------------------------------------

def _load_canonical_system_instruction() -> str:
    if not CANONICAL_SYS_PATH.exists():
        LOGGER.error(f"Canonical system instruction missing: {CANONICAL_SYS_PATH}")
        sys.exit(1)
    return CANONICAL_SYS_PATH.read_text(encoding="utf-8").strip()


def _build_flash_user_prompt(payload_dict: dict) -> str:
    """Byte-identical to the gold-set training user message (see jsonl_exporter.py:155)."""
    return "Solve this problem:\n\n" + json.dumps(payload_dict, indent=2)


def _build_pro_user_prompt(payload_dict: dict, subject: str) -> str:
    return (
        f"Solve the following {subject} problem. Only return the solution JSON object.\n\n"
        f"Problem Payload:\n```json\n{json.dumps(payload_dict, indent=2)}\n```\n"
    )


def generate_solution(
    mode: str,
    payload_dict: dict,
    subject: str,
    image_urls: list,
    pro_system_prompt: str,
    canonical_sys: str,
    client: GeminiClient,
    generator: GoldenGenerator,
    tuned_model_config: Optional[GeminiModelConfig],
    untuned_flash_config: GeminiModelConfig,
    flash_generator: Optional[GoldenGenerator] = None,
):
    """Returns a `GeneratedContent`-like object (has `.text`)."""
    if mode == "pro-assembly":
        return generator.generate_assembly_line(
            prompt=_build_pro_user_prompt(payload_dict, subject),
            system_prompt=pro_system_prompt,
            image_urls=image_urls or None,
        )
    elif mode == "flash-assembly":
        # A3.5 (2026-05-31): the Pro Assembly Line's 3 stages (Solver->Tutor->Format) run on
        # Flash instead of Pro — decomposes the single-call conflation to fix Pedagogy. Same
        # stage prompts as pro-assembly; only the per-stage model differs (config in main()).
        if flash_generator is None:
            raise RuntimeError("flash-assembly mode requires the Flash-configured generator.")
        return flash_generator.generate_assembly_line(
            prompt=_build_pro_user_prompt(payload_dict, subject),
            system_prompt=pro_system_prompt,
            image_urls=image_urls or None,
        )
    elif mode == "flash-untuned":
        return client.generate(
            model_config=untuned_flash_config,
            prompt=_build_flash_user_prompt(payload_dict),
            system_instruction=canonical_sys,
            image_urls=image_urls or None,
        )
    elif mode == "flash-tuned":
        if tuned_model_config is None:
            raise RuntimeError("flash-tuned mode requires --tuned-endpoint or TUNED_FLASH_ENDPOINT env.")
        # Swap to regional sub-client (built in main() for the tuned endpoint's region)
        # for this call only. Restore the global client afterward so any subsequent
        # Pro Assembly call (e.g. via router) reaches gemini-3.1-pro-preview which is
        # only served from the global host.
        _original = client._client
        try:
            client._client = client._regional_subclient
            return client.generate(
                model_config=tuned_model_config,
                prompt=_build_flash_user_prompt(payload_dict),
                system_instruction=canonical_sys,
                image_urls=image_urls or None,
            )
        finally:
            client._client = _original
    else:
        raise ValueError(f"Unknown --model: {mode}")


# ---------------------------------------------------------------------------
# Reporting — per-(source × subject × has_figure) breakdown + M3 decision metrics
# ---------------------------------------------------------------------------

def _full_pass(scores: dict) -> bool:
    return scores["accuracy_score"] == 5 and scores["pedagogy_score"] >= 4 and scores["formatting_score"] >= 4


def _acc_routable(scores: dict) -> bool:
    return scores["accuracy_score"] == 5


def compute_aggregates(results: list) -> dict:
    """Aggregate full-pass / acc-routable / per-dim averages over scored rows."""
    scored = [r for r in results if r["scores"]]
    n = len(scored)
    if n == 0:
        return {"n": 0, "full_pass_pct": 0.0, "acc_routable_pct": 0.0,
                "avg_acc": 0.0, "avg_ped": 0.0, "avg_fmt": 0.0, "is_pass_pct": 0.0}
    return {
        "n": n,
        "full_pass_pct": 100 * sum(1 for r in scored if _full_pass(r["scores"])) / n,
        "acc_routable_pct": 100 * sum(1 for r in scored if _acc_routable(r["scores"])) / n,
        "is_pass_pct": 100 * sum(1 for r in scored if r["scores"]["is_pass"]) / n,
        "avg_acc": sum(r["scores"]["accuracy_score"] for r in scored) / n,
        "avg_ped": sum(r["scores"]["pedagogy_score"] for r in scored) / n,
        "avg_fmt": sum(r["scores"]["formatting_score"] for r in scored) / n,
    }


def compute_breakdown(results: list) -> dict:
    """Group by (source, subject, has_figure) and aggregate within each bucket."""
    buckets = defaultdict(list)
    for r in results:
        key = (r["source"], r["subject"], bool(r["has_figure"]))
        buckets[key].append(r)
    return {key: compute_aggregates(rows) for key, rows in buckets.items()}


def _markdown_breakdown_table(breakdown: dict) -> list:
    lines = [
        "| Source | Subject    | Figure | N  | Full-pass % | Acc-routable % | Avg Acc | Avg Ped | Avg Fmt |",
        "|--------|------------|--------|----|-------------|----------------|---------|---------|---------|",
    ]
    for (source, subject, has_fig), agg in sorted(breakdown.items()):
        lines.append(
            f"| {source:<6} | {subject:<10} | {str(has_fig):<6} | {agg['n']:>2} | "
            f"{agg['full_pass_pct']:>11.1f} | {agg['acc_routable_pct']:>14.1f} | "
            f"{agg['avg_acc']:>7.2f} | {agg['avg_ped']:>7.2f} | {agg['avg_fmt']:>7.2f} |"
        )
    return lines


def write_report(args, results: list, runs_dir: Path, mode: str, tuned_endpoint: Optional[str]) -> Path:
    runs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = runs_dir / f"Experiment_Run_{ts}.md"

    agg = compute_aggregates(results)
    breakdown = compute_breakdown(results)

    # Figure-bearing vs non-figure-bearing aggregates (the multimodal-collapse check)
    fig_results = [r for r in results if r["has_figure"]]
    nofig_results = [r for r in results if not r["has_figure"]]
    fig_agg = compute_aggregates(fig_results)
    nofig_agg = compute_aggregates(nofig_results)

    # Phase 6.5 routing summary: which rows would the router send to Pro?
    router_enabled = (mode == "flash-tuned") and (not getattr(args, "no_router", False))
    routed_to_pro = [r for r in results if router_enabled and r["source"] == "jee" and r.get("has_figure")]
    routed_to_tuned = [r for r in results if not (router_enabled and r["source"] == "jee" and r.get("has_figure"))]
    routed_pro_agg = compute_aggregates(routed_to_pro) if routed_to_pro else None
    routed_tuned_agg = compute_aggregates(routed_to_tuned) if routed_to_tuned else None

    schema_enforced = (mode == "flash-tuned") and (not getattr(args, "no_schema", False))

    lines = [
        f"# Experiment Report: {args.label}",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Mode**: `{mode}`",
        f"**Holdout file**: `{args.holdout_file}`" if args.holdout_file else f"**Source**: ad-hoc random JEE (limit={args.limit})",
        f"**Tuned endpoint**: `{tuned_endpoint}`" if tuned_endpoint else "**Tuned endpoint**: n/a",
        f"**Smart Context**: {'Enabled' if args.use_smart_context else 'Disabled'}",
        f"**response_schema (Phase 6.5)**: {'ENFORCED' if schema_enforced else 'OFF'}" if mode == "flash-tuned" else "",
        f"**Figure-aware router (Phase 6.5)**: {'ENABLED' if router_enabled else 'OFF'}" if mode == "flash-tuned" else "",
        f"**Pro prompt file**: `{args.prompt}`" if mode == "pro-assembly" else "",
        "",
        "## M3 Decision Metrics",
        f"- **Full-pass %** (Accuracy=5 AND Pedagogy≥4 AND Format≥4): **{agg['full_pass_pct']:.1f}%** ({int(round(agg['full_pass_pct']*agg['n']/100))}/{agg['n']})",
        f"- **Accuracy-routable %** (Accuracy=5): **{agg['acc_routable_pct']:.1f}%**",
        f"- **Legacy is_pass %** (total≥13 AND Acc=5): {agg['is_pass_pct']:.1f}%",
        f"- **Avg Accuracy / Pedagogy / Formatting**: {agg['avg_acc']:.2f} / {agg['avg_ped']:.2f} / {agg['avg_fmt']:.2f}",
        "",
        "## Multimodal Sanity Check",
        f"- Figure-bearing N={fig_agg['n']}: Full-pass {fig_agg['full_pass_pct']:.1f}%, Acc-routable {fig_agg['acc_routable_pct']:.1f}%",
        f"- Non-figure  N={nofig_agg['n']}: Full-pass {nofig_agg['full_pass_pct']:.1f}%, Acc-routable {nofig_agg['acc_routable_pct']:.1f}%",
        f"- **Gap** (non-figure − figure) on Acc-routable: {nofig_agg['acc_routable_pct'] - fig_agg['acc_routable_pct']:+.1f}pp "
        f"{'⚠️ >15pp — trigger Path B multimodal retune' if abs(nofig_agg['acc_routable_pct'] - fig_agg['acc_routable_pct']) > 15 else '✓ within tolerance'}",
        "",
        "## Per-(source × subject × figure) Breakdown",
        *_markdown_breakdown_table(breakdown),
        "",
        *([
            "## Routing Summary (Phase 6.5)",
            f"- Routed to Pro Assembly (JEE+has_figure rule): N={len(routed_to_pro)}"
            + (f"  Full-pass {routed_pro_agg['full_pass_pct']:.1f}%, Acc-routable {routed_pro_agg['acc_routable_pct']:.1f}%" if routed_pro_agg else ""),
            f"- Stayed on Tuned Flash: N={len(routed_to_tuned)}"
            + (f"  Full-pass {routed_tuned_agg['full_pass_pct']:.1f}%, Acc-routable {routed_tuned_agg['acc_routable_pct']:.1f}%" if routed_tuned_agg else ""),
            "",
        ] if router_enabled else []),
        "## Per-row Detail",
        "| Q ID | Source | Subject | Fig | NeverDistill | Pass | Acc | Ped | Fmt | Feedback |",
        "|------|--------|---------|-----|--------------|------|-----|-----|-----|----------|",
    ]
    # Drop blank lines introduced by conditional inclusions
    lines = [ln for ln in lines if ln != ""]

    for r in results:
        if r["scores"]:
            s = r["scores"]
            snippet = (s["feedback_notes"] or "").replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            lines.append(
                f"| {r['id']} | {r['source']} | {r['subject']} | "
                f"{'Y' if r['has_figure'] else 'N'} | {'Y' if r.get('never_distill') else 'N'} | "
                f"{'✅' if s['is_pass'] else '❌'} | {s['accuracy_score']} | "
                f"{s['pedagogy_score']} | {s['formatting_score']} | {snippet} |"
            )
        else:
            lines.append(
                f"| {r['id']} | {r['source']} | {r['subject']} | "
                f"{'Y' if r['has_figure'] else 'N'} | {'Y' if r.get('never_distill') else 'N'} | "
                f"⚠️ | - | - | - | GEN ERROR: {r.get('generator_error')} |"
            )

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Companion machine-readable JSON for downstream scripts (e.g. distillation collector)
    json_path = md_path.with_suffix("").with_suffix(".json")
    json_path = md_path.parent / (md_path.stem + "_RAW.json")
    json_payload = {
        "label": args.label,
        "mode": mode,
        "timestamp": ts,
        "holdout_file": args.holdout_file,
        "tuned_endpoint": tuned_endpoint,
        "aggregate": agg,
        "figure_bearing_aggregate": fig_agg,
        "non_figure_aggregate": nofig_agg,
        "breakdown": {"|".join((s, sub, str(f))): a for (s, sub, f), a in breakdown.items()},
        "details": results,
    }
    json_path.write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")

    return md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    # M3 selectors
    parser.add_argument(
        "--model", type=str, choices=["pro-assembly", "flash-untuned", "flash-tuned", "flash-assembly"],
        default=None,
        help="Generator mode. If omitted, falls back to legacy --use-assembly flag.",
    )
    parser.add_argument(
        "--holdout-file", type=str, default=None,
        help="Path to holdout_eval_set.json (relative to ModelEngineering dir). "
             "If omitted, falls back to random JEE sampling via --limit.",
    )
    parser.add_argument(
        "--tuned-endpoint", type=str, default=os.environ.get("TUNED_FLASH_ENDPOINT"),
        help="Tuned model endpoint string for --model flash-tuned. "
             "Env TUNED_FLASH_ENDPOINT is consulted as fallback.",
    )
    # Legacy / ad-hoc args
    parser.add_argument("--limit", type=int, default=10, help="Random JEE sample size when no --holdout-file.")
    parser.add_argument(
        "--prompt", type=str, default="jee_solver_prompt_author.md",
        help="Prompt file under JEEAscentPipeline/prompts — Pro-assembly only.",
    )
    parser.add_argument(
        "--use-assembly", action="store_true",
        help="Deprecated alias for --model pro-assembly.",
    )
    parser.add_argument(
        "--use-smart-context", action="store_true",
        help="Inject NCERT theory context for JEE rows (pro-assembly recommended; flash modes mirror training).",
    )
    parser.add_argument("--label", type=str, default="Experiment", help="Run label for the report.")
    # Phase 6.5 ablation flags
    parser.add_argument(
        "--no-schema", action="store_true",
        help="Disable Vertex response_schema enforcement on flash-tuned. Ablation for Phase 6.5 measurement.",
    )
    parser.add_argument(
        "--no-router", action="store_true",
        help="Disable figure-aware router (JEE+has_figure -> pro-assembly fallback). Ablation for Phase 6.5 measurement.",
    )
    parser.add_argument(
        "--restart", action="store_true",
        help="Delete any existing checkpoint for this label and start fresh.",
    )
    args = parser.parse_args()

    # Resolve mode (--model overrides --use-assembly)
    if args.model is None:
        args.model = "pro-assembly" if args.use_assembly else "flash-untuned"
        LOGGER.info(f"--model not given; inferred '{args.model}' (use --model explicitly to silence this).")
    mode = args.model

    # Load shared components
    config = PipelineConfig()
    try:
        client = GeminiClient(config)
    except TypeError:
        client = GeminiClient(config.project_id, config.location)

    generator = GoldenGenerator(client, config)
    evaluator = get_evaluator()
    db_writer = JEEExtractionDBWriter()

    flash_generator = None
    if mode == "flash-assembly":
        flash_generator = GoldenGenerator(client, flash_assembly_config())

    # Canonical system instruction (used by flash modes only)
    canonical_sys = _load_canonical_system_instruction()

    # Pro-assembly system prompt (rich, from prompts/<--prompt>) — shared with flash-assembly
    # so the only difference between the two is Pro vs Flash on stages 1-2.
    pro_system_prompt = ""
    if mode in ("pro-assembly", "flash-assembly"):
        prompt_file = jee_dir / "prompts" / args.prompt
        if not prompt_file.exists():
            LOGGER.error(f"Prompt file not found: {prompt_file}")
            sys.exit(1)
        pro_system_prompt = prompt_file.read_text(encoding="utf-8")

    # Tuned-endpoint config (used by flash-tuned only)
    tuned_model_config = None
    if mode == "flash-tuned":
        if not args.tuned_endpoint:
            LOGGER.error("--model flash-tuned requires --tuned-endpoint or TUNED_FLASH_ENDPOINT env.")
            sys.exit(1)
        # Mirror untuned_flash_config defaults: structured-JSON output + generous
        # output cap. Without max_output_tokens, Gemini 2.5 thinking can consume
        # the default ~8K budget and leave 0 tokens for the actual answer
        # (manifests as HTTP 200 with empty response.text => json.loads('') error).
        # response_schema enforces step_type + nudge_hint field presence (Phase 6.5
        # fix for the schema-strip Pedagogy failure mode diagnosed in Phase 0).
        tuned_model_config = GeminiModelConfig(
            model_id=args.tuned_endpoint,
            temperature=0.4,
            max_output_tokens=32768,
            response_mime_type="application/json",
            response_schema=(None if args.no_schema else CANONICAL_SOLUTION_SCHEMA),
        )
        LOGGER.info(
            f"Tuned endpoint: {args.tuned_endpoint}  "
            f"response_schema={'OFF (--no-schema)' if args.no_schema else 'ON (Phase 6.5)'}"
        )

        # Tuned endpoints live in a specific Vertex region (us-central1 by default).
        # PipelineConfig.location is typically 'global' for stock Gemini-3 inference.
        # Build a separate regional sub-client for tuned-endpoint calls, and swap
        # it in/out around each tuned call (rather than globally). This preserves
        # Pro Assembly's ability to reach `gemini-3.1-pro-preview` which is only
        # served from the global host. Without this two-client setup, the
        # figure-aware router's Pro-fallback hits 404 on the regional client.
        import re as _re
        from google import genai as _genai
        from google.genai.types import HttpOptions as _HttpOptions
        _m = _re.search(r"locations/([^/]+)/endpoints/", args.tuned_endpoint)
        _endpoint_region = _m.group(1) if _m else "us-central1"
        client._regional_subclient = _genai.Client(
            vertexai=True,
            project=config.project_id,
            location=_endpoint_region,
            http_options=_HttpOptions(timeout=config.api_timeout_seconds * 1000),
        )
        client._regional_endpoint_region = _endpoint_region
        LOGGER.info(
            f"flash-tuned: prepared regional sub-client at region='{_endpoint_region}' "
            f"(global client preserved for Pro Assembly fallback via router)"
        )

    # Untuned Flash base config (single-call Floor anchor)
    untuned_flash_config = GeminiModelConfig(
        model_id=UNTUNED_FLASH_MODEL_ID,
        temperature=0.4,
        response_mime_type="application/json",
        # Sprint A3 (2026-05-30): untuned-3-flash with response_schema was never measured —
        # the original "Floor" baseline ran WITHOUT schema (hence 0% Full-pass). Tuning only
        # ever bought Ped/Fmt, which schema enforcement should now deliver on untuned too.
        # This makes flash-untuned the production `Untuned_with_support` solver config.
        response_schema=CANONICAL_SOLUTION_SCHEMA,
    )

    # Source records — frozen holdout (preferred) OR random JEE batch (legacy)
    if args.holdout_file:
        records = load_holdout(cwd / args.holdout_file)
    else:
        records = fetch_test_batch(db_writer, limit=args.limit)
        LOGGER.info(f"No --holdout-file; sampled {len(records)} random JEE rows.")

    if not records:
        LOGGER.error("Empty test set.")
        sys.exit(1)

    LOGGER.info(
        f"Run config: mode={mode} | records={len(records)} | "
        f"smart_context={args.use_smart_context} | label={args.label}"
    )

    # ------------------------------------------------------------------
    # Resumability: per-row checkpoint as we go, auto-resume on rerun.
    # Each line in the checkpoint file = one result dict; keyed by
    # (source, id) so a rerun with the same --label skips completed rows.
    # `--restart` deletes the checkpoint and starts fresh.
    # ------------------------------------------------------------------
    runs_dir = cwd / "runs"
    runs_dir.mkdir(exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", args.label).strip("_") or "run"
    ckpt_path = runs_dir / f"_checkpoint_{safe_label}.jsonl"

    if args.restart and ckpt_path.exists():
        LOGGER.info(f"--restart: deleting existing checkpoint {ckpt_path.name}")
        ckpt_path.unlink()

    results: list = []
    completed_keys: set = set()
    if ckpt_path.exists():
        try:
            for line in ckpt_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                results.append(obj)
                completed_keys.add((obj["source"], obj["id"]))
            LOGGER.info(
                f"Resuming from {ckpt_path.name}: {len(completed_keys)} rows already complete "
                f"(pass --restart to start fresh)."
            )
        except Exception as e:
            LOGGER.warning(f"Could not parse checkpoint ({e}); starting fresh.")
            results = []
            completed_keys = set()
            ckpt_path.unlink()

    def _append_to_checkpoint(result: dict) -> None:
        with open(ckpt_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, default=str) + "\n")

    try:
      for idx, rec in enumerate(records, 1):
        q_id = rec["id"]
        source = rec["source"]
        subject = rec["subject"]
        if (source, q_id) in completed_keys:
            LOGGER.info(f"[{idx}/{len(records)}] Skipping {source}/{q_id} (already in checkpoint).")
            continue
        ans_key = rec.get("answer_key")
        payload_dict = dict(rec["problem_payload"])  # shallow copy — don't mutate the holdout dict
        if ans_key:
            payload_dict["actual_answer_key"] = ans_key

        # Phase 6.5 figure-aware router: pick per-row mode (default usually = requested mode,
        # but flash-tuned + JEE-figure flips to pro-assembly per KI-3 caveat).
        row_mode = select_mode_for_record(rec, mode, router_enabled=not args.no_router)

        # Inject Smart Context for pro-assembly when explicitly enabled (parity with gold-gen)
        if args.use_smart_context and row_mode == "pro-assembly":
            ctx_block = build_smart_context_payload(q_id, source, db_writer)
            if ctx_block:
                payload_dict["ncert_theory_context"] = ctx_block

        image_urls = rec.get("image_urls") or []

        if row_mode != mode:
            LOGGER.info(f"[{idx}/{len(records)}] ROUTED {source}/{q_id} ({subject}, has_figure={rec.get('has_figure')}) -> {row_mode}")
        else:
            LOGGER.info(f"[{idx}/{len(records)}] Generating for {source}/{q_id} ({subject}) [mode={row_mode}]...")

        # Generate (retry on empty body / parse failure — Vertex tuned endpoints
        # occasionally return HTTP 200 with empty response.text on a subset of inputs
        # for no observable reason; retrying is the cheapest mitigation).
        GEN_RETRY_ATTEMPTS = 3
        candidate_solution = None
        gen_exc = None
        try:
            for _gen_attempt in range(GEN_RETRY_ATTEMPTS):
                try:
                    response = generate_solution(
                        mode=row_mode,
                        payload_dict=payload_dict,
                        subject=subject,
                        image_urls=image_urls,
                        pro_system_prompt=pro_system_prompt,
                        canonical_sys=canonical_sys,
                        client=client,
                        generator=generator,
                        tuned_model_config=tuned_model_config,
                        untuned_flash_config=untuned_flash_config,
                        flash_generator=flash_generator,
                    )
                    text = (response.text or "").strip()
                    if not text:
                        gen_exc = ValueError("empty response.text")
                        if _gen_attempt < GEN_RETRY_ATTEMPTS - 1:
                            LOGGER.warning(f"  -> empty body (attempt {_gen_attempt + 1}/{GEN_RETRY_ATTEMPTS}); retrying")
                            continue
                        raise gen_exc
                    if text.startswith("```json"):
                        text = text.split("```json", 1)[1]
                    elif text.startswith("```"):
                        text = text.split("```", 1)[1]
                    if text.rfind("```") != -1:
                        text = text[: text.rfind("```")].strip()
                    try:
                        candidate_solution = json.loads(text)
                    except json.JSONDecodeError:
                        candidate_solution = json.loads(generator._sanitize_json_escapes(text))
                    gen_exc = None
                    break
                except json.JSONDecodeError as e:
                    gen_exc = e
                    if _gen_attempt < GEN_RETRY_ATTEMPTS - 1:
                        LOGGER.warning(f"  -> JSON parse failed (attempt {_gen_attempt + 1}/{GEN_RETRY_ATTEMPTS}): {e}; retrying")
                        continue
                    raise
            if candidate_solution is None and gen_exc is not None:
                raise gen_exc
        except Exception as e:
            LOGGER.error(f"Generation failed for {source}/{q_id}: {e}")
            row_result = {
                "id": q_id, "source": source, "subject": subject,
                "has_figure": rec.get("has_figure", False),
                "never_distill": rec.get("never_distill", False),
                "scores": None, "generator_error": str(e),
            }
            results.append(row_result)
            _append_to_checkpoint(row_result)
            completed_keys.add((source, q_id))
            continue

        # Evaluate (omit injected smart-context block from eval payload — fairness)
        eval_payload = {
            "problem_text": rec["problem_payload"].get("problem_text", ""),
            "options": rec["problem_payload"].get("options", []),
        }
        try:
            eval_result: EvaluationResult = evaluator.evaluate_solution(
                problem_payload=eval_payload,
                generated_solution=candidate_solution,
                actual_answer_key=ans_key,
            )
            LOGGER.info(
                f"  -> {'PASS' if eval_result.is_pass else 'FAIL'} | "
                f"Acc:{eval_result.accuracy_score} Ped:{eval_result.pedagogy_score} Fmt:{eval_result.formatting_score}"
            )
            row_result = {
                "id": q_id, "source": source, "subject": subject,
                "has_figure": rec.get("has_figure", False),
                "never_distill": rec.get("never_distill", False),
                "scores": eval_result.to_dict(),
                "generator_error": None,
            }
            results.append(row_result)
            _append_to_checkpoint(row_result)
            completed_keys.add((source, q_id))
        except Exception as e:
            LOGGER.error(f"Evaluation failed for {source}/{q_id}: {e}")
            row_result = {
                "id": q_id, "source": source, "subject": subject,
                "has_figure": rec.get("has_figure", False),
                "never_distill": rec.get("never_distill", False),
                "scores": None, "generator_error": f"eval_error: {e}",
            }
            results.append(row_result)
            _append_to_checkpoint(row_result)
            completed_keys.add((source, q_id))
    except KeyboardInterrupt:
        LOGGER.warning(
            f"Interrupted. {len(results)} rows checkpointed to {ckpt_path.name}. "
            f"Rerun the same command to resume (or pass --restart)."
        )
        sys.exit(130)

    if not results:
        LOGGER.error("No results to report.")
        return

    md_path = write_report(args, results, runs_dir, mode, args.tuned_endpoint)

    agg = compute_aggregates(results)
    LOGGER.info("-" * 60)
    LOGGER.info(f"DONE | {args.label} | mode={mode}")
    LOGGER.info(f"  Full-pass %:       {agg['full_pass_pct']:.1f}%")
    LOGGER.info(f"  Acc-routable %:    {agg['acc_routable_pct']:.1f}%")
    LOGGER.info(f"  Avg Acc/Ped/Fmt:   {agg['avg_acc']:.2f} / {agg['avg_ped']:.2f} / {agg['avg_fmt']:.2f}")
    LOGGER.info(f"  Report:            {md_path}")
    LOGGER.info("-" * 60)


if __name__ == "__main__":
    main()
