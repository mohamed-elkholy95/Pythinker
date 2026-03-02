import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.exceptions.base import LLMException
from app.infrastructure.external.llm.openai_llm import OpenAILLM


def _build_llm() -> OpenAILLM:
    llm = OpenAILLM.__new__(OpenAILLM)
    llm._is_mlx_mode = False
    llm._is_glm_api = False
    llm._is_thinking_api = False
    llm._is_openrouter = False
    llm._is_deepseek = False
    llm._model_name = "gpt-4o-mini"
    llm._temperature = 0.1
    llm._max_tokens = 1000
    llm._api_base = "https://api.openai.com/v1"
    llm._cache_manager = None
    llm._supports_stream_usage = False
    llm._last_stream_metadata = None
    llm._slow_tool_call_streak = 0
    llm._slow_tool_call_breaker_until = 0.0
    llm._record_usage = AsyncMock()
    return llm


@pytest.mark.asyncio
async def test_ask_caps_max_tokens_for_tool_calls() -> None:
    llm = _build_llm()

    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message = MagicMock()
    completion.choices[0].message.model_dump = MagicMock(return_value={"role": "assistant", "content": "ok"})
    completion.choices[0].finish_reason = "stop"
    completion.usage = None
    completion.model_dump = MagicMock(return_value={})

    client = AsyncMock()
    client.chat = AsyncMock()
    client.chat.completions = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    llm._get_client = AsyncMock(return_value=client)

    messages = [{"role": "user", "content": "use a tool"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search web",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    with patch(
        "app.infrastructure.external.llm.openai_llm.get_settings",
        return_value=SimpleNamespace(llm_tool_max_tokens=128, llm_slow_request_threshold=30.0),
    ):
        await llm.ask(messages=messages, tools=tools)

    create_kwargs = client.chat.completions.create.await_args.kwargs
    assert create_kwargs["max_tokens"] == 128


@pytest.mark.asyncio
async def test_ask_times_out_slow_tool_calls_with_guardrail() -> None:
    llm = _build_llm()

    async def _slow_create(**_kwargs):
        await asyncio.sleep(0.05)
        return MagicMock()

    client = AsyncMock()
    client.chat = AsyncMock()
    client.chat.completions = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=_slow_create)
    llm._get_client = AsyncMock(return_value=client)

    messages = [{"role": "user", "content": "use a tool"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search web",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    with (
        patch(
            "app.infrastructure.external.llm.openai_llm.get_settings",
            return_value=SimpleNamespace(
                llm_tool_max_tokens=128,
                llm_tool_request_timeout=0.01,
                llm_tool_timeout_max_retries=0,
                fast_model="",
                llm_slow_request_threshold=30.0,
            ),
        ),
        pytest.raises(LLMException, match="timed out"),
    ):
        await llm.ask(messages=messages, tools=tools)


@pytest.mark.asyncio
async def test_ask_tool_timeout_retries_increase_timeout_budget_with_backoff() -> None:
    llm = _build_llm()

    client = AsyncMock()
    client.chat = AsyncMock()
    client.chat.completions = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=MagicMock())
    llm._get_client = AsyncMock(return_value=client)

    messages = [{"role": "user", "content": "use a tool"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search web",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    seen_timeouts: list[float] = []

    async def _timeout_wait_for(awaitable, *args, **kwargs):
        timeout_seconds = kwargs.get("timeout")
        if timeout_seconds is None and args:
            timeout_seconds = args[0]
        seen_timeouts.append(float(timeout_seconds))
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError("timed out")

    with (
        patch(
            "app.infrastructure.external.llm.openai_llm.get_settings",
            return_value=SimpleNamespace(
                llm_tool_max_tokens=128,
                llm_tool_request_timeout=0.01,
                llm_tool_timeout_max_retries=1,
                llm_request_timeout=1.0,
                fast_model="",
                llm_slow_request_threshold=30.0,
            ),
        ),
        patch("app.infrastructure.external.llm.openai_llm.asyncio.wait_for", side_effect=_timeout_wait_for),
        pytest.raises(LLMException, match="timed out"),
    ):
        await llm.ask(messages=messages, tools=tools)

    assert seen_timeouts == [0.01, 0.02]
