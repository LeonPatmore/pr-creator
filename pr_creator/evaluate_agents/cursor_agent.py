from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List

import docker

from .base import EvaluateAgent

logger = logging.getLogger(__name__)


def _collect_env(keys: List[str]) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    for key in keys:
        if key in os.environ:
            env_vars[key] = os.environ[key]
    return env_vars


class CursorEvaluateAgent(EvaluateAgent):
    def evaluate(self, repo_path: Path, relevance_prompt: str) -> bool:
        image = os.environ.get("CURSOR_IMAGE", "leonpatmore2/cursor-agent:latest")
        env_keys = os.environ.get("CURSOR_ENV_KEYS", "CURSOR_API_KEY").split(",")
        env_keys = [k.strip() for k in env_keys if k.strip()]
        env_vars = _collect_env(env_keys)
        repo_abs = str(repo_path.resolve())
        prompt = (
            "You are evaluating whether a repository is relevant to an objective.\n"
            f"Objective: {relevance_prompt}\n"
            "Answer with only 'yes' or 'no'."
        )

        client = docker.from_env()
        output_bytes = client.containers.run(
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

        # containers.run returns bytes when detach=False
        output = (
            output_bytes.decode("utf-8")
            if isinstance(output_bytes, bytes)
            else str(output_bytes)
        )

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
