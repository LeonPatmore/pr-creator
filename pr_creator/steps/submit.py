from __future__ import annotations

import logging
from dataclasses import dataclass

from pr_creator.submit_change import get_submitter

from pydantic_graph import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)


@dataclass
class SubmitChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Submitting changes for %s at %s", self.repo_url, path)
        submitter = get_submitter()
        result = submitter.submit(path)
        if result:
            ctx.state.created_prs.append(result)
        from .cleanup import CleanupRepo

        return CleanupRepo(repo_url=self.repo_url)
