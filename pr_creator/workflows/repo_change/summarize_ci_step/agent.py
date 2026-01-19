from __future__ import annotations

import contextlib
import logging
import os

from pydantic import BaseModel
from pydantic_ai import Agent

from pr_creator.model_builder import build_model
from .system_prompt_builder import build_ci_summary_system_prompt

logger = logging.getLogger(__name__)


class CiSummaryResponse(BaseModel):
    summary: str


@contextlib.asynccontextmanager
async def build_ci_failure_summarizer():
    """
    Build an AI agent for CI failure summarization.

    This intentionally mirrors the orchestrator agent setup pattern (model resolution via
    LiteLLM when configured, otherwise direct model selection).
    """
    model_name = os.environ.get("CI_SUMMARY_MODEL", "openai:gpt-5.2")
    model = build_model(model_name, log_prefix="ci-summary", log=logger)
    system_prompt = build_ci_summary_system_prompt()

    agent: Agent = Agent(
        model=model,
        output_type=CiSummaryResponse,
        system_prompt=system_prompt,
    )

    async def summarize_one(failure_blob: str) -> str:
        result = await agent.run((failure_blob or "").strip())
        return (result.output.summary or "").strip()

    yield summarize_one
