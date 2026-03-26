"""Tests for the retry framework (app.core.retry).

Covers RetryConfig, calculate_delay, is_retryable, with_retry decorator,
pre-configured decorators, and provider-specific configs.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.retry import (
    PROVIDER_RETRY_CONFIGS,
    TRANSIENT_EXCEPTIONS,
    RetryConfig,
    RetryStats,
    calculate_delay,
    is_retryable,
    with_retry,
)


# ── RetryConfig defaults ─────────────────────────────────────────────


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.jitter_factor == 0.25
        assert config.retryable_exceptions == (Exception,)
        assert config.non_retryable_exceptions == ()
        assert config.on_retry is None
        assert config.log_retries is True

    def test_custom_values(self) -> None:
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
            jitter=False,
            jitter_factor=0.5,
            retryable_exceptions=(TimeoutError,),
            non_retryable_exceptions=(ValueError,),
            log_retries=False,
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
        assert config.jitter is False
        assert config.jitter_factor == 0.5
        assert config.retryable_exceptions == (TimeoutError,)
        assert config.non_retryable_exceptions == (ValueError,)
        assert config.log_retries is False

    def test_on_retry_callback(self) -> None:
        cb = MagicMock()
        config = RetryConfig(on_retry=cb)
        assert config.on_retry is cb


class TestRetryStats:
    """Tests for RetryStats dataclass."""

    def test_default_values(self) -> None:
        stats = RetryStats()
        assert stats.attempts == 0
        assert stats.total_delay == 0.0
        assert stats.success is False
        assert stats.final_exception is None
        assert stats.duration_ms == 0.0


# ── calculate_delay ──────────────────────────────────────────────────


class TestCalculateDelay:
    """Tests for calculate_delay function."""

    def test_first_attempt_returns_base_delay(self) -> None:
        config = RetryConfig(base_delay=1.0, jitter=False)
        delay = calculate_delay(1, config)
        assert delay == 1.0

    def test_exponential_backoff(self) -> None:
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False, max_delay=1000.0)
        assert calculate_delay(1, config) == 1.0
        assert calculate_delay(2, config) == 2.0
        assert calculate_delay(3, config) == 4.0
        assert calculate_delay(4, config) == 8.0
        assert calculate_delay(5, config) == 16.0

    def test_max_delay_cap(self) -> None:
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False, max_delay=5.0)
        assert calculate_delay(1, config) == 1.0
        assert calculate_delay(2, config) == 2.0
        assert calculate_delay(3, config) == 4.0
        assert calculate_delay(4, config) == 5.0  # capped
        assert calculate_delay(10, config) == 5.0  # still capped

    def test_jitter_adds_variance(self) -> None:
        config = RetryConfig(base_delay=10.0, jitter=True, jitter_factor=0.25, max_delay=1000.0)
        delays = [calculate_delay(1, config) for _ in range(100)]
        assert min(delays) < 10.0  # some below base
        assert max(delays) > 10.0  # some above base
        # All within jitter range: 10 ± 2.5
        for d in delays:
            assert 0.1 <= d <= 12.5 + 0.01

    def test_jitter_ensures_positive_delay(self) -> None:
        config = RetryConfig(base_delay=0.1, jitter=True, jitter_factor=0.99, max_delay=1000.0)
        for _ in range(50):
            delay = calculate_delay(1, config)
            assert delay >= 0.1

    def test_custom_exponential_base(self) -> None:
        config = RetryConfig(base_delay=1.0, exponential_base=3.0, jitter=False, max_delay=1000.0)
        assert calculate_delay(1, config) == 1.0
        assert calculate_delay(2, config) == 3.0
        assert calculate_delay(3, config) == 9.0


# ── is_retryable ─────────────────────────────────────────────────────


class TestIsRetryable:
    """Tests for is_retryable function."""

    def test_retryable_exception(self) -> None:
        config = RetryConfig(retryable_exceptions=(TimeoutError, ConnectionError))
        assert is_retryable(TimeoutError(), config) is True
        assert is_retryable(ConnectionError(), config) is True

    def test_non_retryable_exception(self) -> None:
        config = RetryConfig(retryable_exceptions=(TimeoutError,))
        assert is_retryable(ValueError(), config) is False

    def test_non_retryable_takes_precedence(self) -> None:
        config = RetryConfig(
            retryable_exceptions=(Exception,),
            non_retryable_exceptions=(ValueError,),
        )
        assert is_retryable(ValueError(), config) is False
        assert is_retryable(TimeoutError(), config) is True

    def test_subclass_matching(self) -> None:
        config = RetryConfig(retryable_exceptions=(OSError,))
        assert is_retryable(ConnectionError(), config) is True  # subclass of OSError
        assert is_retryable(KeyError(), config) is False  # not a subclass of OSError

    def test_empty_non_retryable(self) -> None:
        config = RetryConfig(
            retryable_exceptions=(Exception,),
            non_retryable_exceptions=(),
        )
        assert is_retryable(RuntimeError(), config) is True

    def test_default_retries_all_exceptions(self) -> None:
        config = RetryConfig()
        assert is_retryable(ValueError(), config) is True
        assert is_retryable(RuntimeError(), config) is True
        assert is_retryable(TimeoutError(), config) is True


# ── with_retry decorator ─────────────────────────────────────────────


class TestWithRetry:
    """Tests for with_retry decorator."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3))
        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self) -> None:
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01))
        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self) -> None:
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01))
        async def always_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError, match="timeout"):
            await always_fail()
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_exception_raises_immediately(self) -> None:
        call_count = 0

        @with_retry(
            RetryConfig(
                max_attempts=5,
                base_delay=0.01,
                retryable_exceptions=(TimeoutError,),
            )
        )
        async def fail_with_value_error() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await fail_with_value_error()
        assert call_count == 1  # no retries

    @pytest.mark.asyncio
    async def test_on_retry_callback(self) -> None:
        callback = MagicMock()
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01, on_retry=callback))
        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            return "ok"

        await fail_then_succeed()
        assert callback.call_count == 2  # called on attempt 1 and 2

    @pytest.mark.asyncio
    async def test_on_retry_callback_exception_suppressed(self) -> None:
        def bad_callback(exc: Exception, attempt: int, delay: float) -> None:
            raise RuntimeError("callback error")

        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, base_delay=0.01, on_retry=bad_callback))
        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_with_retry_no_parentheses(self) -> None:
        """Test @with_retry without parentheses."""
        call_count = 0

        @with_retry
        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_with_retry_keyword_args(self) -> None:
        call_count = 0

        @with_retry(max_attempts=2, base_delay=0.01)
        async def fail_once() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("timeout")
            return "ok"

        result = await fail_once()
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_with_retry_single_attempt(self) -> None:
        @with_retry(RetryConfig(max_attempts=1))
        async def always_fail() -> None:
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError):
            await always_fail()

    def test_sync_function_passthrough(self) -> None:
        """Sync functions should pass through without retry."""

        @with_retry(RetryConfig(max_attempts=3))
        def sync_func() -> str:
            return "ok"

        result = sync_func()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_preserves_function_name(self) -> None:
        @with_retry(RetryConfig(max_attempts=3))
        async def my_function() -> None:
            pass

        assert my_function.__name__ == "my_function"

    @pytest.mark.asyncio
    async def test_preserves_function_args(self) -> None:
        @with_retry(RetryConfig(max_attempts=3))
        async def add(a: int, b: int) -> int:
            return a + b

        result = await add(2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_preserves_kwargs(self) -> None:
        @with_retry(RetryConfig(max_attempts=3))
        async def greet(name: str = "world") -> str:
            return f"hello {name}"

        assert await greet() == "hello world"
        assert await greet(name="test") == "hello test"

    @pytest.mark.asyncio
    async def test_non_retryable_precedence_over_retryable(self) -> None:
        call_count = 0

        @with_retry(
            RetryConfig(
                max_attempts=5,
                base_delay=0.01,
                retryable_exceptions=(Exception,),
                non_retryable_exceptions=(ValueError,),
            )
        )
        async def fail_with_value() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("bad")

        with pytest.raises(ValueError):
            await fail_with_value()
        assert call_count == 1


# ── Pre-configured decorators ────────────────────────────────────────


class TestPreConfiguredDecorators:
    """Tests for pre-configured retry decorators."""

    def test_transient_exceptions_tuple(self) -> None:
        assert TimeoutError in TRANSIENT_EXCEPTIONS
        assert ConnectionError in TRANSIENT_EXCEPTIONS
        assert ConnectionResetError in TRANSIENT_EXCEPTIONS
        assert ConnectionRefusedError in TRANSIENT_EXCEPTIONS
        assert BrokenPipeError in TRANSIENT_EXCEPTIONS
        assert OSError in TRANSIENT_EXCEPTIONS

    def test_provider_retry_configs_exist(self) -> None:
        assert "default" in PROVIDER_RETRY_CONFIGS
        assert "glm" in PROVIDER_RETRY_CONFIGS
        assert "anthropic" in PROVIDER_RETRY_CONFIGS
        assert "openai" in PROVIDER_RETRY_CONFIGS
        assert "deepseek" in PROVIDER_RETRY_CONFIGS
        assert "ollama" in PROVIDER_RETRY_CONFIGS

    def test_provider_configs_are_retry_configs(self) -> None:
        for name, config in PROVIDER_RETRY_CONFIGS.items():
            assert isinstance(config, RetryConfig), f"{name} is not RetryConfig"

    def test_glm_has_longer_delays(self) -> None:
        glm = PROVIDER_RETRY_CONFIGS["glm"]
        openai = PROVIDER_RETRY_CONFIGS["openai"]
        assert glm.base_delay > openai.base_delay
        assert glm.max_delay > openai.max_delay

    def test_ollama_has_fewer_retries(self) -> None:
        ollama = PROVIDER_RETRY_CONFIGS["ollama"]
        assert ollama.max_attempts == 2

    def test_all_providers_use_transient_exceptions(self) -> None:
        for name, config in PROVIDER_RETRY_CONFIGS.items():
            assert config.retryable_exceptions == TRANSIENT_EXCEPTIONS, (
                f"{name} should use TRANSIENT_EXCEPTIONS"
            )


# ── with_validation_retry ────────────────────────────────────────────


class TestWithValidationRetry:
    """Tests for with_validation_retry decorator."""

    @pytest.mark.asyncio
    async def test_retries_on_validation_error(self) -> None:
        from pydantic import ValidationError

        from app.core.retry import with_validation_retry

        call_count = 0

        @with_validation_retry(max_attempts=3, base_delay=0.01)
        async def validate_output() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValidationError.from_exception_data(
                    "test",
                    line_errors=[
                        {
                            "type": "missing",
                            "loc": ("field",),
                            "msg": "Field required",
                            "input": {},
                        }
                    ],
                )
            return "valid"

        result = await validate_output()
        assert result == "valid"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self) -> None:
        from app.core.retry import with_validation_retry

        call_count = 0

        @with_validation_retry(max_attempts=3, base_delay=0.01)
        async def timeout_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("timeout")
            return "ok"

        result = await timeout_then_succeed()
        assert result == "ok"
        assert call_count == 2


# ── Edge cases ───────────────────────────────────────────────────────


class TestRetryEdgeCases:
    """Edge case tests for the retry framework."""

    @pytest.mark.asyncio
    async def test_cancellation_propagates(self) -> None:
        """CancelledError should not be retried."""

        @with_retry(RetryConfig(max_attempts=5, base_delay=0.01, retryable_exceptions=(Exception,)))
        async def cancel_self() -> None:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await cancel_self()

    @pytest.mark.asyncio
    async def test_retry_with_async_mock(self) -> None:
        mock = AsyncMock(side_effect=[TimeoutError(), TimeoutError(), "success"])

        @with_retry(RetryConfig(max_attempts=5, base_delay=0.01))
        async def call_mock() -> str:
            return await mock()

        result = await call_mock()
        assert result == "success"
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_different_exceptions_per_retry(self) -> None:
        call_count = 0

        @with_retry(
            RetryConfig(
                max_attempts=4,
                base_delay=0.01,
                retryable_exceptions=(TimeoutError, ConnectionError),
            )
        )
        async def mixed_failures() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("timeout")
            if call_count == 2:
                raise ConnectionError("connection")
            return "ok"

        result = await mixed_failures()
        assert result == "ok"
        assert call_count == 3
