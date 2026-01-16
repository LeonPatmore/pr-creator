from __future__ import annotations

import logging

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.evaluate_relevance_step.planning_clone import (
    prepare_planning_clone,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.service import (
    evaluate_relevance_with_cache,
)
from pr_creator.workflows.orchestrator.evaluate_relevance_step.state_updates import (
    record_irrelevant,
    record_planning_clone,
)
from pr_creator.workflows.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


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
    repo_path = await prepare_planning_clone(
        repo_url=repo_url,
        working_dir=ctx.state.working_dir,
        github_token=ctx.state.github_token,
    )
    await record_planning_clone(ctx, repo_url=repo_url, repo_path=repo_path)

    is_relevant = await evaluate_relevance_with_cache(
        repo_url=repo_url,
        repo_path=repo_path,
        prompt=ctx.state.relevance_prompt,
    )
    logger.info("[orchestrator] relevance %s -> %s", repo_url, is_relevant)

    if not is_relevant:
        await record_irrelevant(ctx, repo_url=repo_url)
        return None

    return repo_url
