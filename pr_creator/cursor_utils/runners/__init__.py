from __future__ import annotations

import os
from functools import lru_cache

from pr_creator.cursor_utils.runners.base import CursorHintPaths, CursorRunner
from pr_creator.cursor_utils.runners.cli_runner import CLICursorRunner
from pr_creator.cursor_utils.runners.docker_runner import DockerCursorRunner


@lru_cache(maxsize=None)
def _get_cursor_runner_cached(selected: str) -> CursorRunner:
    if selected == "docker":
        return DockerCursorRunner()
    if selected == "cli":
        return CLICursorRunner()
    raise ValueError(f"Unknown CURSOR_RUNNER: {selected}")


def get_cursor_runner(kind: str | None = None) -> CursorRunner:
    selected = (kind or os.environ.get("CURSOR_RUNNER") or "docker").lower().strip()
    return _get_cursor_runner_cached(selected)


__all__ = [
    "CursorHintPaths",
    "CursorRunner",
    "CLICursorRunner",
    "DockerCursorRunner",
    "get_cursor_runner",
]
