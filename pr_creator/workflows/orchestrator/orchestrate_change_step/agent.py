from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from .model_builder import build_model
from .system_prompt_builder import build_orchestrator_system_prompt

logger = logging.getLogger(__name__)


class ChangeAgentResponse(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pushed_sha: Optional[str] = None
    error: Optional[str] = None
    changes_pushed: bool = False
    ci_passed: Optional[bool] = None


class OrchestratorResponse(BaseModel):
    results: list[ChangeAgentResponse] = []
    error: Optional[str] = None


class OrchestrateChangeDeps(BaseModel):
    repo_url: str


RepoChangeTool = Callable[[str, str], Awaitable[ChangeAgentResponse]]


def _load_mcp_toolsets(mcp_config_path: Optional[Path]) -> list:
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
        mcp_max_retries = int(os.environ.get("ORCHESTRATOR_MCP_MAX_RETRIES", "5"))
        if mcp_max_retries < 0:
            mcp_max_retries = 0
        for toolset in toolsets:
            if hasattr(toolset, "max_retries"):
                try:
                    toolset.max_retries = mcp_max_retries
                except Exception:
                    # If the toolset doesn't allow assignment, skip.
                    pass
        logger.info(
            "[orchestrator] MCP tool retry policy: ORCHESTRATOR_MCP_MAX_RETRIES=%d",
            mcp_max_retries,
        )
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


@contextlib.asynccontextmanager
async def build_orchestrate_change_agent(
    *,
    repo_change_tool: RepoChangeTool,
    mcp_config_path: Optional[Path] = None,
    github_default_org: Optional[str] = None,
):
    """
    Build orchestrator agent with proper MCP lifecycle management.

    Returns an async context manager that yields (agent, tool_called).
    MCP toolsets are properly managed within this context to avoid
    cancel scope issues when running in parallel tasks.
    """
    tool_called = {"called": False}

    model_name = os.environ.get("ORCHESTRATOR_MODEL", "openai:gpt-5.2")
    model = build_model(model_name)

    toolsets = _load_mcp_toolsets(mcp_config_path)

    system_prompt = build_orchestrator_system_prompt(
        has_mcp_tools=bool(toolsets),
        github_default_org=github_default_org,
    )

    # Enter all MCP toolset contexts before creating the agent
    # This ensures proper lifecycle management within the current task
    async with contextlib.AsyncExitStack() as stack:
        # Enter each MCP toolset as an async context manager
        for toolset in toolsets:
            await stack.enter_async_context(toolset)

        agent: Agent[OrchestrateChangeDeps, OrchestratorResponse] = Agent(
            model=model,
            output_type=OrchestratorResponse,
            deps_type=OrchestrateChangeDeps,
            toolsets=toolsets,
            system_prompt=system_prompt,
        )

        @agent.tool
        async def repo_change(
            _ctx: RunContext[OrchestrateChangeDeps],
            repo_url: str,
            additional_prompt: str,
        ) -> ChangeAgentResponse:
            tool_called["called"] = True
            return await repo_change_tool(repo_url, additional_prompt)

        yield agent, tool_called
