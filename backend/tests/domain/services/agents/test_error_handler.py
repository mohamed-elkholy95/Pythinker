"""Tests for error_handler module — ErrorType, ErrorContext, ErrorHandler, TokenLimitExceededError.

Covers:
  - ErrorType enum: is_recoverable/is_fatal properties for every member
  - ErrorContext dataclass: can_retry, increment_retry, get_retry_delay, get_backoff_config
  - ErrorHandler: classify_error, get_recovery_prompt, get_recent_errors,
    handle_with_retry, retry_with_backoff, record_tool_error/success,
    get_recovery_stats, reset_stats, clear_history
  - TokenLimitExceededError attributes
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.services.agents.error_handler import (
    ErrorContext,
    ErrorHandler,
    ErrorType,
    TokenLimitExceededError,
)

# ---------------------------------------------------------------------------
# ErrorType enum
# ---------------------------------------------------------------------------


class TestErrorType:
    """ErrorType enum classification and properties."""

    @pytest.mark.parametrize(
        "et",
        [
            ErrorType.TIMEOUT,
            ErrorType.BROWSER_TIMEOUT,
            ErrorType.BROWSER_CONNECTION,
            ErrorType.MCP_CONNECTION,
            ErrorType.LLM_API,
            ErrorType.LLM_EMPTY_RESPONSE,
            ErrorType.JSON_PARSE,
            ErrorType.TOOL_EXECUTION,
            ErrorType.BROWSER_NAVIGATION,
            ErrorType.BROWSER_ELEMENT_NOT_FOUND,
        ],
    )
    def test_recoverable_errors(self, et: ErrorType) -> None:
        assert et.is_recoverable is True
        assert et.is_fatal is False

    @pytest.mark.parametrize("et", [ErrorType.TOKEN_LIMIT, ErrorType.STUCK_LOOP])
    def test_fatal_errors(self, et: ErrorType) -> None:
        assert et.is_fatal is True
        assert et.is_recoverable is False

    def test_unknown_is_neither_recoverable_nor_fatal(self) -> None:
        assert ErrorType.UNKNOWN.is_recoverable is False
        assert ErrorType.UNKNOWN.is_fatal is False

    def test_all_members_have_string_value(self) -> None:
        for member in ErrorType:
            assert isinstance(member.value, str)
            assert len(member.value) > 0


# ---------------------------------------------------------------------------
# ErrorContext dataclass
# ---------------------------------------------------------------------------


class TestErrorContext:
    """ErrorContext creation and retry logic."""

    def test_defaults(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="timed out")
        assert ctx.retry_count == 0
        assert ctx.max_retries == 3
        assert ctx.recoverable is True
        assert ctx.can_retry() is True

    def test_can_retry_false_when_not_recoverable(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.UNKNOWN, message="x", recoverable=False)
        assert ctx.can_retry() is False

    def test_can_retry_false_when_max_retries_reached(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x", retry_count=3, max_retries=3)
        assert ctx.can_retry() is False

    def test_increment_retry(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x")
        assert ctx.retry_count == 0
        ctx.increment_retry()
        assert ctx.retry_count == 1

    def test_get_retry_delay_increases_with_retries(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x", jitter=False)
        delays = []
        for _ in range(3):
            delays.append(ctx.get_retry_delay())
            ctx.increment_retry()
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]

    def test_get_retry_delay_capped_at_max(self) -> None:
        ctx = ErrorContext(
            error_type=ErrorType.TIMEOUT,
            message="x",
            retry_count=100,
            max_retry_delay=5.0,
            jitter=False,
        )
        assert ctx.get_retry_delay() <= 5.0

    def test_get_retry_delay_minimum_100ms(self) -> None:
        ctx = ErrorContext(
            error_type=ErrorType.TIMEOUT,
            message="x",
            min_retry_delay=0.001,
            jitter=False,
        )
        assert ctx.get_retry_delay() >= 0.1

    def test_get_retry_delay_with_jitter_varies(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x", jitter=True, retry_count=2)
        delays = {ctx.get_retry_delay() for _ in range(20)}
        # With jitter, we should see some variation
        assert len(delays) > 1

    def test_get_backoff_config(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x", jitter=False)
        config = ctx.get_backoff_config()
        assert config["backoff_factor"] == 1.5
        assert config["min_retry_delay"] == 0.3
        assert config["max_retry_delay"] == 30.0
        assert config["jitter"] is False
        assert config["current_retry"] == 0
        assert config["next_delay"] is not None

    def test_get_backoff_config_next_delay_none_when_exhausted(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x", retry_count=3, max_retries=3)
        config = ctx.get_backoff_config()
        assert config["next_delay"] is None

    def test_metadata_default_empty(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x")
        assert ctx.metadata == {}

    def test_timestamp_set(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x")
        assert ctx.timestamp is not None


# ---------------------------------------------------------------------------
# ErrorHandler — classify_error
# ---------------------------------------------------------------------------


class TestErrorHandlerClassify:
    """ErrorHandler.classify_error classification logic."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    def test_json_error(self) -> None:
        ctx = self.handler.classify_error(ValueError("Invalid JSON data"))
        assert ctx.error_type == ErrorType.JSON_PARSE

    def test_json_decode_error(self) -> None:
        ctx = self.handler.classify_error(Exception("JSONDecodeError occurred"))
        assert ctx.error_type == ErrorType.JSON_PARSE

    def test_token_limit(self) -> None:
        ctx = self.handler.classify_error(Exception("context_length_exceeded for model"))
        assert ctx.error_type == ErrorType.TOKEN_LIMIT

    def test_max_tokens(self) -> None:
        ctx = self.handler.classify_error(Exception("max_tokens exceeded"))
        assert ctx.error_type == ErrorType.TOKEN_LIMIT

    def test_timeout_error(self) -> None:
        ctx = self.handler.classify_error(TimeoutError("Request timed out"))
        assert ctx.error_type == ErrorType.TIMEOUT

    def test_mcp_connection(self) -> None:
        ctx = self.handler.classify_error(Exception("MCP connection failed"))
        assert ctx.error_type == ErrorType.MCP_CONNECTION

    def test_openai_api_error(self) -> None:
        ctx = self.handler.classify_error(Exception("OpenAI API error: rate limit"))
        assert ctx.error_type == ErrorType.LLM_API

    def test_rate_limit(self) -> None:
        ctx = self.handler.classify_error(Exception("API rate limit exceeded"))
        assert ctx.error_type == ErrorType.LLM_API

    def test_tool_execution(self) -> None:
        ctx = self.handler.classify_error(Exception("tool execution failed"))
        assert ctx.error_type == ErrorType.TOOL_EXECUTION

    def test_empty_response(self) -> None:
        ctx = self.handler.classify_error(Exception("empty response from model"))
        assert ctx.error_type == ErrorType.LLM_EMPTY_RESPONSE

    def test_browser_navigation(self) -> None:
        ctx = self.handler.classify_error(Exception("browser failed to navigate to URL"))
        assert ctx.error_type == ErrorType.BROWSER_NAVIGATION

    def test_browser_element_not_found(self) -> None:
        ctx = self.handler.classify_error(Exception("browser: element not found with selector"))
        assert ctx.error_type == ErrorType.BROWSER_ELEMENT_NOT_FOUND

    def test_browser_connection(self) -> None:
        ctx = self.handler.classify_error(Exception("browser connection closed unexpectedly"))
        assert ctx.error_type == ErrorType.BROWSER_CONNECTION

    def test_browser_timeout(self) -> None:
        ctx = self.handler.classify_error(Exception("page browser timeout exceeded"))
        assert ctx.error_type == ErrorType.BROWSER_TIMEOUT

    def test_unknown_error(self) -> None:
        ctx = self.handler.classify_error(Exception("something completely unexpected"))
        assert ctx.error_type == ErrorType.UNKNOWN
        assert ctx.recoverable is False

    def test_llm_keys_exhausted(self) -> None:
        from app.domain.exceptions.base import LLMKeysExhaustedError

        ctx = self.handler.classify_error(LLMKeysExhaustedError("all keys exhausted", key_count=3))
        assert ctx.error_type == ErrorType.LLM_API

    def test_classify_records_to_history(self) -> None:
        self.handler.classify_error(TimeoutError("x"))
        assert len(self.handler.get_recent_errors()) == 1

    def test_classify_deduplicates_same_exception(self) -> None:
        """Same exception instance classified twice should only store once in dedup set."""
        exc = TimeoutError("same")
        self.handler.classify_error(exc)
        self.handler.classify_error(exc)
        # Both get recorded in history (dedup is for logging, not history)
        assert len(self.handler.get_recent_errors()) == 2


