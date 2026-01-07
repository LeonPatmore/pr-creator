from __future__ import annotations

from pydantic_graph import BaseNode, End, GraphRunContext


class NextRepoOrchestrator(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        if not ctx.state.repos:
            return End(None)

        repo_url = ctx.state.repos.pop(0)
        from pr_creator.workflows.orchestrator.evaluate_relevance_step.node import (
            EvaluateRelevanceOrchestrator,
        )

        return EvaluateRelevanceOrchestrator(repo_url=repo_url)
