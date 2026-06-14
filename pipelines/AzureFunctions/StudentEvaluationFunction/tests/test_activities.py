"""
Standalone activity tester — run individual Gemini-calling pipeline steps
in isolation WITHOUT starting the Function host or touching the database.

Usage examples:
  python tests/test_activities.py split-hw   --image "path/to/student_work.jpg"
  python tests/test_activities.py parse-ref  --text-ref "13.9" --subject Physics --chapter "Oscillations"
  python tests/test_activities.py split-tb   --image "path/to/textbook_page.jpg"
  python tests/test_activities.py evaluate   --student-image "page1.jpg" "page2.jpg" --problem-number "13.9" "13.10" [--textbook-image "tb.jpg"]
  python tests/test_activities.py raw-gemini --prompt-file "prompt.txt" --image "img.jpg"

All outputs are saved to tests/output/<timestamp>_<command>/ for inspection.
See tests/HOW_TO_TEST.md for full documentation.
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Load local.settings.json into env (same trick as test_durable_e2e.py) ────
_settings_path = PROJECT_ROOT / "local.settings.json"
if _settings_path.exists():
    with open(_settings_path) as f:
        _vals = json.load(f).get("Values", {})
    for k, v in _vals.items():
        if k not in os.environ:
            os.environ[k] = v

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _output_dir(command: str) -> Path:
    """Create and return a timestamped output directory."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = Path(__file__).parent / "output" / f"{ts}_{command}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(out: Path, name: str, data):
    """Write JSON for dicts/lists, plain text otherwise."""
    fp = out / name
    if isinstance(data, (dict, list)):
        fp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    elif isinstance(data, bytes):
        fp.write_bytes(data)
    else:
        fp.write_text(str(data), encoding="utf-8")
    log.info(f"  ↳ saved  {fp}")


def _read_image(path: str) -> bytes:
    """Read an image file and return raw bytes."""
    p = Path(path)
    if not p.exists():
        log.error(f"Image not found: {path}")
        sys.exit(1)
    return p.read_bytes()


