from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CursorOutputLog:
    path: Path


def _default_output_log_dir() -> Path:
    return Path.home() / ".pr-creator" / "cursor-output-logs"


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
    *, runner: str, intent: str | None, repo_abs: str | None
) -> CursorOutputLog | None:
    """
    Determine where to write a full raw cursor-agent output log.

    Env:
    - PR_CREATOR_CURSOR_OUTPUT_LOG_DIR: directory where per-run logs are created
      (default: ~/.pr-creator/cursor-output-logs)
    """
    log_dir_raw = (os.environ.get("PR_CREATOR_CURSOR_OUTPUT_LOG_DIR") or "").strip()
    log_dir = (
        Path(log_dir_raw).expanduser() if log_dir_raw else _default_output_log_dir()
    )

    intent_slug = _safe_slug(intent or "unknown-intent")
    repo_name = _safe_slug(Path(repo_abs).name if repo_abs else "no-repo")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    pid = os.getpid()
    filename = (
        f"cursor-agent-{_safe_slug(runner)}-{intent_slug}-{repo_name}-{ts}-{pid}.log"
    )
    path = log_dir / filename
    logger.info(
        "[cursor-runner] output_log_dir=%s output_log_file=%s",
        str(log_dir),
        str(path.name),
    )
    return CursorOutputLog(path=path)


def append_output_log(output_log: CursorOutputLog | None, content: str) -> None:
    """
    Best-effort append to the configured output log file (if enabled).

    This helper exists so runners don't each have to repeat mkdir/try/except blocks.
    """
    if not output_log:
        return
    try:
        output_log.path.parent.mkdir(parents=True, exist_ok=True)
        output_log.path.open("a", encoding="utf-8", errors="replace").write(
            content or ""
        )
    except Exception:
        # Best-effort; never crash runner due to output logging.
        pass
