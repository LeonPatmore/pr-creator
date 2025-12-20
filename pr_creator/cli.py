import argparse
import asyncio
from pathlib import Path

from .logging_config import configure_logging
from .state import WorkflowState
from .workflow import run_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--relevance-prompt", required=True)
    parser.add_argument("--repo", action="append", required=True)
    parser.add_argument("--working-dir", default=".repos")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level, force=True)
    state = WorkflowState(
        prompt=args.prompt,
        relevance_prompt=args.relevance_prompt,
        repos=list(args.repo),
        working_dir=Path(args.working_dir),
    )
    asyncio.run(run_workflow(state))


if __name__ == "__main__":
    main()

