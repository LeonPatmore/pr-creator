from __future__ import annotations

from pathlib import Path

from .base import ChangeAgent
from pr_creator.cursor_utils.runner import run_cursor_prompt
from pr_creator.workspace_mounts import (
    REPO_DIR,
    build_workspace_volumes,
    workspace_prompt_prefix,
)


class CursorChangeAgent(ChangeAgent):
    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        repo_abs = str(repo_path.resolve())
        full_prompt = (
            f"{workspace_prompt_prefix(include_repo_hint=True, context_roots=context_roots)}"
            f"{prompt}"
        )
        run_cursor_prompt(
            full_prompt,
            volumes=build_workspace_volumes(repo_abs, context_roots=context_roots),
            workdir=REPO_DIR,
            remove=False,
            extra_env=secrets or {},
        )
