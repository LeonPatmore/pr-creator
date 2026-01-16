from __future__ import annotations

import os
from typing import Dict


def get_cursor_image() -> str:
    """Get the Cursor Docker image from environment, with default."""
    return os.environ.get("CURSOR_IMAGE", "leonpatmore2/cursor-agent:latest")


def _normalize_intent(intent: str) -> str:
    # Environment variable suffixes should be stable + predictable.
    # Keep only a conservative subset of characters.
    return "".join([c for c in intent.strip().upper() if c.isalnum() or c == "_"])


def get_cursor_model(intent: str | None = None) -> str:
    """
    Get the Cursor model from environment, with default.

    Supports intent-specific overrides:
    - CURSOR_MODEL (default for all intents)
    - CURSOR_MODEL_<INTENT> (override for a specific intent, e.g. CURSOR_MODEL_CHANGE)
    """
    if intent and intent.strip():
        suffix = _normalize_intent(intent)
        if suffix:
            v = os.environ.get(f"CURSOR_MODEL_{suffix}")
            if (v or "").strip():
                return v
    return os.environ.get("CURSOR_MODEL", "gpt-5.2")


def get_cursor_env_vars() -> Dict[str, str]:
    """Collect environment variables for Cursor agent."""
    env_keys_str = os.environ.get("CURSOR_ENV_KEYS", "CURSOR_API_KEY")
    env_keys = [k.strip() for k in env_keys_str.split(",") if k.strip()]

    env_vars: Dict[str, str] = {}
    for key in env_keys:
        if key in os.environ:
            env_vars[key] = os.environ[key]

    return env_vars


def should_stream_cursor_output() -> bool:
    value = os.environ.get("CURSOR_STREAM_OUTPUT", "false").strip().lower()
    return value in ("1", "true", "yes", "on")
