import argparse
import asyncio
import json
import os
from pathlib import Path

from .jira_loader import load_prompt_from_jira
from .logging_config import configure_logging
from .prompt_config import load_prompts_from_config
from .state import WorkflowState
from .workflow import run_workflow
from pr_creator.context_roots import normalize_context_roots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=False)
    parser.add_argument(
        "--relevance-prompt",
        required=False,
        help="Prompt used to filter repos for relevance; leave empty to treat all as relevant",
    )
    parser.add_argument(
        "--prompt-config-owner",
        help="GitHub owner of the prompt config repo",
    )
    parser.add_argument(
        "--prompt-config-repo",
        help="GitHub repo name of the prompt config repo",
    )
    parser.add_argument(
        "--prompt-config-ref",
        default="main",
        help="Git ref (branch/sha/tag) for the prompt config file (default: main)",
    )
    parser.add_argument(
        "--prompt-config-path",
        help="Path to the YAML file in the prompt config repo",
    )
    parser.add_argument("--repo", action="append", required=False)
    parser.add_argument(
        "--datadog-team",
        help="Datadog team name for repo discovery (requires DATADOG_API_KEY and DATADOG_APP_KEY)",
    )
    parser.add_argument(
        "--datadog-site",
        default="https://api.datadoghq.com",
        help="Datadog site base URL (default: https://api.datadoghq.com)",
    )
    parser.add_argument("--working-dir", default=".repos")
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--change-id",
        help="Change ID to use for static branch names (ensures re-runs use the same branch)",
    )
    parser.add_argument(
        "--jira-ticket",
        help="Jira ticket id (e.g., ENG-123) to build the prompt from",
    )
    parser.add_argument(
        "--jira-base-url",
        help="Jira base URL, e.g., https://your-org.atlassian.net (env: JIRA_BASE_URL)",
    )
    parser.add_argument(
        "--jira-email",
        help="Jira user email for API token auth (env: JIRA_EMAIL)",
    )
    parser.add_argument(
        "--jira-api-token",
        help="Jira API token (env: JIRA_API_TOKEN)",
    )
    parser.add_argument(
        "--context-root",
        action="append",
        help=(
            "Host directory to mount read-only into the agent workspace for extra context. "
            "Can be passed multiple times. Env equivalent: AGENT_CONTEXT_ROOTS (comma-separated)."
        ),
    )
    parser.add_argument(
        "--secret",
        action="append",
        help=(
            "Secret to pass to the change agent as an environment variable (KEY=VALUE). "
            "Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--secret-env",
        action="append",
        help=(
            "Name of an environment variable to forward to the change agent. "
            "Value is read from the current process environment. Can be passed multiple times."
        ),
    )
    return parser.parse_args()


def _merge_base_prompt_with_cli_prompt(base_prompt: str, cli_prompt: str | None) -> str:
    """
    If a prompt source (prompt config or Jira) is used AND --prompt is also provided,
    append the CLI prompt to the end of the loaded prompt.
    """
    if not cli_prompt or not cli_prompt.strip():
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{cli_prompt.strip()}"


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level, force=True)
    token = os.environ.get("GITHUB_TOKEN")

    context_roots = normalize_context_roots(list(args.context_root or []))

    has_prompt_config = (
        args.prompt_config_owner or args.prompt_config_repo or args.prompt_config_path
    )
    has_jira_prompt = bool(args.jira_ticket)

    if has_prompt_config and has_jira_prompt:
        raise SystemExit("Choose only one prompt source: prompt config or Jira ticket.")

    change_id = args.change_id
    if has_prompt_config:
        if not (
            args.prompt_config_owner
            and args.prompt_config_repo
            and args.prompt_config_path
        ):
            raise SystemExit(
                "When using prompt config, provide --prompt-config-owner, "
                "--prompt-config-repo, and --prompt-config-path"
            )
        prompts = load_prompts_from_config(
            args.prompt_config_owner,
            args.prompt_config_repo,
            args.prompt_config_ref,
            args.prompt_config_path,
            token,
        )
        prompt = _merge_base_prompt_with_cli_prompt(prompts["prompt"], args.prompt)
        relevance_prompt = prompts.get("relevance_prompt") or ""
        # change_id from config takes precedence over CLI arg
        if "change_id" in prompts:
            change_id = prompts["change_id"]
    elif has_jira_prompt:
        jira_prompt = load_prompt_from_jira(
            args.jira_base_url, args.jira_ticket, args.jira_email, args.jira_api_token
        )
        prompt = _merge_base_prompt_with_cli_prompt(jira_prompt["prompt"], args.prompt)
        relevance_prompt = args.relevance_prompt or ""
        # Jira ticket id always defines the change id for stable naming
        change_id = jira_prompt["change_id"]
    else:
        if not args.prompt:
            raise SystemExit(
                "--prompt is required when no prompt config or Jira ticket is provided"
            )
        prompt = args.prompt
        # Empty or missing relevance prompt => treat all repos as relevant
        relevance_prompt = args.relevance_prompt or ""

    state = WorkflowState(
        prompt=prompt,
        relevance_prompt=relevance_prompt,
        repos=list(args.repo or []),
        working_dir=Path(args.working_dir),
        context_roots=context_roots,
        change_agent_secret_kv_pairs=list(args.secret or []),
        change_agent_secret_env_keys=list(args.secret_env or []),
        datadog_team=args.datadog_team,
        datadog_site=args.datadog_site.replace("https://", "").replace("api.", ""),
        change_id=change_id,
    )
    try:
        final_state = asyncio.run(run_workflow(state))
    except ValueError as e:
        raise SystemExit(str(e)) from e
    summary = {
        "irrelevant_repos": final_state.irrelevant,
        "created_prs": final_state.created_prs,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
