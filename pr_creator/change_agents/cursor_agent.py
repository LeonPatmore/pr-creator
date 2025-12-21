from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

from .base import ChangeAgent


def _collect_env(keys: List[str]) -> List[str]:
    env_flags: List[str] = []
    for key in keys:
        if key in os.environ:
            env_flags.extend(["-e", key])
    return env_flags


class CursorChangeAgent(ChangeAgent):
    def run(self, repo_path: Path, prompt: str) -> None:
        image = os.environ.get("CURSOR_IMAGE", "cursor-cli:latest")
        env_keys = os.environ.get("CURSOR_ENV_KEYS", "CURSOR_API_KEY").split(",")
        env_keys = [k.strip() for k in env_keys if k.strip()]
        env_flags = _collect_env(env_keys)
        repo_abs = str(repo_path.resolve())
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{repo_abs}:/workspace",
            "-w",
            "/workspace",
            *env_flags,
            image,
            "cursor-agent",
            "--workspace",
            "/workspace",
            "--print",
            prompt,
        ]
        subprocess.run(cmd, check=True)
