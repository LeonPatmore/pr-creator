from __future__ import annotations

import contextlib
import logging
import os

from pydantic import BaseModel
from pydantic_ai import Agent

from pr_creator.model_builder import build_model
from .system_prompt_builder import build_naming_system_prompt

logger = logging.getLogger(__name__)


class NamingResponse(BaseModel):
    short_desc: str


@contextlib.asynccontextmanager
async def build_naming_agent():
    """
    Build an AI agent for generating short descriptions.

    This mirrors the orchestrator agent setup pattern (model resolution via
    LiteLLM when configured, otherwise direct model selection).
    """
    model_name = os.environ.get("NAMING_MODEL", "openai:gpt-5.2")
    model = build_model(model_name, log_prefix="naming", log=logger)
    system_prompt = build_naming_system_prompt()

    agent: Agent = Agent(
        model=model,
        output_type=NamingResponse,
        system_prompt=system_prompt,
    )

    async def generate_short_desc(prompt: str) -> str | None:
        try:
            result = await agent.run((prompt or "").strip())
            return (result.output.short_desc or "").strip()
        except Exception as e:
            logger.warning("Name generation failed: %s", e)
            return None

    yield generate_short_desc
