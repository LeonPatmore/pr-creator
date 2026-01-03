from __future__ import annotations

import logging
from dataclasses import dataclass

from pr_creator.submit_change import get_submitter

from pydantic_graph import BaseNode, End, GraphRunContext

logger = logging.getLogger(__name__)

_submitter = get_submitter()


@dataclass
class SubmitChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Submitting changes for %s at %s", self.repo_url, path)
        result = _submitter.submit(
            path,
            change_prompt=ctx.state.prompt,
            change_id=ctx.state.change_id,
            branch=ctx.state.branches.get(self.repo_url),
            pr_title=ctx.state.pr_titles.get(self.repo_url),
            commit_message=ctx.state.commit_messages.get(self.repo_url),
        )
        if result:
            ctx.state.created_prs.append(result)
        from .wait_for_actions import WaitForActions

        return WaitForActions(repo_url=self.repo_url)
