from __future__ import annotations


def build_orchestrator_user_prompt(*, repo_url: str | None, base_prompt: str) -> str:
    if repo_url:
        return (
            f"This change prompt applies to the following repo: {repo_url}\n\n"
            f"Base request:\n{base_prompt.strip()}\n"
        )

    return (
        "Target repo is not defined, you should discover it with any available tools or context. "
        "For example, you can use github tools to search for the relevant repository.\n\n"
        f"Base request:\n{base_prompt.strip()}\n"
    )
