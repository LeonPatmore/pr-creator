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
) -> list[str]:
    """
    Discover and normalize repository URLs.

    Returns list of repo URLs for parallel processing.
    Empty list will result in no processing (discovery mode to be implemented).
    """
    repos = resolve_and_normalize_repos(
        list(ctx.state.repos),
        datadog_team=ctx.state.datadog_team,
        datadog_site=ctx.state.datadog_site,
    )

    ctx.state.repos = repos

    # If no repos were discovered, log warning
    if not repos:
        if not ctx.state.mcp_config_path:
            logger.warning(
                "No repositories provided and no MCP config specified. "
                "The orchestrator will skip processing. "
                "Consider providing --repo, --datadog-team, or --mcp-config."
            )
        else:
            logger.info(
                "No repositories provided; skipping parallel processing. "
                "Discovery mode to be implemented in future update."
            )
    else:
        logger.info(
            f"[orchestrator] discovered {len(repos)} repos for parallel processing"
        )

    return repos
