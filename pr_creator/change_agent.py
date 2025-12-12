import os
import subprocess
from pathlib import Path
from typing import List


def collect_env(keys: List[str]) -> List[str]:
    env_flags = []
    for key in keys:
        if key in os.environ:
            env_flags.extend(["-e", f"{key}"])
    return env_flags


class ChangeAgent:
    @staticmethod
    def run(repo_path: Path, prompt: str) -> None:
        image = os.environ.get("CURSOR_IMAGE", "cursor-cli:latest")
        env_keys = os.environ.get("CURSOR_ENV_KEYS", "CURSOR_API_KEY,CURSOR_TOKEN").split(",")
        env_keys = [k.strip() for k in env_keys if k.strip()]
        env_flags = collect_env(env_keys)
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
            "--project",
            "/workspace",
            "--prompt",
            prompt,
        ]
        subprocess.run(cmd, check=True)

