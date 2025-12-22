from __future__ import annotations

import os

from .base import EvaluateAgent
from .cursor_agent import CursorEvaluateAgent

DEFAULT_AGENT = "cursor"


def get_evaluate_agent(name: str | None = None) -> EvaluateAgent:
    agent_name = (name or os.environ.get("EVALUATE_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorEvaluateAgent()
    raise ValueError(f"Unknown evaluate agent: {agent_name}")


__all__ = ["EvaluateAgent", "CursorEvaluateAgent", "get_evaluate_agent"]
