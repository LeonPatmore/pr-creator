from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pr_creator.workflows.repo_change.naming_step.node import GenerateNames
from pr_creator.workflows.repo_change.state import RepoChangeState


def test_naming_step_raises_when_agent_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Agent:
        async def generate_short_desc(self, _prompt: str) -> str | None:
            return None

    class _Ctx:
        def __init__(self, state: RepoChangeState) -> None:
            self.state = state

    monkeypatch.setattr(
        "pr_creator.workflows.repo_change.naming_step.node._agent",
        _Agent(),
    )
    # Make it fail immediately (no retries, no sleep)
    monkeypatch.setattr(
        "pr_creator.workflows.repo_change.naming_step.node._naming_retry_config.get_max_attempts",
        lambda: 0,
    )

    repo_url = "https://github.com/example/repo"
    state = RepoChangeState(prompt="do something", working_dir=Path("/tmp"))

    with pytest.raises(RuntimeError, match=r"\[naming\] generation failed"):
        asyncio.run(GenerateNames(repo_url=repo_url).run(_Ctx(state)))

