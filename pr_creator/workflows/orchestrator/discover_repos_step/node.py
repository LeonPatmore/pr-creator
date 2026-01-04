from __future__ import annotations

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.orchestrator.discover_repos_step.repo_discovery import (
    resolve_and_normalize_repos,
)


class DiscoverReposOrchestrator(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        ctx.state.repos = resolve_and_normalize_repos(
            list(ctx.state.repos),
            datadog_team=ctx.state.datadog_team,
            datadog_site=ctx.state.datadog_site,
        )
        from pr_creator.workflows.orchestrator.next_repo_step.node import (
            NextRepoOrchestrator,
        )

        return NextRepoOrchestrator()
