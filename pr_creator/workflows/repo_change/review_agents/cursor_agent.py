from __future__ import annotations

import logging
from pathlib import Path

from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner

from .base import ReviewAgent


logger = logging.getLogger(__name__)


def _snippet(text: str, *, limit: int = 400) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "..."


def _parse_review_output(output: str) -> tuple[bool, str | None]:
    """
    Parse the Cursor review output using the prompt's output contract.

    Expected:
    - READY_TO_COMMIT
    - CHANGES_REQUIRED\\n<bullet list>
    """
    text = (output or "").strip()
    if not text:
        # Conservative: no signal means we should ask for changes rather than commit.
        logger.info("[review-agent] empty output -> needs_changes=True")
        return (
            True,
            "Review output was empty; please re-run review and provide required fixes.",
        )

    # Look at the first non-empty line as the "verdict".
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first = (lines[0] if lines else "").upper()
    logger.info(
        "[review-agent] parsed verdict=%r (first_line=%r)",
        first,
        lines[0] if lines else "",
    )

    if first == "READY_TO_COMMIT":
        logger.info("[review-agent] READY_TO_COMMIT -> needs_changes=False")
        return False, None

    if first.startswith("CHANGES_REQUIRED"):
        remainder = text.splitlines()[1:]
        feedback = "\n".join(remainder).strip() or None
        # If CHANGES_REQUIRED but no details, still treat as needs changes.
        logger.info(
            "[review-agent] CHANGES_REQUIRED -> needs_changes=True (feedback_present=%s, feedback_snippet=%r)",
            bool(feedback),
            _snippet(feedback or ""),
        )
        return True, feedback or "Changes required (no details provided)."

    # Unknown format: treat as needing changes, and forward raw output to ApplyChanges.
    logger.warning(
        "[review-agent] unknown output format -> needs_changes=True (output_snippet=%r)",
        _snippet(text),
    )
    return True, text


class CursorReviewAgent(ReviewAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    def review(
        self,
        repo_path: Path,
        *,
        context_roots: list[str],
        task_prompt: str | None = None,
        secrets: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        repo_abs = str(repo_path.resolve())
        task_section = ""
        if task_prompt and task_prompt.strip():
            task_section = (
                "\n"
                "Task instructions (source of truth):\n"
                "----\n"
                f"{task_prompt.strip()}\n"
                "----\n"
            )

        prompt = (
            "You are reviewing the current repository state BEFORE submitting a PR.\n"
            "Please inspect all uncommitted work (unstaged + staged + untracked).\n"
            "\n"
            "Important workflow context:\n"
            "- Do NOT require changes to be staged. The submit step will stage everything automatically.\n"
            "\n"
            "Review rules:\n"
            "- Treat the Task instructions (if provided below) as the source of truth.\n"
            "- Only require changes if they are necessary for correctness, security (no leaked secrets/tokens),\n"
            "  or to satisfy explicit requirements in the Task instructions.\n"
            "- Do not request stylistic refactors or generic best-practice changes unless explicitly required.\n"
            "- Example: flag unintended generated/build artifacts that got staged/committed (e.g. build outputs,\n"
            "  dependency directories, caches). Require reverting them and/or adding correct `.gitignore` rules.\n"
            f"{task_section}\n"
            "You may run any relevant commands (e.g. git status, git diff, tests) and read files.\n"
            "If changes are needed before submitting, list them clearly.\n"
            "\n"
            "IMPORTANT OUTPUT FORMAT (no extra text):\n"
            "- If the repo is ready, output exactly: READY_TO_COMMIT\n"
            "- Otherwise output exactly: CHANGES_REQUIRED\\n<bullet list of required changes>\n"
        )

        output = self._runner.run_prompt(
            prompt,
            repo_abs=repo_abs,
            context_roots=context_roots,
            include_repo_hint=True,
            remove=False,
            # For review we need the final verdict line; streaming can yield partials that
            # make parsing flaky (similar to naming agent behavior).
            stream_partial_output=False,
            extra_env=secrets or {},
        )
        logger.info(
            "[review-agent] raw_output_len=%s raw_output_snippet=%r",
            len(output or ""),
            _snippet(output or ""),
        )
        return _parse_review_output(output)
