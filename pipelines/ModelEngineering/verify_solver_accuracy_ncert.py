"""
Phase V.2 ARM 2 — NCERT solver-accuracy verification for untuned gemini-3-flash.

NCERT answer keys are freeform → LLM-judge (accuracy_only) instead of objective match.
Uses the SAME solver prompt as ARM 1 (solver_verify_system_instruction.txt) so the two
arms are comparable. PASSES IMAGES for figure-bearing NCERT rows (images exist, unlike
JEE/KI-3) — this is the multimodal-solver test.

Resumable per-row checkpoint. Reports accuracy by subject x figure.

CLI:
  python verify_solver_accuracy_ncert.py [--in solver_verifyset_ncert.json] [--restart]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

CWD = Path(__file__).resolve().parent
sys.path.insert(0, str(CWD))
sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))

from config import PipelineConfig, GeminiModelConfig  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402
from evaluator_engine import get_evaluator  # noqa: E402

UNTUNED_MODEL = "gemini-3-flash-preview"
SYS_PROMPT = (CWD / "solver_verify_system_instruction.txt").read_text(encoding="utf-8").rstrip("\n")
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"reasoning": {"type": "string"}, "final_answer": {"type": "string"}},
    "required": ["reasoning", "final_answer"],
}


def build_prompt(payload: dict) -> str:
    problem = payload.get("problem_text", "")
    options = payload.get("options", []) or []
    lines = [problem]
    if options:
        lines.append("\nOptions:")
        for i, opt in enumerate(options):
            letter = chr(ord("A") + i)
            text = opt.get("text", opt) if isinstance(opt, dict) else opt
            lines.append(f"  {letter}. {text}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="in_path", default="solver_verifyset_ncert.json")
    p.add_argument("--restart", action="store_true")
    args = p.parse_args()

    runs = CWD / "runs"
    runs.mkdir(exist_ok=True)
    ckpt = runs / "_verify_solver_ncert_ckpt.jsonl"
    if args.restart and ckpt.exists():
        ckpt.unlink()

    records = json.loads((CWD / args.in_path).read_text(encoding="utf-8"))["records"]
    done = {}
    if ckpt.exists():
        for line in ckpt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["id"]] = r

    config = PipelineConfig()
    client = GeminiClient(config)
    evaluator = get_evaluator()
    model_cfg = GeminiModelConfig(
        model_id=UNTUNED_MODEL, temperature=0.2, max_output_tokens=32768,
        response_mime_type="application/json", response_schema=RESPONSE_SCHEMA,
    )

    results = list(done.values())
    for i, rec in enumerate(records, 1):
        if rec["id"] in done:
            continue
        prompt = build_prompt(rec["problem_payload"])
        try:
            resp = client.generate(model_config=model_cfg, prompt=prompt, system_instruction=SYS_PROMPT,
                                   image_urls=rec.get("image_urls") or None)
            text = (resp.text or "").strip()
            gen_solution = json.loads(text) if text else {}
            er = evaluator.evaluate_solution(
                problem_payload=rec["problem_payload"],
                generated_solution=gen_solution,
                actual_answer_key=rec.get("answer_key"),
                mode="accuracy_only",
            )
            acc = er.accuracy_score
            correct = (acc == 5)
            err = None
        except Exception as e:
            acc, correct, err = None, False, str(e)[:200]
        row = {"id": rec["id"], "subject": rec["subject"], "has_figure": rec.get("has_figure"),
               "accuracy_score": acc, "correct": correct, "error": err}
        results.append(row)
        with ckpt.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        status = "OK " if correct else ("ERR" if err else "XX ")
        print(f"[{i}/{len(records)}] {status} {rec['subject']:10} fig={rec.get('has_figure')} acc={acc}")

    def agg(rows):
        n = len(rows); c = sum(1 for r in rows if r["correct"])
        return n, c, (100 * c / n if n else 0.0)

    print("\n" + "=" * 60)
    n, c, pct = agg(results)
    print(f"NCERT JUDGED SOLVER ACCURACY (untuned {UNTUNED_MODEL}, accuracy_only): {pct:.1f}% ({c}/{n})")
    errs = sum(1 for r in results if r.get("error"))
    if errs:
        print(f"  (generation/judge errors: {errs})")
    print("\nBy subject x figure:")
    buckets = defaultdict(list)
    for r in results:
        buckets[(r["subject"], bool(r["has_figure"]))].append(r)
    print(f"  {'subject':10} {'fig':5} {'N':>4} {'acc%':>6}")
    for key in sorted(buckets):
        n, c, pct = agg(buckets[key])
        print(f"  {key[0]:10} {str(key[1]):5} {n:>4} {pct:>6.1f}")

    out_md = runs / "_verify_solver_ncert_RESULT.md"
    lines = [f"# NCERT Judged Solver Accuracy — untuned {UNTUNED_MODEL}", "",
             f"**Overall: {agg(results)[2]:.1f}% ({agg(results)[1]}/{agg(results)[0]})**  (accuracy_only LLM judge; images passed for figure rows)", "",
             "| subject | figure | N | acc% |", "|---|---|---:|---:|"]
    for key in sorted(buckets):
        n, c, pct = agg(buckets[key])
        lines.append(f"| {key[0]} | {key[1]} | {n} | {pct:.1f} |")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport -> {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
