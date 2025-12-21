from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)


def evaluate_relevance(relevance_prompt: str, repo_path: Path) -> bool:
    # Placeholder for relevance evaluation logic; currently always relevant.
    return True


@dataclass
class EvaluateRelevance(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        is_relevant = evaluate_relevance(ctx.state.relevance_prompt, path)
        logger.info("Relevance %s -> %s", self.repo_url, is_relevant)
        if is_relevant:
            ctx.state.relevant.append(self.repo_url)
            from .apply import ApplyChanges

            return ApplyChanges(repo_url=self.repo_url)
        from .next_repo import NextRepo

        return NextRepo()
