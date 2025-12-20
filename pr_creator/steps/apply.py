from __future__ import annotations

import logging
from dataclasses import dataclass

from pr_creator.change_agents import get_change_agent

from .types import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)


@dataclass
class ApplyChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End | None:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Applying change agent on %s at %s", self.repo_url, path)
        agent = get_change_agent()
        agent.run(path, ctx.state.prompt)
        ctx.state.processed.append(self.repo_url)
        from .submit import SubmitChanges

        return SubmitChanges(repo_url=self.repo_url)
