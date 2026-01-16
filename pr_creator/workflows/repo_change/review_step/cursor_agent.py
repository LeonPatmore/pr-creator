from __future__ import annotations

import logging
import re
from pathlib import Path

from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner

from .base import ReviewAgent
from .prompt_builder import build_review_prompt

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
        prompt = build_review_prompt(task_prompt=task_prompt)

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
