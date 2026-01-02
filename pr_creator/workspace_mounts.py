from __future__ import annotations

WORKSPACE_ROOT = "/workspace"
REPO_DIR = f"{WORKSPACE_ROOT}/repo"
CONTEXT_DIR = f"{WORKSPACE_ROOT}/context"


def workspace_prompt_prefix(
    *, include_repo_hint: bool, repo_dir: str | None, context_dirs: list[str]
) -> str:
    """
    Prefix instructions to help an agent locate the repo + optional context.
    """
    lines: list[str] = []
    if include_repo_hint:
        if not repo_dir:
            raise ValueError("repo_dir must be provided when include_repo_hint=True")
        lines.append(
            f"Target repository to edit is located at: {repo_dir}\n"
            f"Treat {repo_dir} as the repo root."
        )

    if context_dirs:
        first = context_dirs[0]
        rest_count = max(0, len(context_dirs) - 1)
        more = f" (and {rest_count} more)" if rest_count else ""
        lines.append(
            "Additional read-only context is available at:\n"
            f"- {first}{more}\n"
            "Use this for reference only; do not modify it. "
            "If your prompt contains any links to external code, always check this context "
            "for the most up-to-date code."
        )

    return ("\n\n".join(lines) + "\n\n") if lines else ""
