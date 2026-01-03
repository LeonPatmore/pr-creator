from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphRunContext

from pr_creator.context_roots import get_context_roots_from_env, merge_context_roots
from pr_creator.jira_loader import load_prompt_from_jira
from pr_creator.prompt_builder import merge_base_prompt_with_cli_prompt
from pr_creator.prompt_config import load_prompts_from_config
from pr_creator.secrets import build_change_agent_secrets
from pr_creator.state import WorkflowState

logger = logging.getLogger(__name__)

PROMPT_SOURCE_PROMPT_CONFIG = "prompt_config"
PROMPT_SOURCE_JIRA = "jira"
PROMPT_SOURCE_CLI = "cli"


def _resolve_secrets(state: WorkflowState) -> None:
    """Resolve secret inputs into `state.change_agent_secrets`."""
    if not (state.change_agent_secret_kv_pairs or state.change_agent_secret_env_keys):
        return

    resolved = build_change_agent_secrets(
        secret_kv_pairs=state.change_agent_secret_kv_pairs,
        secret_env_keys=state.change_agent_secret_env_keys,
        environ=os.environ,
    )
    # Explicit secrets provided on state override derived values.
    state.change_agent_secrets = {**resolved, **state.change_agent_secrets}


def _merge_context_roots(state: WorkflowState) -> None:
    """Merge context roots from env (so CLI + env both apply)."""
    state.context_roots = merge_context_roots(
        state.context_roots, get_context_roots_from_env()
    )


@dataclass(frozen=True)
class PromptSource:
    kind: str
    label: str


def _determine_prompt_source(state: WorkflowState) -> PromptSource:
    has_prompt_config = bool(
        state.prompt_config_owner
        or state.prompt_config_repo
        or state.prompt_config_path
    )
    has_jira_prompt = bool(state.jira_ticket)
    if has_prompt_config and has_jira_prompt:
        raise ValueError("Choose only one prompt source: prompt config or Jira ticket.")

    if has_prompt_config:
        return PromptSource(PROMPT_SOURCE_PROMPT_CONFIG, "prompt config")
    if has_jira_prompt:
        ticket = state.jira_ticket or ""
        return PromptSource(PROMPT_SOURCE_JIRA, f"jira ticket {ticket}")
    return PromptSource(PROMPT_SOURCE_CLI, "cli")


def _load_prompt_from_prompt_config(state: WorkflowState) -> None:
    if not (state.prompt_config_repo and state.prompt_config_path):
        raise ValueError(
            "When using prompt config, provide prompt_config_repo and prompt_config_path "
            "(and prompt_config_owner or PROMPT_CONFIG_OWNER)"
        )

    token = os.environ.get("GITHUB_TOKEN")
    ref = (state.prompt_config_ref or "main").strip() or "main"
    prompts = load_prompts_from_config(
        state.prompt_config_owner,
        state.prompt_config_repo,
        ref,
        state.prompt_config_path,
        token,
    )

    state.prompt = merge_base_prompt_with_cli_prompt(
        prompts["prompt"],
        state.cli_prompt,
        base_origin="prompt config",
    )
    # Config relevance prompt overrides CLI relevance prompt.
    state.relevance_prompt = prompts.get("relevance_prompt") or ""
    if "change_id" in prompts:
        state.change_id = prompts["change_id"]


def _load_prompt_from_jira(state: WorkflowState) -> None:
    ticket = state.jira_ticket or ""
    jira_prompt = load_prompt_from_jira(
        state.jira_base_url,
        ticket,
        state.jira_email,
        state.jira_api_token,
    )

    state.prompt = merge_base_prompt_with_cli_prompt(
        jira_prompt["prompt"],
        state.cli_prompt,
        base_origin=f"jira ticket {ticket}",
    )
    # Jira ticket id always defines the change id for stable naming.
    state.change_id = jira_prompt["change_id"]
    # In Jira mode, relevance_prompt comes from CLI (optional); keep existing.
    state.relevance_prompt = state.relevance_prompt or ""


def _load_prompt_from_cli_only(state: WorkflowState) -> None:
    if not state.cli_prompt or not state.cli_prompt.strip():
        raise ValueError(
            "cli_prompt is required when no prompt config or Jira ticket is provided"
        )
    state.prompt = state.cli_prompt.strip()
    state.relevance_prompt = state.relevance_prompt or ""


def _load_and_merge_prompts(state: WorkflowState) -> PromptSource:
    source = _determine_prompt_source(state)
    if source.kind == PROMPT_SOURCE_PROMPT_CONFIG:
        _load_prompt_from_prompt_config(state)
    elif source.kind == PROMPT_SOURCE_JIRA:
        _load_prompt_from_jira(state)
    else:
        _load_prompt_from_cli_only(state)
    return source


class InitWorkflow(BaseNode):
    async def run(self, ctx: GraphRunContext) -> BaseNode | End:
        _resolve_secrets(ctx.state)
        _merge_context_roots(ctx.state)
        source = _load_and_merge_prompts(ctx.state)

        logger.info(
            "[init] source=%s prompt_len=%s relevance_len=%s change_id=%s",
            source.label,
            len(ctx.state.prompt or ""),
            len(ctx.state.relevance_prompt or ""),
            ctx.state.change_id,
        )

        from .discover import DiscoverRepos

        return DiscoverRepos()
