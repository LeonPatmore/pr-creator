from __future__ import annotations

import logging
import os

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.repo_discovery import discover_repos_from_datadog
from pr_creator.git_urls import normalize_repo_identifier

logger = logging.getLogger(__name__)


class DiscoverRepos(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        repos = list(ctx.state.repos)
        default_org = os.environ.get("GITHUB_DEFAULT_ORG")

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

        normalized: list[str] = []
        for r in deduped:
            normalized.append(normalize_repo_identifier(r, default_org))

        # Deduplicate after normalization to avoid duplicates across formats
        seen_normalized = set()
        normalized_deduped: list[str] = []
        for r in normalized:
            if r not in seen_normalized:
                normalized_deduped.append(r)
                seen_normalized.add(r)

        ctx.state.repos = normalized_deduped
        if not ctx.state.repos:
            raise ValueError("No repositories provided or discovered; cannot proceed.")

        from .next_repo import NextRepo

        return NextRepo()
