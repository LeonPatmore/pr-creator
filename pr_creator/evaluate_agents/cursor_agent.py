from __future__ import annotations

import logging
from pathlib import Path

import docker

from .base import EvaluateAgent
from pr_creator.cursor_config import get_cursor_image, get_cursor_model, get_cursor_env_vars

logger = logging.getLogger(__name__)


class CursorEvaluateAgent(EvaluateAgent):
    def evaluate(self, repo_path: Path, relevance_prompt: str) -> bool:
        image = get_cursor_image()
        model = get_cursor_model()
        env_vars = get_cursor_env_vars()
        repo_abs = str(repo_path.resolve())
        prompt = (
            "You are evaluating whether a repository is relevant to an objective.\n"
            f"Objective: {relevance_prompt}\n\n"
            "You may provide reasoning, but you MUST end your response with a clear final answer.\n"
            "Format your final answer as: **yes** or **no**\n"
            "The final answer should be on its own line or clearly marked with double asterisks."
        )

        client = docker.from_env()
        output_bytes = client.containers.run(
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
    """
    Parse the decision from Cursor agent output.
    Prioritizes final answer markers like **yes** or **no**, then checks from the end backwards.
    """
    output_lower = output.lower()
    
    # First, check for bold markers (common format for final answers)
    if "**yes**" in output_lower or "**y**" in output_lower:
        return True
    if "**no**" in output_lower or "**n**" in output_lower:
        return False
    
    # Parse from the end backwards to find the final answer
    # This handles cases where "yes" or "no" appear in the middle of reasoning
    words = output_lower.replace(".", " ").replace(",", " ").split()
    
    # Check last 10 words first (likely to contain the final answer)
    for word in reversed(words[-10:]):
        if word in {"yes", "y", "true"}:
            return True
        if word in {"no", "n", "false"}:
            return False
    
    # Fallback: check all words (original behavior)
    for word in words:
        if word in {"yes", "y", "true"}:
            return True
        if word in {"no", "n", "false"}:
            return False
    
    return False
