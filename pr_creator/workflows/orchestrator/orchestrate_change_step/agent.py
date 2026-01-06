from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

logger = logging.getLogger(__name__)


class CreatedPR(BaseModel):
    repo_url: str
    branch: str
    pr_url: Optional[str] = None
    pushed_sha: Optional[str] = None


class OrchestrateChangeDeps(BaseModel):
    repo_url: str


RepoChangeTool = Callable[[str, str], Awaitable[list[CreatedPR]]]


def _load_mcp_toolsets(mcp_config_path: Optional[Path]) -> list:
    """
    Load MCP servers from a configuration file.

    Returns a list of MCP toolsets that can be passed to a pydantic-ai Agent.
    Returns an empty list if no config is provided or if loading fails.
    """
    if not mcp_config_path:
        return []

    if not mcp_config_path.exists():
        logger.warning(
            "[orchestrator] MCP config path provided but file does not exist: %s",
            mcp_config_path,
        )
        return []

    try:
        from pydantic_ai.mcp import load_mcp_servers

        logger.info("[orchestrator] loading MCP servers from %s", mcp_config_path)
        toolsets = load_mcp_servers(str(mcp_config_path))
        logger.info("[orchestrator] loaded %d MCP server(s) as toolsets", len(toolsets))
        return toolsets
    except ImportError:
        logger.warning(
            "[orchestrator] pydantic-ai MCP support not available; "
            "install with MCP extras to use --mcp-config"
        )
        return []
    except Exception as e:
        logger.warning(
            "[orchestrator] failed to load MCP servers from %s: %s",
            mcp_config_path,
            e,
        )
        return []


def build_orchestrate_change_agent(
    *, repo_change_tool: RepoChangeTool, mcp_config_path: Optional[Path] = None
) -> tuple[Agent[OrchestrateChangeDeps, list[CreatedPR]], dict[str, bool]]:
    """
    Build a pydantic-ai agent for orchestration.

    The agent is expected to call the provided `repo_change_tool(repo_url, prompt)` tool.
    Its output type is a list of PR records returned by that tool.

    If mcp_config_path is provided, loads MCP servers from the config file and adds them
    as toolsets to the agent, enabling it to access external resources (e.g., GitHub repos).
    """

    tool_called = {"called": False}

    model = os.environ.get("ORCHESTRATOR_MODEL", "openai:gpt-5.2")

    # Load MCP servers if config is provided
    toolsets = _load_mcp_toolsets(mcp_config_path)

    # Build system prompt based on whether MCP tools are available
    system_prompt_parts = [
        "You are a change orchestrator.",
        "You must NOT directly modify any files.",
    ]

    if toolsets:
        system_prompt_parts.append(
            "You have access to external tools (e.g., GitHub repositories) via MCP servers. "
            "Use these tools to explore codebases, understand context, and gather information "
            "before planning changes."
        )

    system_prompt_parts.extend(
        [
            "To make changes, you MUST call the tool `repo_change(repo_url: str, prompt: str)`.",
            "IMPORTANT: `repo_change` performs the full workflow including committing, pushing, and opening PRs.",
            "Do NOT instruct it to create PRs; it already does. Your job is only to craft the repo-specific prompt.\n",
            "You have a tool `repo_change(repo_url: str, prompt: str)`.",
            "- If changes should be made, ALWAYS call repo_change exactly once "
            "with the repo_url and a repo-specific prompt.",
            "- Assume the tool will create a PR when it applies changes.",
            "- Then return EXACTLY the list of PR records returned by the tool "
            "(no extra commentary).",
            "- If no changes should be made, return an empty list.",
        ]
    )

    system_prompt = "\n".join(system_prompt_parts)

    agent: Agent[OrchestrateChangeDeps, list[CreatedPR]] = Agent(
        model=model,
        output_type=list[CreatedPR],
        deps_type=OrchestrateChangeDeps,
        toolsets=toolsets,
        system_prompt=system_prompt,
    )

    @agent.tool
    async def repo_change(
        _ctx: RunContext[OrchestrateChangeDeps], repo_url: str, prompt: str
    ) -> list[CreatedPR]:
        tool_called["called"] = True
        return await repo_change_tool(repo_url, prompt)

    return agent, tool_called
