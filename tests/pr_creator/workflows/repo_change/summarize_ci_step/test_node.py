from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from pr_creator.workflows.repo_change.state import RepoChangeState
from pr_creator.workflows.repo_change.ci_types import CiFailure
from pr_creator.workflows.repo_change.summarize_ci_step import node as summarize_node
from pr_creator.workflows.repo_change.summarize_ci_step.node import SummarizeCiFailures


class _Ctx:
    def __init__(self, state: RepoChangeState):
        self.state = state


@pytest.mark.anyio
async def test_summarize_ci_failures_runs_once_per_failed_check(monkeypatch):
    repo_url = "https://github.com/acme/repo"
    failures = [
        CiFailure(
            pr_url="https://github.com/acme/repo/pull/1",
            head_sha="deadbeef",
            name="lint",
            details_url="https://github.com/acme/repo/actions/runs/1",
            logs="flake8 failed",
        ),
        CiFailure(
            pr_url="https://github.com/acme/repo/pull/1",
            head_sha="deadbeef",
            name="unit-tests",
            details_url="https://github.com/acme/repo/actions/runs/2",
            logs="pytest failed",
        ),
    ]

    calls: list[str] = []

    @contextlib.asynccontextmanager
    async def _fake_summarizer():
        async def _summarize_one(blob: str) -> str:
            calls.append(blob)
            if "check_name: lint" in blob:
                return "Lint failed due to flake8 errors. See the job logs for the first reported file."
            return "Unit tests failed during pytest. See the failing test in the logs."

        yield _summarize_one

    monkeypatch.setattr(summarize_node, "build_ci_failure_summarizer", _fake_summarizer)

    state = RepoChangeState(additional_prompt="x", working_dir=Path("/tmp"))
    state.ci_failures[repo_url] = failures
    ctx = _Ctx(state)

    node = SummarizeCiFailures(repo_url=repo_url)
    result = await node.run(ctx)  # type: ignore[arg-type]

    assert calls and len(calls) == 2
    assert "check_name: lint" in calls[0]
    assert "check_name: unit-tests" in calls[1]

    summaries = state.ci_failure_summaries[repo_url]
    assert len(summaries) == 2
    assert "Lint failed" in summaries[0]
    assert "Unit tests failed" in summaries[1]

    # Node should proceed to cleanup afterwards.
    assert result.__class__.__name__ == "CleanupRepo"
