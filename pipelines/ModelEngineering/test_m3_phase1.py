"""CHECKPOINT 1 — Phase 1 pure-unit tests (no LLM, no DB).

Covers:
  - router.select_mode_for_record: narrowed JEE-only escalation
  - answer_match (re-homed): corrupt key, letter match/mismatch, numeric tolerance
  - flash_assembly_config(): model IDs
  - batch_evaluator import chain (smoke-imports only — no execution)

Run with:
    cd pipelines/ModelEngineering
    python -m pytest test_m3_phase1.py -v
"""
import json
import os
import sys
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — mirror batch_evaluator.py so we hit the same MultiStep package
# ---------------------------------------------------------------------------
cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"

if str(extraction_dir) not in sys.path:
    sys.path.insert(0, str(extraction_dir))


# ---------------------------------------------------------------------------
# router tests
# ---------------------------------------------------------------------------

class TestRouter:
    def setup_method(self):
        from router import select_mode_for_record
        self.fn = select_mode_for_record

    def test_jee_figure_routes_to_pro(self):
        rec = {"source": "jee", "has_figure": True}
        assert self.fn(rec, "flash-assembly") == "pro-assembly"

    def test_jee_figure_flash_untuned_routes_to_pro(self):
        rec = {"source": "jee", "has_figure": True}
        assert self.fn(rec, "flash-untuned") == "pro-assembly"

    def test_jee_figure_flash_tuned_routes_to_pro(self):
        rec = {"source": "jee", "has_figure": True}
        assert self.fn(rec, "flash-tuned") == "pro-assembly"

    def test_ncert_figure_stays_flash(self):
        rec = {"source": "ncert", "has_figure": True}
        assert self.fn(rec, "flash-assembly") == "flash-assembly"

    def test_jee_no_figure_stays_flash(self):
        rec = {"source": "jee", "has_figure": False}
        assert self.fn(rec, "flash-assembly") == "flash-assembly"

    def test_jee_figure_pro_mode_unchanged(self):
        # Pro mode is never a flash mode — router should not fire
        rec = {"source": "jee", "has_figure": True}
        assert self.fn(rec, "pro-assembly") == "pro-assembly"

    def test_router_disabled_jee_figure(self):
        rec = {"source": "jee", "has_figure": True}
        assert self.fn(rec, "flash-assembly", router_enabled=False) == "flash-assembly"

    def test_router_disabled_ncert(self):
        rec = {"source": "ncert", "has_figure": True}
        assert self.fn(rec, "flash-assembly", router_enabled=False) == "flash-assembly"

    def test_missing_source_no_escalation(self):
        # record missing 'source' should not route to pro (source != "jee")
        rec = {"has_figure": True}
        assert self.fn(rec, "flash-assembly") == "flash-assembly"


# ---------------------------------------------------------------------------
# answer_match tests (re-homed to MultiStep)
# ---------------------------------------------------------------------------

class TestAnswerMatch:
    def setup_method(self):
        from answer_match import match, is_corrupt_key
        self.match = match
        self.is_corrupt = is_corrupt_key

    # Corrupt key (KI-6) — 9+ digit NTA ids
    def test_corrupt_key_9digits(self):
        assert self.is_corrupt("123456789") is True

    def test_corrupt_key_11digits(self):
        assert self.is_corrupt("87827056058") is True

    def test_non_corrupt_key_letter(self):
        assert self.is_corrupt("A") is False

    def test_non_corrupt_key_short_number(self):
        assert self.is_corrupt("494") is False

    def test_match_corrupt_returns_unknown(self):
        assert self.match("A", "123456789") == "unknown"

    # MCQ letter matching
    def test_letter_correct(self):
        assert self.match("A", "A") == "correct"

    def test_letter_wrong(self):
        assert self.match("B", "A") == "wrong"

    def test_letter_case_insensitive_correct(self):
        assert self.match("a", "A") == "correct"

    def test_letter_case_insensitive_wrong(self):
        assert self.match("b", "A") == "wrong"

    # Numeric tolerance (Section B)
    def test_numeric_exact(self):
        assert self.match("494", "494") == "correct"

    def test_numeric_within_tolerance(self):
        # 494 vs 494.65 — delta=0.65, tol=max(0.02*494, 0.05)=max(9.88,0.05)=9.88 → correct
        assert self.match("494.65", "494") == "correct"

    def test_numeric_outside_tolerance(self):
        # 500 vs 494 — delta=6, tol=9.88 → correct (still within 2%)
        # Use a clearly wrong value
        assert self.match("600", "494") == "wrong"

    def test_numeric_negative(self):
        assert self.match("-5", "-5") == "correct"

    def test_numeric_zero(self):
        assert self.match("0", "0") == "correct"

    def test_no_key_returns_unknown(self):
        # None key → str(None)="None" → _first_num("None")=None → unknown
        assert self.match("A", None) == "unknown"


