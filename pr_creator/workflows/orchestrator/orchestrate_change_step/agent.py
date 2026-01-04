from __future__ import annotations

from typing import Awaitable, Callable, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext


class CreatedPR(BaseModel):
    repo_url: str
    branch: str
    pr_url: Optional[str] = None
    pushed_sha: Optional[str] = None


class OrchestrateChangeDeps(BaseModel):
    repo_url: str


RepoChangeTool = Callable[[str, str], Awaitable[list[CreatedPR]]]


def build_orchestrate_change_agent(
    *, repo_change_tool: RepoChangeTool
) -> tuple[Agent[OrchestrateChangeDeps, list[CreatedPR]], dict[str, bool]]:
    """
    Build a pydantic-ai agent for orchestration.

    The agent is expected to call the provided `repo_change_tool(repo_url, prompt)` tool.
    Its output type is a list of PR records returned by that tool.
    """

    tool_called = {"called": False}

    agent: Agent[OrchestrateChangeDeps, list[CreatedPR]] = Agent(
        output_type=list[CreatedPR],
        deps_type=OrchestrateChangeDeps,
        system_prompt=(
            "You are a change orchestrator.\n"
            "You must NOT directly modify any files.\n"
            "To make changes, you MUST call the tool `repo_change(repo_url: str, prompt: str)`.\n\n"
            "You have a tool `repo_change(repo_url: str, prompt: str)`.\n"
            "- If you want changes, call repo_change with the repo_url and a repo-specific prompt.\n"
            "- Then return the list of PRs returned by the tool.\n"
            "- If no changes should be made, return an empty list.\n"
        ),
    )

    @agent.tool
    async def repo_change(
        _ctx: RunContext[OrchestrateChangeDeps], repo_url: str, prompt: str
    ) -> list[CreatedPR]:
        tool_called["called"] = True
        return await repo_change_tool(repo_url, prompt)

    return agent, tool_called
