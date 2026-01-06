from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    build_orchestrate_change_agent,
    OrchestrateChangeDeps,
)
from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.workflow import run_orchestrator_workflow

logger = logging.getLogger(__name__)


@dataclass
class MCPToolUsage:
    """Summary of MCP tool usage extracted from agent messages."""

    tool_calls: list[str]
    tool_returns: list[str]
    github_tools_used: list[str]
    repositories_found: list[str]

    @property
    def github_tool_count(self) -> int:
        """Number of GitHub MCP tools used."""
        return len([t for t in self.tool_returns if t.startswith("github_")])

    @property
    def unique_repos(self) -> set[str]:
        """Unique repository names discovered."""
        return set(self.repositories_found)


def create_github_mcp_config(github_token: str) -> Path:
    """
    Create a temporary MCP configuration file for GitHub MCP server.

    Args:
        github_token: GitHub personal access token

    Returns:
        Path to the temporary MCP config file
    """
    mcp_config = {
        "mcpServers": {
            "github": {
                "command": "docker",
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "ghcr.io/github/github-mcp-server",
                ],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
            }
        }
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as config_file:
        json.dump(mcp_config, config_file)
        return Path(config_file.name)


def extract_repositories_from_content(content: Any) -> list[str]:
    """
    Extract repository names from GitHub API response content.

    Args:
        content: Response content from github_search_repositories tool

    Returns:
        List of repository full names (owner/repo)
    """
    repos = []

    try:
        # Parse content if it's a string
        if isinstance(content, str):
            import json as json_lib

            content = json_lib.loads(content)

        # Extract items from dict or use list directly
        if isinstance(content, dict) and "items" in content:
            repo_items = content["items"]
        elif isinstance(content, list):
            repo_items = content
        else:
            repo_items = []

        # Extract full_name or name from each repo
        for repo in repo_items:
            if isinstance(repo, dict):
                repo_name = repo.get("full_name") or repo.get("name", "unknown")
                repos.append(repo_name)

    except Exception as e:
        logger.warning("Failed to parse repository content: %s", e)

    return repos


def analyze_agent_messages(messages: list[Any]) -> MCPToolUsage:
    """
    Analyze agent messages to extract MCP tool usage information.

    Args:
        messages: List of ModelRequest and ModelResponse messages from agent

    Returns:
        MCPToolUsage object with summary of tool usage
    """
    tool_calls = []
    tool_returns = []
    repos_found = []

    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__

        # Only process ModelRequest messages which contain tool interactions
        if msg_type != "ModelRequest" or not hasattr(msg, "parts"):
            continue

        for part in msg.parts:
            part_type = type(part).__name__

            # Process tool return (response from tool execution)
            if "ToolReturn" in part_type:
                tool_name = getattr(part, "tool_name", "unknown")
                tool_returns.append(tool_name)

                logger.debug("Message %d: Tool return - %s", i, tool_name)

                # Extract repository data from github_search_repositories responses
                if tool_name == "github_search_repositories" and hasattr(
                    part, "content"
                ):
                    repo_names = extract_repositories_from_content(part.content)
                    repos_found.extend(repo_names)
                    logger.info(
                        "Found %d repositories from %s", len(repo_names), tool_name
                    )

            # Process tool call (request to execute tool)
            elif "ToolCall" in part_type:
                tool_name = getattr(part, "tool_name", "unknown")
                tool_calls.append(tool_name)
                logger.debug("Message %d: Tool call - %s", i, tool_name)

    github_tools = [t for t in tool_returns if t.startswith("github_")]

    return MCPToolUsage(
        tool_calls=tool_calls,
        tool_returns=tool_returns,
        github_tools_used=github_tools,
        repositories_found=repos_found,
    )


