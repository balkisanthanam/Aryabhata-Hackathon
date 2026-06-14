"""
Phase 0.3 of M3 v2 plan — probe Tuned v1 on its OWN training data
to test whether SFT "took" on the Pedagogy dimension.

Picks N random rows from gold_sft_dataset.jsonl (the training corpus),
regenerates each via the Tuned v1 endpoint, scores via UniversalEvaluator,
and reports whether Tuned scores 5/5/5 on data it was trained on.

Decision logic:
- If Tuned scores 5/5/5 on its own training data => model "knows" the pattern,
  so v1 holdout regression is a GENERALIZATION problem (more data = right lever).
- If Tuned scores <5 (especially Ped<5) on its own training data => SFT didn't
  fully internalize the Tutor style, so v2 may need hyperparameter changes
  (epochs, LoRA rank, sample weighting) OR Ped is fundamentally Pro-bound.

CLI:
  python probe_tuned_on_gold.py                        # default 5 random rows
  python probe_tuned_on_gold.py --n 10 --seed 42       # reproducible 10-row sample
  python probe_tuned_on_gold.py --tuned-endpoint <...>  # override endpoint
"""
import argparse
import json
import random
import sys
from pathlib import Path

CWD = Path(__file__).resolve().parent
DEFAULT_GOLD = CWD / "gold_sft_dataset.jsonl"
DEFAULT_OUT = CWD / "runs" / "_ped_probe_on_gold_v1.md"
DEFAULT_TUNED_ENDPOINT = "projects/556442477537/locations/us-central1/endpoints/8436131057215995904"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gold", default=str(DEFAULT_GOLD))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tuned-endpoint", default=DEFAULT_TUNED_ENDPOINT)
    args = p.parse_args()

    gold_path = Path(args.gold)
    if not gold_path.exists():
        print(f"ERROR: gold file not found: {gold_path}", file=sys.stderr)
        return 2

    # Late imports — the SDK + evaluator setup is heavy and only needed when actually running
    sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))
    from config import PipelineConfig
    from evaluator_engine import get_evaluator
    from google import genai
    from google.genai.types import HttpOptions

    random.seed(args.seed)
    with gold_path.open("r", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    sample = random.sample(rows, min(args.n, len(rows)))
    print(f"Probing {len(sample)} of {len(rows)} Gold rows via Tuned endpoint...")

    canonical = (CWD / "canonical_system_instruction.txt").read_text(encoding="utf-8").rstrip("\n")
    config = PipelineConfig()
    # Regional client (per project_vertex_tuned_endpoint_regional_host_2026_05_26)
    client = genai.Client(
        vertexai=True, project=config.project_id, location="us-central1",
        http_options=HttpOptions(timeout=config.api_timeout_seconds * 1000),
    )
    evaluator = get_evaluator()

    results = []
    for i, row in enumerate(sample, 1):
        msgs = row["messages"]
        user_msg = next(m for m in msgs if m["role"] == "user")
        expected_model_msg = next(m for m in msgs if m["role"] == "model")
        user_content = user_msg["content"]
        # Extract the problem payload back out of "Solve this problem:\n\n<json>" envelope
        if user_content.startswith("Solve this problem:\n\n"):
            payload_json = user_content[len("Solve this problem:\n\n"):]
        else:
            payload_json = user_content
        problem_payload = json.loads(payload_json)

        print(f"[{i}/{len(sample)}] Generating via Tuned...")
        try:
            resp = client.models.generate_content(
                model=args.tuned_endpoint,
                contents=user_content,
                config={"temperature": 0.4, "system_instruction": canonical,
                        "max_output_tokens": 32768, "response_mime_type": "application/json"},
            )
            text = (resp.text or "").strip()
            if not text:
                raise ValueError("empty tuned response")
            candidate_solution = json.loads(text)
        except Exception as e:
            print(f"  -> Tuned generation failed: {e}")
            results.append({"row_index": rows.index(row), "tuned_error": str(e), "scores": None})
            continue

        print(f"  -> Judging...")
        try:
            er = evaluator.evaluate_solution(
                problem_payload=problem_payload,
                generated_solution=candidate_solution,
                actual_answer_key=None,
            )
            print(f"  -> Acc:{er.accuracy_score} Ped:{er.pedagogy_score} Fmt:{er.formatting_score}")
            results.append({
                "row_index": rows.index(row),
                "problem_text_preview": problem_payload.get("problem_text", "")[:200],
                "scores": er.to_dict(),
                "tuned_error": None,
            })
        except Exception as e:
            print(f"  -> Judge failed: {e}")
            results.append({"row_index": rows.index(row), "judge_error": str(e), "scores": None})

    # Render report
    scored = [r for r in results if r.get("scores")]
    n = len(scored)
    if n:
        avg_acc = sum(r["scores"]["accuracy_score"] for r in scored) / n
        avg_ped = sum(r["scores"]["pedagogy_score"] for r in scored) / n
        avg_fmt = sum(r["scores"]["formatting_score"] for r in scored) / n
        full_pass = sum(1 for r in scored if r["scores"]["accuracy_score"] == 5
                        and r["scores"]["pedagogy_score"] >= 4
                        and r["scores"]["formatting_score"] >= 4) / n * 100
        all_555 = sum(1 for r in scored if r["scores"]["accuracy_score"] == 5
                      and r["scores"]["pedagogy_score"] == 5
                      and r["scores"]["formatting_score"] == 5) / n * 100
    else:
        avg_acc = avg_ped = avg_fmt = full_pass = all_555 = 0.0

    lines = []
    lines.append("# Tuned v1 probe on Gold Set training data")
    lines.append(f"**Sample size:** {len(sample)} (scored: {n})  ")
    lines.append(f"**Gold file:** `{gold_path.name}`  ")
    lines.append(f"**Seed:** {args.seed}  ")
    lines.append(f"**Tuned endpoint:** `{args.tuned_endpoint}`")
    lines.append("")
    lines.append("## Aggregate on Gold-set rows (re-generated via Tuned v1)")
    lines.append(f"- Avg Acc / Ped / Fmt: {avg_acc:.2f} / {avg_ped:.2f} / {avg_fmt:.2f}")
    lines.append(f"- Full-pass (Acc=5, Ped>=4, Fmt>=4): {full_pass:.1f}%")
    lines.append(f"- Strict 5/5/5 (matches Gold gate): {all_555:.1f}%")
    lines.append("")
    lines.append("**Interpretation:**")
    lines.append("- If 5/5/5 >= 80%: Tuned v1 has learned the pattern — v1 holdout regression is a **generalization** problem; more data is the right v2 lever.")
    lines.append("- If 5/5/5 << 50% (esp. Ped<5 on training data): SFT didn't take — v2 needs **tuning hyperparameter** changes (more epochs, sample weighting, or accept Ped as Pro-bound).")
    lines.append("")
    lines.append("## Per-row")
    lines.append("")
    lines.append("| # | row_idx | Acc | Ped | Fmt | Strict 5/5/5? | Feedback (first 200) |")
    lines.append("|---|---|---:|---:|---:|---|---|")
    for i, r in enumerate(results, 1):
        if r.get("scores"):
            s = r["scores"]
            strict = "yes" if s["accuracy_score"] == 5 and s["pedagogy_score"] == 5 and s["formatting_score"] == 5 else "no"
            fb = (s.get("feedback_notes") or "").replace("|", "/").replace("\n", " ")[:200]
            lines.append(f"| {i} | {r['row_index']} | {s['accuracy_score']} | {s['pedagogy_score']} | {s['formatting_score']} | {strict} | {fb} |")
        else:
            err = r.get("tuned_error") or r.get("judge_error") or "(unknown)"
            lines.append(f"| {i} | {r['row_index']} | - | - | - | - | ERROR: {err[:200]} |")

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nOK: probe report -> {out_path}")
    print(f"Aggregate on Gold-set rows via Tuned: Acc {avg_acc:.2f} / Ped {avg_ped:.2f} / Fmt {avg_fmt:.2f}; Strict 5/5/5 = {all_555:.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
