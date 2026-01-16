from __future__ import annotations

import logging
import os

from pydantic_ai.models.openai import OpenAIChatModel

logger = logging.getLogger(__name__)


def to_litellm_model_name(model_name: str) -> str:
    if ":" not in model_name:
        return model_name

    provider, model = model_name.split(":", 1)
    return f"{provider}/{model}"


def build_model(model_name: str) -> str | OpenAIChatModel:
    api_base = os.environ.get("LITELLM_API_BASE")

    if not api_base:
        return model_name

    try:
        from pydantic_ai.providers.litellm import LiteLLMProvider

        api_key = os.environ.get("LITELLM_API_KEY")

        if not api_key:
            logger.warning(
                "[orchestrator] LITELLM_API_BASE is set but LITELLM_API_KEY "
                "is not set; falling back to direct model resolution"
            )
            return model_name

        litellm_model_name = to_litellm_model_name(model_name)

        logger.info(
            "[orchestrator] using LiteLLM provider with model %s at %s",
            litellm_model_name,
            api_base,
        )

        provider = LiteLLMProvider(api_base=api_base, api_key=api_key)
        return OpenAIChatModel(litellm_model_name, provider=provider)

    except ImportError:
        logger.warning(
            "[orchestrator] LiteLLM support not available; "
            "falling back to direct model resolution. "
            "Install with: pip install pydantic-ai[litellm]"
        )
        return model_name
    except Exception as e:
        logger.warning(
            "[orchestrator] failed to configure LiteLLM provider: %s; "
            "falling back to direct model resolution",
            e,
        )
        return model_name
