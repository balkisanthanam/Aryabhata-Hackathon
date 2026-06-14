"""
Phase 0.2 of M3 v2 plan — diff Tuned v1 vs Pro Target on rows where
Pro scored Pedagogy=5 AND Tuned scored Pedagogy<5. These are the true
"regression" rows -- Pro CAN do it Socratically on this problem,
Tuned did not.

The RAW files don't carry the candidate_solution text. So this script
identifies the regression rows from the RAW files, then optionally
re-generates Pro + Tuned live for a small sample so we can compare
nudge_hint text side-by-side.

CLI:
  python diff_tuned_vs_pro.py                       # list rows only, no API calls
  python diff_tuned_vs_pro.py --sample 3 --regen   # re-generate Pro + Tuned for 3 rows (~$1, ~3 min)
"""
import argparse
import json
import sys
from pathlib import Path

CWD = Path(__file__).resolve().parent
DEFAULT_TUNED = CWD / "runs" / "Experiment_Run_20260526_105654_RAW.json"
DEFAULT_PRO = CWD / "runs" / "Experiment_Run_20260523_231104_RAW.json"
DEFAULT_HOLDOUT = CWD / "holdout_eval_set.json"
DEFAULT_OUT = CWD / "runs" / "_ped_regression_diff_v1.md"
DEFAULT_TUNED_ENDPOINT = "projects/556442477537/locations/us-central1/endpoints/8436131057215995904"


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_user_prompt(problem_text: str, options: list) -> str:
    payload = json.dumps({"problem_text": problem_text, "options": options or []}, indent=2)
    return "Solve this problem:\n\n" + payload


