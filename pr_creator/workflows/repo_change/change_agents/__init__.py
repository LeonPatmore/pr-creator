from __future__ import annotations

import os

from .base import ChangeAgent
from .cursor_agent import CursorChangeAgent
from pr_creator.cursor_utils.runners import get_cursor_runner

DEFAULT_AGENT = "cursor"


def get_change_agent(name: str | None = None) -> ChangeAgent:
    agent_name = (name or os.environ.get("CHANGE_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorChangeAgent(get_cursor_runner())
    raise ValueError(f"Unknown change agent: {agent_name}")


__all__ = ["ChangeAgent", "CursorChangeAgent", "get_change_agent"]
