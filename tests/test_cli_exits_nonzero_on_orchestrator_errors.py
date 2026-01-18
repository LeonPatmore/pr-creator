from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import pr_creator.cli as cli
from pr_creator.workflows.orchestrator.state import OrchestratorState


def test_cli_exits_nonzero_when_orchestrator_errors_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = SimpleNamespace(
        prompt="some prompt",
        relevance_prompt="",
        prompt_config_owner=None,
        prompt_config_repo=None,
        prompt_config_ref=None,
        prompt_config_path=None,
        repo=[],
        datadog_team=None,
        datadog_site=None,
        working_dir=None,
        log_level="INFO",
        change_id=None,
        jira_ticket=None,
        jira_base_url=None,
        jira_email=None,
        jira_api_token=None,
        context_root=[],
        secret=[],
        secret_env=[],
        github_token=None,
        mcp_config=None,
    )
    monkeypatch.setattr(cli, "parse_args", lambda: args)

    async def _fake_run_orchestrator_workflow(state: OrchestratorState) -> OrchestratorState:
        state.orchestrator_errors.append("boom")
        return state

    monkeypatch.setattr(cli, "run_orchestrator_workflow", _fake_run_orchestrator_workflow)
    monkeypatch.setattr(cli, "_print_workflow_summary", lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1

