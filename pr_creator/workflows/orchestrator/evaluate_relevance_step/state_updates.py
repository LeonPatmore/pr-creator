from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic_graph.beta import StepContext

from pr_creator.workflows.orchestrator.state import OrchestratorState

STATE_LOCK = asyncio.Lock()


async def record_planning_clone(
    ctx: StepContext[OrchestratorState, None, str | None],
    *,
    repo_url: str,
    repo_path: Path,
) -> None:
    async with STATE_LOCK:
        ctx.state.planning_clones[repo_url] = repo_path


async def record_irrelevant(
    ctx: StepContext[OrchestratorState, None, str | None], *, repo_url: str
) -> None:
    async with STATE_LOCK:
        ctx.state.irrelevant.append(repo_url)
