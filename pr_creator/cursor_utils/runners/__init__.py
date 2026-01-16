import os
from functools import lru_cache

from . import base as _base
from . import cli_runner as _cli_runner
from . import docker_runner as _docker_runner

CursorHintPaths = _base.CursorHintPaths
CursorRunner = _base.CursorRunner
CLICursorRunner = _cli_runner.CLICursorRunner
DockerCursorRunner = _docker_runner.DockerCursorRunner


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
