from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

from pr_creator.context_roots import get_context_roots_from_env, merge_context_roots
from pr_creator.workflows.orchestrator.init_step.prompt_loading_support.jira_loader import (
    load_prompt_from_jira,
)
from pr_creator.workflows.orchestrator.init_step.prompt_loading_support.prompt_builder import (
    merge_base_prompt_with_cli_prompt,
)
from pr_creator.workflows.orchestrator.init_step.prompt_loading_support.prompt_config_loader import (
    load_prompts_from_config,
)
from pr_creator.workflows.orchestrator.init_step.secrets import (
    build_change_agent_secrets,
)

logger = logging.getLogger(__name__)


class _SupportsPromptLoading(Protocol):
    prompt: str
    relevance_prompt: str
    cli_prompt: str | None

    prompt_config_owner: str | None
    prompt_config_repo: str | None
    prompt_config_ref: str | None
    prompt_config_path: str | None

    jira_ticket: str | None
    jira_base_url: str | None
    jira_email: str | None
    jira_api_token: str | None

    change_id: str | None

    context_roots: list[str]

    change_agent_secrets: dict[str, str]
    change_agent_secret_kv_pairs: list[str]
    change_agent_secret_env_keys: list[str]


PROMPT_SOURCE_PROMPT_CONFIG = "prompt_config"
PROMPT_SOURCE_JIRA = "jira"
PROMPT_SOURCE_CLI = "cli"


@dataclass(frozen=True)
class PromptSource:
    kind: str
    label: str


def resolve_secrets_and_context(state: _SupportsPromptLoading) -> None:
    if state.change_agent_secret_kv_pairs or state.change_agent_secret_env_keys:
        resolved = build_change_agent_secrets(
            secret_kv_pairs=state.change_agent_secret_kv_pairs,
            secret_env_keys=state.change_agent_secret_env_keys,
            environ=os.environ,
        )
        state.change_agent_secrets = {**resolved, **state.change_agent_secrets}

    state.context_roots = merge_context_roots(
        state.context_roots, get_context_roots_from_env()
    )


def determine_prompt_source(state: _SupportsPromptLoading) -> PromptSource:
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


def load_and_merge_prompts(state: _SupportsPromptLoading) -> PromptSource:
    source = determine_prompt_source(state)

    if source.kind == PROMPT_SOURCE_PROMPT_CONFIG:
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
        state.relevance_prompt = prompts.get("relevance_prompt") or ""
        if "change_id" in prompts:
            state.change_id = prompts["change_id"]

    elif source.kind == PROMPT_SOURCE_JIRA:
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
        state.change_id = jira_prompt["change_id"]
        state.relevance_prompt = state.relevance_prompt or ""

    else:
        if not state.cli_prompt or not state.cli_prompt.strip():
            raise ValueError(
                "cli_prompt is required when no prompt config or Jira ticket is provided"
            )
        state.prompt = state.cli_prompt.strip()
        state.relevance_prompt = state.relevance_prompt or ""

    logger.info(
        "[init] source=%s prompt_len=%s relevance_len=%s change_id=%s",
        source.label,
        len(state.prompt or ""),
        len(state.relevance_prompt or ""),
        state.change_id,
    )
    return source
