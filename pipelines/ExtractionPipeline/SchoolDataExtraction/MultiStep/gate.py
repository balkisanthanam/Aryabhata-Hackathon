"""Flash → gate → Pro cascade helper (M3 Pipeline Integration, Component 3).

Decision D2: generation is always key-blind. Keys feed the gate only.
Decision D3: recovery cascade = Flash → match → independent Pro re-solve (key-blind)
             → GATE_FAILED if Pro also misses. No key-fed fixer.
Decision D4: JEE figures route to Pro via router (KI-3-blind); NCERT figures stay Flash.
Decision D5: corrupt / unknown keys (is_corrupt_key) → KEY_UNVERIFIED, never a miss,
             never triggers Pro.

Usage (JEE wiring example):
    sol, status = solve_with_gate(
        prompt=user_prompt,          # key-blind — must NOT contain answer_key
        system_prompt=schema_prompt,
        answer_key=row["answer_key"],
        options=qc.get("options"),
        image_urls=image_urls or None,
        flash_generator=flash_gen,
        pro_generator=pro_gen,
        source="jee",
        has_figure=row_has_figure,
    )
    # status: 'UNVERIFIED' | 'KEY_UNVERIFIED' | 'GATE_FAILED' | 'FIGURE_UNVERIFIED'
"""
import json
import logging
from typing import List, Optional, Tuple

from answer_match import match
from router import select_mode_for_record

logger = logging.getLogger(__name__)


def _parse_final_answer(text: str, generator) -> Optional[str]:
    """Extract final_answer from model output, reusing the canonical parse logic (G4)."""
    s = text.strip()
    if s.startswith("```json"):
        s = s.split("```json", 1)[1]
    elif s.startswith("```"):
        s = s.split("```", 1)[1]
    if "```" in s:
        s = s[:s.rfind("```")].strip()

    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        sanitized = generator._sanitize_json_escapes(s)
        try:
            parsed = json.loads(sanitized)
        except json.JSONDecodeError:
            logger.warning("gate: could not parse model output as JSON; verdict will be 'unknown'")
            return None

    if not isinstance(parsed, dict):
        return None
    return parsed.get("final_answer")


def solve_with_gate(
    prompt: str,
    system_prompt: str,
    answer_key,
    options,
    image_urls: Optional[List[str]],
    flash_generator,
    pro_generator,
    source: str = "ncert",
    has_figure: bool = False,
) -> Tuple[object, str]:
    """Flash → answer-key gate → independent Pro re-solve cascade.

    Args:
        prompt:          Key-blind user prompt (must NOT contain the answer key).
        system_prompt:   Stage-3 schema instruction (passed to generate_assembly_line).
        answer_key:      Stored answer key for gate verification only.
        options:         MCQ options list (for letter-resolution in answer_match).
        image_urls:      Figure URLs for Stage 1; None for text-only rows.
        flash_generator: GoldenGenerator with flash_assembly_config().
        pro_generator:   GoldenGenerator with default Pro config.
        source:          Record source ("jee" or "ncert") for router (D4).
        has_figure:      True if the record has an associated figure image (D4).

    Returns:
        (generated_content, review_status) where review_status is one of:
            'UNVERIFIED'        — Flash/Pro answer matches key
            'KEY_UNVERIFIED'    — corrupt/unknown key; result stored, not a miss (D5)
            'GATE_FAILED'       — Flash AND Pro both missed on a text row; high-signal flag
            'FIGURE_UNVERIFIED' — router→Pro missed on a figure row (KI-3-blind); distinct
                                  from GATE_FAILED (figure gap, not a strong model miss)
    """
    assert "actual_answer_key" not in prompt, "D2: solver prompt must be key-blind"

    # Router: JEE figures → Pro directly (KI-3-blind; no image attached, no Flash first-pass)
    mode = select_mode_for_record(
        {"source": source, "has_figure": has_figure},
        "flash-assembly",
    )
    if mode == "pro-assembly":
        logger.info(f"gate: router→pro-assembly (source={source!r}, has_figure={has_figure})")
        sol = pro_generator.generate_assembly_line(
            prompt=prompt,
            system_prompt=system_prompt,
            image_urls=image_urls,
        )
        pro_answer = _parse_final_answer(sol.text, pro_generator)
        verdict = match(pro_answer, answer_key, options)
        logger.info(f"gate: router-Pro verdict={verdict!r} answer={pro_answer!r}")
        if verdict == "correct":
            return sol, "UNVERIFIED"
        if verdict == "unknown":
            return sol, "KEY_UNVERIFIED"
        return sol, "FIGURE_UNVERIFIED"  # figure-blind miss (KI-3) — distinct from GATE_FAILED

    # Flash solve — key-blind
    sol = flash_generator.generate_assembly_line(
        prompt=prompt,
        system_prompt=system_prompt,
        image_urls=image_urls,
    )
    flash_answer = _parse_final_answer(sol.text, flash_generator)
    verdict = match(flash_answer, answer_key, options)
    logger.info(f"gate: Flash verdict={verdict!r} answer={flash_answer!r}")

    if verdict == "correct":
        return sol, "UNVERIFIED"
    if verdict == "unknown":
        # Corrupt key (KI-6) or unresolvable — never a miss, never route to Pro (D5)
        return sol, "KEY_UNVERIFIED"

    # Flash missed — independent Pro re-solve, also key-blind (D3)
    logger.info("gate: Flash miss → Pro re-solve")
    pro_sol = pro_generator.generate_assembly_line(
        prompt=prompt,
        system_prompt=system_prompt,
        image_urls=image_urls,
    )
    pro_answer = _parse_final_answer(pro_sol.text, pro_generator)
    v2 = match(pro_answer, answer_key, options)
    logger.info(f"gate: Pro verdict={v2!r} answer={pro_answer!r}")

    if v2 == "correct":
        return pro_sol, "UNVERIFIED"
    return pro_sol, "GATE_FAILED"
