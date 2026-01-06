from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    CreatedPR,
    OrchestrateChangeDeps,
    build_orchestrate_change_agent,
)
from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.workflow import run_repo_change_for_repo

logger = logging.getLogger(__name__)


async def _repo_change_tool(
    ctx: GraphRunContext, *, repo_url: str, prompt: str
) -> list[dict[str, str]]:
    assert ctx.state.working_dir is not None
    repo_state = RepoChangeState(
        prompt=prompt,
        working_dir=Path(ctx.state.working_dir),
        github_token=ctx.state.github_token,
        context_roots=list(ctx.state.context_roots or []),
        change_agent_secrets=dict(ctx.state.change_agent_secrets or {}),
        change_id=ctx.state.change_id,
    )
    final_repo_state = await run_repo_change_for_repo(repo_state, repo_url=repo_url)
    # Return the repo-change results; the orchestrator aggregates them.
    return list(final_repo_state.created_prs or [])


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
        tool_prs: list[dict[str, str]] = []

        async def _tool_repo_change(repo_url: str, prompt: str) -> list[CreatedPR]:
            ctx.state.repo_prompts[repo_url] = prompt
            nonlocal tool_prs
            logger.info(
                "[orchestrator] calling repo_change: repo_url=%s prompt_len=%s prompt_snippet=%r",
                repo_url,
                len(prompt or ""),
                (prompt or "").strip().replace("\r\n", "\n")[:300],
            )
            tool_prs = await _repo_change_tool(ctx, repo_url=repo_url, prompt=prompt)
            logger.info(
                "[orchestrator] repo_change returned %d PR record(s): %s",
                len(tool_prs),
                [
                    {
                        "repo_url": p.get("repo_url"),
                        "branch": p.get("branch"),
                        "pr_url": p.get("pr_url"),
                        "pushed_sha": p.get("pushed_sha"),
                    }
                    for p in tool_prs
                ],
            )
            return [CreatedPR.model_validate(p) for p in tool_prs]

        agent, tool_called = build_orchestrate_change_agent(
            repo_change_tool=_tool_repo_change,
            mcp_config_path=ctx.state.mcp_config_path,
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
        prs = result.output

        # Enforce the contract: changes should only happen through the repo_change tool.
        # If the agent didn't call it, prs will typically be empty.
        if not tool_called["called"] and prs:
            logger.warning(
                "[orchestrator] agent returned %d PRs without calling repo_change tool",
                len(prs),
            )

        # Aggregate tool output into orchestrator state.
        ctx.state.created_prs.extend([p.model_dump() for p in prs])

        from pr_creator.workflows.orchestrator.next_repo_step.node import (
            NextRepoOrchestrator,
        )

        return NextRepoOrchestrator()
