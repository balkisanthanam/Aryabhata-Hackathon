"""Load local settings for the ConceptIndex pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


PIPELINE_DIR = Path(__file__).resolve().parent
SETTINGS_CANDIDATES = (
    PIPELINE_DIR / "local.settings.local.json",
    PIPELINE_DIR / "local.settings.json",
)

_LOADED_SETTINGS_PATH: Optional[Path] = None
_LOAD_ATTEMPTED = False


def load_local_settings() -> Optional[Path]:
    """Load local settings into os.environ without overriding existing values."""
    global _LOAD_ATTEMPTED
    global _LOADED_SETTINGS_PATH

    if _LOAD_ATTEMPTED:
        return _LOADED_SETTINGS_PATH

    _LOAD_ATTEMPTED = True

    for settings_path in SETTINGS_CANDIDATES:
        if not settings_path.exists():
            continue

        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        values = payload.get("Values", payload)
        if not isinstance(values, dict):
            raise ValueError(f"Invalid local settings file: {settings_path}")

        for key, value in values.items():
            if key in os.environ or value is None:
                continue
            os.environ[key] = str(value)

        _LOADED_SETTINGS_PATH = settings_path
        return settings_path

    return None
