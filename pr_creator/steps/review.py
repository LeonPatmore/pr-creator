from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.review_agents import (
    ReviewAgent,
    get_review_agent,
    get_review_max_attempts,
)

logger = logging.getLogger(__name__)

_agent: ReviewAgent = get_review_agent()


def _snippet(text: str | None, *, limit: int = 300) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "..."


def _max_review_attempts() -> int:
    return get_review_max_attempts()


@dataclass
class ReviewChanges(BaseNode):
    repo_url: str

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        path = ctx.state.cloned[self.repo_url]
        logger.info("Reviewing changes for %s at %s", self.repo_url, path)
        logger.info(
            "[review] agent=%s max_attempts=%s current_attempts=%s",
            type(_agent).__name__,
            _max_review_attempts(),
            ctx.state.review_attempts.get(self.repo_url, 0),
        )

        needs_changes, feedback = _agent.review(
            path,
            context_roots=ctx.state.context_roots,
            task_prompt=ctx.state.prompt,
            secrets=ctx.state.change_agent_secrets,
        )
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
            attempts = ctx.state.review_attempts.get(self.repo_url, 0)
            max_attempts = _max_review_attempts()
            if attempts < max_attempts:
                ctx.state.review_attempts[self.repo_url] = attempts + 1
                ctx.state.review_pending[self.repo_url] = (
                    feedback if feedback is not None else "Changes required."
                )
                logger.info(
                    "[review] changes required; returning to apply (attempt %s)",
                    attempts + 1,
                )
                from .apply import ApplyChanges

                return ApplyChanges(repo_url=self.repo_url)

            logger.warning(
                "[review] changes still required after %s attempt(s) (max=%s); proceeding to submit",
                attempts,
                max_attempts,
            )

        from .submit import SubmitChanges

        return SubmitChanges(repo_url=self.repo_url)
