from __future__ import annotations

import logging
from pathlib import Path

from .base import EvaluateAgent
from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner

logger = logging.getLogger(__name__)


class CursorEvaluateAgent(EvaluateAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    def evaluate(self, repo_path: Path, relevance_prompt: str) -> bool:
        repo_abs = str(repo_path.resolve())
        prompt = (
            "You are evaluating whether a repository is relevant to an objective.\n"
            f"Objective: {relevance_prompt}\n\n"
            "You may provide reasoning, but you MUST end your response with a clear final answer.\n"
            "Format your final answer as: **yes** or **no**\n"
            "The final answer should be on its own line or clearly marked with double asterisks."
        )

        output = self._runner.run_prompt(
            prompt,
            repo_abs=repo_abs,
            context_roots=[],
            include_repo_hint=True,
            remove=False,
            stream_partial_output=True,
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