# ---------------------------------------------------------------------------
# flash_assembly_config tests
# ---------------------------------------------------------------------------

class TestFlashAssemblyConfig:
    @pytest.fixture(autouse=True)
    def set_gcp_project(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    def test_solver_model_is_flash(self):
        from config import flash_assembly_config
        cfg = flash_assembly_config()
        assert cfg.solver_model.model_id == "gemini-3-flash-preview"

    def test_tutor_model_is_flash(self):
        from config import flash_assembly_config
        cfg = flash_assembly_config()
        assert cfg.tutor_model.model_id == "gemini-3-flash-preview"

    def test_formatter_model_unchanged(self):
        from config import flash_assembly_config
        cfg = flash_assembly_config()
        assert cfg.formatter_model.model_id == "gemini-3-flash-preview"
        assert cfg.formatter_model.thinking_level == "LOW"

    def test_solver_temperature(self):
        from config import flash_assembly_config
        cfg = flash_assembly_config()
        assert cfg.solver_model.temperature == 0.4

    def test_tutor_temperature(self):
        from config import flash_assembly_config
        cfg = flash_assembly_config()
        assert cfg.tutor_model.temperature == 0.6


# ---------------------------------------------------------------------------
# batch_evaluator smoke-import (confirms router + config import chain)
# ---------------------------------------------------------------------------

class TestBatchEvaluatorImports:
    @pytest.fixture(autouse=True)
    def set_gcp_project(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    def test_flash_assembly_config_importable_from_config(self):
        from config import flash_assembly_config  # noqa: F401

    def test_router_importable(self):
        from router import select_mode_for_record  # noqa: F401

    def test_answer_match_importable(self):
        from answer_match import match, score_rows, is_corrupt_key  # noqa: F401

    def test_gate_importable(self):
        from gate import solve_with_gate  # noqa: F401


# ---------------------------------------------------------------------------
# Golden strings — verbatim copies of the pre-refactor inline literals from
# solver_engine.py stages 1/2/3.  Any drift here is a byte-identical regression.
# ---------------------------------------------------------------------------

_GOLDEN_SOLVER_SYSTEM = (
    "You are a cold, calculating Math & Physics expert. Focus entirely on mathematical correctness. "
    "Parse the images, compute logic, dimensional analysis, and raw step-by-step logic. "
    "Do not worry about pedagogy or strict formatting beyond clear derivations. "
    "If textbook theory or context is provided, use it strictly to ground your calculations "
    "and prevent hallucination—never mathematically force or 'fudge' numbers simply to match an expected answer key. "
    "Return the raw textual derivations and final answer."
)

_GOLDEN_TUTOR_SYSTEM = (
    "You are a Master Teacher reviewing a TA's logic for an IIT-JEE student. "
    "Take the raw math derivations provided and translate them into a pedagogical, step-by-step tutorial. "
    "Inject helpful conceptual explanations and 'nudge_hints' (tips for where students get stuck). "
    "Validate that the logic flows correctly and fix any subtle math/physics errors. "
    "CRITICAL: NEVER skip algebraic substitutions or calculations. You MUST explicitly write out the final mathematical simplification step that bridges the formulas to the exact final answer option. "
    "CRITICAL RULE FOR HINTS: Your `nudge_hints` must be purely Socratic questions that guide the student to think. NEVER provide direct statements that quote the theory, and NEVER give away the exact next step or the answer. "
    "If the solver derivation quotes direct textbook theory or laws (e.g. Le Chatelier's), DO NOT write the rule as a direct statement in your hint. Instead, formulate a question asking the student how that specific law applies. "
    "Do not output JSON, just structure the pedagogical text clearly."
)

_GOLDEN_FORMATTER_PREFIX = (
    "You are a rigid Data Architect API Endpoint. "
    "Map the provided tutor's text perfectly into the required JSON schema output. "
    "Enforce all LaTeX/MathJax invariant syntax (e.g., proper inline `$` or `$$` blocking). "
    "Do NOT add, change, or evaluate the logic. Just format the text you are given into JSON. "
    "Here is the strict schema instruction:\n\n"
)


# ---------------------------------------------------------------------------
# PromptSet / DEFAULT_PROMPT_SET — full equality against pre-refactor literals
# ---------------------------------------------------------------------------

class TestPromptSet:
    def setup_method(self):
        from solver_engine import DEFAULT_PROMPT_SET, PromptSet
        self.dps = DEFAULT_PROMPT_SET
        self.PromptSet = PromptSet

    def test_solver_system_exact(self):
        assert self.dps.solver_system == _GOLDEN_SOLVER_SYSTEM

    def test_tutor_system_exact(self):
        assert self.dps.tutor_system == _GOLDEN_TUTOR_SYSTEM

    def test_formatter_prefix_exact(self):
        assert self.dps.formatter_system_prefix == _GOLDEN_FORMATTER_PREFIX

    def test_default_build_solver_user_is_none(self):
        assert self.dps.build_solver_user is None

    def test_promptset_is_dataclass(self):
        import dataclasses
        assert dataclasses.is_dataclass(self.PromptSet)


# ---------------------------------------------------------------------------
# solve_with_gate — all 4 cascade branches, stub generators (no LLM)
# ---------------------------------------------------------------------------

class _FakeContent:
    """Minimal stand-in for GeneratedContent — gate only uses .text."""
    def __init__(self, final_answer: str):
        self.text = json.dumps({"steps": [], "final_answer": final_answer})


class _FakeGenerator:
    """Stub GoldenGenerator: records call count, returns canned JSON."""
    def __init__(self, final_answer: str):
        self._answer = final_answer
        self.call_count = 0

    def generate_assembly_line(self, prompt, system_prompt, image_urls=None):
        self.call_count += 1
        return _FakeContent(self._answer)

    @staticmethod
    def _sanitize_json_escapes(text: str) -> str:
        return text


class TestSolveWithGate:
    def setup_method(self):
        from gate import solve_with_gate
        self.gate = solve_with_gate

    def _call(self, flash_answer, pro_answer, answer_key, options=None,
              source="ncert", has_figure=False):
        flash_gen = _FakeGenerator(flash_answer)
        pro_gen = _FakeGenerator(pro_answer)
        result, status = self.gate(
            prompt="Solve this.",
            system_prompt="{}",
            answer_key=answer_key,
            options=options,
            image_urls=None,
            flash_generator=flash_gen,
            pro_generator=pro_gen,
            source=source,
            has_figure=has_figure,
        )
        return result, status, flash_gen, pro_gen

    def test_flash_correct_returns_unverified(self):
        result, status, flash_gen, pro_gen = self._call("A", "X", "A")
        assert status == "UNVERIFIED"
        assert flash_gen.call_count == 1
        assert pro_gen.call_count == 0  # Pro must NOT be called

    def test_corrupt_key_returns_key_unverified_no_pro(self):
        result, status, flash_gen, pro_gen = self._call("A", "X", "123456789")
        assert status == "KEY_UNVERIFIED"
        assert flash_gen.call_count == 1
        assert pro_gen.call_count == 0  # Corrupt key must never trigger Pro (D5)

    def test_flash_wrong_pro_correct_returns_unverified(self):
        result, status, flash_gen, pro_gen = self._call("B", "A", "A")
        assert status == "UNVERIFIED"
        assert flash_gen.call_count == 1
        assert pro_gen.call_count == 1
        # Result should be the Pro solution
        assert json.loads(result.text)["final_answer"] == "A"

    def test_flash_wrong_pro_wrong_returns_gate_failed(self):
        result, status, flash_gen, pro_gen = self._call("B", "C", "A")
        assert status == "GATE_FAILED"
        assert flash_gen.call_count == 1
        assert pro_gen.call_count == 1
        # Result should be the Pro solution (best available, flagged for review)
        assert json.loads(result.text)["final_answer"] == "C"

    def test_jee_figure_pro_correct_returns_unverified(self):
        # JEE figure → router→Pro; Pro matches key → UNVERIFIED
        result, status, flash_gen, pro_gen = self._call(
            "A", "A", "A",
            source="jee", has_figure=True,
        )
        assert status == "UNVERIFIED"
        assert flash_gen.call_count == 0  # Flash must NOT be called for JEE figures
        assert pro_gen.call_count == 1

    def test_jee_figure_pro_miss_returns_figure_unverified(self):
        # JEE figure → router→Pro; Pro misses → FIGURE_UNVERIFIED (KI-3, not GATE_FAILED)
        result, status, flash_gen, pro_gen = self._call(
            "X", "B", "A",   # flash never called; pro returns "B" ≠ "A"
            source="jee", has_figure=True,
        )
        assert status == "FIGURE_UNVERIFIED"
        assert flash_gen.call_count == 0
        assert pro_gen.call_count == 1
        assert json.loads(result.text)["final_answer"] == "B"

    def test_d2_assertion_fires_on_key_fed_prompt(self):
        # solve_with_gate must reject any prompt that contains the answer key
        import pytest
        flash_gen = _FakeGenerator("A")
        pro_gen   = _FakeGenerator("A")
        with pytest.raises(AssertionError, match="D2"):
            self.gate(
                prompt="Solve this. actual_answer_key: A",
                system_prompt="{}",
                answer_key="A",
                options=None,
                image_urls=None,
                flash_generator=flash_gen,
                pro_generator=pro_gen,
            )
