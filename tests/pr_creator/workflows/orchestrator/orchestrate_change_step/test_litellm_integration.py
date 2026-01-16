import os
from unittest.mock import MagicMock, patch

import pytest

from pr_creator.workflows.orchestrator.orchestrate_change_step.agent import (
    build_orchestrate_change_agent,
)
from pr_creator.workflows.orchestrator.orchestrate_change_step.model_builder import (
    build_model,
)
from pydantic_ai.models.openai import OpenAIChatModel


def test_build_model_without_litellm():
    with patch.dict(os.environ, {}, clear=True):
        model = build_model("openai:gpt-5.2")
        assert model == "openai:gpt-5.2"
        assert isinstance(model, str)


def test_build_model_with_litellm_missing_api_key(caplog):
    with patch.dict(
        os.environ,
        {
            "LITELLM_API_BASE": "http://localhost:4000",
        },
        clear=True,
    ):
        model = build_model("openai:gpt-5.2")
        assert model == "openai:gpt-5.2"
        assert isinstance(model, str)
        assert "LITELLM_API_KEY is not set" in caplog.text


def test_build_model_with_litellm_configured(caplog):
    mock_provider = MagicMock()
    mock_litellm_provider_class = MagicMock(return_value=mock_provider)

    with (
        patch.dict(
            os.environ,
            {
                "LITELLM_API_BASE": "http://localhost:4000",
                "LITELLM_API_KEY": "test-key",
            },
            clear=True,
        ),
        patch(
            "pydantic_ai.providers.litellm.LiteLLMProvider",
            mock_litellm_provider_class,
        ),
        caplog.at_level(
            "INFO",
            logger="pr_creator.workflows.orchestrator.orchestrate_change_step.model_builder",
        ),
    ):
        model = build_model("openai:gpt-5.2")
        assert isinstance(model, OpenAIChatModel)
        assert "using LiteLLM provider with model openai/gpt-5.2" in caplog.text


def test_build_model_transforms_model_name_for_litellm():
    mock_provider = MagicMock()
    mock_litellm_provider_class = MagicMock(return_value=mock_provider)

    with (
        patch.dict(
            os.environ,
            {
                "LITELLM_API_BASE": "http://localhost:4000",
                "LITELLM_API_KEY": "test-key",
            },
            clear=True,
        ),
        patch(
            "pydantic_ai.providers.litellm.LiteLLMProvider",
            mock_litellm_provider_class,
        ),
    ):
        test_cases = [
            ("openai:gpt-5.2", "openai/gpt-5.2"),
            (
                "anthropic:claude-3-5-sonnet-20241022",
                "anthropic/claude-3-5-sonnet-20241022",
            ),
            ("azure:gpt-4", "azure/gpt-4"),
        ]

        for input_name, expected_litellm_name in test_cases:
            model = build_model(input_name)
            assert isinstance(model, OpenAIChatModel)


def test_build_model_with_litellm_import_error(caplog):
    import sys

    with (
        patch.dict(
            os.environ,
            {
                "LITELLM_API_BASE": "http://localhost:4000",
                "LITELLM_API_KEY": "test-key",
            },
            clear=True,
        ),
        patch.dict(
            sys.modules,
            {"pydantic_ai.providers.litellm": None},
        ),
    ):
        model = build_model("openai:gpt-5.2")
        assert model == "openai:gpt-5.2"
        assert isinstance(model, str)
        assert "LiteLLM support not available" in caplog.text


@pytest.mark.anyio
async def test_build_orchestrate_change_agent_with_litellm():
    async def mock_repo_change_tool(repo_url: str, prompt: str):
        pass

    mock_provider = MagicMock()
    mock_litellm_provider_class = MagicMock(return_value=mock_provider)

    with (
        patch.dict(
            os.environ,
            {
                "ORCHESTRATOR_MODEL": "openai:gpt-5.2",
                "LITELLM_API_BASE": "http://localhost:4000",
                "LITELLM_API_KEY": "test-key",
            },
            clear=True,
        ),
        patch(
            "pydantic_ai.providers.litellm.LiteLLMProvider",
            mock_litellm_provider_class,
        ),
    ):
        async with build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change_tool
        ) as (agent, tool_called):
            assert agent is not None
            assert tool_called == {"called": False}


@pytest.mark.anyio
async def test_build_orchestrate_change_agent_without_litellm():
    async def mock_repo_change_tool(repo_url: str, prompt: str):
        pass

    with (
        patch.dict(
            os.environ,
            {"ORCHESTRATOR_MODEL": "openai:gpt-5.2"},
            clear=True,
        ),
        patch("pydantic_ai.providers.openai.OpenAIProvider"),
    ):
        async with build_orchestrate_change_agent(
            repo_change_tool=mock_repo_change_tool
        ) as (agent, tool_called):
            assert agent is not None
            assert tool_called == {"called": False}
