from __future__ import annotations

import pytest

from pr_creator.workflows.repo_change.wait_for_actions_step import github_actions as ga


def _cfg():
    # Polling is mocked out; keep these small.
    return ga.CiWaitConfig(
        timeout_seconds=5,
        poll_seconds=0,
        heartbeat_seconds=0,
        pending_no_checks_grace_seconds=0,
        max_log_bytes=1000,
        max_log_chars=1000,
        acceptable_conclusions=("success",),
    )


@pytest.mark.anyio
async def test_wait_for_ci_fail_fast_returns_on_first_failure(monkeypatch):
    """
    When fail_fast_on_failure=True, the waiter should return as soon as a failed
    check-run is observed, even if other checks are still pending.
    """
    monkeypatch.setattr(ga, "parse_pr_url", lambda _url: ("o", "r", 1))
    monkeypatch.setattr(ga, "get_pr_head_sha", lambda *_a, **_k: "sha")

    # Iteration 1: one failing completed check and one pending check.
    check_runs = [
        {
            "name": "lint",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "sha",
            "details_url": "https://github.com/o/r/actions/runs/1",
        },
        {
            "name": "tests",
            "status": "in_progress",
            "conclusion": None,
            "head_sha": "sha",
        },
    ]
    monkeypatch.setattr(ga, "get_check_runs", lambda *_a, **_k: list(check_runs))
    monkeypatch.setattr(
        ga, "get_combined_status_and_statuses", lambda *_a, **_k: ("pending", [])
    )
    monkeypatch.setattr(ga.time, "sleep", lambda _s: None)

    failures = ga.wait_for_ci(
        "https://github.com/o/r/pull/1",
        token="t",
        cfg=_cfg(),
        fail_fast_on_failure=True,
    )
    assert failures
    assert len(failures) == 1
    assert failures[0].name == "lint"


@pytest.mark.anyio
async def test_wait_for_ci_final_attempt_waits_for_all_failures(monkeypatch):
    """
    When fail_fast_on_failure=False, failures should not stop polling if anything
    is still pending. Once nothing is pending, return a message that includes
    all failures.
    """
    monkeypatch.setattr(ga, "parse_pr_url", lambda _url: ("o", "r", 1))
    monkeypatch.setattr(ga, "get_pr_head_sha", lambda *_a, **_k: "sha")

    # Two polling iterations: first has pending + one failed; second has two failed and no pending.
    seq = [
        [
            {
                "name": "lint",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": "sha",
                "details_url": "https://github.com/o/r/actions/runs/1",
            },
            {
                "name": "tests",
                "status": "in_progress",
                "conclusion": None,
                "head_sha": "sha",
            },
        ],
        [
            {
                "name": "lint",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": "sha",
                "details_url": "https://github.com/o/r/actions/runs/1",
            },
            {
                "name": "tests",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": "sha",
                "details_url": "https://github.com/o/r/actions/runs/2",
            },
        ],
    ]
    it = iter(seq)

    def _get_check_runs(*_a, **_k):
        try:
            return next(it)
        except StopIteration:
            # If called again, keep returning the terminal state.
            return seq[-1]

    monkeypatch.setattr(ga, "get_check_runs", _get_check_runs)
    monkeypatch.setattr(
        ga,
        "get_combined_status_and_statuses",
        lambda *_a, **_k: ("pending", []),
    )

    # Make _has_pending depend on check run status only (combined_state is pending in both iterations).
    # That mirrors real behavior: pending should flip to False once no check run is queued/in_progress.
    monkeypatch.setattr(ga.time, "sleep", lambda _s: None)

    # Capture which failures were summarized.
    failures = ga.wait_for_ci(
        "https://github.com/o/r/pull/1",
        token="t",
        cfg=_cfg(),
        fail_fast_on_failure=False,
    )
    assert failures
    assert sorted([f.name for f in failures]) == ["lint", "tests"]
