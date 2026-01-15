from __future__ import annotations

import os

from pr_creator.cursor_utils.runners import get_cursor_runner

from .base import NamingAgent
from .config import DEFAULT_NAMING_MAX_ATTEMPTS, get_naming_max_attempts
from .cursor_agent import CursorNamingAgent

DEFAULT_AGENT = "cursor"


def get_naming_agent(name: str | None = None) -> NamingAgent:
    agent_name = (name or os.environ.get("NAMING_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorNamingAgent(get_cursor_runner())
    raise ValueError(f"Unknown naming agent: {agent_name}")


__all__ = [
    "DEFAULT_NAMING_MAX_ATTEMPTS",
    "NamingAgent",
    "CursorNamingAgent",
    "get_naming_agent",
    "get_naming_max_attempts",
]
