import subprocess

import pytest

from pr_creator.cursor_utils.runners.cli_runner import CLICursorRunner


@pytest.mark.anyio
async def test_cli_runner_passes_timeout_env_to_subprocess_run(monkeypatch):
    monkeypatch.setenv("CURSOR_AGENT_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("CURSOR_WORKSPACE_ROOT", "/tmp")

    called = {}

    def fake_run(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = CLICursorRunner(cli_bin="cursor-agent")
    out = await runner.run_prompt(
        "hello",
        intent="change",
        repo_abs="/tmp/repo",
        context_roots=[],
        include_repo_hint=False,
        remove=False,
        stream_partial_output=False,
        extra_env={},
    )

    assert out == "ok"
    assert called["kwargs"]["timeout"] == 12.5


@pytest.mark.anyio
async def test_cli_runner_uses_default_timeout_when_env_unset(monkeypatch):
    monkeypatch.delenv("CURSOR_AGENT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("CURSOR_WORKSPACE_ROOT", "/tmp")

    called = {}

    def fake_run(*args, **kwargs):
        called["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = CLICursorRunner(cli_bin="cursor-agent")
    await runner.run_prompt(
        "hello",
        intent="change",
        repo_abs="/tmp/repo",
        context_roots=[],
        include_repo_hint=False,
        remove=False,
        stream_partial_output=False,
        extra_env={},
    )

    assert called["kwargs"]["timeout"] == 1200.0
