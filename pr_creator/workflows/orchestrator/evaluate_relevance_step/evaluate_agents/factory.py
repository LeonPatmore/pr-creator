from __future__ import annotations

import os

from pr_creator.cursor_utils.runners import get_cursor_runner
from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.base import (
    EvaluateAgent,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.cursor_agent import (
    CursorEvaluateAgent,
)

DEFAULT_AGENT = "cursor"


def get_evaluate_agent(name: str | None = None) -> EvaluateAgent:
    agent_name = (name or os.environ.get("EVALUATE_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorEvaluateAgent(get_cursor_runner())
    raise ValueError(f"Unknown evaluate agent: {agent_name}")
