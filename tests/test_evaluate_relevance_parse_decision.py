from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pr_creator.workflows.orchestrator.evaluate_relevance_step.evaluate_agents.cursor_agent import (  # noqa: E402
    _parse_decision,
)


def test_parse_decision_ignores_prompt_echo_and_respects_final_no() -> None:
    output = """
Target repository to edit is located at: /tmp/repo
Treat /tmp/repo as the repo root.

You are evaluating whether a repository is relevant to an objective.
Objective: Something

You may provide reasoning, but you MUST end your response with a clear final answer.
Format your final answer as: **yes** or **no**
The final answer should be on its own line or clearly marked with double asterisks.

This repo is not relevant.

**no**
""".strip()
    assert _parse_decision(output) is False


def test_parse_decision_handles_marker_not_on_its_own_line() -> None:
    # Mirrors the shape seen in logs where the model emits "**no**This repo..."
    output = """
Format your final answer as: **yes** or **no**
This repo is a Spring Boot service and it IS using the base image.
**no**This repo is a Spring Boot service (it uses Spring Boot starters).

**no**
""".strip()
    assert _parse_decision(output) is False


def test_parse_decision_final_yes() -> None:
    output = "some reasoning\n\n**yes**\n"
    assert _parse_decision(output) is True
