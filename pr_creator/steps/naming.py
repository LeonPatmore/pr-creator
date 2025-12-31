from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.naming_agents import get_naming_agent

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe or "auto-change"


@dataclass
class GenerateNames(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        change_id = ctx.state.change_id
        naming_agent = get_naming_agent()
        short_desc = naming_agent.generate_short_desc(ctx.state.prompt)
        slug = _slugify(short_desc)
        human_desc = short_desc.replace("-", " ").strip().capitalize()

        # Branch name
        default_prefix = os.environ.get("DEFAULT_BRANCH_PREFIX", "auto/pr")
        if change_id:
            branch = f"{change_id}/{slug}"
        else:
            branch = f"{default_prefix}/{slug}"

        # PR title and commit message
        pr_title = f"{change_id}: {human_desc}" if change_id else human_desc
        commit_message = pr_title

        ctx.state.branches[self.repo_url] = branch
        ctx.state.pr_titles[self.repo_url] = pr_title
        ctx.state.commit_messages[self.repo_url] = commit_message

        from .clone import CloneRepo

        return CloneRepo(repo_url=self.repo_url)
