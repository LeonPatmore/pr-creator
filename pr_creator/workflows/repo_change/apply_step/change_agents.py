from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner

DEFAULT_AGENT = "cursor"


class ChangeAgent(ABC):
    @abstractmethod
    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        """Apply changes to the given repo."""
        raise NotImplementedError


class CursorChangeAgent(ChangeAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    def run(
        self,
        repo_path: Path,
        prompt: str,
        *,
        context_roots: list[str],
        secrets: dict[str, str] | None = None,
    ) -> None:
        repo_abs = str(repo_path.resolve())
        guarded_prompt = (
            "# YOUR ROLE\n"
            "\n"
            "Your ONLY job is to make the code changes requested in the task below.\n"
            "\n"
            "The workflow will automatically handle:\n"
            "- Committing changes\n"
            "- Pushing to remote\n"
            "- Creating pull requests\n"
            "\n"
            "# EXISTING CHANGES IN THIS BRANCH\n"
            "\n"
            "If there are already uncommitted or committed changes in the current branch:\n"
            "- Treat them as YOUR OWN changes that you made previously\n"
            "- Do NOT revert or undo them unless they are incorrect\n"
            "- Build upon them or refine them as needed to complete the task\n"
            "- You may be iterating on previous work to address feedback or fix issues\n"
            "\n"
            "# DOCUMENTATION FILES - CRITICAL CONSTRAINTS\n"
            "\n"
            "Do NOT create new documentation files (*.md, *.rst, *.txt docs, etc.) unless explicitly requested.\n"
            "\n"
            "Do NOT update existing documentation files unless the change is CRITICAL and directly required.\n"
            "\n"
            "Examples of UNJUSTIFIED documentation changes (do NOT make these):\n"
            "- Adding suggestions for how to rollout changes\n"
            "- Explaining reasoning or rationale for why code changes were made\n"
            "- Adding general usage examples or tutorials\n"
            "\n"
            "Examples of JUSTIFIED documentation changes (these are acceptable):\n"
            "- Updating an existing list of environment variables when you added/changed a variable\n"
            "- Updating an existing CLI flags table when you added/changed a flag\n"
            "- Fixing broken links or incorrect information that would mislead users\n"
            "- Updating version numbers or dependencies in existing documentation\n"
            "\n"
            "When in doubt: skip the documentation change. Code changes are your priority.\n"
            "\n"
            "# WHAT YOU MUST NOT DO\n"
            "\n"
            "Do NOT perform any of these actions:\n"
            "- Do NOT commit changes\n"
            "- Do NOT push to remote\n"
            "- Do NOT create pull requests\n"
            "- Do NOT stage changes with git add\n"
            "\n"
            "# CODE QUALITY CONSTRAINTS\n"
            "\n"
            "When making changes:\n"
            "- Do NOT change file line endings (do not convert LF<->CRLF)\n"
            "- Avoid whitespace-only changes\n"
            "- Only modify files that are necessary to satisfy the task\n"
            "\n"
            "# CODE COMMENTS - CRITICAL\n"
            "\n"
            "Do NOT add excessive comments. Only add code comments when they "
            "provide essential non-obvious information.\n"
            "\n"
            "Avoid redundant comments that simply restate what the code does.\n"
            "\n"
            "Good comments explain:\n"
            "- Why a non-obvious approach was chosen\n"
            "- Complex business logic or algorithms\n"
            "- Important gotchas or edge cases\n"
            "- References to external documentation or tickets\n"
            "\n"
            "Bad comments to avoid:\n"
            '- Restating obvious operations (e.g., "# Set the value to x")\n'
            "- Describing what can be clearly understood from well-named variables/functions\n"
            "- Commenting every single line or block\n"
            "\n"
            "# TASK\n"
            "\n" + (prompt or "")
        )
        self._runner.run_prompt(
            guarded_prompt,
            intent="change",
            remove=False,
            repo_abs=repo_abs,
            context_roots=context_roots,
            include_repo_hint=True,
            stream_partial_output=True,
            extra_env=secrets or {},
        )


def get_change_agent(name: str | None = None) -> ChangeAgent:
    agent_name = (name or os.environ.get("CHANGE_AGENT") or DEFAULT_AGENT).lower()
    if agent_name == "cursor":
        return CursorChangeAgent(get_cursor_runner())
    raise ValueError(f"Unknown change agent: {agent_name}")


__all__ = ["ChangeAgent", "CursorChangeAgent", "get_change_agent"]
