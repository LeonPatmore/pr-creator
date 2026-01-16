from __future__ import annotations

import logging

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.discover_repos_step.repo_discovery import (
    resolve_and_normalize_repos,
)

logger = logging.getLogger(__name__)


async def discover_repos_step(
    ctx: StepContext[OrchestratorState, None, None],
) -> list[str | None]:
    """
    Discover and normalize repository URLs.

    Returns list of repo URLs for parallel processing.
    If no repos are discovered and MCP is configured, returns [None] so the orchestrate
    step can run with a no-repo prompt.
    """
    repos = resolve_and_normalize_repos(
        list(ctx.state.repos),
        datadog_team=ctx.state.datadog_team,
        datadog_site=ctx.state.datadog_site,
    )

    ctx.state.repos = repos

    if not repos:
        if not ctx.state.mcp_config_path:
            logger.warning(
                "No repositories provided and no MCP config specified. "
                "The orchestrator will skip processing. "
                "Consider providing --repo, --datadog-team, or --mcp-config."
            )
            return []
        else:
            logger.info(
                "[orchestrator] no repositories discovered; running orchestrator with no-repo prompt"
            )
            return [None]
    else:
        logger.info(
            f"[orchestrator] discovered {len(repos)} repos for parallel processing"
        )
        return repos
