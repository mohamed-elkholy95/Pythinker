import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.services.llm.middleware import LLMRequest, LLMResponse
from app.infrastructure.external.llm.middleware_impl import CircuitBreakerMiddleware, RetryMiddleware


@pytest.mark.asyncio
async def test_retry_middleware_fails_fast_when_deadline_expired() -> None:
    middleware = RetryMiddleware()
    request = LLMRequest(
        messages=[{"role": "user", "content": "hello"}],
        metadata={"provider": "openai", "deadline_monotonic": time.monotonic() - 0.1},
    )
    next_handler = AsyncMock(return_value=LLMResponse(content="ok"))

    with pytest.raises(TimeoutError, match="deadline"):
        await middleware(request, next_handler)

    next_handler.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_middleware_uses_glm_specific_config() -> None:
    middleware = CircuitBreakerMiddleware()
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], metadata={"provider": "glm"})

    @asynccontextmanager
    async def _execute(**_kwargs):
        yield

    breaker = SimpleNamespace(execute=_execute)

    with (
        patch(
            "app.infrastructure.external.llm.middleware_impl.get_settings",
            return_value=SimpleNamespace(feature_llm_provider_fallback=True),
        ),
        patch("app.core.circuit_breaker_registry.CircuitBreakerRegistry.get_or_create", return_value=breaker) as get_cb,
    ):
        response = await middleware(request, AsyncMock(return_value=LLMResponse(content="ok")))

    assert response.content == "ok"
    assert get_cb.call_count == 1
    kwargs = get_cb.call_args.kwargs
    assert kwargs["name"] == "llm:glm"
    config = kwargs["config"]
    assert config.failure_threshold == 3
    assert config.recovery_timeout == 120
    assert config.sliding_window_size == 10
    assert config.failure_rate_threshold == 0.4