# ---------------------------------------------------------------------------
# ErrorHandler — get_recovery_prompt
# ---------------------------------------------------------------------------


class TestErrorHandlerRecoveryPrompt:
    """ErrorHandler.get_recovery_prompt generation."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    def test_json_parse_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.JSON_PARSE, message="bad json")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert prompt is not None
        assert "JSON" in prompt

    def test_stuck_loop_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.STUCK_LOOP, message="loop detected")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert prompt is not None
        assert "different approach" in prompt.lower() or "alternative" in prompt.lower()

    def test_tool_execution_includes_message(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TOOL_EXECUTION, message="file not found error")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "file not found" in prompt.lower()

    def test_token_limit_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TOKEN_LIMIT, message="exceeded")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "trimmed" in prompt.lower()

    def test_empty_response_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.LLM_EMPTY_RESPONSE, message="empty")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "tool" in prompt.lower()

    def test_browser_navigation_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.BROWSER_NAVIGATION, message="navigation failed")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "URL" in prompt or "url" in prompt.lower()

    def test_browser_element_not_found_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.BROWSER_ELEMENT_NOT_FOUND, message="element missing")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "browser_view" in prompt.lower()

    def test_browser_connection_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.BROWSER_CONNECTION, message="disconnected")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "restart" in prompt.lower()

    def test_browser_timeout_prompt(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.BROWSER_TIMEOUT, message="timeout")
        prompt = self.handler.get_recovery_prompt(ctx)
        assert "browser_view" in prompt.lower()


# ---------------------------------------------------------------------------
# ErrorHandler — get_recent_errors
# ---------------------------------------------------------------------------


class TestErrorHandlerRecentErrors:
    """ErrorHandler.get_recent_errors filtering."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    def test_empty_initially(self) -> None:
        assert self.handler.get_recent_errors() == []

    def test_returns_classified_errors(self) -> None:
        self.handler.classify_error(TimeoutError("x"))
        self.handler.classify_error(ValueError("JSON parse failed"))
        assert len(self.handler.get_recent_errors()) == 2

    def test_filter_by_type(self) -> None:
        self.handler.classify_error(TimeoutError("x"))
        self.handler.classify_error(ValueError("JSON parse failed"))
        timeouts = self.handler.get_recent_errors(ErrorType.TIMEOUT)
        assert len(timeouts) == 1
        assert timeouts[0].error_type == ErrorType.TIMEOUT

    def test_limit(self) -> None:
        for i in range(10):
            self.handler.classify_error(TimeoutError(f"t{i}"))
        assert len(self.handler.get_recent_errors(limit=3)) == 3

    def test_clear_history(self) -> None:
        self.handler.classify_error(TimeoutError("x"))
        self.handler.clear_history()
        assert self.handler.get_recent_errors() == []


