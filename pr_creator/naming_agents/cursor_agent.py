from __future__ import annotations

import json
import logging

from pr_creator.cursor_utils.runner import run_cursor_prompt
from .base import NamingAgent

logger = logging.getLogger(__name__)


class CursorNamingAgent(NamingAgent):
    def generate_short_desc(self, prompt: str) -> str:
        instruction = (
            "You are generating a short description for a change prompt.\n"
            "- Produce a single JSON object ONLY, no extra text.\n"
            '- Shape: {"short_desc": "<kebab-case-phrase>"}\n'
            "- short_desc: 6-10 words, lowercase, kebab-case, no punctuation beyond hyphens."
        )
        full_prompt = f"{instruction}\n\nPrompt:\n{prompt}"
        try:
            output = run_cursor_prompt(full_prompt, remove=True)
            logger.info("Name generation output: %s", output.strip())
            data = json.loads(output)
            return data.get("short_desc") or "auto-change"
        except Exception as e:
            logger.warning("Name generation failed, using fallback: %s", e)
            return "auto-change"
