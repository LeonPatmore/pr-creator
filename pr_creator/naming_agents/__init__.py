from __future__ import annotations

import os

from .base import NamingAgent
from .cursor_agent import CursorNamingAgent

DEFAULT_AGENT = "cursor"


def get_naming_agent(name: str | None = None) -> NamingAgent:
    agent_name = (name or os.environ.get("NAMING_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorNamingAgent()
    raise ValueError(f"Unknown naming agent: {agent_name}")


__all__ = ["NamingAgent", "CursorNamingAgent", "get_naming_agent"]
