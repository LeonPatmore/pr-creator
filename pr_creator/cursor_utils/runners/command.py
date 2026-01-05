from __future__ import annotations


def build_cursor_agent_command(
    *,
    cli_bin: str,
    workspace_root: str,
    model: str,
    prompt: str,
    stream_partial_output: bool,
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
