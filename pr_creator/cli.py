import argparse
import asyncio
import json
import logging
from pathlib import Path

from .logging_config import configure_logging
from pr_creator.workflows.orchestrator.state import OrchestratorState
from pr_creator.workflows.orchestrator.workflow import run_orchestrator_workflow
from pr_creator.context_roots import normalize_context_roots

logger = logging.getLogger(__name__)


def _print_workflow_summary(final_state, summary: dict) -> None:
    """Print a formatted summary of the orchestrator workflow results."""
    print("\n" + "=" * 80)
    print("ORCHESTRATOR WORKFLOW SUMMARY")
    print("=" * 80)

    if final_state.created_prs:
        print(f"\n✓ Successfully created {len(final_state.created_prs)} PR(s):")
        for pr in final_state.created_prs:
            repo_name = pr["repo_url"].split("/")[-1]
            print(f"  • {repo_name}")
            print(f"    Branch:  {pr['branch']}")
            print(f"    PR URL:  {pr['pr_url']}")

            # Show SHA if available
            if pr.get("pushed_sha"):
                print(f"    SHA:     {pr['pushed_sha'][:12]}")

            # Show whether changes were pushed
            changes_pushed = pr.get(
                "changes_pushed", True
            )  # Default to True for backward compat
            if not changes_pushed:
                print("    Changes: No new changes (PR already exists)")

            # Show CI status if available
            ci_passed = pr.get("ci_passed")
            if ci_passed is True:
                print("    CI:      ✓ Passed")
            elif ci_passed is False:
                print("    CI:      ✗ Failed")
            # If None, don't show anything (CI not waited for)
    else:
        print("\n✗ No PRs created")

    if final_state.irrelevant:
        print(f"\n⊘ Filtered {len(final_state.irrelevant)} irrelevant repo(s):")
        for repo in final_state.irrelevant:
            repo_name = repo.split("/")[-1]
            print(f"  • {repo_name}")

    if final_state.orchestrator_errors:
        print(f"\n✗ Encountered {len(final_state.orchestrator_errors)} error(s):")
        for error in final_state.orchestrator_errors:
            print(f"  • {error}")
            logger.error("Orchestrator error: %s", error)

    print("\n" + "=" * 80)

    # Also output raw JSON for machine consumption
    print(json.dumps(summary))


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
        help="Git ref (branch/sha/tag) for the prompt config file",
    )
    parser.add_argument(
        "--prompt-config-path",
        help="Path to the YAML file in the prompt config repo",
    )
    parser.add_argument(
        "--repo",
        action="append",
        required=False,
        help=(
            "Target repository URL or short name (owner/repo). Can be specified multiple times. "
            "If omitted, the orchestrator will attempt to discover repos."
        ),
    )
    parser.add_argument(
        "--datadog-team",
        help="Datadog team name for repo discovery (requires DATADOG_API_KEY and DATADOG_APP_KEY)",
    )
    parser.add_argument(
        "--datadog-site",
        help="Datadog site base URL",
    )
    parser.add_argument("--working-dir")
    parser.add_argument("--log-level", help="Logging level")
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
    parser.add_argument(
        "--github-token",
        help=(
            "GitHub token used for clone/push/PR creation. If omitted, falls back to env GITHUB_TOKEN."
        ),
    )
    parser.add_argument(
        "--mcp-config",
        help=(
            "Path to MCP servers configuration file (JSON format). "
            "If provided, the orchestrator will load MCP servers as tools. "
            "See https://ai.pydantic.dev/mcp/client/ for config format."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level, force=True)

    context_roots = normalize_context_roots(list(args.context_root or []))

    try:
        # Orchestrator owns discovery/iteration and is always enabled.
        state_kwargs: dict = dict(
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
            working_dir=(
                Path(args.working_dir).expanduser()
                if (args.working_dir or "").strip()
                else None
            ),
            github_token=args.github_token,
            context_roots=context_roots,
            change_agent_secret_kv_pairs=list(args.secret or []),
            change_agent_secret_env_keys=list(args.secret_env or []),
            datadog_team=args.datadog_team,
            change_id=args.change_id,
            mcp_config_path=(
                Path(args.mcp_config).expanduser()
                if (args.mcp_config or "").strip()
                else None
            ),
        )
        if (args.datadog_site or "").strip():
            state_kwargs["datadog_site"] = args.datadog_site.replace(
                "https://", ""
            ).replace("api.", "")

        state = OrchestratorState(**state_kwargs)
        final_state = asyncio.run(run_orchestrator_workflow(state))
    except ValueError as e:
        raise SystemExit(str(e)) from e

    summary = {
        "irrelevant_repos": final_state.irrelevant,
        "created_prs": final_state.created_prs,
        "orchestrator_errors": final_state.orchestrator_errors,
    }

    _print_workflow_summary(final_state, summary)


if __name__ == "__main__":
    main()
