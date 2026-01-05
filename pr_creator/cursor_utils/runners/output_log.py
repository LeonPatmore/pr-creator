from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class CursorOutputLog:
    path: Path


def _safe_slug(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "unknown"
    out: list[str] = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        elif ch in (" ", "/"):
            out.append("-")
        # else drop
    slug = "".join(out).strip("-") or "unknown"
    return slug[:80]


def resolve_cursor_output_log(
    *, runner: str, repo_abs: str | None
) -> CursorOutputLog | None:
    """
    Determine where to write a full raw cursor-agent output log (if enabled).

    Env:
    - PR_CREATOR_CURSOR_OUTPUT_LOG_FILE: explicit file path (appends)
    - PR_CREATOR_CURSOR_OUTPUT_LOG_DIR: directory where per-run logs are created
    """
    explicit = (os.environ.get("PR_CREATOR_CURSOR_OUTPUT_LOG_FILE") or "").strip()
    if explicit:
        return CursorOutputLog(path=Path(explicit).expanduser())

    log_dir = (os.environ.get("PR_CREATOR_CURSOR_OUTPUT_LOG_DIR") or "").strip()
    if not log_dir:
        return None

    repo_name = _safe_slug(Path(repo_abs).name if repo_abs else "no-repo")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    pid = os.getpid()
    filename = f"cursor-agent-{_safe_slug(runner)}-{repo_name}-{ts}-{pid}.log"
    return CursorOutputLog(path=Path(log_dir).expanduser() / filename)
