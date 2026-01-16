from __future__ import annotations

import asyncio
import logging
import os
import time
from functools import partial
from pathlib import Path

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    ChangeAgentResponse,
    OrchestrateChangeDeps,
    OrchestratorResponse,
    build_orchestrate_change_agent,
)
from pr_creator.workflows.orchestrator.orchestrate_change_step.user_prompt_builder import (
    build_orchestrator_user_prompt,
)
from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.workflow import run_repo_change_for_repo

logger = logging.getLogger(__name__)


MAX_PARALLEL_REPOS = int(os.environ.get("MAX_PARALLEL_REPOS", "3"))
_concurrency_semaphore = asyncio.Semaphore(MAX_PARALLEL_REPOS)

# Lock for thread-safe state mutations (shared state across parallel tasks)
_state_lock = asyncio.Lock()


async def repo_change_tool(
    ctx: StepContext, repo_url: str, additional_prompt: str
) -> ChangeAgentResponse:
    """
    Implementation of the `repo_change(repo_url, additional_prompt)` tool that the orchestrator agent calls.

    This lives in `node.py` (not `agent.py`) because it must:
    - read/write workflow state (`ctx.state.*`)
    - invoke the repo-change workflow
    - translate failures into structured tool output instead of crashing the orchestrator
    """
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
        async with _state_lock:
            ctx.state.orchestrator_errors.append(msg)
        # Return an error response to the orchestrator agent (as tool output),
        # so it can decide how to proceed.
        return ChangeAgentResponse(
            repo_url=repo_url,
            branch=None,
            pr_url=None,
            pushed_sha=None,
            error=msg,
        )


async def _record_error(ctx: StepContext, error: str) -> None:
    """Record error in state (thread-safe)."""
    async with _state_lock:
        ctx.state.orchestrator_errors.append(error)


async def _record_results(
    ctx: StepContext,
    results: list[ChangeAgentResponse],
    repo_url: str,
    tool_called: bool,
) -> None:
    """Record orchestrator results in state (thread-safe)."""
    if not tool_called and results:
        logger.warning(
            "[orchestrator] agent returned %d PRs without calling repo_change tool for %s",
            len(results),
            repo_url,
        )

    async with _state_lock:
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
                    }
                )


async def orchestrate_change_step(
    ctx: StepContext[OrchestratorState, None, str | None],
) -> None:
    """
    Orchestrate change for repositories.

    Accepts either:
    - a repo URL (normal path), or
    - None

    The ONLY difference is the user prompt: when no repo is provided, the prompt omits
    the target-repo header. None produced by relevance filtering is skipped.
    """
    repo_url = ctx.inputs

    # In the parallel map() path, None means "filtered out as irrelevant" — skip.
    if repo_url is None and ctx.state.repos:
        logger.debug("[orchestrator] skipping irrelevant repo (None input)")
        return

    repo_url_for_logging = repo_url or "<no-repo>"

    async with _concurrency_semaphore:
        logger.info(
            "[orchestrator] processing %s (active: %d/%d)",
            repo_url_for_logging,
            MAX_PARALLEL_REPOS - _concurrency_semaphore._value,
            MAX_PARALLEL_REPOS,
        )

        bound_repo_change_tool = partial(repo_change_tool, ctx)

        start_build = time.time()
        logger.info(
            "[orchestrator] building agent (MCP config: %s)",
            "enabled" if ctx.state.mcp_config_path else "disabled",
        )

        async with build_orchestrate_change_agent(
            repo_change_tool=bound_repo_change_tool,
            mcp_config_path=ctx.state.mcp_config_path,
            github_default_org=ctx.state.github_default_org,
        ) as (agent, tool_called):
            logger.debug(
                "[orchestrator] agent built (took %.2fs)",
                time.time() - start_build,
            )

            user_prompt = build_orchestrator_user_prompt(
                repo_url=repo_url, base_prompt=ctx.state.prompt
            )
            deps_repo_url = repo_url or ""

            start_run = time.time()
            logger.debug("[orchestrator] calling agent.run()")

            try:
                result = await agent.run(
                    user_prompt, deps=OrchestrateChangeDeps(repo_url=deps_repo_url)
                )
                logger.info(
                    "[orchestrator] agent.run() completed (took %.2fs)",
                    time.time() - start_run,
                )
                response: OrchestratorResponse = result.output
            except Exception as e:
                error_msg = f"Orchestrator agent failed: {type(e).__name__}: {e}"
                logger.error("[orchestrator] %s", error_msg)
                await _record_error(ctx, error_msg)
                return

            if response.error:
                logger.error("[orchestrator] agent returned error: %s", response.error)
                await _record_error(ctx, response.error)
                return

            await _record_results(
                ctx,
                response.results,
                repo_url_for_logging,
                tool_called["called"],
            )
