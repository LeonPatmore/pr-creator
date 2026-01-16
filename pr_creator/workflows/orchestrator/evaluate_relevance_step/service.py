from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pr_creator.retry_utils import RetryConfig
from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.factory import (
    get_evaluate_agent,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.relevance_cache import (
    DiskRelevanceCache,
    compute_prompt_hash,
    try_get_repo_head_sha,
)

logger = logging.getLogger(__name__)

_agent = get_evaluate_agent()
_cache = DiskRelevanceCache()
_evaluate_retry_config = RetryConfig(env_prefix="EVALUATE")


async def evaluate_with_retry(
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
            return await evaluate_with_retry(
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


async def evaluate_relevance_with_cache(
    *, repo_url: str, repo_path: Path, prompt: str
) -> bool:
    sha = try_get_repo_head_sha(repo_path)
    prompt_hash = compute_prompt_hash(prompt)

    if not sha:
        logger.warning(
            "[orchestrator] no SHA for %s; evaluating without cache", repo_url
        )
        return await evaluate_with_retry(
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

    decision = await evaluate_with_retry(
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
