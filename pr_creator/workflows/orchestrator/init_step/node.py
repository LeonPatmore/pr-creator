from __future__ import annotations

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.orchestrator.init_step.prompt_loading_support.prompt_loading import (
    load_and_merge_prompts,
    resolve_secrets_and_context,
)


class InitOrchestrator(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        resolve_secrets_and_context(ctx.state)
        load_and_merge_prompts(ctx.state)

        from pr_creator.workflows.orchestrator.discover_repos_step.node import (
            DiscoverReposOrchestrator,
        )

        return DiscoverReposOrchestrator()
