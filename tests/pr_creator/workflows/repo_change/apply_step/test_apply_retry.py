"""Test retry behavior for the apply (change agent) step."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pr_creator.workflows.repo_change.apply_step.node import ApplyChanges
from pr_creator.workflows.repo_change.state import RepoChangeState


@pytest.mark.anyio
async def test_apply_changes_retries_on_failure(tmp_path: Path):
    """Test that ApplyChanges retries on agent failure up to max attempts."""
    repo_url = "https://github.com/test/repo"

    # Create initial state
    state = RepoChangeState(
        prompt="Make changes",
        working_dir=tmp_path,
        cloned={repo_url: tmp_path},
        apply_attempts={},
    )

    # Mock the agent to fail on first two attempts, succeed on third
    call_count = 0

    async def mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError(f"Agent failed (attempt {call_count})")
        # Success on third attempt
        return None

    with patch("pr_creator.workflows.repo_change.apply_step.node._agent") as mock_agent:
        mock_agent.run = AsyncMock(side_effect=mock_run)

        with patch(
            "pr_creator.workflows.repo_change.apply_step.node._apply_retry_config.get_max_attempts",
            return_value=4,
        ):
            with patch(
                "pr_creator.workflows.repo_change.apply_step.node._apply_retry_config.calculate_backoff",
                return_value=0.01,
            ):
                with patch(
                    "pr_creator.workflows.repo_change.apply_step.node._post_apply_guardrails"
                ):
                    # Create mock context
                    class _Ctx:
                        def __init__(self, state):
                            self.state = state

                    ctx = _Ctx(state)

                    node = ApplyChanges(repo_url=repo_url)

                    # First attempt should fail and return self for retry
                    result1 = await node.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(result1, ApplyChanges)
                    assert result1.repo_url == repo_url
                    assert state.apply_attempts[repo_url] == 1
                    assert call_count == 1

                    # Second attempt should fail and return self for retry
                    result2 = await result1.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(result2, ApplyChanges)
                    assert result2.repo_url == repo_url
                    assert state.apply_attempts[repo_url] == 2
                    assert call_count == 2

                    # Third attempt should succeed
                    from pr_creator.workflows.repo_change.review_step.node import (
                        ReviewChanges,
                    )

                    result3 = await result2.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(result3, ReviewChanges)
                    assert result3.repo_url == repo_url
                    assert repo_url in state.processed
                    assert call_count == 3


@pytest.mark.anyio
async def test_apply_changes_raises_after_max_attempts(tmp_path: Path):
    """Test that ApplyChanges raises exception after exhausting max attempts."""
    repo_url = "https://github.com/test/repo"

    # Create initial state
    state = RepoChangeState(
        prompt="Make changes",
        working_dir=tmp_path,
        cloned={repo_url: tmp_path},
        apply_attempts={},
    )

    # Mock the agent to always fail
    async def mock_run(*args, **kwargs):
        raise RuntimeError("Agent failed")

    with patch("pr_creator.workflows.repo_change.apply_step.node._agent") as mock_agent:
        mock_agent.run = AsyncMock(side_effect=mock_run)

        # max_attempts=1 means we allow attempts 0 and 1 (2 total tries)
        with patch(
            "pr_creator.workflows.repo_change.apply_step.node._apply_retry_config.get_max_attempts",
            return_value=1,
        ):
            with patch(
                "pr_creator.workflows.repo_change.apply_step.node._apply_retry_config.calculate_backoff",
                return_value=0.01,
            ):
                with patch(
                    "pr_creator.workflows.repo_change.apply_step.node._post_apply_guardrails"
                ):

                    class _Ctx:
                        def __init__(self, state):
                            self.state = state

                    ctx = _Ctx(state)

                    node = ApplyChanges(repo_url=repo_url)

                    # First attempt should fail and return self for retry
                    result1 = await node.run(ctx)  # type: ignore[arg-type]
                    assert isinstance(result1, ApplyChanges)
                    assert state.apply_attempts[repo_url] == 1

                    # Second attempt should raise since we've hit max attempts
                    with pytest.raises(RuntimeError, match="Agent failed"):
                        await result1.run(ctx)  # type: ignore[arg-type]

                    # Verify we tried exactly 2 times
                    assert mock_agent.run.call_count == 2


@pytest.mark.anyio
async def test_apply_changes_success_first_try(tmp_path: Path):
    """Test that ApplyChanges works on first attempt when agent succeeds."""
    repo_url = "https://github.com/test/repo"

    # Create initial state
    state = RepoChangeState(
        prompt="Make changes",
        working_dir=tmp_path,
        cloned={repo_url: tmp_path},
        apply_attempts={},
    )

    with patch("pr_creator.workflows.repo_change.apply_step.node._agent") as mock_agent:
        mock_agent.run = AsyncMock(return_value=None)

        with patch(
            "pr_creator.workflows.repo_change.apply_step.node._post_apply_guardrails"
        ):

            class _Ctx:
                def __init__(self, state):
                    self.state = state

            ctx = _Ctx(state)

            node = ApplyChanges(repo_url=repo_url)

            # Should succeed on first attempt
            from pr_creator.workflows.repo_change.review_step.node import ReviewChanges

            result = await node.run(ctx)  # type: ignore[arg-type]
            assert isinstance(result, ReviewChanges)
            assert result.repo_url == repo_url
            assert repo_url in state.processed
            assert mock_agent.run.call_count == 1
            # No retry attempts recorded since it succeeded first time
            assert (
                repo_url not in state.apply_attempts
                or state.apply_attempts[repo_url] == 0
            )


def test_calculate_backoff():
    """Test that backoff calculation works correctly with min/max bounds."""
    from pr_creator.retry_utils import RetryConfig

    config = RetryConfig(
        env_prefix="TEST",
        default_max_attempts=4,
        default_backoff_base=2.0,
        default_backoff_min=1.0,
        default_backoff_max=30.0,
    )

    # Test exponential backoff: min * (base^attempt)
    # Attempt 0: 1.0 * (2^0) = 1.0 * 1 = 1.0
    assert config.calculate_backoff(0) == 1.0

    # Attempt 1: 1.0 * (2^1) = 1.0 * 2 = 2.0
    assert config.calculate_backoff(1) == 2.0

    # Attempt 2: 1.0 * (2^2) = 1.0 * 4 = 4.0
    assert config.calculate_backoff(2) == 4.0

    # Attempt 3: 1.0 * (2^3) = 1.0 * 8 = 8.0
    assert config.calculate_backoff(3) == 8.0

    # Attempt 4: 1.0 * (2^4) = 1.0 * 16 = 16.0
    assert config.calculate_backoff(4) == 16.0

    # Attempt 5: 1.0 * (2^5) = 1.0 * 32 = 32.0 (clamped to max 30.0)
    assert config.calculate_backoff(5) == 30.0

    # Attempt 6: 2^6 = 64.0 (clamped to max 30.0)
    assert config.calculate_backoff(6) == 30.0


@pytest.mark.anyio
async def test_apply_changes_uses_backoff_between_retries(tmp_path: Path):
    """Test that ApplyChanges waits with backoff between retries."""
    repo_url = "https://github.com/test/repo"

    # Create initial state
    state = RepoChangeState(
        prompt="Make changes",
        working_dir=tmp_path,
        cloned={repo_url: tmp_path},
        apply_attempts={},
    )

    # Mock the agent to fail twice, succeed on third
    call_count = 0

    async def mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("Agent failed")
        return None

    # Track asyncio.sleep calls
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch("pr_creator.workflows.repo_change.apply_step.node._agent") as mock_agent:
        mock_agent.run = AsyncMock(side_effect=mock_run)

        with patch(
            "pr_creator.workflows.repo_change.apply_step.node._apply_retry_config.get_max_attempts",
            return_value=4,
        ):
            with patch(
                "pr_creator.workflows.repo_change.apply_step.node._apply_retry_config.calculate_backoff",
                side_effect=[1.0, 2.0, 4.0],
            ):
                with patch(
                    "pr_creator.workflows.repo_change.apply_step.node.asyncio.sleep",
                    side_effect=mock_sleep,
                ):
                    with patch(
                        "pr_creator.workflows.repo_change.apply_step.node._post_apply_guardrails"
                    ):

                        class _Ctx:
                            def __init__(self, state):
                                self.state = state

                        ctx = _Ctx(state)

                        node = ApplyChanges(repo_url=repo_url)

                        # First attempt fails
                        result1 = await node.run(ctx)  # type: ignore[arg-type]
                        assert isinstance(result1, ApplyChanges)
                        assert len(sleep_calls) == 1
                        assert sleep_calls[0] == 1.0

                        # Second attempt fails
                        result2 = await result1.run(ctx)  # type: ignore[arg-type]
                        assert isinstance(result2, ApplyChanges)
                        assert len(sleep_calls) == 2
                        assert sleep_calls[1] == 2.0

                        # Third attempt succeeds
                        from pr_creator.workflows.repo_change.review_step.node import (
                            ReviewChanges,
                        )

                        result3 = await result2.run(ctx)  # type: ignore[arg-type]
                        assert isinstance(result3, ReviewChanges)
                        # No sleep after success
                        assert len(sleep_calls) == 2