# ---------------------------------------------------------------------------
# ErrorHandler — handle_with_retry
# ---------------------------------------------------------------------------


class TestHandleWithRetry:
    """ErrorHandler.handle_with_retry with real async operations."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        op = AsyncMock(return_value="ok")
        success, result = await self.handler.handle_with_retry(op, max_retries=2)
        assert success is True
        assert result == "ok"
        op.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_after_retry(self) -> None:
        call_count = 0

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("flaky timeout")
            return "recovered"

        success, result = await self.handler.handle_with_retry(flaky, max_retries=3)
        assert success is True
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_failure_after_max_retries(self) -> None:
        async def always_fail() -> str:
            raise TimeoutError("permanent")

        success, result = await self.handler.handle_with_retry(always_fail, max_retries=1)
        assert success is False
        assert isinstance(result, ErrorContext)
        assert result.error_type == ErrorType.TIMEOUT

    @pytest.mark.asyncio
    async def test_non_recoverable_does_not_retry(self) -> None:
        call_count = 0

        async def fatal_op() -> str:
            nonlocal call_count
            call_count += 1
            raise Exception("something completely unexpected")

        success, _result = await self.handler.handle_with_retry(fatal_op, max_retries=3)
        assert success is False
        assert call_count == 1  # Only called once — non-recoverable

    @pytest.mark.asyncio
    async def test_on_retry_callback_called(self) -> None:
        call_count = 0
        retry_attempts: list[int] = []

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("retry me")
            return "ok"

        async def on_retry(ctx: ErrorContext, attempt: int) -> None:
            retry_attempts.append(attempt)

        success, _result = await self.handler.handle_with_retry(flaky, max_retries=3, on_retry=on_retry)
        assert success is True
        assert len(retry_attempts) == 1


# ---------------------------------------------------------------------------
# ErrorHandler — retry_with_backoff
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """ErrorHandler.retry_with_backoff."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TIMEOUT, message="x", max_retries=3)
        result = await self.handler.retry_with_backoff(AsyncMock(return_value="done"), ctx)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_success_after_retries(self) -> None:
        call_count = 0

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("flaky")
            return "recovered"

        ctx = ErrorContext(
            error_type=ErrorType.TIMEOUT,
            message="x",
            max_retries=5,
            min_retry_delay=0.01,
            max_retry_delay=0.05,
            jitter=False,
        )
        result = await self.handler.retry_with_backoff(flaky, ctx)
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises(self) -> None:
        async def always_fail() -> str:
            raise TimeoutError("permanent")

        ctx = ErrorContext(
            error_type=ErrorType.TIMEOUT,
            message="x",
            max_retries=2,
            min_retry_delay=0.01,
            jitter=False,
        )
        with pytest.raises(TimeoutError, match="permanent"):
            await self.handler.retry_with_backoff(always_fail, ctx)


