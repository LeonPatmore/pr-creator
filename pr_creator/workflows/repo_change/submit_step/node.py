from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import partial

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.repo_change.submit_step import get_submitter

logger = logging.getLogger(__name__)


@dataclass
class SubmitChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Submitting changes for %s at %s", self.repo_url, path)
        # Resolve submitter at runtime; token is loaded once at CLI and threaded via state.
        submitter = get_submitter(github_token=ctx.state.github_token)
        # Submitting does git + network (blocking); offload so repo workflows can run in parallel.
        result = await asyncio.to_thread(
            partial(
                submitter.submit,
                path,
                change_prompt=ctx.state.additional_prompt,
                base_prompt=ctx.state.base_prompt,
                change_id=ctx.state.change_id,
                branch=ctx.state.branches.get(self.repo_url),
                pr_title=ctx.state.pr_titles.get(self.repo_url),
                commit_message=ctx.state.commit_messages.get(self.repo_url),
            )
        )

        # Track whether changes were pushed
        # If result is None, no changes were pushed
        # If result has pushed_sha, changes were pushed
        ctx.state.changes_pushed = False

        if result:
            pr_url = (result or {}).get("pr_url")
            pushed_sha = (result or {}).get("pushed_sha")

            # Track pushed sha even if PR creation is skipped (e.g., missing token).
            if pushed_sha:
                ctx.state.created_pr_pushed_sha = pushed_sha
                ctx.state.changes_pushed = True

            # Only consider "created_pr" to exist if we have a PR URL.
            if pr_url:
                if not ctx.state.created_pr:
                    ctx.state.created_pr = pr_url
                else:
                    assert ctx.state.created_pr == pr_url, (
                        "SubmitChanges returned different PR URL for same repo: "
                        f"existing={ctx.state.created_pr!r} new={pr_url!r}"
                    )

        from pr_creator.workflows.repo_change.wait_for_actions_step.node import (
            WaitForActions,
        )

        return WaitForActions(repo_url=self.repo_url)
