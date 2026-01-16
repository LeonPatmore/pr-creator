from __future__ import annotations

import logging
import time
from functools import partial

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.state import OrchestratorState

from .agent import OrchestrateChangeDeps, build_orchestrate_change_agent
from .concurrency import CONCURRENCY_SEMAPHORE, MAX_PARALLEL_REPOS
from .state_updates import record_error, record_results
from .tools import repo_change_tool
from .user_prompt_builder import build_orchestrator_user_prompt

logger = logging.getLogger(__name__)


async def orchestrate_change_step(
    ctx: StepContext[OrchestratorState, None, str | None],
) -> None:
    repo_url = ctx.inputs

    # In the parallel map() path, None means "filtered out as irrelevant" — skip.
    if repo_url is None and ctx.state.repos:
        logger.debug("[orchestrator] skipping irrelevant repo (None input)")
        return

    repo_url_for_logging = repo_url or "<no-repo>"

    async with CONCURRENCY_SEMAPHORE:
        logger.info(
            "[orchestrator] processing %s (active: %d/%d)",
            repo_url_for_logging,
            MAX_PARALLEL_REPOS - CONCURRENCY_SEMAPHORE._value,
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
                response = result.output
            except Exception as e:
                error_msg = f"Orchestrator agent failed: {type(e).__name__}: {e}"
                logger.error("[orchestrator] %s", error_msg)
                await record_error(ctx, error_msg)
                return

            if response.error:
                logger.error("[orchestrator] agent returned error: %s", response.error)
                await record_error(ctx, response.error)
                return

            await record_results(
                ctx,
                response.results,
                repo_url_for_logging,
                tool_called["called"],
            )
