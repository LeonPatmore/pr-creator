from __future__ import annotations

import asyncio
from pathlib import Path

from pr_creator.repo_workspace import prepare_workspace


async def prepare_planning_clone(
    *, repo_url: str, working_dir: Path, github_token: str | None
) -> Path:
    """Prepare a read-only planning clone for evaluation."""
    planning_dir = working_dir / "_orchestrator"
    repo_clone = await asyncio.to_thread(
        prepare_workspace,
        repo=repo_url,
        working_dir=planning_dir,
        github_token=github_token,
        branch_name=None,
        stable=True,
    )
    return repo_clone.path
