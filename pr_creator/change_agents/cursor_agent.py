from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

import docker

from .base import ChangeAgent


def _collect_env(keys: List[str]) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    for key in keys:
        if key in os.environ:
            env_vars[key] = os.environ[key]
    return env_vars


class CursorChangeAgent(ChangeAgent):
    def run(self, repo_path: Path, prompt: str) -> None:
        image = os.environ.get("CURSOR_IMAGE", "leonpatmore2/cursor-agent:latest")
        env_keys = os.environ.get("CURSOR_ENV_KEYS", "CURSOR_API_KEY").split(",")
        env_keys = [k.strip() for k in env_keys if k.strip()]
        env_vars = _collect_env(env_keys)
        repo_abs = str(repo_path.resolve())

        client = docker.from_env()
        client.containers.run(
            image,
            command=[
                "cursor-agent",
                "--workspace",
                "/workspace",
                "--print",
                prompt,
            ],
            volumes={repo_abs: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            environment=env_vars,
            remove=True,
        )
