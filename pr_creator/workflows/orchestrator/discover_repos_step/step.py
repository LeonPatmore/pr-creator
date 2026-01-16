from __future__ import annotations

import logging

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.discover_repos_step.policy import (
    choose_parallel_inputs,
)
from pr_creator.workflows.orchestrator.discover_repos_step.repo_discovery import (
    resolve_and_normalize_repos,
)
from pr_creator.workflows.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


async def discover_repos_step(
    ctx: StepContext[OrchestratorState, None, None],
) -> list[str | None]:
    repos = resolve_and_normalize_repos(
        list(ctx.state.repos),
        datadog_team=ctx.state.datadog_team,
        datadog_site=ctx.state.datadog_site,
    )

    ctx.state.repos = repos

    policy = choose_parallel_inputs(
        repos=repos, has_mcp_config=bool(ctx.state.mcp_config_path)
    )
    if policy.log_message:
        logger.log(policy.log_level, "%s", policy.log_message)

    return policy.parallel_inputs
