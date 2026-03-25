"""Tests for the generalized retry framework (app.core.retry).

Covers:
- RetryConfig defaults and field validation
- RetryStats defaults
- calculate_delay: exponential growth, max cap, jitter range, no-jitter exact values
- is_retryable: matching exceptions, non-matching, non_retryable precedence
- with_retry decorator: success on first try, retry-then-success, exhausted attempts,
  non-retryable immediate raise, on_retry callback, without-parentheses form,
  individual keyword-param overrides, sync function passthrough
- TRANSIENT_EXCEPTIONS contents
- PROVIDER_RETRY_CONFIGS keys and types
- Pre-configured decorator existence (llm_retry, tool_retry, db_retry, etc.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.retry import (
    PROVIDER_RETRY_CONFIGS,
    TRANSIENT_EXCEPTIONS,
    RetryConfig,
    RetryStats,
    calculate_delay,
    db_retry,
    http_retry,
    is_retryable,
    llm_retry,
    llm_validation_retry,
    sandbox_retry,
    tool_retry,
    with_retry,
)

# ---------------------------------------------------------------------------
# RetryConfig defaults
# ---------------------------------------------------------------------------


class TestRetryConfigDefaults:
    """RetryConfig should carry sensible default values after construction."""

    def test_max_attempts_default(self):
        config = RetryConfig()
        assert config.max_attempts == 3

    def test_base_delay_default(self):
        config = RetryConfig()
        assert config.base_delay == 1.0

    def test_max_delay_default(self):
        config = RetryConfig()
        assert config.max_delay == 60.0

    def test_exponential_base_default(self):
        config = RetryConfig()
        assert config.exponential_base == 2.0

    def test_jitter_default_is_true(self):
        config = RetryConfig()
        assert config.jitter is True

    def test_jitter_factor_default(self):
        config = RetryConfig()
        assert config.jitter_factor == 0.25

    def test_retryable_exceptions_default_is_base_exception(self):
        config = RetryConfig()
        assert config.retryable_exceptions == (Exception,)

    def test_non_retryable_exceptions_default_is_empty(self):
        config = RetryConfig()
        assert config.non_retryable_exceptions == ()

    def test_on_retry_default_is_none(self):
        config = RetryConfig()
        assert config.on_retry is None

    def test_log_retries_default_is_true(self):
        config = RetryConfig()
        assert config.log_retries is True


# ---------------------------------------------------------------------------
# RetryStats defaults
# ---------------------------------------------------------------------------


class TestRetryStatsDefaults:
    """RetryStats should initialise all fields to zero/falsy values."""

    def test_attempts_default(self):
        stats = RetryStats()
        assert stats.attempts == 0

    def test_total_delay_default(self):
        stats = RetryStats()
        assert stats.total_delay == 0.0

    def test_success_default(self):
        stats = RetryStats()
        assert stats.success is False

    def test_final_exception_default(self):
        stats = RetryStats()
        assert stats.final_exception is None

    def test_duration_ms_default(self):
        stats = RetryStats()
        assert stats.duration_ms == 0.0


# ---------------------------------------------------------------------------
# calculate_delay
# ---------------------------------------------------------------------------


class TestCalculateDelay:
    """Verify delay calculation under various configurations."""

    def _no_jitter_config(self, **kwargs) -> RetryConfig:
        return RetryConfig(jitter=False, log_retries=False, **kwargs)

    def test_first_attempt_equals_base_delay(self):
        config = self._no_jitter_config(base_delay=2.0)
        assert calculate_delay(1, config) == pytest.approx(2.0)

    def test_second_attempt_doubles(self):
        config = self._no_jitter_config(base_delay=1.0, exponential_base=2.0)
        assert calculate_delay(2, config) == pytest.approx(2.0)

    def test_third_attempt_quadruples(self):
        config = self._no_jitter_config(base_delay=1.0, exponential_base=2.0)
        assert calculate_delay(3, config) == pytest.approx(4.0)

    def test_exponential_growth_custom_base(self):
        config = self._no_jitter_config(base_delay=1.0, exponential_base=3.0)
        # attempt 3: 1.0 * 3^2 = 9.0
        assert calculate_delay(3, config) == pytest.approx(9.0)

    def test_max_delay_cap(self):
        config = self._no_jitter_config(base_delay=1.0, exponential_base=2.0, max_delay=5.0)
        # attempt 5: 1.0 * 2^4 = 16.0, capped at 5.0
        assert calculate_delay(5, config) == pytest.approx(5.0)

    def test_jitter_stays_within_range(self):
        config = RetryConfig(jitter=True, jitter_factor=0.25, base_delay=4.0, exponential_base=2.0, max_delay=60.0)
        delays = [calculate_delay(1, config) for _ in range(200)]
        # Without jitter: 4.0; with ±25% jitter: [3.0, 5.0]
        assert all(3.0 <= d <= 5.0 for d in delays)

    def test_no_jitter_is_exact(self):
        config = self._no_jitter_config(base_delay=3.0, exponential_base=2.0)
        # attempt 4: 3.0 * 2^3 = 24.0
        assert calculate_delay(4, config) == pytest.approx(24.0)

    def test_jitter_never_returns_negative(self):
        config = RetryConfig(jitter=True, jitter_factor=0.25, base_delay=0.1, max_delay=60.0)
        delays = [calculate_delay(1, config) for _ in range(200)]
        assert all(d >= 0 for d in delays)


# ---------------------------------------------------------------------------
# is_retryable
# ---------------------------------------------------------------------------


class TestIsRetryable:
    """is_retryable should respect retryable_exceptions and non_retryable_exceptions."""

    def test_matching_exception_is_retryable(self):
        config = RetryConfig(retryable_exceptions=(ValueError,), non_retryable_exceptions=())
        assert is_retryable(ValueError("oops"), config) is True

    def test_non_matching_exception_is_not_retryable(self):
        config = RetryConfig(retryable_exceptions=(ValueError,), non_retryable_exceptions=())
        assert is_retryable(TypeError("nope"), config) is False

    def test_non_retryable_takes_precedence_over_retryable(self):
        # ValueError is both in retryable and non_retryable — non_retryable wins
        config = RetryConfig(
            retryable_exceptions=(ValueError,),
            non_retryable_exceptions=(ValueError,),
        )
        assert is_retryable(ValueError("conflict"), config) is False

    def test_subclass_exception_matches_parent_retryable(self):
        config = RetryConfig(retryable_exceptions=(OSError,), non_retryable_exceptions=())
        assert is_retryable(ConnectionError("sub"), config) is True

    def test_empty_retryable_exceptions_returns_false(self):
        config = RetryConfig(retryable_exceptions=(), non_retryable_exceptions=())
        assert is_retryable(Exception("any"), config) is False

    def test_base_exception_catches_everything(self):
        config = RetryConfig(retryable_exceptions=(Exception,), non_retryable_exceptions=())
        assert is_retryable(RuntimeError("any"), config) is True


# ---------------------------------------------------------------------------
# with_retry decorator — async paths
# ---------------------------------------------------------------------------


class TestWithRetryDecorator:
    """Behavioural tests for the with_retry decorator on async functions."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_returns_value(self):
        config = RetryConfig(jitter=False, log_retries=False)

        @with_retry(config)
        async def always_ok():
            return 42

        result = await always_ok()
        assert result == 42

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        """Function fails once then succeeds — result should be returned."""
        config = RetryConfig(max_attempts=3, jitter=False, log_retries=False, base_delay=0.0)
        call_count = 0

        @with_retry(config)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "ok"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await flaky()

        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_attempts_raises_last_exception(self):
        config = RetryConfig(max_attempts=3, jitter=False, log_retries=False, base_delay=0.0)

        @with_retry(config)
        async def always_fail():
            raise TimeoutError("gone")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(TimeoutError, match="gone"):
            await always_fail()

    @pytest.mark.asyncio
    async def test_exhausted_attempts_call_count(self):
        config = RetryConfig(max_attempts=3, jitter=False, log_retries=False, base_delay=0.0)
        call_count = 0

        @with_retry(config)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ValueError):
            await always_fail()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        config = RetryConfig(
            max_attempts=5,
            jitter=False,
            log_retries=False,
            retryable_exceptions=(TimeoutError,),
            non_retryable_exceptions=(ValueError,),
        )
        call_count = 0

        @with_retry(config)
        async def bad():
            nonlocal call_count
            call_count += 1
            raise ValueError("no-retry")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ValueError, match="no-retry"):
            await bad()

        # Must not have retried at all
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_on_retry_callback_is_called(self):
        callback = MagicMock()
        config = RetryConfig(
            max_attempts=3,
            jitter=False,
            log_retries=False,
            base_delay=0.0,
            on_retry=callback,
        )

        @with_retry(config)
        async def fail_twice():
            raise ConnectionError("cb-test")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ConnectionError):
            await fail_twice()

        # callback called for attempts 1 and 2 (attempt 3 exhausts, no further retry)
        assert callback.call_count == 2

    @pytest.mark.asyncio
    async def test_on_retry_callback_receives_exception_attempt_delay(self):
        received: list = []

        def capture(exc, attempt, delay):
            received.append((type(exc).__name__, attempt, delay))

        config = RetryConfig(
            max_attempts=2,
            jitter=False,
            log_retries=False,
            base_delay=0.5,
            on_retry=capture,
        )

        @with_retry(config)
        async def fail():
            raise TimeoutError("t")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(TimeoutError):
            await fail()

        assert received[0][0] == "TimeoutError"
        assert received[0][1] == 1  # first retry is after attempt 1
        assert received[0][2] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_on_retry_callback_exception_does_not_propagate(self):
        """on_retry errors must be swallowed (contextlib.suppress)."""

        def bad_callback(exc, attempt, delay):
            raise RuntimeError("callback exploded")

        config = RetryConfig(
            max_attempts=2,
            jitter=False,
            log_retries=False,
            base_delay=0.0,
            on_retry=bad_callback,
        )

        @with_retry(config)
        async def fail():
            raise TimeoutError("t")

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            # Should raise TimeoutError (original), NOT RuntimeError from callback
            pytest.raises(TimeoutError),
        ):
            await fail()

    @pytest.mark.asyncio
    async def test_asyncio_sleep_is_called_between_retries(self):
        config = RetryConfig(max_attempts=3, jitter=False, log_retries=False, base_delay=1.0)

        @with_retry(config)
        async def always_fail():
            raise ConnectionError("x")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, pytest.raises(ConnectionError):
            await always_fail()

        # Two retries = two sleeps
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_without_parentheses(self):
        """@with_retry (no call) should also work via the callable-check path."""

        @with_retry
        async def greet(name: str) -> str:
            return f"hello {name}"

        result = await greet("world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_individual_param_overrides(self):
        """with_retry(max_attempts=...) overrides the default RetryConfig."""
        call_count = 0

        @with_retry(max_attempts=2, base_delay=0.0)
        async def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("x")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ValueError):
            await fail()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retryable_exceptions_param_override(self):
        """Only the specified exception type should trigger retries."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.0, retryable_exceptions=(TimeoutError,))
        async def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable in this config")

        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ValueError):
            await fail()

        # ValueError is not in retryable_exceptions, so should not retry
        assert call_count == 1


# ---------------------------------------------------------------------------
# Sync function passthrough
# ---------------------------------------------------------------------------


class TestSyncFunctionPassthrough:
    """with_retry applied to a sync function should return it as-is (no retry)."""

    def test_sync_function_returns_value(self):
        @with_retry(RetryConfig(log_retries=False))
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    def test_sync_function_raises_without_retry(self):
        call_count = 0

        @with_retry(RetryConfig(max_attempts=5, log_retries=False))
        def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("sync-fail")

        with pytest.raises(ValueError):
            fail()

        # Sync wrapper passes through immediately — no retry loop
        assert call_count == 1


# ---------------------------------------------------------------------------
# TRANSIENT_EXCEPTIONS
# ---------------------------------------------------------------------------


class TestTransientExceptions:
    """TRANSIENT_EXCEPTIONS must include the expected network-level error types."""

    def test_timeout_error_included(self):
        assert TimeoutError in TRANSIENT_EXCEPTIONS

    def test_connection_error_included(self):
        assert ConnectionError in TRANSIENT_EXCEPTIONS

    def test_connection_reset_error_included(self):
        assert ConnectionResetError in TRANSIENT_EXCEPTIONS

    def test_connection_refused_error_included(self):
        assert ConnectionRefusedError in TRANSIENT_EXCEPTIONS

    def test_broken_pipe_error_included(self):
        assert BrokenPipeError in TRANSIENT_EXCEPTIONS

    def test_os_error_included(self):
        assert OSError in TRANSIENT_EXCEPTIONS

    def test_is_a_tuple_of_exception_types(self):
        assert isinstance(TRANSIENT_EXCEPTIONS, tuple)
        assert all(issubclass(exc, BaseException) for exc in TRANSIENT_EXCEPTIONS)


# ---------------------------------------------------------------------------
# PROVIDER_RETRY_CONFIGS
# ---------------------------------------------------------------------------


class TestProviderRetryConfigs:
    """PROVIDER_RETRY_CONFIGS must contain expected provider keys with valid configs."""

    EXPECTED_KEYS: frozenset[str] = frozenset({"default", "glm", "anthropic", "openai", "deepseek", "ollama"})

    def test_all_expected_keys_present(self):
        assert self.EXPECTED_KEYS.issubset(PROVIDER_RETRY_CONFIGS.keys())

    def test_all_values_are_retry_config_instances(self):
        for key, value in PROVIDER_RETRY_CONFIGS.items():
            assert isinstance(value, RetryConfig), f"{key!r} is not a RetryConfig"

    def test_glm_has_higher_base_delay(self):
        glm = PROVIDER_RETRY_CONFIGS["glm"]
        default = PROVIDER_RETRY_CONFIGS["default"]
        assert glm.base_delay >= default.base_delay

    def test_ollama_has_fewer_max_attempts(self):
        ollama = PROVIDER_RETRY_CONFIGS["ollama"]
        default = PROVIDER_RETRY_CONFIGS["default"]
        assert ollama.max_attempts <= default.max_attempts

    def test_openai_has_lower_max_delay(self):
        openai = PROVIDER_RETRY_CONFIGS["openai"]
        default = PROVIDER_RETRY_CONFIGS["default"]
        assert openai.max_delay <= default.max_delay


# ---------------------------------------------------------------------------
# Pre-configured decorators
# ---------------------------------------------------------------------------


class TestPreConfiguredDecorators:
    """All pre-built decorator objects should be callable (ready for use)."""

    def test_llm_retry_is_callable(self):
        assert callable(llm_retry)

    def test_llm_validation_retry_is_callable(self):
        assert callable(llm_validation_retry)

    def test_tool_retry_is_callable(self):
        assert callable(tool_retry)

    def test_db_retry_is_callable(self):
        assert callable(db_retry)

    def test_http_retry_is_callable(self):
        assert callable(http_retry)

    def test_sandbox_retry_is_callable(self):
        assert callable(sandbox_retry)

    @pytest.mark.asyncio
    async def test_llm_retry_wraps_async_function(self):
        """llm_retry should produce a working async wrapper."""

        @llm_retry
        async def ask() -> str:
            return "answer"

        result = await ask()
        assert result == "answer"

    @pytest.mark.asyncio
    async def test_tool_retry_wraps_async_function(self):
        @tool_retry
        async def run_tool() -> int:
            return 99

        result = await run_tool()
        assert result == 99
