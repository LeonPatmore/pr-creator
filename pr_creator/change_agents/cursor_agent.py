from __future__ import annotations

from pathlib import Path

from .base import ChangeAgent
from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner


class CursorChangeAgent(ChangeAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        repo_abs = str(repo_path.resolve())
        self._runner.run_prompt(
            prompt,
            remove=False,
            repo_abs=repo_abs,
            context_roots=context_roots,
            include_repo_hint=True,
            stream_partial_output=True,
            extra_env=secrets or {},
        )
