from __future__ import annotations

import json
import os
import subprocess
import sys
from subprocess import PIPE, STDOUT

from pr_creator.cursor_utils.config import get_cursor_env_vars, get_cursor_model
from pr_creator.cursor_utils.runners.base import CursorHintPaths
from pr_creator.workspace_mounts import workspace_prompt_prefix


def _base_cursor_command(
    *,
    cli_bin: str,
    workspace_root: str,
    model: str,
    stream_partial_output: bool,
    prompt: str,
) -> list[str]:
    cmd = [
        cli_bin,
        "--workspace",
        workspace_root,
        "--model",
        model,
        "--force",
    ]
    if stream_partial_output:
        cmd.extend(["--output-format", "stream-json", "--stream-partial-output"])
    cmd.extend(["--print", prompt])
    return cmd


def _run_streaming_process(
    command: list[str], *, cwd: str | None, env: dict[str, str]
) -> str:
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=PIPE,
        stderr=STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None  # for type checkers
    raw_chunks: list[str] = []
    text_chunks: list[str] = []
    stream_mode = (env.get("CURSOR_STREAM_MODE") or "assistant").lower().strip()
    show_thinking = (env.get("CURSOR_STREAM_SHOW_THINKING") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    )

    def emit(text: str) -> None:
        text_chunks.append(text)
        sys.stdout.write(text)
        sys.stdout.flush()

    def emit_raw(line: str) -> None:
        raw_chunks.append(line)
        sys.stdout.write(line)
        sys.stdout.flush()

    def extract_text(event: dict) -> tuple[str | None, str | None]:
        """
        Return (kind, text) where kind is one of:
        - "thinking"
        - "assistant"
        - "other"
        """
        if "type" in event and isinstance(event["type"], str):
            kind = event["type"]
        else:
            kind = "other"

        # Common shape we see: {"type":"thinking","subtype":"delta","text":"..."}
        if "text" in event and isinstance(event["text"], str):
            return kind, event["text"]

        # OpenAI-ish shape: {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"..."}]}}
        msg = event.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                if parts:
                    return "assistant", "".join(parts)

        return kind, None

    for line in proc.stdout:
        if stream_mode == "raw":
            emit_raw(line)
            continue

        # Best-effort: parse stream-json and print a human-friendly subset.
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except Exception:
            # Not JSON: print as-is.
            emit_raw(line)
            continue

        if not isinstance(event, dict):
            emit_raw(line)
            continue

        kind, text = extract_text(event)
        if kind == "thinking" and not show_thinking:
            continue

        if stream_mode == "assistant":
            # Only show assistant-ish text (and optionally thinking).
            if kind not in ("assistant", "thinking"):
                continue

        if text:
            emit(text)
    rc = proc.wait()
    output = "".join(text_chunks) if stream_mode != "raw" else "".join(raw_chunks)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, command, output=output)
    return output


class CLICursorRunner:
    """
    Runs Cursor locally using the `cursor-agent` CLI on the host.

    Requirements:
    - `cursor-agent` must be available on PATH, or set env `CURSOR_CLI_BIN`.
    """

    def __init__(self, *, cli_bin: str | None = None) -> None:
        self._cli_bin = cli_bin or os.environ.get("CURSOR_CLI_BIN") or "cursor-agent"

    def hint_paths(
        self, *, repo_abs: str | None, context_roots: list[str]
    ) -> CursorHintPaths:
        return CursorHintPaths(repo_dir=repo_abs, context_dirs=context_roots)

    def run_prompt(
        self,
        prompt: str,
        *,
        repo_abs: str | None,
        context_roots: list[str],
        include_repo_hint: bool,
        remove: bool,
        stream_partial_output: bool,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        # `remove` is Docker-only; keep signature for compatibility.
        _ = remove
        model = get_cursor_model()

        env_vars = os.environ.copy()
        env_vars.update(get_cursor_env_vars())
        if extra_env:
            env_vars.update(extra_env)

        hint = self.hint_paths(repo_abs=repo_abs, context_roots=context_roots)
        prefix = workspace_prompt_prefix(
            include_repo_hint=include_repo_hint,
            repo_dir=hint.repo_dir,
            context_dirs=hint.context_dirs,
        )
        full_prompt = f"{prefix}{prompt}"

        workspace_root = os.environ.get("CURSOR_WORKSPACE_ROOT")
        if not workspace_root:
            paths = [p for p in [repo_abs, *context_roots] if p]
            try:
                workspace_root = os.path.commonpath(paths) if paths else os.getcwd()
            except Exception:
                workspace_root = repo_abs or os.getcwd()

        command = _base_cursor_command(
            cli_bin=self._cli_bin,
            workspace_root=workspace_root,
            model=model,
            stream_partial_output=stream_partial_output,
            prompt=full_prompt,
        )

        # For interactive visibility, stream to stdout when requested (and still capture).
        if stream_partial_output:
            return _run_streaming_process(command, cwd=repo_abs or None, env=env_vars)

        result = subprocess.run(
            command,
            cwd=repo_abs or None,
            env=env_vars,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
