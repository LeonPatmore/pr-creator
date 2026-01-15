from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic_graph.beta import StepContext

from pr_creator.repo_workspace import prepare_workspace
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


async def _evaluate_relevance_with_cache_async(
    *, repo_url: str, repo_path: Path, prompt: str
) -> bool:
    sha = try_get_repo_head_sha(repo_path)
    prompt_hash = compute_prompt_hash(prompt)

    if not sha:
        # If we cannot resolve a revision SHA, fall back to evaluating without caching.
        logger.warning(
            "[orchestrator] no SHA for %s; evaluating without cache", repo_url
        )
        return await _agent.evaluate(repo_path, prompt)

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

    decision = await _agent.evaluate(repo_path, prompt)
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


def _evaluate_relevance_with_cache(
    *, repo_url: str, repo_path: Path, prompt: str
) -> bool:
    sha = try_get_repo_head_sha(repo_path)
    prompt_hash = compute_prompt_hash(prompt)

    if not sha:
        # If we cannot resolve a revision SHA, fall back to evaluating without caching.
        # Note: _agent.evaluate is now async, so this must be called with await from async context
        raise RuntimeError(
            "Cannot evaluate without SHA - this function should not be called without a valid SHA"
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

    # Cache miss - we'll need to evaluate, but that's async now
    # This function should not be called anymore - use the async version
    raise RuntimeError("Cache miss - use async evaluation path")


async def evaluate_relevance_step(
    ctx: StepContext[OrchestratorState, None, str],
) -> str | None:
    """
    Evaluate relevance for a single repository.

    Input: repo_url (string) from parallel .map()
    Output: repo_url if relevant, None if not (filtered out)

    This step runs in parallel for each discovered repo.
    """
    repo_url = ctx.inputs

    # If relevance_prompt is empty, treat all repos as relevant.
    if not ctx.state.relevance_prompt:
        logger.info(
            "[orchestrator] relevance skipped for %s (no relevance_prompt provided)",
            repo_url,
        )
        return repo_url

    # Prepare a read-only planning clone for evaluation.
    assert ctx.state.working_dir is not None
    planning_dir = Path(ctx.state.working_dir) / "_orchestrator"
    # Workspace preparation does git clone/fetch (blocking I/O); offload to threads
    repo_clone = await asyncio.to_thread(
        prepare_workspace,
        repo=repo_url,
        working_dir=planning_dir,
        github_token=ctx.state.github_token,
        branch_name=None,
        stable=True,
    )
    async with _state_lock:
        ctx.state.planning_clones[repo_url] = repo_clone.path

    # Relevance evaluation calls Cursor agent (blocking); directly call async version
    is_relevant = await _evaluate_relevance_with_cache_async(
        repo_url=repo_url,
        repo_path=repo_clone.path,
        prompt=ctx.state.relevance_prompt,
    )
    logger.info("[orchestrator] relevance %s -> %s", repo_url, is_relevant)

    if not is_relevant:
        async with _state_lock:
            ctx.state.irrelevant.append(repo_url)
        return None  # Filter out irrelevant repos

    return repo_url  # Continue to orchestrate step
