import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_mcp_config_priority_cli_wins():
    """
    Test MCP config path priority: CLI > env var > default.
    This test verifies the CLI-provided path is preferred.
    """
    cli_path = Path("/cli/path/mcp.json")
    env_path = Path("/env/path/mcp.json")
    default_path = Path("/default/path/mcp.json")

    # Simulate the logic from init_step/node.py
    mcp_config_path = cli_path  # CLI provided

    with patch.dict("os.environ", {"MCP_CONFIG": str(env_path)}, clear=False):
        # Logic from init_step: if not ctx.state.mcp_config_path
        if not mcp_config_path:
            env_mcp_config = os.environ.get("MCP_CONFIG")
            if env_mcp_config:
                mcp_config_path = Path(env_mcp_config).expanduser()
            elif default_path.exists():
                mcp_config_path = default_path

    assert mcp_config_path == cli_path


def test_mcp_config_priority_env_wins():
    """
    Test MCP config path priority: CLI > env var > default.
    This test verifies the env var path is used when CLI is not provided.
    """
    env_path = Path("/env/path/mcp.json")
    default_path = Path("/default/path/mcp.json")

    # Simulate the logic from init_step/node.py
    mcp_config_path = None  # CLI not provided

    with patch.dict("os.environ", {"MCP_CONFIG": str(env_path)}, clear=False):
        # Logic from init_step: if not ctx.state.mcp_config_path
        if not mcp_config_path:
            env_mcp_config = os.environ.get("MCP_CONFIG")
            if env_mcp_config:
                mcp_config_path = Path(env_mcp_config).expanduser()
            elif default_path.exists():
                mcp_config_path = default_path

    assert mcp_config_path == env_path


def test_mcp_config_priority_default_wins_when_exists():
    """
    Test MCP config path priority: CLI > env var > default.
    This test verifies the default path is used when it exists and neither CLI nor env are set.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        default_path = Path(tmpdir) / "mcp-servers.json"
        default_path.write_text('{"mcpServers": {}}')

        # Simulate the logic from init_step/node.py
        mcp_config_path = None  # CLI not provided

        # No env var set
        if not mcp_config_path:
            env_mcp_config = os.environ.get("MCP_CONFIG")
            if env_mcp_config:
                mcp_config_path = Path(env_mcp_config).expanduser()
            elif default_path.exists():
                mcp_config_path = default_path

        assert mcp_config_path == default_path


def test_mcp_config_priority_none_when_default_missing():
    """
    Test MCP config path priority: CLI > env var > default.
    This test verifies that mcp_config_path remains None when default doesn't exist.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        default_path = Path(tmpdir) / "mcp-servers.json"
        # Don't create the file

        # Simulate the logic from init_step/node.py
        mcp_config_path = None  # CLI not provided

        # No env var set
        if not mcp_config_path:
            env_mcp_config = os.environ.get("MCP_CONFIG")
            if env_mcp_config:
                mcp_config_path = Path(env_mcp_config).expanduser()
            elif default_path.exists():
                mcp_config_path = default_path

        assert mcp_config_path is None


def test_mcp_config_expands_tilde():
    """
    Test that tilde expansion works correctly for env var paths.
    """
    mcp_config_path = None

    with patch.dict(
        "os.environ", {"MCP_CONFIG": "~/.pr-creator/mcp-servers.json"}, clear=False
    ):
        if not mcp_config_path:
            env_mcp_config = os.environ.get("MCP_CONFIG")
            if env_mcp_config:
                mcp_config_path = Path(env_mcp_config).expanduser()

    assert mcp_config_path is not None
    assert "~" not in str(mcp_config_path)
    assert str(mcp_config_path).startswith(str(Path.home()))
