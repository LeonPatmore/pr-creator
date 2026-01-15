from __future__ import annotations

import json
import logging
import re

from pr_creator.cursor_utils.runners import CursorRunner, get_cursor_runner

from .base import NamingAgent

logger = logging.getLogger(__name__)


def _strip_markdown_code_fences(text: str) -> str:
    """
    Strip markdown code fences (```json ... ```) from LLM output before parsing JSON.

    Handles:
    - ```json\n{...}\n``` anywhere in the text
    - ```\n{...}\n``` anywhere in the text
    - Prioritizes the last code block if multiple exist
    - Returns the content between fences if present, otherwise returns original text.
    """
    stripped = text.strip()
    # Find all code blocks with optional language tags
    # Pattern matches: ```json (or ```jsonc or just ```) followed by content then ```
    pattern = r"```(?:json|jsonc)?\s*\n(.*?)\n```"
    matches = list(re.finditer(pattern, stripped, re.DOTALL))

    if matches:
        # Use the last match (most likely to be the actual answer)
        return matches[-1].group(1).strip()

    return stripped


class CursorNamingAgent(NamingAgent):
    def __init__(self, runner: CursorRunner | None = None) -> None:
        self._runner = runner or get_cursor_runner()

    async def generate_short_desc(self, prompt: str) -> str | None:
        instruction = (
            "You are generating a short description for a change prompt.\n"
            "- Produce a single JSON object ONLY, no extra text.\n"
            '- Shape: {"short_desc": "<kebab-case-phrase>"}\n'
            "- short_desc: 3-6 words, lowercase, kebab-case, no punctuation beyond hyphens."
        )
        full_prompt = f"{instruction}\n\nPrompt:\n{prompt}"
        try:
            output = await self._runner.run_prompt(
                full_prompt,
                intent="naming",
                repo_abs=None,
                context_roots=[],
                include_repo_hint=False,
                remove=True,
                # For name generation we need the final JSON line, not streamed fragments.
                stream_partial_output=False,
            )
            logger.info("Name generation output: %s", output.strip())
            # Strip markdown code fences if present (LLM sometimes adds ```json ... ```)
            cleaned_output = _strip_markdown_code_fences(output)
            data = json.loads(cleaned_output)
            return data.get("short_desc") or None
        except Exception as e:
            logger.warning("Name generation failed, returning None: %s", e)
            return None
