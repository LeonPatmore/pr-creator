from __future__ import annotations

from pathlib import Path

from .base import ChangeAgent
from pr_creator.cursor_utils.runner import run_cursor_prompt


class CursorChangeAgent(ChangeAgent):
    def run(self, repo_path: Path, prompt: str) -> None:
        repo_abs = str(repo_path.resolve())
        run_cursor_prompt(
            prompt,
            volumes={repo_abs: {"bind": "/workspace", "mode": "rw"}},
            remove=False,
        )
