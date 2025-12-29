from __future__ import annotations

import os
from typing import Dict


def get_cursor_image() -> str:
    """Get the Cursor Docker image from environment, with default."""
    return os.environ.get("CURSOR_IMAGE", "leonpatmore2/cursor-agent:latest")


def get_cursor_model() -> str:
    """Get the Cursor model from environment, with default."""
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
