from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pr_creator.workflows.repo_change.review_step.node import ReviewChanges
from pr_creator.workflows.repo_change.state import RepoChangeState


@pytest.mark.anyio
async def test_review_step_retries_on_unexpected_error(tmp_path: Path):
    repo_url = "https://github.com/test/repo"
    state = RepoChangeState(
        additional_prompt="Do stuff",
        working_dir=tmp_path,
        cloned={repo_url: tmp_path},
        review_step_attempts={},
    )

    call_count = 0

    async def mock_review(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("boom")
        return False, None

    sleep_calls: list[float] = []

    async def mock_sleep(seconds: float):
        sleep_calls.append(seconds)

    with patch(
        "pr_creator.workflows.repo_change.review_step.node._agent"
    ) as mock_agent:
        mock_agent.review = AsyncMock(side_effect=mock_review)
        with patch(
            "pr_creator.workflows.repo_change.review_step.node._review_step_retry_config.get_max_attempts",
            return_value=4,
        ):
            with patch(
                "pr_creator.workflows.repo_change.review_step.node._review_step_retry_config.calculate_backoff",
                side_effect=[0.01, 0.02, 0.03],
            ):
                with patch(
                    "pr_creator.workflows.repo_change.review_step.node.asyncio.sleep",
                    side_effect=mock_sleep,
                ):

                    class _Ctx:
                        def __init__(self, state):
                            self.state = state

                    ctx = _Ctx(state)
                    node = ReviewChanges(repo_url=repo_url)

                    res1 = await node.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(res1, ReviewChanges)
                    assert state.review_step_attempts[repo_url] == 1

                    res2 = await res1.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(res2, ReviewChanges)
                    assert state.review_step_attempts[repo_url] == 2

                    from pr_creator.workflows.repo_change.submit_step.node import (
                        SubmitChanges,
                    )

                    res3 = await res2.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(res3, SubmitChanges)
                    assert call_count == 3
                    assert sleep_calls == [0.01, 0.02]


@pytest.mark.anyio
async def test_review_changes_required_loop_capped_at_two(tmp_path: Path, monkeypatch):
    repo_url = "https://github.com/test/repo"
    state = RepoChangeState(
        additional_prompt="Do stuff",
        working_dir=tmp_path,
        cloned={repo_url: tmp_path},
        review_attempts={},
    )

    # Even if configured higher, it must cap to 2.
    monkeypatch.setenv("REVIEW_MAX_ATTEMPTS", "999")

    with patch(
        "pr_creator.workflows.repo_change.review_step.node._agent"
    ) as mock_agent:
        mock_agent.review = AsyncMock(return_value=(True, "Fix it"))

        with patch(
            "pr_creator.workflows.repo_change.review_step.node.asyncio.sleep"
        ) as mock_sleep:

            class _Ctx:
                def __init__(self, state):
                    self.state = state

            ctx = _Ctx(state)

            node = ReviewChanges(repo_url=repo_url)
            res1 = await node.run(ctx)  # type: ignore[arg-type]
            from pr_creator.workflows.repo_change.apply_step.node import ApplyChanges

            assert isinstance(res1, ApplyChanges)
            assert state.review_attempts[repo_url] == 1

            res2 = await ReviewChanges(repo_url=repo_url).run(ctx)  # type: ignore[arg-type]
            assert isinstance(res2, ApplyChanges)
            assert state.review_attempts[repo_url] == 2

            from pr_creator.workflows.repo_change.submit_step.node import SubmitChanges

            res3 = await ReviewChanges(repo_url=repo_url).run(ctx)  # type: ignore[arg-type]
            assert isinstance(res3, SubmitChanges)

            # Changes-required loop should not use backoff sleep.
            mock_sleep.assert_not_called()
