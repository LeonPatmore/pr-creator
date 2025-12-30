from __future__ import annotations

from pathlib import Path

import docker

from .base import ChangeAgent
from pr_creator.cursor_config import (
    get_cursor_image,
    get_cursor_model,
    get_cursor_env_vars,
)


class CursorChangeAgent(ChangeAgent):
    def run(self, repo_path: Path, prompt: str) -> None:
        image = get_cursor_image()
        model = get_cursor_model()
        env_vars = get_cursor_env_vars()
        repo_abs = str(repo_path.resolve())

        client = docker.from_env()
        client.containers.run(
            image,
            command=[
                "cursor-agent",
                "--workspace",
                "/workspace",
                "--model",
                model,
                "--print",
                prompt,
            ],
            volumes={repo_abs: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            environment=env_vars,
            remove=False,
        )
