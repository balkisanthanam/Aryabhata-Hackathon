"""
Phase V.2 ARM 1 — objective solver-accuracy verification for untuned gemini-3-flash on JEE.

Runs untuned `gemini-3-flash-preview` on the JEE verify set, extracts final_answer via
response_schema, and matches it against the clean JEE answer_key PROGRAMMATICALLY
(no LLM judge → no judge non-determinism, near-zero cost).

Matching:
  - MCQ (answer_key in A/B/C/D): extract option letter from final_answer; fallback to
    mapping answer_key letter -> option text and comparing.
  - Numeric (answer_key numeric): extract number from final_answer; compare with tolerance.

Resumable per-row checkpoint. Reports accuracy by subject x difficulty x figure.

CLI:
  python verify_solver_accuracy.py [--in solver_verifyset_jee.json] [--restart]
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CWD = Path(__file__).resolve().parent
sys.path.insert(0, str(CWD))
sys.path.insert(0, str(CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"))

from config import PipelineConfig, GeminiModelConfig  # noqa: E402
from gemini_client import GeminiClient  # noqa: E402

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


_LETTER_RE = re.compile(r"\b([ABCD])\b")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s).strip().lower())


def match_answer(final_answer: str, answer_key: str, options: list) -> bool:
    fa = str(final_answer).strip()
    ak = str(answer_key).strip()

    # MCQ: answer_key is a single letter A-D
    if len(ak) == 1 and ak.upper() in "ABCD":
        # 1. direct letter in the solver answer
        m = _LETTER_RE.search(fa.upper())
        if m and m.group(1) == ak.upper():
            return True
        # 2. fallback: solver gave the option VALUE; map answer_key letter -> option text
        idx = ord(ak.upper()) - ord("A")
        if 0 <= idx < len(options):
            opt = options[idx]
            opt_text = opt.get("text", opt) if isinstance(opt, dict) else opt
            if _norm(opt_text) and _norm(opt_text) in _norm(fa):
                return True
            # numeric inside the option
            onum = _NUM_RE.search(str(opt_text))
            fnum = _NUM_RE.search(fa)
            if onum and fnum and abs(float(onum.group()) - float(fnum.group())) < 1e-6:
                return True
        return False

    # Numeric integer-type
    aknum = _NUM_RE.search(ak)
    fanum = _NUM_RE.search(fa)
    if aknum and fanum:
        try:
            return abs(float(aknum.group()) - float(fanum.group())) < 1e-6
        except ValueError:
            return False
    # exact normalized string fallback
    return _norm(fa) == _norm(ak)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="in_path", default="solver_verifyset_jee.json")
    p.add_argument("--restart", action="store_true")
    args = p.parse_args()

    runs = CWD / "runs"
    runs.mkdir(exist_ok=True)
    ckpt = runs / "_verify_solver_jee_ckpt.jsonl"
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
            obj = json.loads(text) if text else {}
            final_answer = obj.get("final_answer", "")
            correct = match_answer(final_answer, rec["answer_key"], rec["problem_payload"].get("options", []))
            err = None
        except Exception as e:
            final_answer, correct, err = "", False, str(e)[:200]
        row = {"id": rec["id"], "subject": rec["subject"], "difficulty": rec.get("difficulty"),
               "has_figure": rec.get("has_figure"), "answer_key": rec["answer_key"],
               "final_answer": final_answer, "correct": correct, "error": err}
        results.append(row)
        with ckpt.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        status = "OK " if correct else ("ERR" if err else "XX ")
        print(f"[{i}/{len(records)}] {status} {rec['subject']:10} {rec.get('difficulty'):6} fig={rec.get('has_figure')} ak={rec['answer_key']!r} got={final_answer!r}")

    # Aggregate
    def agg(rows):
        n = len(rows); c = sum(1 for r in rows if r["correct"])
        return n, c, (100 * c / n if n else 0.0)

    print("\n" + "=" * 60)
    n, c, pct = agg(results)
    print(f"JEE OBJECTIVE SOLVER ACCURACY (untuned {UNTUNED_MODEL}): {pct:.1f}% ({c}/{n})")
    errs = sum(1 for r in results if r.get("error"))
    if errs:
        print(f"  (generation errors: {errs})")
    print("\nBy subject x difficulty x figure:")
    buckets = defaultdict(list)
    for r in results:
        buckets[(r["subject"], r["difficulty"], bool(r["has_figure"]))].append(r)
    print(f"  {'subject':10} {'diff':6} {'fig':5} {'N':>4} {'acc%':>6}")
    for key in sorted(buckets):
        n, c, pct = agg(buckets[key])
        print(f"  {key[0]:10} {str(key[1]):6} {str(key[2]):5} {n:>4} {pct:>6.1f}")
    # by subject, by difficulty, by figure marginals
    for dim_name, dim_idx in [("subject", 0), ("difficulty", 1), ("figure", 2)]:
        print(f"\nMarginal by {dim_name}:")
        m = defaultdict(list)
        for r in results:
            keyval = (r["subject"], r["difficulty"], bool(r["has_figure"]))[dim_idx]
            m[keyval].append(r)
        for k in sorted(m, key=lambda x: str(x)):
            n, c, pct = agg(m[k])
            print(f"  {str(k):12} {n:>4} {pct:>6.1f}%")

    # Save markdown
    out_md = runs / "_verify_solver_jee_RESULT.md"
    lines = [f"# JEE Objective Solver Accuracy — untuned {UNTUNED_MODEL}", "",
             f"**Overall: {agg(results)[2]:.1f}% ({agg(results)[1]}/{agg(results)[0]})**  (objective answer-key match, no LLM judge)", "",
             "| subject | difficulty | figure | N | acc% |", "|---|---|---|---:|---:|"]
    for key in sorted(buckets):
        n, c, pct = agg(buckets[key])
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {n} | {pct:.1f} |")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport -> {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
