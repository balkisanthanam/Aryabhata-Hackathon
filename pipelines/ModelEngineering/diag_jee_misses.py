"""Diagnostic: re-solve specific JEE verify rows with untuned gemini-3-flash and show the
model's final_answer + reasoning next to the stored key + options. Lets us judge by hand
whether a 'miss' is a genuine solver error, a key/representation artifact, or garbled text.

Usage: python diag_jee_misses.py 476 925 2091 1913 3262 3412
"""
import json
import sys
from pathlib import Path

CWD = Path(__file__).resolve().parent
sys.path.insert(0, str(CWD))
sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))

from config import PipelineConfig, GeminiModelConfig  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402
from verify_solver_accuracy import build_prompt, SYS_PROMPT, RESPONSE_SCHEMA, UNTUNED_MODEL  # noqa: E402


def main():
    ids = [int(x) for x in sys.argv[1:]] or [476, 925, 2091, 1913, 3262, 3412]
    recs = json.loads((CWD / "solver_verifyset_jee.json").read_text(encoding="utf-8"))["records"]
    by = {r["id"]: r for r in recs}
    client = GeminiClient(PipelineConfig())
    cfg = GeminiModelConfig(model_id=UNTUNED_MODEL, temperature=0.2, max_output_tokens=32768,
                            response_mime_type="application/json", response_schema=RESPONSE_SCHEMA)
    for i in ids:
        rec = by.get(i)
        if not rec:
            print(f"\n=== id {i}: NOT IN VERIFY SET"); continue
        payload = rec["problem_payload"]
        prompt = build_prompt(payload)
        try:
            resp = client.generate(model_config=cfg, prompt=prompt, system_instruction=SYS_PROMPT)
            sol = json.loads((resp.text or "").strip() or "{}")
            fa = sol.get("final_answer", "<EMPTY>") if isinstance(sol, dict) else "<NON-DICT>"
            reasoning = sol.get("reasoning", "") if isinstance(sol, dict) else ""
            opts = payload.get("options") or []
            optstr = " | ".join(f"{chr(65+j)}:{(o.get('text') if isinstance(o,dict) else o)}" for j, o in enumerate(opts))
            print(f"\n=== id {i} | {rec['subject']} | diff={rec.get('difficulty')}")
            print(f"  Q     : {payload.get('problem_text','')[:160].replace(chr(10),' ')}")
            if optstr:
                print(f"  OPTS  : {optstr[:160]}")
            print(f"  KEY   : {rec.get('answer_key')}")
            print(f"  MODEL : {fa}")
            print(f"  WHY   : {reasoning[:260].replace(chr(10),' ')}")
        except Exception as e:
            print(f"\n=== id {i}: ERROR {str(e)[:160]}")


if __name__ == "__main__":
    main()
