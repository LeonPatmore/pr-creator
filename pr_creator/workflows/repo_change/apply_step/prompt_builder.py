from __future__ import annotations

from pr_creator.workflows.repo_change.ci_types import CiFailure


def build_change_prompt(
    *,
    repo_specific_prompt: str,
    base_prompt: str | None,
    ci_failures: list[CiFailure],
    review_feedback: str,
) -> str:
    """
    Build the final prompt for the change agent.

    Priority order (highest to lowest):
    1. CI failures (must fix immediately)
    2. Review feedback (must address)
    3. Repo-specific instructions (tailored by orchestrator)
    4. Original base request (context from pr-creator CLI)
    """

    sections: list[str] = []

    if ci_failures:
        # The apply step is responsible for formatting CI failures for the change agent.
        # Keep this concise and structured; detailed investigation should follow links/logs.
        failure_lines: list[str] = []
        for f in ci_failures:
            details = f.details_url or ""
            logs = (f.logs or "").strip()
            failure_lines.append(
                "\n".join(
                    [
                        f"### Failed check: {f.name}",
                        f"- pr_url: {f.pr_url}",
                        f"- head_sha: {f.head_sha}",
                        f"- details_url: {details}",
                        "#### Logs",
                        logs or "No logs available.",
                    ]
                )
            )
        ci_section = "\n\n".join(failure_lines).strip()
        sections.append(
            "## CRITICAL: Fix failing CI / GitHub Actions\n"
            "The PR is failing CI. Use the logs below to fix the issue.\n"
            "If there is a conflict, prioritize this section.\n\n"
            f"{ci_section}\n"
        )

    if review_feedback:
        sections.append(
            "## CRITICAL: Address review feedback\n"
            "Apply the following review feedback before doing anything else.\n"
            "If there is a conflict, prioritize this section.\n\n"
            f"{review_feedback}\n"
        )

    sections.append(f"{repo_specific_prompt.strip()}\n")

    if base_prompt and base_prompt.strip() != repo_specific_prompt.strip():
        sections.append(
            "---\n\n"
            "## Original base request (for context)\n"
            f"{base_prompt.strip()}\n"
        )

    return "\n\n".join(sections).rstrip()


def guard_change_agent_prompt(prompt: str) -> str:
    """
    Wrap a repo-specific change prompt with workflow-level constraints.

    This is intentionally owned by the repo-change workflow (not the change agent
    implementation) so the policy applies consistently across agent backends.
    """

    return (
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
        "This branch may already have changes compared to the base branch (e.g., main).\n"
        "These changes include:\n"
        "- Previously committed changes on this branch\n"
        "- Uncommitted/unstaged changes\n"
        "\n"
        "To see ALL changes on this branch vs the base, use: `git diff origin/main...HEAD`\n"
        "To see uncommitted changes only, use: `git status` and `git diff`\n"
        "\n"
        "When working with existing changes:\n"
        "- Treat them as YOUR OWN changes that you made previously\n"
        "- Do NOT revert or undo them unless they are incorrect\n"
        "- Redundant/unnecessary code comments are considered incorrect and MUST be removed\n"
        "- Build upon them or refine them as needed to complete the task\n"
        "- You may be iterating on previous work to address feedback or fix issues\n"
        "- Understand the full context by reviewing both committed and uncommitted changes\n"
        "\n"
        "If this branch already contains code comments (including previously committed comments),\n"
        "you MUST remove any that are not essential non-obvious information.\n"
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
        "# MINIMAL CHANGES - CRITICAL\n"
        "\n"
        "Do NOT make changes unless they are required.\n"
        "Do NOT make changes which are not relevant to the task.\n"
        "Keep changes minimal.\n"
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
        "Do NOT add code comments unless it is absolutely required.\n"
        "Treat adding a comment as a last resort.\n"
        "Prefer making the code self-explanatory (better names, smaller functions, clearer structure)\n"
        "instead of explaining it with comments.\n"
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
        "- Adding narrative/rationale comments about what you changed in this PR\n"
        "- Adding TODOs or notes unless explicitly requested\n"
        "\n"
        "# TASK\n"
        "\n" + (prompt or "")
    )


def build_guarded_change_prompt(
    *,
    repo_specific_prompt: str,
    base_prompt: str | None,
    ci_failures: list[CiFailure],
    review_feedback: str,
) -> str:
    return guard_change_agent_prompt(
        build_change_prompt(
            repo_specific_prompt=repo_specific_prompt,
            base_prompt=base_prompt,
            ci_failures=ci_failures,
            review_feedback=review_feedback,
        )
    )
