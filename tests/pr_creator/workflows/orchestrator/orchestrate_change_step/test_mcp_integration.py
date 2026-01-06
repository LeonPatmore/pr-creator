from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    build_orchestrate_change_agent,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_repo_change_tool():
    """Fixture providing a mock repo_change tool."""
    return AsyncMock(return_value=[])


@pytest.fixture
def mock_agent_instance():
    """Fixture providing a mock agent instance."""
    return MagicMock()


def create_temp_mcp_config(config: dict) -> Path:
    """
    Create a temporary MCP config file.

    Args:
        config: MCP configuration dictionary

    Returns:
        Path to temporary config file
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        return Path(f.name)


def get_agent_toolsets(mock_agent_class) -> list:
    """
    Extract toolsets argument from mocked Agent constructor call.

    Args:
        mock_agent_class: Mocked Agent class

    Returns:
        List of toolsets passed to Agent constructor
    """
    call_kwargs = mock_agent_class.call_args.kwargs
    return call_kwargs.get("toolsets", [])


def get_agent_system_prompt(mock_agent_class) -> str:
    """
    Extract system prompt from mocked Agent constructor call.

    Args:
        mock_agent_class: Mocked Agent class

    Returns:
        System prompt string passed to Agent constructor
    """
    call_kwargs = mock_agent_class.call_args.kwargs
    return call_kwargs.get("system_prompt", "")


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
def test_build_agent_without_mcp_config(
    mock_agent_class, mock_repo_change_tool, mock_agent_instance
):
    """
    Test that agent builds successfully without MCP config.

    When no MCP config is provided, the agent should:
    - Build successfully
    - Have no toolsets
    - Use standard system prompt
    """
    mock_agent_class.return_value = mock_agent_instance

    agent, tool_called = build_orchestrate_change_agent(
        repo_change_tool=mock_repo_change_tool, mcp_config_path=None
    )

    assert agent is not None
    assert tool_called == {"called": False}

    toolsets = get_agent_toolsets(mock_agent_class)
    assert toolsets == []

    logger.info("✓ Agent built without MCP config")


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
def test_build_agent_with_nonexistent_mcp_config(
    mock_agent_class, mock_repo_change_tool, mock_agent_instance
):
    """
    Test that agent builds gracefully when MCP config file doesn't exist.

    When MCP config path points to non-existent file, the agent should:
    - Build successfully (graceful degradation)
    - Log a warning
    - Have no toolsets
    """
    mock_agent_class.return_value = mock_agent_instance
    nonexistent_path = Path("/tmp/nonexistent-mcp-config.json")

    agent, tool_called = build_orchestrate_change_agent(
        repo_change_tool=mock_repo_change_tool, mcp_config_path=nonexistent_path
    )

    assert agent is not None
    assert tool_called == {"called": False}

    toolsets = get_agent_toolsets(mock_agent_class)
    assert toolsets == []

    logger.info("✓ Agent handled missing MCP config gracefully")


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
@patch("pydantic_ai.mcp.load_mcp_servers")
def test_build_agent_with_valid_mcp_config(
    mock_load_mcp_servers, mock_agent_class, mock_repo_change_tool, mock_agent_instance
):
    """
    Test that agent loads MCP servers when valid config is provided.

    When valid MCP config is provided, the agent should:
    - Load MCP servers using pydantic_ai.mcp.load_mcp_servers
    - Include MCP toolsets in agent configuration
    - Update system prompt to mention external tools
    """
    mock_agent_class.return_value = mock_agent_instance

    # Create temporary MCP config
    config = {
        "mcpServers": {
            "test-server": {
                "command": "echo",
                "args": ["test"],
                "env": {},
            }
        }
    }
    config_path = create_temp_mcp_config(config)

    try:
        # Mock load_mcp_servers to return mock toolset
        mock_toolset = MagicMock()
        mock_load_mcp_servers.return_value = [mock_toolset]

        agent, tool_called = build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change_tool, mcp_config_path=config_path
        )

        assert agent is not None
        assert tool_called == {"called": False}

        # Verify MCP servers were loaded
        mock_load_mcp_servers.assert_called_once_with(str(config_path))

        # Verify toolsets were passed to Agent
        toolsets = get_agent_toolsets(mock_agent_class)
        assert toolsets == [mock_toolset]

        # Verify system prompt mentions external tools
        system_prompt = get_agent_system_prompt(mock_agent_class)
        assert "external tools" in system_prompt.lower()

        logger.info("✓ Agent loaded MCP servers successfully")

    finally:
        config_path.unlink(missing_ok=True)


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
@patch("pydantic_ai.mcp.load_mcp_servers")
def test_build_agent_handles_import_error(
    mock_load_mcp_servers, mock_agent_class, mock_repo_change_tool, mock_agent_instance
):
    """
    Test that agent handles missing pydantic-ai MCP support gracefully.

    When pydantic_ai.mcp is not available (ImportError), the agent should:
    - Build successfully (graceful degradation)
    - Log a warning about missing MCP support
    - Have no toolsets
    """
    mock_agent_class.return_value = mock_agent_instance

    config = {"mcpServers": {"test": {"command": "echo"}}}
    config_path = create_temp_mcp_config(config)

    try:
        # Simulate ImportError
        mock_load_mcp_servers.side_effect = ImportError(
            "No module named 'pydantic_ai.mcp'"
        )

        agent, tool_called = build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change_tool, mcp_config_path=config_path
        )

        # Agent should still be created without MCP toolsets
        assert agent is not None
        assert tool_called == {"called": False}

        toolsets = get_agent_toolsets(mock_agent_class)
        assert toolsets == []

        logger.info("✓ Agent handled missing pydantic-ai MCP support gracefully")

    finally:
        config_path.unlink(missing_ok=True)


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
@patch("pydantic_ai.mcp.load_mcp_servers")
def test_build_agent_handles_invalid_config(
    mock_load_mcp_servers, mock_agent_class, mock_repo_change_tool, mock_agent_instance
):
    """
    Test that agent handles invalid MCP config gracefully.

    When MCP config is malformed or invalid, the agent should:
    - Build successfully (graceful degradation)
    - Log a warning about config error
    - Have no toolsets
    """
    mock_agent_class.return_value = mock_agent_instance

    # Create file with invalid JSON
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json")
        config_path = Path(f.name)

    try:
        # Simulate exception when loading config
        mock_load_mcp_servers.side_effect = ValueError("Invalid config format")

        agent, tool_called = build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change_tool, mcp_config_path=config_path
        )

        # Agent should still be created without MCP toolsets
        assert agent is not None
        assert tool_called == {"called": False}

        toolsets = get_agent_toolsets(mock_agent_class)
        assert toolsets == []

        logger.info("✓ Agent handled invalid MCP config gracefully")

    finally:
        config_path.unlink(missing_ok=True)


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
@patch("pydantic_ai.mcp.load_mcp_servers")
def test_system_prompt_includes_mcp_instructions(
    mock_load_mcp_servers, mock_agent_class, mock_repo_change_tool
):
    """
    Test that system prompt changes when MCP tools are available.

    The system prompt should:
    - Be standard without MCP tools
    - Include MCP/external tools instructions when MCP is available
    - Guide agent to use MCP tools for exploration
    """
    # Capture system prompts from Agent constructor calls
    system_prompts = []

    def capture_system_prompt(**kwargs):
        mock_instance = MagicMock()
        system_prompts.append(kwargs.get("system_prompt", ""))
        return mock_instance

    mock_agent_class.side_effect = capture_system_prompt

    # Build agent without MCP
    build_orchestrate_change_agent(
        repo_change_tool=mock_repo_change_tool, mcp_config_path=None
    )
    prompt_without_mcp = system_prompts[-1]

    # Build agent with MCP
    config = {"mcpServers": {"test": {"command": "echo"}}}
    config_path = create_temp_mcp_config(config)

    try:
        mock_load_mcp_servers.return_value = [MagicMock()]

        build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change_tool, mcp_config_path=config_path
        )
        prompt_with_mcp = system_prompts[-1]

        # Verify prompts are different
        assert len(prompt_with_mcp) > len(prompt_without_mcp)
        assert "external tools" in prompt_with_mcp.lower()
        assert "external tools" not in prompt_without_mcp.lower()
        assert "mcp" in prompt_with_mcp.lower()

        logger.info("✓ System prompt correctly includes MCP instructions")

    finally:
        config_path.unlink(missing_ok=True)


@patch("pr_creator.workflows.orchestrator.orchestrate_change_step.agent.Agent")
def test_system_prompt_includes_github_default_org(
    mock_agent_class, mock_repo_change_tool
):
    """
    Test that system prompt includes GitHub default org when provided.

    The system prompt should:
    - Include GitHub default org information when provided
    - Not mention GitHub default org when not provided
    """
    # Capture system prompts from Agent constructor calls
    system_prompts = []

    def capture_system_prompt(**kwargs):
        mock_instance = MagicMock()
        system_prompts.append(kwargs.get("system_prompt", ""))
        return mock_instance

    mock_agent_class.side_effect = capture_system_prompt

    # Build agent without github_default_org
    build_orchestrate_change_agent(
        repo_change_tool=mock_repo_change_tool,
        mcp_config_path=None,
        github_default_org=None,
    )
    prompt_without_org = system_prompts[-1]

    # Build agent with github_default_org
    build_orchestrate_change_agent(
        repo_change_tool=mock_repo_change_tool,
        mcp_config_path=None,
        github_default_org="my-test-org",
    )
    prompt_with_org = system_prompts[-1]

    # Verify prompts are different
    assert len(prompt_with_org) > len(prompt_without_org)
    assert "my-test-org" in prompt_with_org
    assert "my-test-org" not in prompt_without_org
    assert "GITHUB DEFAULT ORGANIZATION" in prompt_with_org
    assert "GITHUB DEFAULT ORGANIZATION" not in prompt_without_org

    logger.info("✓ System prompt correctly includes GitHub default org when provided")
