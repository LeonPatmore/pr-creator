import argparse
import asyncio
import json
import os
from pathlib import Path

from .logging_config import configure_logging
from .prompt_config import load_prompts_from_config
from .state import WorkflowState
from .workflow import run_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=False)
    parser.add_argument("--relevance-prompt", required=False)
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level, force=True)
    token = os.environ.get("GITHUB_TOKEN")

    if args.prompt_config_owner or args.prompt_config_repo or args.prompt_config_path:
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
        prompt = prompts["prompt"]
        relevance_prompt = prompts["relevance_prompt"]
    else:
        if not args.prompt or not args.relevance_prompt:
            raise SystemExit(
                "--prompt and --relevance-prompt are required when no prompt config is provided"
            )
        prompt = args.prompt
        relevance_prompt = args.relevance_prompt

    state = WorkflowState(
        prompt=prompt,
        relevance_prompt=relevance_prompt,
        repos=list(args.repo or []),
        working_dir=Path(args.working_dir),
        datadog_team=args.datadog_team,
        datadog_site=args.datadog_site.replace("https://", "").replace("api.", ""),
    )
    final_state = asyncio.run(run_workflow(state))
    summary = {
        "irrelevant_repos": final_state.irrelevant,
        "created_prs": final_state.created_prs,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
