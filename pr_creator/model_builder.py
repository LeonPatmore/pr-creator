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


def build_model(
    model_name: str,
    *,
    log_prefix: str = "model",
    log: logging.Logger | None = None,
) -> str | OpenAIChatModel:
    """
    Resolve a pydantic-ai model name, optionally via a LiteLLM proxy.

    If LITELLM_API_BASE is set and LiteLLM support is available, return an
    OpenAIChatModel configured with LiteLLMProvider. Otherwise, return the raw model name.
    """
    log = log or logger

    api_base = os.environ.get("LITELLM_API_BASE")
    if not api_base:
        return model_name

    try:
        from pydantic_ai.providers.litellm import LiteLLMProvider

        api_key = os.environ.get("LITELLM_API_KEY")
        if not api_key:
            log.warning(
                "[%s] LITELLM_API_BASE is set but LITELLM_API_KEY is not set; "
                "falling back to direct model resolution",
                log_prefix,
            )
            return model_name

        litellm_model_name = to_litellm_model_name(model_name)
        log.info(
            "[%s] using LiteLLM provider with model %s at %s",
            log_prefix,
            litellm_model_name,
            api_base,
        )

        provider = LiteLLMProvider(api_base=api_base, api_key=api_key)
        return OpenAIChatModel(litellm_model_name, provider=provider)

    except ImportError:
        log.warning(
            "[%s] LiteLLM support not available; falling back to direct model resolution. "
            "Install with: pip install pydantic-ai[litellm]",
            log_prefix,
        )
        return model_name
    except Exception as e:
        log.warning(
            "[%s] failed to configure LiteLLM provider: %s; falling back to direct model resolution",
            log_prefix,
            e,
        )
        return model_name