def _print_banner(title: str, result: dict, duration_ms: float):
    """Print a formatted summary."""
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"  Duration : {duration_ms:,.0f} ms")
    model = result.get("model") or "(unknown)"
    print(f"  Model    : {model}")
    usage = result.get("usage_metadata")
    if usage:
        pin = usage.get("prompt_tokens", "?")
        pout = usage.get("completion_tokens", "?")
        ptot = usage.get("total_tokens", "?")
        print(f"  Tokens   : {pin} in  /  {pout} out  /  {ptot} total")
    print(f"{'='*65}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Command: split-hw
#   Mirrors activities/split_student_hw.py
#   Input : student handwriting image
#   Output: bounding-box JSON + cropped per-problem images
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_split_hw(args):
    from utils.gemini_client import call_gemini, MODEL_BOUNDING_BOX
    from utils.prompt_loader import load_prompt
    from utils.image_processing import group_and_stitch, image_bytes_to_base64

    out = _output_dir("split_hw")
    image_paths = args.image  # list (nargs="+")
    log.info("── split-hw: Student Handwriting Split ──")
    log.info(f"   Images ({len(image_paths)}): {image_paths}")

    # Load prompt from blob
    prompt = load_prompt("Student_HW_Split.md")
    _save(out, "prompt.md", prompt)

    # Prepare content parts: all images first, then prompt (mirrors activity)
    image_bytes_list = []
    content_parts = []
    for idx, img_path in enumerate(image_paths):
        img_bytes = _read_image(img_path)
        image_bytes_list.append(img_bytes)
        suffix = Path(img_path).suffix
        _save(out, f"input_image_{idx}{suffix}", img_bytes)
        content_parts.append({"mime_type": "image/jpeg", "data": img_bytes})
    content_parts.append(prompt)

    model = args.model or MODEL_BOUNDING_BOX
    log.info(f"   Model : {model}")
    log.info("   Calling Gemini …")

    start = time.time()
    gemini_resp = call_gemini(
        model_id=model,
        content_parts=content_parts,
        response_json=True,
        temperature=0.1,
    )
    duration_ms = (time.time() - start) * 1000

    parsed = gemini_resp["parsed_result"]
    _save(out, "raw_response.txt", gemini_resp.get("raw_response_text", ""))
    _save(out, "parsed_result.json", parsed)
    _save(out, "meta.json", {
        "model": gemini_resp.get("model"),
        "usage_metadata": gemini_resp.get("usage_metadata"),
        "duration_ms": duration_ms,
    })

    _print_banner("Student Handwriting Split", gemini_resp, duration_ms)

    solutions = parsed.get("solutions", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(solutions, list):
        print(f"  Bounding boxes detected: {len(solutions)}")
        for i, s in enumerate(solutions):
            pid = s.get("problem_id", f"#{i+1}")
            box = s.get("box_2d", "?")
            print(f"    [{i+1}] {pid}  box_2d={box}")

        # Optional: crop images with PIL
        if not args.skip_crop:
            log.info("  Cropping with PIL …")
            try:
                cropped = group_and_stitch(solutions, image_bytes_list)
                for item in cropped:
                    fname = f"crop_{item['problem_id']}.jpg"
                    _save(out, fname, item["image_bytes"])
                print(f"  Cropped {len(cropped)} problem image(s) → {out}")
            except Exception as e:
                log.warning(f"  Cropping failed (non-fatal): {e}")
    else:
        print(f"  Result: {json.dumps(parsed, indent=2)[:500]}")

    print(f"\n  Output dir: {out}")
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════
# Command: parse-ref
#   Mirrors activities/parse_text_ref.py
#   Input : free-form problem text like "13.8, 13.9"
#   Output: structured { metadata, exercises[{exercise_label, problem_numbers}] }
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_parse_ref(args):
    from utils.gemini_client import call_gemini, MODEL_TEXT_PARSE
    from utils.prompt_loader import load_prompt, fill_template

    out = _output_dir("parse_ref")
    log.info("── parse-ref: Text Reference Parsing ──")
    log.info(f"   Text ref : {args.text_ref}")
    log.info(f"   Subject  : {args.subject}, Chapter: {args.chapter}")

    prompt_template = load_prompt("Text_ParsingPrompt.md")
    filled = fill_template(prompt_template, user_input=args.text_ref)
    _save(out, "prompt.md", filled)

    model = args.model or MODEL_TEXT_PARSE
    log.info(f"   Model : {model}")
    log.info("   Calling Gemini …")

    start = time.time()
    gemini_resp = call_gemini(
        model_id=model,
        content_parts=[filled],
        response_json=True,
        temperature=0.1,
    )
    duration_ms = (time.time() - start) * 1000

    parsed = gemini_resp["parsed_result"]
    _save(out, "raw_response.txt", gemini_resp.get("raw_response_text", ""))
    _save(out, "parsed_result.json", parsed)
    _save(out, "meta.json", {
        "model": gemini_resp.get("model"),
        "usage_metadata": gemini_resp.get("usage_metadata"),
        "duration_ms": duration_ms,
    })

    _print_banner("Text Reference Parsing", gemini_resp, duration_ms)

    if isinstance(parsed, dict):
        exercises = parsed.get("exercises", [])
        total = sum(len(ex.get("problem_numbers", [])) for ex in exercises)
        print(f"  Exercises: {len(exercises)},  Total problems: {total}")
        for ex in exercises:
            label = ex.get("exercise_label", "(none)")
            nums = ex.get("problem_numbers", [])
            print(f"    Exercise '{label}': {nums}")
    else:
        print(f"  Result: {json.dumps(parsed, indent=2)[:500]}")

    print(f"\n  Output dir: {out}")
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════
# Command: split-tb
#   Mirrors activities/split_textbook.py  (Path B)
#   Input : textbook page image (photo of problems)
#   Output: bounding-box JSON + cropped per-problem images
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_split_textbook(args):
    from utils.gemini_client import call_gemini, MODEL_BOUNDING_BOX
    from utils.prompt_loader import load_prompt
    from utils.image_processing import group_and_stitch

    out = _output_dir("split_tb")
    image_paths = args.image  # list (nargs="+")
    log.info("── split-tb: Textbook Problem Splitting ──")
    log.info(f"   Images ({len(image_paths)}): {image_paths}")

    prompt = load_prompt("SplitTextBookProblems.txt")
    _save(out, "prompt.txt", prompt)

    # All images first, then prompt (mirrors activity)
    image_bytes_list = []
    content_parts = []
    for idx, img_path in enumerate(image_paths):
        img_bytes = _read_image(img_path)
        image_bytes_list.append(img_bytes)
        suffix = Path(img_path).suffix
        _save(out, f"input_image_{idx}{suffix}", img_bytes)
        content_parts.append({"mime_type": "image/jpeg", "data": img_bytes})
    content_parts.append(prompt)

    model = args.model or MODEL_BOUNDING_BOX
    log.info(f"   Model : {model}")
    log.info("   Calling Gemini …")

    start = time.time()
    gemini_resp = call_gemini(
        model_id=model,
        content_parts=content_parts,
        response_json=True,
        temperature=0.1,
    )
    duration_ms = (time.time() - start) * 1000

    parsed = gemini_resp["parsed_result"]
    _save(out, "raw_response.txt", gemini_resp.get("raw_response_text", ""))
    _save(out, "parsed_result.json", parsed)
    _save(out, "meta.json", {
        "model": gemini_resp.get("model"),
        "usage_metadata": gemini_resp.get("usage_metadata"),
        "duration_ms": duration_ms,
    })

    _print_banner("Textbook Problem Splitting", gemini_resp, duration_ms)

    solutions = parsed.get("solutions", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(solutions, list):
        print(f"  Problem regions detected: {len(solutions)}")
        for i, s in enumerate(solutions):
            pid = s.get("problem_id", f"#{i+1}")
            box = s.get("box_2d", "?")
            print(f"    [{i+1}] {pid}  box_2d={box}")

        if not args.skip_crop:
            log.info("  Cropping with PIL …")
            try:
                cropped = group_and_stitch(solutions, image_bytes_list)
                for item in cropped:
                    _save(out, f"crop_{item['problem_id']}.jpg", item["image_bytes"])
                print(f"  Cropped {len(cropped)} problem image(s) → {out}")
            except Exception as e:
                log.warning(f"  Cropping failed (non-fatal): {e}")
    else:
        print(f"  Result: {json.dumps(parsed, indent=2)[:500]}")

    print(f"\n  Output dir: {out}")
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════
# Command: evaluate
#   Mirrors activities/evaluate_batch.py  (single problem, text_ref path)
#   Input : student image + problem number + chapter PDF (from blob)
#   Output: evaluation JSON
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_evaluate(args):
    """
    v4 Unified Evaluation: sends full student page images + problem list to Gemini.
    No image splitting — Gemini locates the relevant work on the student's pages.
    Optionally includes textbook page images as reference context.
    """
    from utils.gemini_client import call_gemini, MODEL_EVALUATION
    from utils.prompt_loader import load_prompt, fill_template
    from utils.blob_storage import fetch_blob_content

    out = _output_dir("evaluate")
    problems = args.problem_number  # list of strings (nargs="+")
    student_images = args.student_image  # list of paths (nargs="+")
    textbook_images = args.textbook_image or []  # optional list of paths

    log.info("── evaluate: Unified Multi-Problem Evaluation (v4) ──")
    log.info(f"   Student images  : {student_images}")
    log.info(f"   Textbook images : {textbook_images or '(none)'}")
    log.info(f"   Problems        : {problems}")
    log.info(f"   Subject         : {args.subject}")
    log.info(f"   Chapter         : {args.chapter}")

    # Read all student page images
    student_pages = []
    for i, img_path in enumerate(student_images):
        img_bytes = _read_image(img_path)
        _save(out, f"student_page_{i}{Path(img_path).suffix}", img_bytes)
        student_pages.append(img_bytes)
    log.info(f"   Loaded {len(student_pages)} student page(s)")

    # Read optional textbook page images
    textbook_pages = []
    for i, img_path in enumerate(textbook_images):
        img_bytes = _read_image(img_path)
        _save(out, f"textbook_page_{i}{Path(img_path).suffix}", img_bytes)
        textbook_pages.append(img_bytes)
    if textbook_pages:
        log.info(f"   Loaded {len(textbook_pages)} textbook page(s)")

    # Build Problems list for prompt
    problem_lines = []
    for pn in problems:
        desc = f"Problem {pn}"
        if args.exercise_label:
            desc = f"Exercise {args.exercise_label}, {desc}"
        problem_lines.append(f"- {desc}")
    problems_str = "\n".join(problem_lines)

    # Load and fill the evaluation prompt
    prompt_template = load_prompt("Evaluation.txt")
    filled = fill_template(
        prompt_template,
        **{
            "class": args.class_val,
            "Subject": args.subject,
            "Problems": problems_str,
        }
    )
    _save(out, "prompt.txt", filled)

    # Build content parts: prompt → textbook pages → student pages → optional PDF
    content_parts = [filled]

    for i, tb_bytes in enumerate(textbook_pages):
        content_parts.append(f"\n[TEXTBOOK PAGE {i + 1}]")
        content_parts.append({"mime_type": "image/jpeg", "data": tb_bytes})

    for i, page_bytes in enumerate(student_pages):
        content_parts.append(f"\n[STUDENT PAGE {i + 1}]")
        content_parts.append({"mime_type": "image/jpeg", "data": page_bytes})

    # Load PDF if provided
    if args.pdf_url:
        log.info(f"   PDF URL: {args.pdf_url}")
        pdf_bytes = fetch_blob_content(args.pdf_url, as_text=False)
        _save(out, "reference.pdf", pdf_bytes)
        content_parts.append("\n[REFERENCE MATERIAL PDF]")
        content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})

    if args.pdf_file:
        log.info(f"   PDF File: {args.pdf_file}")
        pdf_bytes = Path(args.pdf_file).read_bytes()
        _save(out, "reference.pdf", pdf_bytes)
        content_parts.append("\n[REFERENCE MATERIAL PDF]")
        content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})

    model = args.model or MODEL_EVALUATION
    log.info(f"   Model : {model}")
    log.info("   Calling Gemini …")

    start = time.time()
    gemini_resp = call_gemini(
        model_id=model,
        content_parts=content_parts,
        response_json=True,
    )
    duration_ms = (time.time() - start) * 1000

    parsed = gemini_resp["parsed_result"]
    _save(out, "raw_response.txt", gemini_resp.get("raw_response_text", ""))
    _save(out, "parsed_result.json", parsed)
    _save(out, "meta.json", {
        "model": gemini_resp.get("model"),
        "usage_metadata": gemini_resp.get("usage_metadata"),
        "duration_ms": duration_ms,
        "problems_requested": problems,
        "student_pages": len(student_pages),
        "textbook_pages": len(textbook_pages),
    })

    _print_banner("Unified Multi-Problem Evaluation (v4)", gemini_resp, duration_ms)

    # Handle {"evaluations": [...]} response format
    if isinstance(parsed, dict) and "evaluations" in parsed:
        evals = parsed["evaluations"]
        print(f"  Problems evaluated: {len(evals)}")
        for ev in evals:
            pid = ev.get("problem_id", "?")
            found = ev.get("found_in_student_work", "?")
            status = ev.get("evaluation_status", "?")
            print(f"  ── Problem {pid}: found={found}, status={status}")
            feedback = ev.get("feedback_for_student", "")
            if feedback:
                preview = str(feedback)[:200] + ("…" if len(str(feedback)) > 200 else "")
                print(f"     Feedback: {preview}")
    elif isinstance(parsed, dict):
        status = parsed.get("evaluation_status", "?")
        print(f"  Status : {status}")
    else:
        print(f"  Result: {json.dumps(parsed, indent=2)[:500]}")

    print(f"\n  Output dir: {out}")
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════
# Command: raw-gemini
#   Free-form: any prompt + optional image/PDF
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_raw_gemini(args):
    from utils.gemini_client import call_gemini, MODEL_EVALUATION

    out = _output_dir("raw_gemini")
    log.info("── raw-gemini: Freeform Gemini Call ──")

    prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
    _save(out, "prompt.txt", prompt_text)
    log.info(f"   Prompt: {args.prompt_file} ({len(prompt_text)} chars)")

    content_parts = []

    if args.image:
        image_bytes = _read_image(args.image)
        content_parts.append({"mime_type": "image/jpeg", "data": image_bytes})
        log.info(f"   Image : {args.image}")

    if args.pdf:
        pdf_bytes = Path(args.pdf).read_bytes()
        content_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})
        log.info(f"   PDF   : {args.pdf}")

    content_parts.append(prompt_text)

    model = args.model or MODEL_EVALUATION
    log.info(f"   Model     : {model}")
    log.info(f"   JSON mode : {args.json_mode}")
    log.info("   Calling Gemini …")

    start = time.time()
    gemini_resp = call_gemini(
        model_id=model,
        content_parts=content_parts,
        response_json=args.json_mode,
        temperature=args.temperature,
    )
    duration_ms = (time.time() - start) * 1000

    parsed = gemini_resp["parsed_result"]
    _save(out, "raw_response.txt", gemini_resp.get("raw_response_text", ""))
    _save(out, "parsed_result.json" if isinstance(parsed, (dict, list)) else "parsed_result.txt", parsed)
    _save(out, "meta.json", {
        "model": gemini_resp.get("model"),
        "usage_metadata": gemini_resp.get("usage_metadata"),
        "duration_ms": duration_ms,
    })

    _print_banner("Raw Gemini Call", gemini_resp, duration_ms)
    if isinstance(parsed, (dict, list)):
        print(f"  {json.dumps(parsed, indent=2)[:600]}")
    else:
        print(f"  {str(parsed)[:600]}")

    print(f"\n  Output dir: {out}")
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Test individual Gemini-calling activities in isolation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model", default=None,
        help="Override Gemini model ID (default: per-activity model constant)"
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # ── split-hw ──
    p = subs.add_parser("split-hw", help="Split student handwriting image(s) → per-problem bounding boxes + crops")
    p.add_argument("--image", required=True, nargs="+", help="Path(s) to student work image(s) (JPG/PNG). Multiple files = multi-page.")
    p.add_argument("--skip-crop", action="store_true", help="Skip PIL cropping, only return bounding-box JSON")

    # ── parse-ref ──
    p = subs.add_parser("parse-ref", help="Parse free-form text reference → structured problem numbers")
    p.add_argument("--text-ref", required=True, help='e.g. "13.8, 13.9"  or  "Exercise 13.1 Q4,Q5"')
    p.add_argument("--subject", default="Physics", help="Subject (default: Physics)")
    p.add_argument("--chapter", default="", help="Chapter title")

    # ── split-tb ──
    p = subs.add_parser("split-tb", help="Split textbook page image(s) → per-problem bounding boxes + crops")
    p.add_argument("--image", required=True, nargs="+", help="Path(s) to textbook page image(s) (JPG/PNG). Multiple files = multi-page.")
    p.add_argument("--skip-crop", action="store_true", help="Skip PIL cropping")

    # ── evaluate ──
    p = subs.add_parser("evaluate", help="Evaluate student solution(s) — sends full page images + problem list to Gemini")
    p.add_argument("--student-image", required=True, nargs="+", help="Path(s) to student work page images (JPG/PNG). Multiple = multi-page.")
    p.add_argument("--problem-number", required=True, nargs="+", help='Problem number(s) to evaluate, e.g. "13.9" "13.10"')
    p.add_argument("--textbook-image", nargs="+", default=None, help="Optional path(s) to textbook/exam page images for reference context.")
    p.add_argument("--subject", default="Physics")
    p.add_argument("--class-val", default="11", help="Class (default: 11)")
    p.add_argument("--chapter", default="", help="Chapter title")
    p.add_argument("--exercise-label", default=None, help='e.g. "Exercise 13.1"')
    p.add_argument("--pdf-url", default=None, help="Blob URL of the chapter PDF (for reference)")
    p.add_argument("--pdf-file", default=None, help="Local path to chapter PDF (alternative to --pdf-url)")

    # ── raw-gemini ──
    p = subs.add_parser("raw-gemini", help="Call Gemini with a custom prompt + optional image/PDF")
    p.add_argument("--prompt-file", required=True, help="Path to prompt text file")
    p.add_argument("--image", default=None, help="Optional image path")
    p.add_argument("--pdf", default=None, help="Optional PDF path")
    p.add_argument("--json-mode", action="store_true", help="Request JSON response from Gemini")
    p.add_argument("--temperature", type=float, default=None)

    args = parser.parse_args()

    dispatch = {
        "split-hw":    cmd_split_hw,
        "parse-ref":   cmd_parse_ref,
        "split-tb":    cmd_split_textbook,
        "evaluate":    cmd_evaluate,
        "raw-gemini":  cmd_raw_gemini,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
