from __future__ import annotations

import logging

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.orchestrator.discover_repos_step.repo_discovery import (
    resolve_and_normalize_repos,
)

logger = logging.getLogger(__name__)


class DiscoverReposOrchestrator(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        ctx.state.repos = resolve_and_normalize_repos(
            list(ctx.state.repos),
            datadog_team=ctx.state.datadog_team,
            datadog_site=ctx.state.datadog_site,
        )

        # If no repos were discovered, go directly to orchestrator without a repo
        # The orchestrator agent will need to discover the target repo
        if not ctx.state.repos:
            if not ctx.state.mcp_config_path:
                logger.warning(
                    "No repositories provided and no MCP config specified. "
                    "The orchestrator will attempt to discover repos but may fail without access to discovery tools. "
                    "Consider providing --repo, --datadog-team, or --mcp-config."
                )
            else:
                logger.info(
                    "No repositories provided; orchestrator will discover target repo using MCP tools."
                )

            from pr_creator.workflows.orchestrator.orchestrate_change_step.node import (
                OrchestrateChange,
            )

            return OrchestrateChange(repo_url=None)

        from pr_creator.workflows.orchestrator.next_repo_step.node import (
            NextRepoOrchestrator,
        )

        return NextRepoOrchestrator()
