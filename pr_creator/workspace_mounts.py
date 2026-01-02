from __future__ import annotations

from pathlib import Path
from typing import Any

WORKSPACE_ROOT = "/workspace"
REPO_DIR = f"{WORKSPACE_ROOT}/repo"
CONTEXT_DIR = f"{WORKSPACE_ROOT}/context"


def build_workspace_volumes(
    repo_abs: str | None, *, context_roots: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Build docker-py `volumes` mapping for an agent container.

    We mount the *target repo* at /workspace/repo (rw) and any extra context roots
    at /workspace/context/<n> (ro). This avoids staging untracked context files
    into the target repo during submit.
    """
    volumes: dict[str, dict[str, Any]] = {}

    if repo_abs:
        volumes[repo_abs] = {"bind": REPO_DIR, "mode": "rw"}

    for idx, root in enumerate(context_roots):
        try:
            root_abs = str(Path(root).expanduser().resolve())
        except Exception:
            root_abs = root
        volumes[root_abs] = {"bind": f"{CONTEXT_DIR}/{idx}", "mode": "ro"}

    return volumes


def workspace_prompt_prefix(
    *, include_repo_hint: bool, context_roots: list[str]
) -> str:
    """
    Prefix instructions to help an agent locate the repo + optional context.
    """
    lines: list[str] = []
    if include_repo_hint:
        lines.append(
            f"Target repository to edit is located at: {REPO_DIR}\n"
            f"Treat {REPO_DIR} as the repo root."
        )

    if context_roots:
        lines.append(
            "Additional read-only context is available at:\n"
            f"- {CONTEXT_DIR}/0 (and higher indexes)\n"
            "Use this for reference only; do not modify it. "
            "If your prompt contains any links to external code, always check this context "
            "for the most up-to-date code."
        )

    return ("\n\n".join(lines) + "\n\n") if lines else ""
