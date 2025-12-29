from __future__ import annotations

import logging
from dataclasses import dataclass
from pr_creator.evaluate_agents import get_evaluate_agent

from pydantic_graph import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)

_agent = get_evaluate_agent()


@dataclass
class EvaluateRelevance(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        # If relevance_prompt is empty, treat all repos as relevant.
        if ctx.state.relevance_prompt:
            is_relevant = _agent.evaluate(path, ctx.state.relevance_prompt)
        else:
            logger.info(
                "No relevance prompt provided; defaulting %s to relevant", self.repo_url
            )
            is_relevant = True
        logger.info("Relevance %s -> %s", self.repo_url, is_relevant)
        if is_relevant:
            ctx.state.relevant.append(self.repo_url)
            from .apply import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)
        from .next_repo import NextRepo

        ctx.state.irrelevant.append(self.repo_url)
        return NextRepo()
