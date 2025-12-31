from __future__ import annotations

import json
import logging

from pr_creator.cursor_utils.runner import run_cursor_prompt
from .base import NamingAgent

logger = logging.getLogger(__name__)


class CursorNamingAgent(NamingAgent):
    def generate_short_desc(self, prompt: str) -> str | None:
        instruction = (
            "You are generating a short description for a change prompt.\n"
            "- Produce a single JSON object ONLY, no extra text.\n"
            '- Shape: {"short_desc": "<kebab-case-phrase>"}\n'
            "- short_desc: 3-6 words, lowercase, kebab-case, no punctuation beyond hyphens."
        )
        full_prompt = f"{instruction}\n\nPrompt:\n{prompt}"
        try:
            output = run_cursor_prompt(
                full_prompt,
                remove=True,
                # For name generation we need the final JSON line, not streamed fragments.
                stream_partial_output=False,
            )
            logger.info("Name generation output: %s", output.strip())
            data = json.loads(output)
            return data.get("short_desc") or None
        except Exception as e:
            logger.warning("Name generation failed, returning None: %s", e)
            return None
