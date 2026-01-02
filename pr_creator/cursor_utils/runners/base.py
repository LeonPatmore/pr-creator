from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CursorHintPaths:
    """
    Paths that we tell the agent to use inside its execution environment.

    - Docker runner uses container paths (e.g. /workspace/repo)
    - CLI runner uses host paths (e.g. /Users/.../repo)
    """

    repo_dir: str | None
    context_dirs: list[str]


class CursorRunner(Protocol):
    """
    Execute `cursor-agent` (Docker or local CLI).

    - `repo_abs`: absolute host path to the target repo (or `None` if no repo is needed).
    - `context_roots`: absolute host paths to extra read-only context dirs (may be empty).

    Docker mounts these into container paths; CLI uses host paths directly.
    """

    def hint_paths(
        self, *, repo_abs: str | None, context_roots: list[str]
    ) -> CursorHintPaths: ...

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
    ) -> str: ...
