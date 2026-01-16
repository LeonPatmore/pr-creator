"""Test retry logic for the evaluate relevance step."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pr_creator.workflows.orchestrator.evaluate_relevance_step.service import (
    evaluate_relevance_with_cache,
)


@pytest.mark.anyio
async def test_evaluate_relevance_retries_on_failure(tmp_path: Path):
    """Test that evaluate relevance retries on agent failure up to max attempts."""
    repo_url = "https://github.com/test/repo"
    prompt = "test relevance prompt"

    # Mock the agent to fail on first two attempts, succeed on third
    call_count = 0

    async def mock_evaluate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError(f"Agent failed (attempt {call_count})")
        # Success on third attempt
        return True

    with patch(
        "pr_creator.workflows.orchestrator.evaluate_relevance_step.service.try_get_repo_head_sha",
        return_value="abc123def",  # Return a fake SHA
    ):
        with patch(
            "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._cache"
        ) as mock_cache:
            mock_cache.get.return_value = None  # No cache hit

            with patch(
                "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._agent"
            ) as mock_agent:
                mock_agent.evaluate = AsyncMock(side_effect=mock_evaluate)

                with patch(
                    "pr_creator.workflows.orchestrator.evaluate_relevance_step."
                    "service._evaluate_retry_config.get_max_attempts",
                    return_value=2,  # Max 2 retries = 3 total attempts
                ):
                    with patch(
                        "pr_creator.workflows.orchestrator.evaluate_relevance_step."
                        "service._evaluate_retry_config.calculate_backoff",
                        return_value=0.01,  # Fast backoff for testing
                    ):
                        result = await evaluate_relevance_with_cache(
                            repo_url=repo_url,
                            repo_path=tmp_path,
                            prompt=prompt,
                        )

                        assert result is True
                        assert call_count == 3


@pytest.mark.anyio
async def test_evaluate_relevance_raises_after_max_attempts(tmp_path: Path):
    """Test that evaluate relevance raises exception after exhausting max attempts."""
    repo_url = "https://github.com/test/repo"
    prompt = "test relevance prompt"

    # Mock the agent to always fail
    async def mock_evaluate(*args, **kwargs):
        raise RuntimeError("Agent always fails")

    with patch(
        "pr_creator.workflows.orchestrator.evaluate_relevance_step.service.try_get_repo_head_sha",
        return_value="abc123def",
    ):
        with patch(
            "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._cache"
        ) as mock_cache:
            mock_cache.get.return_value = None  # No cache hit

            with patch(
                "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._agent"
            ) as mock_agent:
                mock_agent.evaluate = AsyncMock(side_effect=mock_evaluate)

                with patch(
                    "pr_creator.workflows.orchestrator.evaluate_relevance_step."
                    "service._evaluate_retry_config.get_max_attempts",
                    return_value=1,  # Max 1 retry = 2 total attempts
                ):
                    with patch(
                        "pr_creator.workflows.orchestrator.evaluate_relevance_step."
                        "service._evaluate_retry_config.calculate_backoff",
                        return_value=0.01,
                    ):
                        with pytest.raises(RuntimeError, match="Agent always fails"):
                            await evaluate_relevance_with_cache(
                                repo_url=repo_url,
                                repo_path=tmp_path,
                                prompt=prompt,
                            )

                        # Verify we tried exactly 2 times (initial + 1 retry)
                        assert mock_agent.evaluate.call_count == 2


@pytest.mark.anyio
async def test_evaluate_relevance_success_first_try(tmp_path: Path):
    """Test that evaluate relevance works on first attempt when agent succeeds."""
    repo_url = "https://github.com/test/repo"
    prompt = "test relevance prompt"

    # Mock the agent to succeed immediately
    async def mock_evaluate(*args, **kwargs):
        return False

    with patch(
        "pr_creator.workflows.orchestrator.evaluate_relevance_step.service.try_get_repo_head_sha",
        return_value="abc123def",
    ):
        with patch(
            "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._cache"
        ) as mock_cache:
            mock_cache.get.return_value = None  # No cache hit

            with patch(
                "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._agent"
            ) as mock_agent:
                mock_agent.evaluate = AsyncMock(side_effect=mock_evaluate)

                result = await evaluate_relevance_with_cache(
                    repo_url=repo_url,
                    repo_path=tmp_path,
                    prompt=prompt,
                )

                assert result is False
                assert mock_agent.evaluate.call_count == 1


@pytest.mark.anyio
async def test_evaluate_relevance_uses_cache(tmp_path: Path):
    """Test that evaluate relevance uses cache when available."""
    repo_url = "https://github.com/test/repo"
    prompt = "test relevance prompt"

    # Mock the cache to return a cached value
    with patch(
        "pr_creator.workflows.orchestrator.evaluate_relevance_step.service.try_get_repo_head_sha",
        return_value="abc123def",
    ):
        with patch(
            "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._cache"
        ) as mock_cache:
            mock_cache.get.return_value = True  # Cached as relevant

            with patch(
                "pr_creator.workflows.orchestrator.evaluate_relevance_step.service._agent"
            ) as mock_agent:
                result = await evaluate_relevance_with_cache(
                    repo_url=repo_url,
                    repo_path=tmp_path,
                    prompt=prompt,
                )

                assert result is True
                # Agent should not be called when cache hits
                mock_agent.evaluate.assert_not_called()
