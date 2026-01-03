import argparse
import asyncio
import json
from pathlib import Path

from .logging_config import configure_logging
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
        help="GitHub owner of the prompt config repo (env fallback: PROMPT_CONFIG_OWNER)",
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


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level, force=True)

    context_roots = normalize_context_roots(list(args.context_root or []))

    state = WorkflowState(
        prompt="",
        relevance_prompt=args.relevance_prompt or "",
        cli_prompt=args.prompt,
        prompt_config_owner=args.prompt_config_owner,
        prompt_config_repo=args.prompt_config_repo,
        prompt_config_ref=args.prompt_config_ref,
        prompt_config_path=args.prompt_config_path,
        jira_ticket=args.jira_ticket,
        jira_base_url=args.jira_base_url,
        jira_email=args.jira_email,
        jira_api_token=args.jira_api_token,
        repos=list(args.repo or []),
        working_dir=Path(args.working_dir),
        context_roots=context_roots,
        change_agent_secret_kv_pairs=list(args.secret or []),
        change_agent_secret_env_keys=list(args.secret_env or []),
        datadog_team=args.datadog_team,
        datadog_site=args.datadog_site.replace("https://", "").replace("api.", ""),
        change_id=args.change_id,
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
