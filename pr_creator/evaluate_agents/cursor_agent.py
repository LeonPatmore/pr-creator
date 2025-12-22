from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import List

from .base import EvaluateAgent

logger = logging.getLogger(__name__)


def _collect_env(keys: List[str]) -> List[str]:
    env_flags: List[str] = []
    for key in keys:
        if key in os.environ:
            env_flags.extend(["-e", key])
    return env_flags


class CursorEvaluateAgent(EvaluateAgent):
    def evaluate(self, repo_path: Path, relevance_prompt: str) -> bool:
        image = os.environ.get("CURSOR_IMAGE", "cursor-cli:latest")
        env_keys = os.environ.get("CURSOR_ENV_KEYS", "CURSOR_API_KEY").split(",")
        env_keys = [k.strip() for k in env_keys if k.strip()]
        env_flags = _collect_env(env_keys)
        repo_abs = str(repo_path.resolve())
        prompt = (
            "You are evaluating whether a repository is relevant to an objective.\n"
            f"Objective: {relevance_prompt}\n"
            "Answer with only 'yes' or 'no'."
        )
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
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        output = (result.stdout or "") + (result.stderr or "")
        logger.info("Cursor evaluate output for %s: %s", repo_path, output.strip())
        decision = _parse_decision(output)
        logger.info("Cursor evaluate decision for %s: %s", repo_path, decision)
        return decision


def _parse_decision(output: str) -> bool:
    words = output.lower().replace(".", " ").split()
    for word in words:
        if word in {"yes", "y", "true"}:
            return True
        if word in {"no", "n", "false"}:
            return False
    return False
