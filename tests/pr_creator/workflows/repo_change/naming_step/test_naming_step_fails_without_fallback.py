from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

from pr_creator.workflows.repo_change.naming_step.node import GenerateNames
from pr_creator.workflows.repo_change.state import RepoChangeState


def test_naming_step_raises_when_agent_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextlib.asynccontextmanager
    async def _mock_agent():
        async def _generate(_prompt: str) -> str | None:
            return None

        yield _generate

    class _Ctx:
        def __init__(self, state: RepoChangeState) -> None:
            self.state = state

    monkeypatch.setattr(
        "pr_creator.workflows.repo_change.naming_step.node.build_naming_agent",
        _mock_agent,
    )
    # Make it fail immediately (no retries, no sleep)
    monkeypatch.setattr(
        "pr_creator.workflows.repo_change.naming_step.node._naming_retry_config.get_max_attempts",
        lambda: 0,
    )

    repo_url = "https://github.com/example/repo"
    state = RepoChangeState(additional_prompt="do something", working_dir=Path("/tmp"))

    with pytest.raises(RuntimeError, match=r"\[naming\] generation failed"):
        asyncio.run(GenerateNames(repo_url=repo_url).run(_Ctx(state)))


def test_naming_step_uses_base_prompt_when_prompt_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that naming agent uses base_prompt when prompt is empty.

    This happens when orchestrator passes empty additional_prompt because
    no repo-specific context is needed.
    """
    received_prompts = []

    @contextlib.asynccontextmanager
    async def _mock_agent():
        async def _generate(prompt: str) -> str | None:
            received_prompts.append(prompt)
            return "test-branch-name"

        yield _generate

    class _Ctx:
        def __init__(self, state: RepoChangeState) -> None:
            self.state = state

    monkeypatch.setattr(
        "pr_creator.workflows.repo_change.naming_step.node.build_naming_agent",
        _mock_agent,
    )

    repo_url = "https://github.com/example/repo"
    base_prompt = "Add authentication feature"
    state = RepoChangeState(
        additional_prompt="",  # Empty additional_prompt from orchestrator
        base_prompt=base_prompt,  # Original CLI prompt
        working_dir=Path("/tmp"),
    )

    asyncio.run(GenerateNames(repo_url=repo_url).run(_Ctx(state)))

    # Should have used base_prompt, not empty prompt
    assert len(received_prompts) == 1
    assert received_prompts[0] == base_prompt
