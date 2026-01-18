from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.retry_utils import RetryConfig
from pr_creator.workflows.repo_change.naming_step.naming_agents import get_naming_agent
from pr_creator.workflows.repo_change.naming_step.naming_utils import (
    limit_slug,
    slugify,
    truncate_with_ellipsis,
)

logger = logging.getLogger(__name__)

_agent = get_naming_agent()

# Naming retry configuration
_naming_retry_config = RetryConfig(env_prefix="NAMING")


@dataclass
class GenerateNames(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        change_id = ctx.state.change_id

        attempts = ctx.state.naming_attempts.get(self.repo_url, 0)
        max_attempts = _naming_retry_config.get_max_attempts()

        logger.info(
            "[naming] agent=%s max_attempts=%s current_attempts=%s",
            type(_agent).__name__,
            max_attempts,
            attempts,
        )

        short_desc = await _agent.generate_short_desc(ctx.state.prompt)

        if short_desc is None:
            if attempts < max_attempts:
                ctx.state.naming_attempts[self.repo_url] = attempts + 1
                backoff_seconds = _naming_retry_config.calculate_backoff(attempts)
                logger.warning(
                    "[naming] generation failed; retrying after %.1fs backoff (attempt %s)",
                    backoff_seconds,
                    attempts + 1,
                )
                await asyncio.sleep(backoff_seconds)
                return GenerateNames(repo_url=self.repo_url)

            raise RuntimeError(
                f"[naming] generation failed for repo_url={self.repo_url!r} "
                f"after {attempts} attempt(s) (max={max_attempts})"
            )

        slug_raw = slugify(short_desc)

        # Keep branch slugs short and stable by default.
        slug = limit_slug(slug_raw, max_words=5, max_len=40)

        # Human-readable short description for titles/messages
        human_readable_desc = short_desc.replace("-", " ").strip().capitalize()
        human_desc = (
            truncate_with_ellipsis(human_readable_desc, 80) or "Automated changes"
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

        from pr_creator.workflows.repo_change.workspace_step.node import WorkspaceRepo

        return WorkspaceRepo(repo_url=self.repo_url)
