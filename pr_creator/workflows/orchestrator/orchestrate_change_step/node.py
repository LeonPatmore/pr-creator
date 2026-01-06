from __future__ import annotations

import logging
from functools import partial
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    ChangeAgentResponse,
    OrchestrateChangeDeps,
    OrchestratorResponse,
    build_orchestrate_change_agent,
)
from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.workflow import run_repo_change_for_repo

logger = logging.getLogger(__name__)


async def repo_change_tool(
    ctx: GraphRunContext, repo_url: str, prompt: str
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


@dataclass
class OrchestrateChange(BaseNode):
    """
    AI-driven orchestration step.

    This step is an AI agent that can "call" the repo-change workflow as a tool.

    If repo_url is None, the agent is responsible for discovering the target repository
    using available tools (e.g., GitHub MCP tools).
    """

    repo_url: str | None

    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        bound_repo_change_tool = partial(repo_change_tool, ctx)

        agent, tool_called = build_orchestrate_change_agent(
            repo_change_tool=bound_repo_change_tool,
            mcp_config_path=ctx.state.mcp_config_path,
            github_default_org=ctx.state.github_default_org,
        )

        # Build user prompt with appropriate prefix based on whether repo is specified
        if self.repo_url:
            user_prompt = (
                f"This change prompt applies to the following repo: {self.repo_url}\n\n"
                f"Base request:\n{ctx.state.prompt.strip()}\n"
            )
        else:
            user_prompt = (
                "Target repo is not defined, you should discover it with any available tools or context. "
                "For example, you can use github tools to search for the relevant repository.\n\n"
                f"Base request:\n{ctx.state.prompt.strip()}\n"
            )

        result = await agent.run(
            user_prompt, deps=OrchestrateChangeDeps(repo_url=self.repo_url or "")
        )
        response: OrchestratorResponse = result.output

        # Check if the agent returned an error (e.g., unable to determine target repo)
        if response.error:
            logger.error(
                "[orchestrator] agent returned error: %s",
                response.error,
            )
            ctx.state.orchestrator_errors.append(response.error)
            # Skip to next repo (or end workflow if no more repos)
            from pr_creator.workflows.orchestrator.next_repo_step.node import (
                NextRepoOrchestrator,
            )

            return NextRepoOrchestrator()

        results = response.results

        # Enforce the contract: changes should only happen through the repo_change tool.
        # If the agent didn't call it, results will typically be empty.
        if not tool_called["called"] and results:
            logger.warning(
                "[orchestrator] agent returned %d PRs without calling repo_change tool",
                len(results),
            )

        # Aggregate tool output into orchestrator state.
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
                    }
                )

        from pr_creator.workflows.orchestrator.next_repo_step.node import (
            NextRepoOrchestrator,
        )

        return NextRepoOrchestrator()
