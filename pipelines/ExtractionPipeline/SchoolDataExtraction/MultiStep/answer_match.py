"""answer_match.py — robust JEE objective answer comparator + key-sanity validation.

Single source of truth for "did the model's final_answer match the stored answer_key?"
Used by (a) clean re-scoring of Phase V verify checkpoints, and (b) the Program-A Tier-1
answer-key gate (mismatch → route to Pro).

Handles the three artifact classes the M3 sprint surfaced (see KI-6):
  - CORRUPT keys  : a leaked NTA correct_option_id (>=9 digits) left in answer_key.
                    Not a real answer → verdict 'unknown' (NEVER counts as a model miss,
                    and the gate must NOT trust/route on it).
  - Numeric keys  : Section-B integers / decimals → compare with a relative tolerance
                    so 494 vs 494.65 (rounding) matches.
  - MCQ letters   : A/B/C/D → compare letters; if the model emitted an option *value*
                    and the options list is available, resolve value→letter first.

Verdicts: 'correct' | 'wrong' | 'unknown'.
"""
import re

_CORRUPT_RE = re.compile(r"^\d{9,}$")
_LETTER_RE = re.compile(r"^[A-D]$")
_NUM_RE = re.compile(r"-?\d+\.?\d*")


def is_corrupt_key(key) -> bool:
    """A 9+ digit answer_key is a leaked NTA id, not a real answer (KI-6)."""
    return bool(_CORRUPT_RE.fullmatch(str(key).strip()))


def _first_num(s):
    m = _NUM_RE.search(str(s).replace(",", ""))
    return float(m.group()) if m else None


def _letter(s):
    s = str(s).strip().upper()
    return s if _LETTER_RE.fullmatch(s) else None


def _resolve_value_to_letter(value, options):
    """If options is a list of {text,...}, return the A/B/C/D index whose text matches value."""
    if not options:
        return None
    vn = _first_num(value)
    for i, opt in enumerate(options[:4]):
        txt = opt.get("text") if isinstance(opt, dict) else str(opt)
        if txt is None:
            continue
        if str(value).strip() and str(value).strip() in txt:
            return "ABCD"[i]
        on = _first_num(txt)
        if vn is not None and on is not None and abs(vn - on) <= max(0.02 * abs(on), 0.05):
            return "ABCD"[i]
    return None


def match(model_answer, answer_key, options=None, rel_tol=0.02, abs_tol=0.05) -> str:
    """Return 'correct' | 'wrong' | 'unknown' for one JEE objective row."""
    key = str(answer_key).strip()
    if is_corrupt_key(key):
        return "unknown"

    kl = _letter(key)
    if kl is not None:  # MCQ — key is a letter
        ml = _letter(model_answer)
        if ml is None:  # model emitted a value; try to resolve via options
            ml = _resolve_value_to_letter(model_answer, options)
        if ml is None:
            return "unknown"  # can't compare letter to value without options
        return "correct" if ml == kl else "wrong"

    # numeric key (Section B integer / decimal)
    kn, an = _first_num(key), _first_num(model_answer)
    if kn is None or an is None:
        return "unknown"
    return "correct" if abs(kn - an) <= max(rel_tol * abs(kn), abs_tol) else "wrong"


def score_rows(rows, key_field="answer_key", ans_field="final_answer", opt_field=None):
    """Score an iterable of dict rows. Returns dict with counts + per-verdict id lists.

    'unknown' rows (corrupt keys / unresolvable) are EXCLUDED from the accuracy denominator —
    they are data defects, not model performance.
    """
    correct, wrong, unknown = [], [], []
    for r in rows:
        v = match(r.get(ans_field), r.get(key_field), r.get(opt_field) if opt_field else None)
        rid = r.get("id")
        (correct if v == "correct" else wrong if v == "wrong" else unknown).append(rid)
    scored = len(correct) + len(wrong)
    return {
        "correct": correct,
        "wrong": wrong,
        "unknown": unknown,
        "n_scored": scored,
        "n_unknown": len(unknown),
        "accuracy": (len(correct) / scored) if scored else None,
    }