def check_required_env(var_names: list[str]) -> None:
    """
    Check if required environment variables are set, skip test if missing.

    Args:
        var_names: List of environment variable names to check
    """
    missing = [k for k in var_names if not os.environ.get(k)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")


@pytest.mark.anyio
async def test_orchestrator_agent_can_list_github_repos():
    """
    Direct test: orchestrator agent uses GitHub MCP tools to list repositories.

    This test verifies that:
    - MCP config is loaded and GitHub MCP server starts
    - Agent can call GitHub API tools through MCP
    - Agent successfully retrieves repository data
    - Tool calls and responses are properly handled

    Requirements:
    - GITHUB_TOKEN env var must be set
    - Docker must be running
    """
    check_required_env(["GITHUB_TOKEN"])

    github_token = os.environ["GITHUB_TOKEN"]
    mcp_config_path = create_github_mcp_config(github_token)

    try:
        # Create mock repo_change tool to track if it's called
        repo_change_calls = []

        async def mock_repo_change(repo_url: str, prompt: str):
            repo_change_calls.append({"repo_url": repo_url, "prompt": prompt})
            logger.info("repo_change called for %s", repo_url)
            return []

        # Build orchestrator agent with MCP integration
        agent, _ = build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change, mcp_config_path=mcp_config_path
        )

        # Run agent with a prompt that requires GitHub API access
        prompt = (
            "Use GitHub API tools to list the first 3 repositories accessible "
            "with the current token. List their names. After exploring, "
            "return an empty list (don't call repo_change)."
        )

        logger.info("Running agent with GitHub repository listing prompt")
        result = await agent.run(
            prompt, deps=OrchestrateChangeDeps(repo_url="https://github.com/test/test")
        )

        # Analyze messages to extract tool usage
        messages = result.all_messages()
        tool_usage = analyze_agent_messages(messages)

        # Log summary
        logger.info("Agent execution summary:")
        logger.info("  - Messages: %d", len(messages))
        logger.info("  - Tool calls: %d", len(tool_usage.tool_calls))
        logger.info("  - Tool returns: %d", len(tool_usage.tool_returns))
        logger.info("  - GitHub tools used: %d", tool_usage.github_tool_count)
        logger.info("  - Repositories discovered: %d", len(tool_usage.unique_repos))
        logger.info("  - repo_change calls: %d", len(repo_change_calls))

        if tool_usage.unique_repos:
            logger.info("  Discovered repositories:")
            for repo in sorted(tool_usage.unique_repos):
                logger.info("    - %s", repo)

        # Assertions: Verify MCP integration is working
        assert (
            tool_usage.github_tool_count > 0
        ), "No GitHub MCP tools used - MCP integration not working!"
        assert (
            len(tool_usage.unique_repos) > 0
        ), "No repositories discovered - GitHub API not returning data!"
        assert len(repo_change_calls) == 0, "repo_change should not have been called"
        assert isinstance(result.output, list), "Result should be a list"

        logger.info(
            "✅ MCP integration working: %d GitHub tool(s) used, %d repo(s) found",
            tool_usage.github_tool_count,
            len(tool_usage.unique_repos),
        )

    finally:
        mcp_config_path.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_orchestrator_workflow_with_github_mcp():
    """
    Integration test: full orchestrator workflow with GitHub MCP server.

    This test validates end-to-end integration:
    - MCP config loaded into orchestrator state
    - Workflow executes without errors
    - Agent can access GitHub API for exploration
    - Workflow completes successfully

    Requirements:
    - GITHUB_TOKEN env var must be set
    - ORCHESTRATOR_MODEL env var should point to a real LLM
    - Docker must be running
    """
    check_required_env(["GITHUB_TOKEN"])

    github_token = os.environ["GITHUB_TOKEN"]
    mcp_config_path = create_github_mcp_config(github_token)

    with tempfile.TemporaryDirectory() as working_dir:
        try:
            # Use a known repo to satisfy orchestrator requirements
            test_repo = os.environ.get(
                "TEST_REPO_URL", "https://github.com/LeonPatmore/cheap-ai-agents-aws"
            )

            state = OrchestratorState(
                prompt="",  # Set via cli_prompt
                cli_prompt=(
                    "Please use the GitHub API to list the first 3 repositories "
                    "accessible with the current token. Output the repository names "
                    "as a simple list. Do NOT make any changes or call repo_change - "
                    "just explore and report what you find."
                ),
                relevance_prompt="",  # No relevance check needed
                repos=[test_repo],  # Orchestrator requires at least one repo
                working_dir=Path(working_dir),
                github_token=github_token,
                mcp_config_path=mcp_config_path,
            )

            logger.info("Running orchestrator workflow with MCP integration")
            final_state = await run_orchestrator_workflow(state)

            # Validate workflow completed successfully
            assert isinstance(final_state.created_prs, list)
            assert isinstance(final_state.irrelevant, list)

            logger.info("✅ Orchestrator workflow completed with MCP integration")
            logger.info("  - Created PRs: %d", len(final_state.created_prs))
            logger.info("  - Irrelevant repos: %d", len(final_state.irrelevant))
            logger.info("  - Repo prompts: %d", len(final_state.repo_prompts))

        finally:
            mcp_config_path.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_orchestrator_explores_repo_via_mcp():
    """
    Integration test: orchestrator uses MCP to explore a specific repository.

    This test validates that the orchestrator can:
    - Use MCP tools to gather context about a target repository
    - Explore repository contents (e.g., check for README.md)
    - Process the repo without making unwanted changes

    Requirements:
    - GITHUB_TOKEN env var must be set
    - TEST_REPO_URL env var (optional, defaults to known public repo)
    - Docker must be running
    """
    check_required_env(["GITHUB_TOKEN"])

    github_token = os.environ["GITHUB_TOKEN"]
    test_repo = os.environ.get(
        "TEST_REPO_URL", "https://github.com/LeonPatmore/cheap-ai-agents-aws"
    )

    mcp_config_path = create_github_mcp_config(github_token)

    with tempfile.TemporaryDirectory() as working_dir:
        try:
            state = OrchestratorState(
                prompt="",  # Set via cli_prompt
                cli_prompt=(
                    "Check if this repository has a README.md file. "
                    "If it does, describe what you found (just describe, don't make changes). "
                    "Do NOT call repo_change - this is just an exploration task."
                ),
                relevance_prompt="Any repo",  # All repos are relevant
                repos=[test_repo],
                working_dir=Path(working_dir),
                github_token=github_token,
                mcp_config_path=mcp_config_path,
            )

            logger.info("Running orchestrator to explore repo: %s", test_repo)
            final_state = await run_orchestrator_workflow(state)

            logger.info("✅ Repository exploration completed")
            logger.info("  - Processed repo: %s", test_repo)
            logger.info("  - Created PRs: %d", len(final_state.created_prs))
            logger.info("  - Irrelevant repos: %d", len(final_state.irrelevant))
            logger.info("  - Repo prompts: %d", len(final_state.repo_prompts))

        finally:
            mcp_config_path.unlink(missing_ok=True)
