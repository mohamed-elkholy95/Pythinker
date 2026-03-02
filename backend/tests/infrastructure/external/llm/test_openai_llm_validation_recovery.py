"""Tests for OpenAILLM message-validation recovery paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.llm.openai_llm import OpenAILLM


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content

    def model_dump(self) -> dict[str, str]:
        return {"role": "assistant", "content": self.content}


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = None

    def model_dump(self) -> dict[str, str]:
        return {"ok": "true"}


class _FakeDelta:
    def __init__(self, content: str | None):
        self.content = content
        self.tool_calls = None


class _FakeChunkChoice:
    def __init__(self, content: str | None, finish_reason: str | None = None):
        self.delta = _FakeDelta(content)
        self.finish_reason = finish_reason


class _FakeStreamChunk:
    def __init__(self, content: str | None, finish_reason: str | None = None):
        self.choices = [_FakeChunkChoice(content, finish_reason)]
        self.usage = None


class _FakeStream:
    def __init__(self, chunks: list[_FakeStreamChunk]):
        self._chunks = chunks

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _build_llm() -> OpenAILLM:
    llm = OpenAILLM.__new__(OpenAILLM)
    llm._is_thinking_api = False
    llm._is_mlx_mode = False
    llm._model_name = "gpt-4o-mini"
    llm._temperature = 0.0
    llm._max_tokens = 256
    llm._api_base = "https://provider.example/v1"
    llm._supports_stream_usage = False
    llm._cache_manager = None
    llm._last_stream_metadata = None
    llm._slow_tool_call_streak = 0
    llm._slow_tool_call_breaker_until = 0.0
    llm._slow_breaker_missing_fast_model_warned = False
    llm._slow_breaker_invalid_fast_model_warned = False
    llm._record_usage = AsyncMock()
    llm._record_stream_usage = AsyncMock()
    llm._record_usage_counts = AsyncMock()
    return llm


@pytest.mark.asyncio
async def test_ask_retries_with_validation_recovery_payload() -> None:
    llm = _build_llm()
    create_mock = AsyncMock(
        side_effect=[
            Exception("Error code: 400 - {'error': {'code': '1214', 'message': 'The messages parameter is illegal.'}}"),
            _FakeResponse("Recovered response"),
        ]
    )
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))

    result = await llm.ask(
        [
            {"role": "developer", "content": None},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "search", "content": ""},
        ],
        enable_caching=False,
    )

    assert result["content"] == "Recovered response"
    assert create_mock.await_count == 2
    retry_messages = create_mock.await_args_list[1].kwargs["messages"]
    assert all(message["role"] != "tool" for message in retry_messages)
    assert all(isinstance(message.get("content"), str) and message.get("content") for message in retry_messages)


@pytest.mark.asyncio
async def test_ask_stream_retries_with_validation_recovery_payload() -> None:
    llm = _build_llm()
    stream = _FakeStream(
        [
            _FakeStreamChunk("hello "),
            _FakeStreamChunk("world"),
            _FakeStreamChunk(None, finish_reason="stop"),
        ]
    )
    create_mock = AsyncMock(
        side_effect=[
            Exception("Error code: 400 - {'error': {'code': '1214', 'message': 'The messages parameter is illegal.'}}"),
            stream,
        ]
    )
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))

    chunks = [
        chunk
        async for chunk in llm.ask_stream(
            [
                {"role": "system", "content": ""},
                {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            ],
            enable_caching=False,
        )
    ]

    assert "".join(chunks) == "hello world"
    assert create_mock.await_count == 2
    retry_messages = create_mock.await_args_list[1].kwargs["messages"]
    assert all(isinstance(message.get("content"), str) and message.get("content") for message in retry_messages)
    assert llm.last_stream_metadata == {
        "finish_reason": "stop",
        "truncated": False,
        "provider": "openai",
    }
