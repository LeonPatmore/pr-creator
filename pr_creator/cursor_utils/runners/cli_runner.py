from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from subprocess import PIPE, STDOUT
from typing import Final

from pr_creator.cursor_utils.config import get_cursor_env_vars, get_cursor_model
from pr_creator.cursor_utils.runners.base import CursorHintPaths
from pr_creator.cursor_utils.runners.command import build_cursor_agent_command
from pr_creator.cursor_utils.runners.output_log import (
    append_output_log,
    resolve_cursor_output_log,
)
from pr_creator.workspace_mounts import workspace_prompt_prefix

logger = logging.getLogger(__name__)

_TRUTHY: Final[set[str]] = {"1", "true", "yes", "y", "on"}
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 1200.0


def _get_timeout_seconds() -> float | None:
    raw = (os.environ.get("CURSOR_AGENT_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        v = float(raw)
    except Exception:
        return _DEFAULT_TIMEOUT_SECONDS
    return v if v > 0 else None


def _show_thinking(env: dict[str, str]) -> bool:
    return (env.get("CURSOR_STREAM_SHOW_THINKING") or "").strip().lower() in _TRUTHY


def _run_streaming_process(
    command: list[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    show_thinking: bool,
    output_log_path: str | None,
) -> str:
    output_log_fp = None
    if output_log_path:
        try:
            os.makedirs(os.path.dirname(output_log_path), exist_ok=True)
            output_log_fp = open(
                output_log_path, "a", encoding="utf-8", errors="replace"
            )
        except Exception:
            output_log_fp = None

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
    text_chunks: list[str] = []
    saw_assistant_delta = False
    saw_stream_json = False

    def write_log(line: str) -> None:
        if not output_log_fp:
            return
        try:
            output_log_fp.write(line)
            output_log_fp.flush()
        except Exception:
            return

    def emit(text: str) -> None:
        text_chunks.append(text)
        sys.stdout.write(text)
        sys.stdout.flush()

    def emit_raw(line: str) -> None:
        sys.stdout.write(line)
        sys.stdout.flush()

    def extract_text(event: dict) -> tuple[str | None, str | None, str | None]:
        """
        Return (kind, subtype, text) where kind is one of:
        - "thinking"
        - "assistant"
        - "other"
        """
        if "type" in event and isinstance(event["type"], str):
            kind = event["type"]
        else:
            kind = "other"

        subtype = event.get("subtype")
        if not isinstance(subtype, str):
            subtype = None

        # Common shape we see: {"type":"thinking","subtype":"delta","text":"..."}
        if "text" in event and isinstance(event["text"], str):
            return kind, subtype, event["text"]

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
                    return "assistant", subtype, "".join(parts)

        return kind, subtype, None

    for line in proc.stdout:
        write_log(line)
        # Best-effort: parse stream-json and print a human-friendly subset.
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except Exception:
            # Not JSON: cursor-agent sometimes emits both stream-json events AND
            # human-readable plain text. If we already detected stream-json, suppress
            # subsequent non-JSON lines to avoid duplicating output in the console.
            #
            # We still write all lines to the output log file (see write_log above).
            if not saw_stream_json:
                emit_raw(line)
            continue

        if not isinstance(event, dict):
            if not saw_stream_json:
                emit_raw(line)
            continue

        saw_stream_json = True
        kind, subtype, text = extract_text(event)
        if kind not in ("assistant", "thinking"):
            continue
        if kind == "thinking" and not show_thinking:
            continue

        # Avoid printing full-message events after already streaming deltas; this is a common
        # cause of "everything prints twice" when stream-json includes both delta + final.
        if kind == "assistant":
            if subtype and subtype.lower() in ("delta", "chunk", "partial"):
                saw_assistant_delta = True
            if (
                saw_assistant_delta
                and "message" in event
                and (not subtype or subtype.lower() in ("message", "final", "complete"))
            ):
                continue

        if text:
            emit(text)
    rc = proc.wait()
    output = "".join(text_chunks)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, command, output=output)
    if output_log_fp:
        output_log_fp.close()
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

    async def run_prompt(
        self,
        prompt: str,
        *,
        intent: str | None = None,
        repo_abs: str | None,
        context_roots: list[str],
        include_repo_hint: bool,
        remove: bool,
        stream_partial_output: bool,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        # `remove` is Docker-only; keep signature for compatibility.
        _ = remove
        model = get_cursor_model(intent=intent)

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

        command = build_cursor_agent_command(
            cli_bin=self._cli_bin,
            workspace_root=workspace_root,
            model=model,
            stream_partial_output=stream_partial_output,
            prompt=full_prompt,
        )

        # Keep this log line for debugging runner behavior (do not change its shape).
        stream_mode = "assistant"
        show_thinking = _show_thinking(env_vars)
        effective_stream_partial_output = stream_partial_output
        logger.info(
            "[cursor-runner] runner=cli bin=%s model=%s stream_partial_output=%s "
            "stream_mode=%s show_thinking=%s cwd=%s workspace_root=%s prompt_len=%s",
            self._cli_bin,
            model,
            effective_stream_partial_output,
            stream_mode,
            show_thinking,
            repo_abs or "",
            workspace_root,
            len(full_prompt),
        )

        output_log = resolve_cursor_output_log(
            runner="cli", intent=intent, repo_abs=repo_abs
        )
        timeout_seconds = _get_timeout_seconds()

        # Offload blocking subprocess calls to thread pool to avoid blocking event loop
        if stream_partial_output:
            return await asyncio.to_thread(
                _run_streaming_process,
                command,
                cwd=repo_abs or None,
                env=env_vars,
                show_thinking=show_thinking,
                output_log_path=str(output_log.path) if output_log else None,
            )

        def _run_subprocess():
            result = subprocess.run(
                command,
                cwd=repo_abs or None,
                env=env_vars,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            append_output_log(output_log, result.stdout or "")
            return result.stdout

        return await asyncio.to_thread(_run_subprocess)
