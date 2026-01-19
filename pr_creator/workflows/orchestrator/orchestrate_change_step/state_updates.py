from __future__ import annotations

import asyncio
import logging

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.state import OrchestratorState

from .agent import ChangeAgentResponse

logger = logging.getLogger(__name__)

STATE_LOCK = asyncio.Lock()


async def record_error(
    ctx: StepContext[OrchestratorState, None, str | None], error: str
) -> None:
    async with STATE_LOCK:
        ctx.state.orchestrator_errors.append(error)


async def record_results(
    ctx: StepContext[OrchestratorState, None, str | None],
    results: list[ChangeAgentResponse],
    repo_url: str,
    tool_called: bool,
) -> None:
    if not tool_called and results:
        logger.warning(
            "[orchestrator] agent returned %d PRs without calling repo_change tool for %s",
            len(results),
            repo_url,
        )

    async with STATE_LOCK:
        for r in results:
            if r.error:
                ctx.state.orchestrator_errors.append(r.error)
                continue

            if r.pr_url:
                ctx.state.created_prs.append(
                    {
                        "repo_url": r.repo_url,
                        "branch": r.branch or "",
                        "pr_url": r.pr_url,
                        "pushed_sha": r.pushed_sha,
                        "changes_pushed": r.changes_pushed,
                        "ci_passed": r.ci_passed,
                        "ci_failure_summaries": r.ci_failure_summaries,
                    }
                )
