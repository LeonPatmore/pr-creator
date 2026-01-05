from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner

DEFAULT_AGENT = "cursor"


class ChangeAgent(ABC):
    @abstractmethod
    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        """Apply changes to the given repo."""
        raise NotImplementedError


class CursorChangeAgent(ChangeAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        repo_abs = str(repo_path.resolve())
        guarded_prompt = (
            "IMPORTANT:\n"
            "- Do NOT change file line endings (do not convert LF<->CRLF).\n"
            "- Avoid whitespace-only changes.\n"
            "- Only modify files that are necessary to satisfy the task.\n"
            "\n" + (prompt or "")
        )
        self._runner.run_prompt(
            guarded_prompt,
            remove=False,
            repo_abs=repo_abs,
            context_roots=context_roots,
            include_repo_hint=True,
            stream_partial_output=True,
            extra_env=secrets or {},
        )


def get_change_agent(name: str | None = None) -> ChangeAgent:
    agent_name = (name or os.environ.get("CHANGE_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorChangeAgent(get_cursor_runner())
    raise ValueError(f"Unknown change agent: {agent_name}")


__all__ = ["ChangeAgent", "CursorChangeAgent", "get_change_agent"]
