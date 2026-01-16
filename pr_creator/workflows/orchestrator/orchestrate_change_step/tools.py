from __future__ import annotations

import logging
from pathlib import Path

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.workflow import run_repo_change_for_repo

from .agent import ChangeAgentResponse
from .state_updates import record_error

logger = logging.getLogger(__name__)


async def repo_change_tool(
    ctx: StepContext[OrchestratorState, None, str | None],
    repo_url: str,
    additional_prompt: str,
) -> ChangeAgentResponse:
    ctx.state.repo_prompts[repo_url] = additional_prompt
    logger.info(
        "[orchestrator] calling repo_change: repo_url=%s additional_prompt_len=%s additional_prompt_snippet=%r",
        repo_url,
        len(additional_prompt or ""),
        (additional_prompt or "").strip().replace("\r\n", "\n")[:300],
    )

    assert ctx.state.working_dir is not None
    repo_state = RepoChangeState(
        prompt=additional_prompt,
        working_dir=Path(ctx.state.working_dir),
        github_token=ctx.state.github_token,
        context_roots=list(ctx.state.context_roots or []),
        change_agent_secrets=dict(ctx.state.change_agent_secrets or {}),
        change_id=ctx.state.change_id,
        base_prompt=ctx.state.prompt,
    )

    try:
        final_repo_state = await run_repo_change_for_repo(repo_state, repo_url=repo_url)

        resp = ChangeAgentResponse(
            repo_url=repo_url,
            branch=(final_repo_state.branches or {}).get(repo_url) or None,
            pr_url=final_repo_state.created_pr,
            pushed_sha=final_repo_state.created_pr_pushed_sha,
            error=None,
            changes_pushed=final_repo_state.changes_pushed,
            ci_passed=final_repo_state.ci_passed,
        )
        if not resp.pr_url:
            logger.info("[orchestrator] repo_change produced no PR for %s", repo_url)
        else:
            logger.info("[orchestrator] repo_change returned PR: %s", resp.model_dump())
        return resp
    except Exception as e:
        msg = (
            f"repo_change workflow failed for repo_url={repo_url!r}: "
            f"{type(e).__name__}: {e}"
        )
        logger.exception("[orchestrator] %s", msg)
        await record_error(ctx, msg)
        return ChangeAgentResponse(
            repo_url=repo_url,
            branch=None,
            pr_url=None,
            pushed_sha=None,
            error=msg,
        )
