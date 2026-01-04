from __future__ import annotations


def merge_base_prompt_with_cli_prompt(
    base_prompt: str,
    cli_prompt: str | None,
    *,
    base_origin: str,
) -> str:
    """
    Merge a loaded/base prompt (Jira or prompt-config) with an optional CLI prompt.

    Priority:
    - CLI prompt is highest priority instructions
    - base prompt is background/context
    """
    base = (base_prompt or "").strip()
    cli = (cli_prompt or "").strip()
    if not cli:
        return base_prompt
    return (
        "## Highest priority instructions (CLI)\n"
        f"{cli}\n\n"
        f"## Background / base prompt ({base_origin})\n"
        f"{base}\n"
    )