# ---------------------------------------------------------------------------
# ErrorHandler — recovery stats
# ---------------------------------------------------------------------------


class TestRecoveryStats:
    """ErrorHandler recovery statistics tracking."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    def test_initial_stats_empty(self) -> None:
        stats = self.handler.get_recovery_stats()
        assert stats["total_retry_attempts"] == 0
        assert stats["successful_recoveries"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["by_error_type"] == {}

    @pytest.mark.asyncio
    async def test_stats_after_successful_retry(self) -> None:
        call_count = 0

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("x")
            return "ok"

        await self.handler.handle_with_retry(flaky, max_retries=3)
        stats = self.handler.get_recovery_stats()
        assert stats["successful_recoveries"] >= 1

    def test_reset_stats(self) -> None:
        self.handler._total_retry_attempts = 5
        self.handler._successful_recoveries = 3
        self.handler.reset_stats()
        stats = self.handler.get_recovery_stats()
        assert stats["total_retry_attempts"] == 0
        assert stats["successful_recoveries"] == 0

    def test_retry_success_rate_no_data(self) -> None:
        rate = self.handler.get_retry_success_rate(ErrorType.TIMEOUT)
        assert rate == 0.0

    def test_get_all_retry_stats_empty(self) -> None:
        stats = self.handler.get_all_retry_stats()
        assert stats == {}


# ---------------------------------------------------------------------------
# ErrorHandler — record_tool_error / record_tool_success
# ---------------------------------------------------------------------------


class TestToolErrorRecording:
    """ErrorHandler.record_tool_error and record_tool_success."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    def test_record_tool_error_does_not_raise(self) -> None:
        ctx = ErrorContext(error_type=ErrorType.TOOL_EXECUTION, message="failed")
        # Should not raise even if pattern analyzer import fails
        self.handler.record_tool_error("search", ctx)

    def test_record_tool_success_does_not_raise(self) -> None:
        # Should not raise even if pattern analyzer import fails
        self.handler.record_tool_success("search")


# ---------------------------------------------------------------------------
# ErrorHandler — _get_recovery_strategy
# ---------------------------------------------------------------------------


class TestRecoveryStrategy:
    """ErrorHandler._get_recovery_strategy returns correct strategies."""

    def setup_method(self) -> None:
        self.handler = ErrorHandler()

    def test_json_parse_recoverable(self) -> None:
        strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.JSON_PARSE, "")
        assert recoverable is True
        assert strategy is not None

    def test_token_limit_recoverable(self) -> None:
        _strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.TOKEN_LIMIT, "")
        assert recoverable is True

    def test_unknown_not_recoverable(self) -> None:
        _strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.UNKNOWN, "")
        assert recoverable is False

    def test_llm_api_rate_limit(self) -> None:
        strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.LLM_API, "rate limit hit")
        assert recoverable is True
        assert "backoff" in strategy.lower()

    def test_llm_api_auth_failure(self) -> None:
        _strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.LLM_API, "authentication error")
        assert recoverable is False

    def test_llm_api_quota_exceeded(self) -> None:
        _strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.LLM_API, "insufficient_quota")
        assert recoverable is False

    def test_llm_api_exhausted(self) -> None:
        _strategy, recoverable = self.handler._get_recovery_strategy(ErrorType.LLM_API, "keys exhausted")
        assert recoverable is False


# ---------------------------------------------------------------------------
# TokenLimitExceededError
# ---------------------------------------------------------------------------


class TestTokenLimitExceededError:
    """TokenLimitExceededError custom exception."""

    def test_message(self) -> None:
        err = TokenLimitExceededError("too many tokens")
        assert str(err) == "too many tokens"

    def test_attributes(self) -> None:
        err = TokenLimitExceededError("over limit", current_tokens=5000, max_tokens=4096)
        assert err.current_tokens == 5000
        assert err.max_tokens == 4096

    def test_defaults_none(self) -> None:
        err = TokenLimitExceededError("x")
        assert err.current_tokens is None
