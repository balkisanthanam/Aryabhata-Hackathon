"""Shared per-record model router for the Flash → Pro escalation path.

Decision D4 (M3_PipelineIntegration_Plan.md): route to Pro only for JEE figures.
  - JEE figures are KI-3-blind: no image is attached, so Flash can't see them.
    They stay on Pro until figure crops are implemented (KI-3 fix).
  - NCERT figures: proven ≈ Pro on NCERT visual test (_NCERT_VISUAL_TEST.md).
    They stay on Flash regardless of has_figure.

router_enabled=False bypasses the override for ablation runs (--no-router in
the harness).
"""


def select_mode_for_record(record: dict, default_mode: str, router_enabled: bool = True) -> str:
    """Return the model mode to use for this record.

    Args:
        record:       Must contain 'source' ("jee"/"ncert") and 'has_figure' (bool).
        default_mode: The requested mode before per-record routing.
        router_enabled: Set False to bypass routing (ablation / --no-router).
    """
    if not router_enabled:
        return default_mode
    is_flash = default_mode in ("flash-tuned", "flash-untuned", "flash-assembly")
    if is_flash and record.get("source") == "jee" and record.get("has_figure"):
        return "pro-assembly"
    return default_mode
