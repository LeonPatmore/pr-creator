from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pr_creator.workflows.repo_change.review_step.cursor_agent import (  # noqa: E402
    _parse_review_output,
)


def test_parse_review_ready_to_commit_exact() -> None:
    assert _parse_review_output("READY_TO_COMMIT") == (False, None)


def test_parse_review_changes_required_with_feedback() -> None:
    needs_changes, feedback = _parse_review_output(
        "CHANGES_REQUIRED\n- fix the dockerfile\n- update workflow\n"
    )
    assert needs_changes is True
    assert feedback == "- fix the dockerfile\n- update workflow"


def test_parse_review_accepts_all_requirements_are_met() -> None:
    # Mirrors the shape seen in logs where the model approves but doesn't emit READY_TO_COMMIT.
    needs_changes, feedback = _parse_review_output(
        "All requirements are met:\n\n- Uses new base images\n- Multi-stage build\n"
    )
    assert needs_changes is False
    assert feedback is None


def test_parse_review_prefers_final_verdict_marker() -> None:
    output = """
IMPORTANT OUTPUT FORMAT (no extra text):
- If the repo is ready, output exactly: READY_TO_COMMIT
- Otherwise output exactly: CHANGES_REQUIRED\\n<bullet list of required changes>

Some reasoning...

CHANGES_REQUIRED
- do the required thing
""".strip()
    needs_changes, feedback = _parse_review_output(output)
    assert needs_changes is True
    assert feedback == "- do the required thing"
