from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.init_step.prompt_loading_support.prompt_loading import (
    load_and_merge_prompts,
    resolve_secrets_and_context,
)
from pr_creator.workflows.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)

DEFAULT_WORKING_DIR = Path.home() / ".pr-creator" / "repos"
DEFAULT_DATADOG_SITE = "datadoghq.com"
DEFAULT_PROMPT_CONFIG_REF = "main"
DEFAULT_MCP_CONFIG_PATH = Path.home() / ".pr-creator" / "mcp-servers.json"


async def init_step(ctx: StepContext[OrchestratorState, None, None]) -> None:
    """Initialize orchestrator state with defaults, secrets, and prompts."""
    if not ctx.state.working_dir:
        ctx.state.working_dir = DEFAULT_WORKING_DIR
    if not ctx.state.datadog_site:
        ctx.state.datadog_site = DEFAULT_DATADOG_SITE
    if not ctx.state.prompt_config_ref:
        ctx.state.prompt_config_ref = DEFAULT_PROMPT_CONFIG_REF

    if not ctx.state.github_token:
        ctx.state.github_token = os.environ.get("GITHUB_TOKEN")

    if not ctx.state.github_default_org:
        ctx.state.github_default_org = os.environ.get("GITHUB_DEFAULT_ORG")

    if not ctx.state.mcp_config_path:
        env_mcp_config = os.environ.get("MCP_CONFIG")
        if env_mcp_config:
            ctx.state.mcp_config_path = Path(env_mcp_config).expanduser()
        elif DEFAULT_MCP_CONFIG_PATH.exists():
            ctx.state.mcp_config_path = DEFAULT_MCP_CONFIG_PATH

    resolve_secrets_and_context(ctx.state)
    load_and_merge_prompts(ctx.state)

    return None
