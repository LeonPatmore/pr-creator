from __future__ import annotations

import logging
import re
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

    # Cursor sometimes violates the strict output contract (e.g. starts with
    # "All requirements are met:"), so we parse from the end backwards and
    # prioritize explicit verdict markers if present.
    #
    # This mirrors our evaluate-agent parsing strategy (_parse_decision).
    raw_lines = [ln.strip() for ln in text.splitlines()]
    non_empty = [ln for ln in raw_lines if ln]

    # 1) Prefer explicit markers, scanning from the end backwards.
    for i in range(len(raw_lines) - 1, -1, -1):
        ln = raw_lines[i]
        if not ln:
            continue
        upper = ln.upper()
        if upper == "READY_TO_COMMIT":
            logger.info("[review-agent] parsed verdict=%r (line=%r)", upper, ln)
            logger.info("[review-agent] READY_TO_COMMIT -> needs_changes=False")
            return False, None
        if upper.startswith("CHANGES_REQUIRED"):
            feedback = "\n".join(raw_lines[i + 1 :]).strip() or None
            logger.info(
                "[review-agent] parsed verdict=%r (line=%r)", "CHANGES_REQUIRED", ln
            )
            # If CHANGES_REQUIRED but no details, still treat as needs changes.
            logger.info(
                "[review-agent] CHANGES_REQUIRED -> needs_changes=True (feedback_present=%s, feedback_snippet=%r)",
                bool(feedback),
                _snippet(feedback or ""),
            )
            return True, feedback or "Changes required (no details provided)."

    # 2) No explicit markers: accept common approval phrasing as READY_TO_COMMIT.
    #
    # We keep this intentionally narrow to avoid false positives.
    text_upper = text.upper()
    approval_phrases = [
        r"\bALL REQUIREMENTS ARE MET\b",
        r"\bREPOSITORY IS READY TO COMMIT\b",
        r"\bREPO IS READY TO COMMIT\b",
        r"\bNO CHANGES REQUIRED\b",
        r"\bNO CHANGES NEEDED\b",
    ]
    for pat in approval_phrases:
        if re.search(pat, text_upper):
            logger.info(
                "[review-agent] parsed verdict=%r (phrase=%r)", "READY_TO_COMMIT", pat
            )
            return False, None

    # 3) If the agent says "changes required" but didn't use the marker, treat as needing changes.
    # This is still conservative because the unknown-format fallback will request changes anyway.
    if re.search(r"\bCHANGES REQUIRED\b", text_upper) or re.search(
        r"\bNEEDS CHANGES\b", text_upper
    ):
        logger.info(
            "[review-agent] parsed verdict=%r (phrase=%r)",
            "CHANGES_REQUIRED",
            "CHANGES REQUIRED/NEEDS CHANGES",
        )
        return True, text

    # Unknown format: treat as needing changes, and forward raw output to ApplyChanges.
    logger.warning(
        "[review-agent] unknown output format -> needs_changes=True (output_snippet=%r)",
        _snippet("\n".join(non_empty) if non_empty else text),
    )
    return True, "\n".join(non_empty) if non_empty else text


class CursorReviewAgent(ReviewAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    async def review(
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
            "\n"
            "# WHAT TO REVIEW\n"
            "\n"
            "Review ALL changes on this branch compared to the base branch (typically main).\n"
            "This includes:\n"
            "1. Previously committed changes on this branch\n"
            "2. Currently uncommitted changes (staged + unstaged + untracked)\n"
            "\n"
            "To see the full diff of what will be in the PR, use:\n"
            "- `git diff origin/main...HEAD` (all committed changes on branch)\n"
            "- `git status` and `git diff` (uncommitted changes)\n"
            "- Or combine both views to understand the complete changeset\n"
            "\n"
            "Important workflow context:\n"
            "- Do NOT require changes to be staged. The submit step will stage everything automatically.\n"
            "- Consider the ENTIRE changeset that will be included in the PR, not just uncommitted files.\n"
            "\n"
            "Review rules:\n"
            "- Treat the Task instructions (if provided below) as the source of truth.\n"
            "- Only require changes if they are necessary for correctness, security (no leaked secrets/tokens),\n"
            "  or to satisfy explicit requirements in the Task instructions.\n"
            "- Do not request stylistic refactors or generic best-practice changes unless explicitly required.\n"
            "- Example: flag unintended generated/build artifacts that got staged/committed (e.g. build outputs,\n"
            "  dependency directories, caches). Require reverting them and/or adding correct `.gitignore` rules.\n"
            f"{task_section}\n"
            "You may run any relevant commands (e.g. git status, git diff, git log, tests) and read files.\n"
            "If changes are needed before submitting, list them clearly.\n"
            "\n"
            "IMPORTANT OUTPUT FORMAT (no extra text):\n"
            "- If the repo is ready, output exactly: READY_TO_COMMIT\n"
            "- Otherwise output exactly: CHANGES_REQUIRED\\n<bullet list of required changes>\n"
        )

        output = await self._runner.run_prompt(
            prompt,
            intent="review",
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
