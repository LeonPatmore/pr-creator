from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.naming_agents import get_naming_agent

logger = logging.getLogger(__name__)


def _truncate_with_ellipsis(text: str, max_len: int) -> str:
    text = text.strip()
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len].rstrip()
    return text[: max_len - 3].rstrip(" -:") + "..."


def _limit_slug(slug: str, max_words: int, max_len: int) -> str:
    parts = [p for p in slug.split("-") if p]
    if max_words > 0:
        parts = parts[:max_words]
    limited = "-".join(parts) if parts else "auto-change"
    if max_len > 0 and len(limited) > max_len:
        limited = limited[:max_len].rstrip("-")
    return limited or "auto-change"


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
        short_desc = naming_agent.generate_short_desc(ctx.state.prompt) or "auto-change"
        slug_raw = _slugify(short_desc)

        # Keep branch slugs short and stable by default.
        slug = _limit_slug(slug_raw, max_words=5, max_len=40)

        # Human-readable short description for titles/messages
        human_readable_desc = short_desc.replace("-", " ").strip().capitalize()
        human_desc = (
            _truncate_with_ellipsis(human_readable_desc, 80) or "Automated changes"
        )

        # Branch name
        default_prefix = os.environ.get("DEFAULT_BRANCH_PREFIX", "auto/pr")
        if change_id:
            branch = f"{change_id}/{slug}"
        else:
            branch = f"{default_prefix}/{slug}"

        # PR title and commit message
        if change_id:
            pr_title = f"{change_id}: {human_desc}"
        else:
            pr_title = human_desc
        commit_message = pr_title

        ctx.state.branches[self.repo_url] = branch
        ctx.state.pr_titles[self.repo_url] = pr_title
        ctx.state.commit_messages[self.repo_url] = commit_message

        from .workspace import WorkspaceRepo

        return WorkspaceRepo(repo_url=self.repo_url)
