"""Diagnostic: re-solve specific NCERT verify rows with untuned gemini-3-flash and show
the model's final_answer next to the stored key + the accuracy_only judge's reasoning.
Confirms whether Phase V NCERT 'misses' are genuine solver errors or measurement artifacts
(MAX_TOKENS truncation / judge harshness on freeform/structured answers).

Usage: python diag_ncert_misses.py 447 1154 1155 1167 1168 317 675 598 394 787
"""
import json
import sys
from pathlib import Path

CWD = Path(__file__).resolve().parent
sys.path.insert(0, str(CWD))
sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))

from config import PipelineConfig, GeminiModelConfig  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402
from evaluator_engine import get_evaluator  # noqa: E402
from verify_solver_accuracy_ncert import build_prompt, SYS_PROMPT, RESPONSE_SCHEMA, UNTUNED_MODEL  # noqa: E402


def main():
    ids = [int(x) for x in sys.argv[1:]] or [447, 1154, 1155, 1167, 1168, 317, 675, 598, 394, 787]
    recs = json.loads((CWD / "solver_verifyset_ncert.json").read_text(encoding="utf-8"))["records"]
    by = {r["id"]: r for r in recs}
    client = GeminiClient(PipelineConfig())
    evaluator = get_evaluator()
    # higher token budget to rule out MAX_TOKENS truncation as the cause
    cfg = GeminiModelConfig(model_id=UNTUNED_MODEL, temperature=0.2, max_output_tokens=65536,
                            response_mime_type="application/json", response_schema=RESPONSE_SCHEMA)
    for i in ids:
        rec = by.get(i)
        if not rec:
            print(f"\n=== id {i}: NOT IN VERIFY SET"); continue
        prompt = build_prompt(rec["problem_payload"])
        try:
            resp = client.generate(model_config=cfg, prompt=prompt, system_instruction=SYS_PROMPT,
                                   image_urls=rec.get("image_urls") or None)
            text = (resp.text or "").strip()
            sol = json.loads(text) if text else {}
            fa = sol.get("final_answer", "<EMPTY/TRUNCATED>") if isinstance(sol, dict) else "<NON-DICT>"
            er = evaluator.evaluate_solution(problem_payload=rec["problem_payload"], generated_solution=sol,
                                             actual_answer_key=rec.get("answer_key"), mode="accuracy_only")
            fb = getattr(er, "feedback_notes", None) or getattr(er, "feedback", None) or ""
            print(f"\n=== id {i} | {rec['subject']} | acc={er.accuracy_score}")
            print(f"  KEY  : {str(rec.get('answer_key'))[:120]}")
            print(f"  MODEL: {str(fa)[:120]}")
            print(f"  JUDGE: {str(fb)[:240]}")
        except Exception as e:
            print(f"\n=== id {i}: ERROR {str(e)[:160]}")


if __name__ == "__main__":
    main()
