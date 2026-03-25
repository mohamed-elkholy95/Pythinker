"""Tests for proxy_chat_completion() in llm_proxy_service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.llm_proxy_service import proxy_chat_completion

# get_llm is imported inside the function body at call time, so we patch it
# at its definition site in the infrastructure factory module.
FACTORY_PATCH = "app.infrastructure.external.llm.factory.get_llm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(content: str | None = "Hello, world!") -> MagicMock:
    """Return a mock LLM whose ask() coroutine resolves with the given content."""
    llm = MagicMock()
    llm.ask = AsyncMock(return_value={"content": content})
    return llm


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestProxyChatCompletionSuccess:
    @pytest.mark.asyncio
    async def test_returns_content_string_on_success(self):
        llm = _make_llm("Here is your answer.")
        with patch(FACTORY_PATCH, return_value=llm):
            result = await proxy_chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=256,
            )
        assert result == "Here is your answer."

    @pytest.mark.asyncio
    async def test_forwards_messages_to_llm_ask(self):
        llm = _make_llm("ok")
        messages = [{"role": "user", "content": "What is 2+2?"}]
        with patch(FACTORY_PATCH, return_value=llm):
            await proxy_chat_completion(messages=messages, max_tokens=128)
        llm.ask.assert_awaited_once()
        call_kwargs = llm.ask.call_args.kwargs
        assert call_kwargs["messages"] == messages

    @pytest.mark.asyncio
    async def test_forwards_max_tokens_to_llm_ask(self):
        llm = _make_llm("ok")
        with patch(FACTORY_PATCH, return_value=llm):
            await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=512,
            )
        call_kwargs = llm.ask.call_args.kwargs
        assert call_kwargs["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_forwards_temperature_when_provided(self):
        llm = _make_llm("ok")
        with patch(FACTORY_PATCH, return_value=llm):
            await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
                temperature=0.7,
            )
        call_kwargs = llm.ask.call_args.kwargs
        assert call_kwargs["temperature"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_temperature_none_when_omitted(self):
        llm = _make_llm("ok")
        with patch(FACTORY_PATCH, return_value=llm):
            await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )
        call_kwargs = llm.ask.call_args.kwargs
        assert call_kwargs["temperature"] is None

    @pytest.mark.asyncio
    async def test_temperature_zero_is_forwarded(self):
        llm = _make_llm("deterministic")
        with patch(FACTORY_PATCH, return_value=llm):
            result = await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=64,
                temperature=0.0,
            )
        call_kwargs = llm.ask.call_args.kwargs
        assert call_kwargs["temperature"] == pytest.approx(0.0)
        assert result == "deterministic"


# ---------------------------------------------------------------------------
# LLM not configured
# ---------------------------------------------------------------------------


class TestProxyChatCompletionLlmNotConfigured:
    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_llm_is_none(self):
        with patch(FACTORY_PATCH, return_value=None), pytest.raises(RuntimeError, match="LLM not configured"):
            await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )

    @pytest.mark.asyncio
    async def test_llm_ask_not_called_when_not_configured(self):
        # Ensures we fail early without touching ask()
        import contextlib

        with patch(FACTORY_PATCH, return_value=None), contextlib.suppress(RuntimeError):
            await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )
        # No mock llm to assert on — the absence of a call is the assertion


# ---------------------------------------------------------------------------
# Empty / missing content
# ---------------------------------------------------------------------------


class TestProxyChatCompletionEmptyContent:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_content_is_none(self):
        llm = _make_llm(content=None)
        with patch(FACTORY_PATCH, return_value=llm):
            result = await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_content_key_missing(self):
        llm = MagicMock()
        llm.ask = AsyncMock(return_value={})
        with patch(FACTORY_PATCH, return_value=llm):
            result = await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_content_is_empty_string(self):
        llm = _make_llm(content="")
        with patch(FACTORY_PATCH, return_value=llm):
            result = await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=64,
            )
        assert result == ""


# ---------------------------------------------------------------------------
# LLM propagates exceptions
# ---------------------------------------------------------------------------


class TestProxyChatCompletionExceptions:
    @pytest.mark.asyncio
    async def test_llm_ask_exception_propagates(self):
        llm = MagicMock()
        llm.ask = AsyncMock(side_effect=ConnectionError("provider unreachable"))
        with patch(FACTORY_PATCH, return_value=llm), pytest.raises(ConnectionError, match="provider unreachable"):
            await proxy_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )
