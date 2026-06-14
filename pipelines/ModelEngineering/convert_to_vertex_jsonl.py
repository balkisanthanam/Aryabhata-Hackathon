"""
Convert OpenAI ChatML SFT JSONL to Vertex Gemini-native tuning format.

Input:  gold_sft_dataset.jsonl (produced by jsonl_exporter.py)
        {"messages":[{"role":"system","content":...},
                     {"role":"user","content": <str OR list-of-parts>},
                     {"role":"model","content":...}]}

  Text-only user content (string):
    "content": "Solve this problem:\\n\\n{...json...}"

  Multimodal user content (list of parts, written by jsonl_exporter.py --multimodal):
    "content": [
        {"type": "text", "text": "Solve this problem:\\n\\n{...json...}"},
        {"type": "image_url", "image_url": {"url": "https://..."}}
    ]

Output: gold_sft_vertex_v[1|2].jsonl (Vertex Gemini SFT)
        {"systemInstruction":{"role":"system","parts":[{"text":...}]},
         "contents":[{"role":"user","parts":[{"text":...}, {"inlineData":{"mimeType":..., "data":<b64>}}]},
                     {"role":"model","parts":[{"text":...}]}]}

Per-line validations (fail loud — no silent skips):
  1. JSON parses
  2. messages has system + user + model in that order
  3. System content byte-equals canonical_system_instruction.txt (rstripped) -- strict mode
  4. Every text part is non-empty (whitespace-only counts as empty)
  5. Model content parses to {"steps":[...], "final_answer":...}
  6. Rough token estimate (chars/4 + 258/image) < 131_072 (Gemini 2.5 Flash context cap)
  7. Aggregate: lines_out == lines_in

CLI:
  # Text-only:
  python convert_to_vertex_jsonl.py --in gold_sft_dataset.jsonl --out gold_sft_vertex_v1.jsonl
  # Multimodal (fetches image bytes, embeds as base64 inlineData):
  python convert_to_vertex_jsonl.py --in gold_sft_dataset_v2.jsonl --out gold_sft_vertex_v2.jsonl --multimodal
  # Skip system-prompt byte-equality assertion:
  python convert_to_vertex_jsonl.py --no-strict
"""

import argparse
import base64
import json
import sys
from pathlib import Path

CWD = Path(__file__).resolve().parent
CANONICAL_PATH = CWD / "canonical_system_instruction.txt"
TOKEN_CHAR_RATIO = 4
IMAGE_TOKEN_ESTIMATE = 258  # per-image rough estimate per Vertex Gemini docs
MODEL_CONTEXT_CAP = 131_072

# sys.path setup so we can import _fetch_image_bytes from gemini_client when --multimodal
_extraction_dir = CWD.parent / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
if _extraction_dir.exists() and str(_extraction_dir) not in sys.path:
    sys.path.insert(0, str(_extraction_dir))


class ConversionError(Exception):
    """Raised when a training line fails validation. Carries the line number."""
    def __init__(self, line_no: int, msg: str):
        super().__init__(f"line {line_no}: {msg}")
        self.line_no = line_no


def load_canonical_system() -> str:
    raw = CANONICAL_PATH.read_text(encoding="utf-8")
    return raw.rstrip("\n")


# Per-process cache so repeated image URLs aren't re-fetched within a single conversion.
_IMAGE_BYTES_CACHE: dict = {}


def _fetch_image_part(url: str, line_no: int) -> dict:
    """Fetch image bytes + mime, return a Vertex inlineData part. Cached per-URL."""
    cached = _IMAGE_BYTES_CACHE.get(url)
    if cached is None:
        try:
            from gemini_client import GeminiClient
            from config import PipelineConfig
        except ImportError as e:
            raise ConversionError(line_no, f"gemini_client unavailable for image fetch: {e}")
        # Build a one-shot GeminiClient just to use _fetch_image_bytes (light helper).
        client = _IMAGE_BYTES_CACHE.get("__client__")
        if client is None:
            client = GeminiClient(PipelineConfig())
            _IMAGE_BYTES_CACHE["__client__"] = client
        try:
            img_bytes, mime = client._fetch_image_bytes(url)
        except Exception as e:
            raise ConversionError(line_no, f"image fetch failed for {url[:80]!r}: {e}")
        cached = (img_bytes, mime)
        _IMAGE_BYTES_CACHE[url] = cached
    img_bytes, mime = cached
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(img_bytes).decode("ascii")}}


def _convert_user_content(user_content, line_no: int, multimodal: bool) -> tuple[list, int, int]:
    """Convert ChatML user content (string OR list-of-parts) to Vertex parts list.

    Returns (parts, text_chars, image_count). Raises ConversionError on invalid shape.
    """
    if isinstance(user_content, str):
        if not user_content.strip():
            raise ConversionError(line_no, "user.content (string) is empty")
        return [{"text": user_content}], len(user_content), 0

    if not isinstance(user_content, list) or not user_content:
        raise ConversionError(line_no, f"user.content must be string or non-empty list, got {type(user_content).__name__}")

    parts = []
    text_chars = 0
    image_count = 0
    for i, part in enumerate(user_content):
        if not isinstance(part, dict):
            raise ConversionError(line_no, f"user.content[{i}] is not a dict")
        ptype = part.get("type")
        if ptype == "text":
            t = part.get("text", "")
            if not isinstance(t, str) or not t.strip():
                raise ConversionError(line_no, f"user.content[{i}] text is empty")
            parts.append({"text": t})
            text_chars += len(t)
        elif ptype == "image_url":
            if not multimodal:
                raise ConversionError(line_no, f"user.content[{i}] is image_url but --multimodal not set; re-run with --multimodal or use a text-only input file")
            url_obj = part.get("image_url") or {}
            url = url_obj.get("url") if isinstance(url_obj, dict) else None
            if not url:
                raise ConversionError(line_no, f"user.content[{i}] image_url missing url")
            parts.append(_fetch_image_part(url, line_no))
            image_count += 1
        else:
            raise ConversionError(line_no, f"user.content[{i}] unknown type {ptype!r} (expected 'text' or 'image_url')")
    if not parts:
        raise ConversionError(line_no, "user.content produced zero parts")
    return parts, text_chars, image_count


def validate_and_convert(line_no: int, raw_line: str, canonical_system: str, strict: bool, multimodal: bool) -> tuple[dict, int]:
    """Returns (vertex_obj, image_count_for_this_row)."""
    try:
        obj = json.loads(raw_line)
    except json.JSONDecodeError as e:
        raise ConversionError(line_no, f"invalid JSON: {e}")

    messages = obj.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        raise ConversionError(line_no, f"expected 3 messages, got {len(messages) if isinstance(messages, list) else type(messages).__name__}")

    sys_msg, user_msg, model_msg = messages
    if sys_msg.get("role") != "system":
        raise ConversionError(line_no, f"messages[0].role expected 'system', got {sys_msg.get('role')!r}")
    if user_msg.get("role") != "user":
        raise ConversionError(line_no, f"messages[1].role expected 'user', got {user_msg.get('role')!r}")
    if model_msg.get("role") != "model":
        raise ConversionError(line_no, f"messages[2].role expected 'model', got {model_msg.get('role')!r}")

    sys_text = sys_msg.get("content", "")
    model_text = model_msg.get("content", "")

    for label, text in (("system", sys_text), ("model", model_text)):
        if not isinstance(text, str) or not text.strip():
            raise ConversionError(line_no, f"{label}.content is empty or non-string")

    user_parts, user_text_chars, image_count = _convert_user_content(user_msg.get("content"), line_no, multimodal)

    if strict and sys_text != canonical_system:
        diverge = next((i for i, (a, b) in enumerate(zip(sys_text, canonical_system)) if a != b), min(len(sys_text), len(canonical_system)))
        raise ConversionError(
            line_no,
            f"system content drifts from canonical (first diff at char {diverge}; "
            f"file_len={len(canonical_system)} train_len={len(sys_text)}). "
            f"Re-export training data via jsonl_exporter or update canonical_system_instruction.txt."
        )

    try:
        model_obj = json.loads(model_text)
    except json.JSONDecodeError as e:
        raise ConversionError(line_no, f"model content is not valid JSON: {e}")
    if not isinstance(model_obj, dict) or "steps" not in model_obj or "final_answer" not in model_obj:
        raise ConversionError(line_no, "model content must be {steps:[...], final_answer:...}")
    if not isinstance(model_obj["steps"], list) or len(model_obj["steps"]) == 0:
        raise ConversionError(line_no, "model.steps must be a non-empty list")

    total_tokens_est = (len(sys_text) + user_text_chars + len(model_text)) // TOKEN_CHAR_RATIO + image_count * IMAGE_TOKEN_ESTIMATE
    if total_tokens_est >= MODEL_CONTEXT_CAP:
        raise ConversionError(line_no, f"estimated token count {total_tokens_est} >= {MODEL_CONTEXT_CAP} (images={image_count})")

    return {
        "systemInstruction": {"role": "system", "parts": [{"text": sys_text}]},
        "contents": [
            {"role": "user", "parts": user_parts},
            {"role": "model", "parts": [{"text": model_text}]},
        ],
    }, image_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in", dest="in_path", default="gold_sft_dataset.jsonl", help="Input ChatML JSONL")
    parser.add_argument("--out", dest="out_path", default="gold_sft_vertex_v1.jsonl", help="Output Vertex JSONL")
    parser.add_argument("--no-strict", action="store_true", help="Skip system-instruction byte-equality assertion (default: strict)")
    parser.add_argument(
        "--multimodal", action="store_true",
        help="Accept list-of-parts user content (text + image_url) and emit Vertex inlineData. "
             "Requires gemini_client + Azure Blob credentials to fetch image bytes.",
    )
    args = parser.parse_args()

    in_path = (CWD / args.in_path) if not Path(args.in_path).is_absolute() else Path(args.in_path)
    out_path = (CWD / args.out_path) if not Path(args.out_path).is_absolute() else Path(args.out_path)
    strict = not args.no_strict

    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        return 2

    canonical_system = load_canonical_system()
    print(f"Canonical system instruction: {len(canonical_system)} bytes  (strict={strict}, multimodal={args.multimodal})")
    print(f"Reading:  {in_path}")
    print(f"Writing:  {out_path}")

    in_lines = 0
    out_lines = 0
    total_images = 0
    lines_with_images = 0
    with in_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for raw in fin:
            raw = raw.strip()
            if not raw:
                continue
            in_lines += 1
            try:
                vertex_obj, image_count = validate_and_convert(in_lines, raw, canonical_system, strict, args.multimodal)
            except ConversionError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 1
            fout.write(json.dumps(vertex_obj, ensure_ascii=False) + "\n")
            out_lines += 1
            if image_count:
                lines_with_images += 1
                total_images += image_count

    if in_lines != out_lines:
        print(f"ERROR: line count mismatch in={in_lines} out={out_lines}", file=sys.stderr)
        return 1

    print(f"OK: converted {in_lines} lines -> {out_path}")
    if args.multimodal:
        print(f"     {lines_with_images} lines contain {total_images} image parts (avg "
              f"{total_images / max(lines_with_images, 1):.1f} images/line for image-bearing rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
