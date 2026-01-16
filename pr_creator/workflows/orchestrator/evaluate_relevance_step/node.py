from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic_graph.beta import StepContext

from pr_creator.repo_workspace import prepare_workspace
from pr_creator.retry_utils import RetryConfig
from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.evaluate_relevance_step.relevance_cache import (
    DiskRelevanceCache,
    compute_prompt_hash,
    try_get_repo_head_sha,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.factory import (
    get_evaluate_agent,
)

logger = logging.getLogger(__name__)

_agent = get_evaluate_agent()
_cache = DiskRelevanceCache()

# Lock for thread-safe state mutations
_state_lock = asyncio.Lock()

_evaluate_retry_config = RetryConfig(env_prefix="EVALUATE")


async def _evaluate_with_retry(
    *, repo_url: str, repo_path: Path, prompt: str, attempt: int = 0
) -> bool:
    max_attempts = _evaluate_retry_config.get_max_attempts()

    try:
        return await _agent.evaluate(repo_path, prompt)
    except Exception as e:
        if attempt < max_attempts:
            backoff_seconds = _evaluate_retry_config.calculate_backoff(attempt)
            logger.warning(
                "[orchestrator] evaluate failed for %s; retrying after %.1fs backoff (attempt %s): %s",
                repo_url,
                backoff_seconds,
                attempt + 1,
                str(e),
            )
            await asyncio.sleep(backoff_seconds)
            return await _evaluate_with_retry(
                repo_url=repo_url,
                repo_path=repo_path,
                prompt=prompt,
                attempt=attempt + 1,
            )

        logger.error(
            "[orchestrator] evaluate failed for %s after %s attempt(s) (max=%s): %s",
            repo_url,
            attempt,
            max_attempts,
            str(e),
        )
        raise


async def _evaluate_relevance_with_cache(
    *, repo_url: str, repo_path: Path, prompt: str
) -> bool:
    sha = try_get_repo_head_sha(repo_path)
    prompt_hash = compute_prompt_hash(prompt)

    if not sha:
        # If we cannot resolve a revision SHA, fall back to evaluating without caching.
        logger.warning(
            "[orchestrator] no SHA for %s; evaluating without cache", repo_url
        )
        return await _evaluate_with_retry(
            repo_url=repo_url, repo_path=repo_path, prompt=prompt
        )

    cached = _cache.get(repo_identifier=repo_url, sha=sha, prompt_hash=prompt_hash)
    if cached is not None:
        logger.info(
            "[orchestrator] relevance cache hit repo=%s sha=%s prompt=%s -> %s",
            repo_url,
            sha[:8],
            prompt_hash[:8],
            cached,
        )
        return cached

    decision = await _evaluate_with_retry(
        repo_url=repo_url, repo_path=repo_path, prompt=prompt
    )
    _cache.set(
        repo_identifier=repo_url, sha=sha, prompt_hash=prompt_hash, value=decision
    )
    logger.info(
        "[orchestrator] relevance cache store repo=%s sha=%s prompt=%s -> %s",
        repo_url,
        sha[:8],
        prompt_hash[:8],
        decision,
    )
    return decision


async def _prepare_planning_clone(
    *, repo_url: str, working_dir: Path, github_token: str | None
) -> Path:
    """Prepare a read-only planning clone for evaluation."""
    planning_dir = working_dir / "_orchestrator"
    repo_clone = await asyncio.to_thread(
        prepare_workspace,
        repo=repo_url,
        working_dir=planning_dir,
        github_token=github_token,
        branch_name=None,
        stable=True,
    )
    return repo_clone.path


async def evaluate_relevance_step(
    ctx: StepContext[OrchestratorState, None, str | None],
) -> str | None:
    repo_url = ctx.inputs

    # Allow a None sentinel to flow through the parallel pipeline. This is used
    # to let downstream orchestration run with a no-repo prompt.
    if repo_url is None:
        return None

    if not ctx.state.relevance_prompt:
        logger.info(
            "[orchestrator] relevance skipped for %s (no relevance_prompt provided)",
            repo_url,
        )
        return repo_url

    assert ctx.state.working_dir is not None
    repo_path = await _prepare_planning_clone(
        repo_url=repo_url,
        working_dir=ctx.state.working_dir,
        github_token=ctx.state.github_token,
    )
    async with _state_lock:
        ctx.state.planning_clones[repo_url] = repo_path

    is_relevant = await _evaluate_relevance_with_cache(
        repo_url=repo_url,
        repo_path=repo_path,
        prompt=ctx.state.relevance_prompt,
    )
    logger.info("[orchestrator] relevance %s -> %s", repo_url, is_relevant)

    if not is_relevant:
        async with _state_lock:
            ctx.state.irrelevant.append(repo_url)
        return None

    return repo_url
