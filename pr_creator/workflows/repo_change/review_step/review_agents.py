from __future__ import annotations

import os

from pr_creator.cursor_utils.runners import get_cursor_runner

from .base import ReviewAgent
from .cursor_agent import CursorReviewAgent

DEFAULT_AGENT = "cursor"


def get_review_agent(name: str | None = None) -> ReviewAgent:
    agent_name = (name or os.environ.get("REVIEW_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorReviewAgent(get_cursor_runner())
    raise ValueError(f"Unknown review agent: {agent_name}")
