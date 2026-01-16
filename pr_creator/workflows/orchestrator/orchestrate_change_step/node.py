from __future__ import annotations

import asyncio
import logging
import os
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
from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.workflow import run_repo_change_for_repo

logger = logging.getLogger(__name__)

# Concurrency limit: max number of repos processed in parallel
# Can be controlled via environment variable
MAX_PARALLEL_REPOS = int(os.environ.get("MAX_PARALLEL_REPOS", "3"))
_concurrency_semaphore = asyncio.Semaphore(MAX_PARALLEL_REPOS)

# Lock for thread-safe state mutations (shared state across parallel tasks)
_state_lock = asyncio.Lock()


async def repo_change_tool(
    ctx: StepContext, repo_url: str, prompt: str
) -> ChangeAgentResponse:
    """
    Implementation of the `repo_change(repo_url, prompt)` tool that the orchestrator agent calls.

    This lives in `node.py` (not `agent.py`) because it must:
    - read/write workflow state (`ctx.state.*`)
    - invoke the repo-change workflow
    - translate failures into structured tool output instead of crashing the orchestrator
    """
    ctx.state.repo_prompts[repo_url] = prompt
    logger.info(
        "[orchestrator] calling repo_change: repo_url=%s prompt_len=%s prompt_snippet=%r",
        repo_url,
        len(prompt or ""),
        (prompt or "").strip().replace("\r\n", "\n")[:300],
    )
    assert ctx.state.working_dir is not None
    repo_state = RepoChangeState(
        prompt=prompt,
        working_dir=Path(ctx.state.working_dir),
        github_token=ctx.state.github_token,
        context_roots=list(ctx.state.context_roots or []),
        change_agent_secrets=dict(ctx.state.change_agent_secrets or {}),
        change_id=ctx.state.change_id,
        base_prompt=ctx.state.prompt,
    )
    try:
        final_repo_state = await run_repo_change_for_repo(repo_state, repo_url=repo_url)

        # Repo-change is single-repo and now produces at most one PR URL.
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


async def orchestrate_change_step(
    ctx: StepContext[OrchestratorState, None, str | None],
) -> None:
    """
    Orchestrate change for a single repository (parallel execution).

    Input: repo_url (string) or None from parallel .map()
    Output: None (results recorded in state)

    This step runs in parallel for each relevant repo, with concurrency control.
    Each parallel execution gets its own MCP server instance.

    If the input is None (irrelevant repo filtered by evaluate step), this step
    returns immediately without processing.
    """
    repo_url = ctx.inputs

    # Skip processing if repo was filtered out as irrelevant
    if repo_url is None:
        logger.debug(
            "[orchestrator] skipping None input (irrelevant repo filtered out)"
        )
        return

    # Acquire semaphore for concurrency control
    async with _concurrency_semaphore:
        logger.info(
            f"[orchestrator] processing {repo_url} "
            f"(active: {MAX_PARALLEL_REPOS - _concurrency_semaphore._value}/{MAX_PARALLEL_REPOS})"
        )

        bound_repo_change_tool = partial(repo_change_tool, ctx)

        import time

        start_build = time.time()
        logger.info(
            "[orchestrator] building agent for %s (MCP config: %s)",
            repo_url,
            "enabled" if ctx.state.mcp_config_path else "disabled",
        )
        agent, tool_called = build_orchestrate_change_agent(
            repo_change_tool=bound_repo_change_tool,
            mcp_config_path=ctx.state.mcp_config_path,
            github_default_org=ctx.state.github_default_org,
        )
        logger.info(
            "[orchestrator] agent built for %s (took %.2fs)",
            repo_url,
            time.time() - start_build,
        )

        # Build user prompt for this specific repo
        user_prompt = (
            f"This change prompt applies to the following repo: {repo_url}\n\n"
            f"Base request:\n{ctx.state.prompt.strip()}\n"
        )

        try:
            start_run = time.time()
            logger.info("[orchestrator] calling agent.run() for %s", repo_url)
            result = await agent.run(
                user_prompt, deps=OrchestrateChangeDeps(repo_url=repo_url)
            )
            logger.info(
                "[orchestrator] agent.run() completed for %s (took %.2fs)",
                repo_url,
                time.time() - start_run,
            )
            response: OrchestratorResponse = result.output
        except Exception as e:
            error_msg = (
                f"Orchestrator agent failed for {repo_url}: {type(e).__name__}: {e}"
            )
            logger.error("[orchestrator] %s", error_msg)
            async with _state_lock:
                ctx.state.orchestrator_errors.append(error_msg)
            return

        # Check if the agent returned an error
        if response.error:
            logger.error(
                "[orchestrator] agent returned error for %s: %s",
                repo_url,
                response.error,
            )
            async with _state_lock:
                ctx.state.orchestrator_errors.append(response.error)
            return

        results = response.results

        # Enforce the contract: changes should only happen through the repo_change tool.
        if not tool_called["called"] and results:
            logger.warning(
                "[orchestrator] agent returned %d PRs without calling repo_change tool for %s",
                len(results),
                repo_url,
            )

        # Aggregate tool output into orchestrator state (thread-safe).
        async with _state_lock:
            for r in results:
                # Record tool-level failures.
                if r.error:
                    ctx.state.orchestrator_errors.append(r.error)
                    continue
                # Record successful PRs in the orchestrator rollup.
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


async def orchestrate_change_discovery_mode(
    ctx: StepContext[OrchestratorState, None, None],
) -> None:
    """
    Orchestrate change in discovery mode (no repos specified).

    The orchestrator agent will discover the target repository using available tools.
    This runs sequentially (not parallel) since we don't know the target repos upfront.
    """
    logger.info("[orchestrator] discovery mode: orchestrator will discover target repo")

    bound_repo_change_tool = partial(repo_change_tool, ctx)

    logger.info(
        "[orchestrator] building agent for discovery mode (MCP config: %s)",
        "enabled" if ctx.state.mcp_config_path else "disabled",
    )
    agent, tool_called = build_orchestrate_change_agent(
        repo_change_tool=bound_repo_change_tool,
        mcp_config_path=ctx.state.mcp_config_path,
        github_default_org=ctx.state.github_default_org,
    )

    # Build user prompt without repo specification
    user_prompt = (
        "Target repo is not defined, you should discover it with any available tools or context. "
        "For example, you can use github tools to search for the relevant repository.\n\n"
        f"Base request:\n{ctx.state.prompt.strip()}\n"
    )

    try:
        logger.info("[orchestrator] calling agent.run() for discovery mode")
        result = await agent.run(user_prompt, deps=OrchestrateChangeDeps(repo_url=""))
        logger.info("[orchestrator] agent.run() completed for discovery mode")
        response: OrchestratorResponse = result.output
    except Exception as e:
        error_msg = (
            f"Orchestrator agent failed in discovery mode: {type(e).__name__}: {e}"
        )
        logger.error("[orchestrator] %s", error_msg)
        async with _state_lock:
            ctx.state.orchestrator_errors.append(error_msg)
        return

    # Check if the agent returned an error
    if response.error:
        logger.error(
            "[orchestrator] agent returned error in discovery mode: %s",
            response.error,
        )
        async with _state_lock:
            ctx.state.orchestrator_errors.append(response.error)
        return

    results = response.results

    # Enforce the contract
    if not tool_called["called"] and results:
        logger.warning(
            "[orchestrator] agent returned %d PRs without calling repo_change tool",
            len(results),
        )

    # Aggregate tool output into orchestrator state (thread-safe)
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
