from __future__ import annotations

import os

from .base import ReviewAgent
from .config import DEFAULT_REVIEW_MAX_ATTEMPTS, get_review_max_attempts
from .cursor_agent import CursorReviewAgent
from pr_creator.cursor_utils.runners import get_cursor_runner

DEFAULT_AGENT = "cursor"


def get_review_agent(name: str | None = None) -> ReviewAgent:
    agent_name = (name or os.environ.get("REVIEW_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorReviewAgent(get_cursor_runner())
    raise ValueError(f"Unknown review agent: {agent_name}")


__all__ = [
    "DEFAULT_REVIEW_MAX_ATTEMPTS",
    "ReviewAgent",
    "CursorReviewAgent",
    "get_review_agent",
    "get_review_max_attempts",
]
