from __future__ import annotations

import logging
import os

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.repo_discovery import discover_repos_from_datadog

logger = logging.getLogger(__name__)


class DiscoverRepos(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        repos = list(ctx.state.repos)

        if ctx.state.datadog_team:
            dd_api = os.environ.get("DATADOG_API_KEY")
            dd_app = os.environ.get("DATADOG_APP_KEY")
            discovered = discover_repos_from_datadog(
                ctx.state.datadog_team,
                dd_api,
                dd_app,
                ctx.state.datadog_site,
            )
            repos.extend(discovered)

        # Deduplicate while preserving order
        seen = set()
        deduped: list[str] = []
        for r in repos:
            if r not in seen:
                deduped.append(r)
                seen.add(r)

        ctx.state.repos = deduped
        if not ctx.state.repos:
            raise ValueError("No repositories provided or discovered; cannot proceed.")

        from .next_repo import NextRepo

        return NextRepo()
