from __future__ import annotations

from unittest.mock import patch

from pr_creator.cli import parse_args


def test_parse_args_with_mcp_config():
    """Test that --mcp-config argument is parsed correctly."""
    with patch(
        "sys.argv",
        [
            "pr-creator",
            "--prompt",
            "test prompt",
            "--repo",
            "https://github.com/test/repo",
            "--mcp-config",
            "/path/to/mcp-config.json",
        ],
    ):
        args = parse_args()
        assert args.mcp_config == "/path/to/mcp-config.json"
        assert args.prompt == "test prompt"


def test_parse_args_without_mcp_config():
    """Test that mcp_config is None when not provided."""
    with patch(
        "sys.argv",
        [
            "pr-creator",
            "--prompt",
            "test prompt",
            "--repo",
            "https://github.com/test/repo",
        ],
    ):
        args = parse_args()
        assert args.mcp_config is None


def test_parse_args_mcp_config_with_tilde():
    """Test that mcp_config handles tilde expansion."""
    with patch(
        "sys.argv",
        [
            "pr-creator",
            "--prompt",
            "test",
            "--repo",
            "test",
            "--mcp-config",
            "~/.pr-creator/mcp-servers.json",
        ],
    ):
        args = parse_args()
        assert args.mcp_config == "~/.pr-creator/mcp-servers.json"
