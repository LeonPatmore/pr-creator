from __future__ import annotations

import os
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.orchestrator.init_step.prompt_loading_support.prompt_loading import (
    load_and_merge_prompts,
    resolve_secrets_and_context,
)

DEFAULT_WORKING_DIR = Path.home() / ".pr-creator" / "repos"
DEFAULT_DATADOG_SITE = "datadoghq.com"
DEFAULT_PROMPT_CONFIG_REF = "main"


class InitOrchestrator(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        if not ctx.state.working_dir:
            ctx.state.working_dir = DEFAULT_WORKING_DIR
        if not ctx.state.datadog_site:
            ctx.state.datadog_site = DEFAULT_DATADOG_SITE
        if not ctx.state.prompt_config_ref:
            ctx.state.prompt_config_ref = DEFAULT_PROMPT_CONFIG_REF

        # GitHub auth token is optional overall, but if not explicitly provided via CLI,
        # fall back to the process environment so prompt-config loading + PR submission work.
        if not ctx.state.github_token:
            ctx.state.github_token = os.environ.get("GITHUB_TOKEN")

        resolve_secrets_and_context(ctx.state)
        load_and_merge_prompts(ctx.state)

        from pr_creator.workflows.orchestrator.discover_repos_step.node import (
            DiscoverReposOrchestrator,
        )

        return DiscoverReposOrchestrator()
