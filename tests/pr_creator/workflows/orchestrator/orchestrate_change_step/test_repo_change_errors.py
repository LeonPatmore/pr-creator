import pytest

from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    OrchestratorResponse,
)
from pr_creator.workflows.orchestrator.orchestrate_change_step.node import (
    OrchestrateChange,
)
from pr_creator.workflows.orchestrator.state import OrchestratorState


@pytest.mark.anyio
async def test_orchestrate_change_catches_repo_change_exception_and_returns_error_record(
    monkeypatch, tmp_path
):
    state = OrchestratorState(
        prompt="base prompt",
        relevance_prompt="",
        repos=[],
        working_dir=tmp_path,
        github_token=None,
        mcp_config_path=None,
    )

    # Patch the repo-change workflow to raise.
    import pr_creator.workflows.orchestrator.orchestrate_change_step.node as orch_node

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(orch_node, "run_repo_change_for_repo", _boom)

    # Patch the agent builder so we don't invoke a real model; instead we force one tool call.
    def _fake_build_orchestrate_change_agent(*, repo_change_tool, mcp_config_path=None):
        class _Agent:
            async def run(self, user_prompt, deps):
                tool_out = await repo_change_tool(
                    "https://github.com/example/example", "do something"
                )
                # The agent returns whatever the tool returned as a result entry.
                return type(
                    "R",
                    (),
                    {"output": OrchestratorResponse(results=[tool_out], error=None)},
                )()

        return _Agent(), {"called": True}

    monkeypatch.setattr(
        orch_node,
        "build_orchestrate_change_agent",
        _fake_build_orchestrate_change_agent,
    )

    node = OrchestrateChange(repo_url="https://github.com/example/example")

    class _Ctx:
        def __init__(self, state):
            self.state = state

    await node.run(_Ctx(state))  # type: ignore[arg-type]

    # Tool failure should be recorded as orchestrator_errors, not a created PR.
    assert state.created_prs == []
    assert state.orchestrator_errors, "Expected orchestrator to record error"
    assert "repo_change workflow failed" in state.orchestrator_errors[-1]
    # No PR record should be emitted on tool failure.
