from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.retry_utils import RetryConfig
from pr_creator.workflows.repo_change.review_step.review_agents import (
    ReviewAgent,
    get_review_agent,
)

logger = logging.getLogger(__name__)

_agent: ReviewAgent = get_review_agent()
_review_step_retry_config = RetryConfig(env_prefix="REVIEW_STEP")
_REVIEW_CHANGES_REQUIRED_MAX_RETRIES = 2


def _snippet(text: str | None, *, limit: int = 300) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "..."


def _max_changes_required_retries() -> int:
    """
    Max number of review->apply retries when the reviewer returns CHANGES_REQUIRED.
    This is intentionally capped to keep the workflow bounded.
    """
    raw = (os.environ.get("REVIEW_MAX_ATTEMPTS") or "").strip()
    if not raw:
        return _REVIEW_CHANGES_REQUIRED_MAX_RETRIES
    try:
        return max(0, min(int(raw), _REVIEW_CHANGES_REQUIRED_MAX_RETRIES))
    except Exception:
        return _REVIEW_CHANGES_REQUIRED_MAX_RETRIES


@dataclass
class ReviewChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        changes_required_attempts = ctx.state.review_attempts.get(self.repo_url, 0)
        max_changes_required_retries = _max_changes_required_retries()
        step_attempts = ctx.state.review_step_attempts.get(self.repo_url, 0)
        max_step_attempts = _review_step_retry_config.get_max_attempts()
        logger.info("Reviewing changes for %s at %s", self.repo_url, path)
        logger.info(
            "[review] agent=%s step_max_attempts=%s step_current_attempts=%s "
            "changes_required_max_retries=%s changes_required_current_retries=%s",
            type(_agent).__name__,
            max_step_attempts,
            step_attempts,
            max_changes_required_retries,
            changes_required_attempts,
        )

        try:
            needs_changes, feedback = await _agent.review(
                Path(path),
                context_roots=ctx.state.context_roots,
                task_prompt=ctx.state.prompt,
                secrets=ctx.state.change_agent_secrets,
            )
        except Exception as e:
            if step_attempts < max_step_attempts:
                ctx.state.review_step_attempts[self.repo_url] = step_attempts + 1
                backoff_seconds = _review_step_retry_config.calculate_backoff(
                    step_attempts
                )
                logger.warning(
                    "[review] agent errored; retrying after %.1fs backoff (attempt %s): %s",
                    backoff_seconds,
                    step_attempts + 1,
                    str(e),
                )
                await asyncio.sleep(backoff_seconds)
                return ReviewChanges(repo_url=self.repo_url)

            logger.error(
                "[review] agent errored after %s attempt(s) (max=%s): %s",
                step_attempts,
                max_step_attempts,
                str(e),
            )
            raise

        logger.info(
            "[review] result needs_changes=%s feedback_present=%s feedback_snippet=%r",
            needs_changes,
            bool(feedback and feedback.strip()),
            _snippet(feedback),
        )

        ctx.state.review_feedback[self.repo_url] = (
            feedback if feedback is not None else "READY_TO_COMMIT"
        )

        if needs_changes:
            if changes_required_attempts < max_changes_required_retries:
                ctx.state.review_attempts[self.repo_url] = changes_required_attempts + 1
                ctx.state.review_pending[self.repo_url] = (
                    feedback if feedback is not None else "Changes required."
                )
                logger.info(
                    "[review] changes required; returning to apply (retry %s/%s)",
                    changes_required_attempts + 1,
                    max_changes_required_retries,
                )
                from pr_creator.workflows.repo_change.apply_step.node import (
                    ApplyChanges,
                )

                return ApplyChanges(repo_url=self.repo_url)

            logger.warning(
                "[review] changes still required after %s retry/retries (max=%s); proceeding to submit",
                changes_required_attempts,
                max_changes_required_retries,
            )

        from pr_creator.workflows.repo_change.submit_step.node import SubmitChanges

        return SubmitChanges(repo_url=self.repo_url)