def _render_nudge_diff(pro_sol: dict, tuned_sol: dict) -> list[str]:
    lines = []
    pro_steps = pro_sol.get("steps", []) if isinstance(pro_sol, dict) else []
    tuned_steps = tuned_sol.get("steps", []) if isinstance(tuned_sol, dict) else []
    max_n = max(len(pro_steps), len(tuned_steps))
    for i in range(max_n):
        p = pro_steps[i] if i < len(pro_steps) else {}
        t = tuned_steps[i] if i < len(tuned_steps) else {}
        lines.append(f"#### Step {i+1}")
        lines.append("")
        lines.append("**Pro nudge_hint:**")
        lines.append("> " + (p.get("nudge_hint", "(missing)") or "(empty)").replace("\n", "\n> "))
        lines.append("")
        lines.append("**Tuned nudge_hint:**")
        lines.append("> " + (t.get("nudge_hint", "(missing)") or "(empty)").replace("\n", "\n> "))
        lines.append("")
    return lines


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tuned-raw", default=str(DEFAULT_TUNED))
    p.add_argument("--pro-raw", default=str(DEFAULT_PRO))
    p.add_argument("--holdout", default=str(DEFAULT_HOLDOUT))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--sample", type=int, default=0, help="Live re-generate this many rows (Pro + Tuned)")
    p.add_argument("--regen", action="store_true", help="Required to actually call the API")
    p.add_argument("--tuned-endpoint", default=DEFAULT_TUNED_ENDPOINT)
    args = p.parse_args()

    tuned = _load(Path(args.tuned_raw))
    pro = _load(Path(args.pro_raw))

    tuned_by_id = {(r["source"], r["id"]): r for r in tuned["details"] if r.get("scores")}
    pro_by_id = {(r["source"], r["id"]): r for r in pro["details"] if r.get("scores")}

    regressions = []
    for key, t in tuned_by_id.items():
        pr = pro_by_id.get(key)
        if not pr:
            continue
        if pr["scores"].get("pedagogy_score") == 5 and t["scores"].get("pedagogy_score", 5) < 5:
            regressions.append((key, pr, t))

    lines = []
    lines.append(f"# Pedagogy Regression Diff — Pro vs Tuned v1")
    lines.append(f"**Tuned RAW:** `{Path(args.tuned_raw).name}`  ")
    lines.append(f"**Pro RAW:** `{Path(args.pro_raw).name}`  ")
    lines.append(f"**Regression rows** (Pro Ped=5 AND Tuned Ped<5): **{len(regressions)}**")
    lines.append("")
    lines.append("## Regression list")
    lines.append("")
    lines.append("| source/id | subject | has_figure | Tuned Acc/Ped/Fmt | Tuned judge feedback (first 200) |")
    lines.append("|---|---|---|---|---|")
    for (src, qid), pr, t in regressions:
        s = t["scores"]
        fb = (s.get("feedback_notes") or "").replace("|", "/").replace("\n", " ")[:200]
        lines.append(f"| {src}/{qid} | {t['subject']} | {t['has_figure']} | {s['accuracy_score']}/{s['pedagogy_score']}/{s['formatting_score']} | {fb} |")
    lines.append("")

    if args.sample > 0 and args.regen and regressions:
        # Live re-generate Pro + Tuned for `sample` rows, render diff
        import sys as _sys
        _sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))
        from config import PipelineConfig, GeminiModelConfig
        from gemini_client import GeminiClient
        from solver_engine import GoldenGenerator
        from google import genai
        from google.genai.types import HttpOptions

        config = PipelineConfig()
        client = GeminiClient(config)
        generator = GoldenGenerator(client, config)

        # Regional client for Tuned endpoint (per project_vertex_tuned_endpoint_regional_host_2026_05_26 memory)
        regional_client = genai.Client(
            vertexai=True, project=config.project_id, location="us-central1",
            http_options=HttpOptions(timeout=config.api_timeout_seconds * 1000),
        )

        # Load holdout for problem text + image URLs
        with Path(args.holdout).open("r", encoding="utf-8") as f:
            holdout = json.load(f)
        holdout_by_id = {(r["source"], r["id"]): r for r in holdout["records"]}

        canonical = (CWD / "canonical_system_instruction.txt").read_text(encoding="utf-8").rstrip("\n")

        chosen = regressions[: args.sample]
        lines.append(f"## Live diff (sample of {len(chosen)})")
        for (src, qid), pr, t in chosen:
            rec = holdout_by_id.get((src, qid))
            if not rec:
                lines.append(f"\n### {src}/{qid} — not in holdout (skipped)")
                continue
            problem = rec["problem_payload"].get("problem_text") or ""
            options = rec["problem_payload"].get("options", [])
            image_urls = rec.get("image_urls") or []
            prompt = _build_user_prompt(problem, options)

            lines.append("")
            lines.append(f"### {src}/{qid} ({t['subject']}, has_figure={t['has_figure']})")
            lines.append("")
            lines.append(f"**Problem:** {problem[:240]}...")
            lines.append("")

            try:
                pro_resp = generator.generate_assembly_line(
                    prompt=prompt + ("\n\nNote: actual_answer_key=" + str(rec.get("answer_key")) if rec.get("answer_key") else ""),
                    system_prompt=(CWD.parent / "JEEAscentPipeline" / "prompts" / "JEE_SolutionGen_Aryabhatta.txt").read_text(encoding="utf-8") if (CWD.parent / "JEEAscentPipeline" / "prompts" / "JEE_SolutionGen_Aryabhatta.txt").exists() else canonical,
                    image_urls=image_urls or None,
                )
                pro_sol = json.loads(pro_resp.text)
            except Exception as e:
                lines.append(f"_Pro regen failed: {e}_")
                pro_sol = {}

            try:
                tuned_resp = regional_client.models.generate_content(
                    model=args.tuned_endpoint,
                    contents=prompt,
                    config={"temperature": 0.4, "system_instruction": canonical, "max_output_tokens": 32768, "response_mime_type": "application/json"},
                )
                tuned_text = (tuned_resp.text or "").strip()
                tuned_sol = json.loads(tuned_text) if tuned_text else {}
            except Exception as e:
                lines.append(f"_Tuned regen failed: {e}_")
                tuned_sol = {}

            lines.extend(_render_nudge_diff(pro_sol, tuned_sol))

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {len(regressions)} regression rows -> {out_path}")
    if args.sample > 0 and not args.regen:
        print(f"Note: --sample {args.sample} was specified but --regen was NOT — no API calls made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
