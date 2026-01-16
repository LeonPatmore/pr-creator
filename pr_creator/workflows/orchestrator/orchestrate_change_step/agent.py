from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

logger = logging.getLogger(__name__)


class ChangeAgentResponse(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pushed_sha: Optional[str] = None
    error: Optional[str] = None
    # Whether any changes were pushed for this repo
    changes_pushed: bool = False
    # Whether CI checks passed (None = not waited for, False = failed, True = passed)
    ci_passed: Optional[bool] = None


class OrchestratorResponse(BaseModel):
    """Response from the orchestrator agent."""

    # One entry per repo_change tool call.
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
    *,
    repo_change_tool: RepoChangeTool,
    mcp_config_path: Optional[Path] = None,
    github_default_org: Optional[str] = None,
) -> tuple[Agent[OrchestrateChangeDeps, OrchestratorResponse], dict[str, bool]]:
    """
    Build a pydantic-ai agent for orchestration.

    The agent is expected to call the provided `repo_change_tool(repo_url, prompt)` tool.
    Its output type is an OrchestratorResponse containing a list of PR records returned by that tool
    or an error message if repositories cannot be determined.

    If mcp_config_path is provided, loads MCP servers from the config file and adds them
    as toolsets to the agent, enabling it to access external resources (e.g., GitHub repos).
    Each parallel agent gets its own MCP server instance.

    If github_default_org is provided, includes it as context in the system prompt to help
    the agent construct proper repository URLs when discovering repositories.
    """

    tool_called = {"called": False}

    model = os.environ.get("ORCHESTRATOR_MODEL", "openai:gpt-5.2")

    # Load MCP servers (each agent gets its own instance)
    toolsets = _load_mcp_toolsets(mcp_config_path)

    # Build system prompt based on whether MCP tools are available
    system_prompt_parts = [
        "# ROLE",
        (
            "You are a change orchestrator. Your job is to determine which "
            "repositories need changes and delegate work to the `repo_change` tool."
        ),
        "",
        "# CRITICAL CONSTRAINTS",
        "- You must NOT directly modify any files yourself",
        "- You MUST call `repo_change(repo_url: str, prompt: str)` to make changes",
        "- You MUST NOT call `repo_change` unless you know the exact target repository URL(s)",
        (
            "- NEVER use placeholder/guessed values like UNKNOWN/UNKNOWN, owner/repo you are "
            "not sure about, or any fabricated URL"
        ),
        (
            "- If you CANNOT determine which repository is required, return an error (see "
            "Error Handling section) and do NOT call `repo_change`"
        ),
        "",
        "# ERROR HANDLING",
        "If you cannot determine which repository or repositories are required for this change:",
        "1. Set `results` to an empty list",
        "2. Set `error` field with a detailed explanation of why you cannot determine the target repository",
        (
            "3. Do NOT proceed with changes when the target repository is unclear (i.e., "
            "do NOT call `repo_change`)"
        ),
        (
            "4. Ask for the missing info explicitly (e.g., request 1+ GitHub repo URL(s) "
            "or an owner/repo slug)"
        ),
        "",
        "# REPO URL REQUIREMENTS (STRICT)",
        (
            "Only call `repo_change` when `repo_url` is a valid GitHub HTTPS URL "
            "like `https://github.com/<owner>/<repo>`."
        ),
        (
            "Never call `repo_change` with empty strings, partial slugs you "
            "haven't verified, or placeholder values containing `UNKNOWN`."
        ),
        "",
    ]

    if toolsets:
        system_prompt_parts.extend(
            [
                "# AVAILABLE TOOLS",
                "You have access to external tools via MCP servers (e.g., GitHub API).",
                "Use these tools to:",
                "- Explore codebases and understand context",
                "- Search for repositories",
                "- Gather information before planning changes",
                "",
                "# GITHUB SEARCH SYNTAX",
                "When using GitHub search tools (e.g., github_search_code, github_search_repositories):",
                "- Use 'org:ORGANIZATION' to search within an organization",
                "- Use 'repo:OWNER/REPO' to search within a specific repository",
                "- Use 'path:DIRECTORY' to limit search to a specific directory",
                "- NEVER combine org and repo as 'org:OWNER/REPO' - this is invalid syntax",
                "- Example valid queries: 'org:acme-corp repo:infrastructure', 'repo:acme-corp/infrastructure'",
                "- Example invalid queries: 'org:acme-corp/infrastructure' (will fail with 422 error)",
                "",
            ]
        )

    if github_default_org:
        system_prompt_parts.extend(
            [
                "# GITHUB DEFAULT ORGANIZATION",
                f"The default GitHub organization is: {github_default_org}",
                f"When constructing repository URLs, you can use: https://github.com/{github_default_org}/<repo-name>",
                "",
            ]
        )

    system_prompt_parts.extend(
        [
            "# MAKING CHANGES",
            "To apply changes, use the `repo_change(repo_url: str, prompt: str)` tool:",
            "",
            "Tool: `repo_change(repo_url: str, prompt: str)`",
            (
                "- repo_url: Full GitHub repository URL (must be a real, verified repo; "
                "no placeholders)"
            ),
            "- prompt: Repo-specific instructions for what changes to make",
            "",
            "Important notes:",
            (
                "- The tool automatically handles the FULL workflow: applying "
                "changes, committing, pushing, and creating PRs"
            ),
            (
                "- Do NOT instruct the tool to create PRs - it already does this "
                "automatically"
            ),
            "- Your job is ONLY to craft clear, repo-specific change instructions",
            "- Call this tool exactly once per repository that needs changes",
            (
                "- If you cannot name the repo URL(s) with high confidence, STOP and return "
                "an error instead of calling the tool"
            ),
            "- Append the tool return value to `results`",
            (
                "- If the tool returns a response with `error` set, treat that as a failure: "
                "do not claim success, and surface the failure in your top-level `error` field"
            ),
            "",
            "# RESPONSE FORMAT",
            "Return an OrchestratorResponse with:",
            (
                "- `results`: List of ChangeAgentResponse returned by the repo_change tool "
                "(empty if no changes made)"
            ),
            "- `error`: Error message if you cannot determine target repositories (otherwise null)",
            "",
            "Examples:",
            '- Changes made: `{"results": [{...}], "error": null}`',
            '- No changes needed: `{"results": [], "error": null}`',
            '- Cannot determine repo: `{"results": [], "error": "Could not find repository matching..."}`',
        ]
    )

    system_prompt = "\n".join(system_prompt_parts)

    agent: Agent[OrchestrateChangeDeps, OrchestratorResponse] = Agent(
        model=model,
        output_type=OrchestratorResponse,
        deps_type=OrchestrateChangeDeps,
        toolsets=toolsets,
        system_prompt=system_prompt,
    )

    @agent.tool
    async def repo_change(
        _ctx: RunContext[OrchestrateChangeDeps], repo_url: str, prompt: str
    ) -> ChangeAgentResponse:
        tool_called["called"] = True
        return await repo_change_tool(repo_url, prompt)

    return agent, tool_called
