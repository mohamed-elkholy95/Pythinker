"""
Tests for the error handler module.
"""

import pytest
from app.domain.services.agents.error_handler import (
    ErrorHandler,
    ErrorType,
    ErrorContext,
    TokenLimitExceeded,
)


class TestErrorType:
    """Tests for ErrorType enum"""

    def test_error_types_exist(self):
        """Verify all expected error types exist"""
        expected_types = [
            "JSON_PARSE",
            "TOKEN_LIMIT",
            "TOOL_EXECUTION",
            "LLM_API",
            "MCP_CONNECTION",
            "TIMEOUT",
            "STUCK_LOOP",
            "UNKNOWN",
        ]
        for error_type in expected_types:
            assert hasattr(ErrorType, error_type)


class TestErrorContext:
    """Tests for ErrorContext dataclass"""

    def test_can_retry_within_limit(self):
        """Test retry check within limit"""
        ctx = ErrorContext(
            error_type=ErrorType.JSON_PARSE,
            message="Test error",
            retry_count=0,
            max_retries=3
        )
        assert ctx.can_retry() is True

    def test_can_retry_at_limit(self):
        """Test retry check at limit"""
        ctx = ErrorContext(
            error_type=ErrorType.JSON_PARSE,
            message="Test error",
            retry_count=3,
            max_retries=3
        )
        assert ctx.can_retry() is False

    def test_can_retry_non_recoverable(self):
        """Test non-recoverable errors cannot retry"""
        ctx = ErrorContext(
            error_type=ErrorType.UNKNOWN,
            message="Test error",
            recoverable=False,
            retry_count=0
        )
        assert ctx.can_retry() is False

    def test_increment_retry(self):
        """Test retry counter increment"""
        ctx = ErrorContext(
            error_type=ErrorType.JSON_PARSE,
            message="Test error",
            retry_count=0
        )
        ctx.increment_retry()
        assert ctx.retry_count == 1


class TestErrorHandler:
    """Tests for ErrorHandler class"""

    def test_classify_json_error(self):
        """Test classification of JSON errors"""
        handler = ErrorHandler()
        exception = ValueError("JSON decode error: Expecting value")
        ctx = handler.classify_error(exception)

        assert ctx.error_type == ErrorType.JSON_PARSE
        assert ctx.recoverable is True

    def test_classify_token_limit_error(self):
        """Test classification of token limit errors"""
        handler = ErrorHandler()
        exception = Exception("context_length_exceeded: maximum context length is 8192")
        ctx = handler.classify_error(exception)

        assert ctx.error_type == ErrorType.TOKEN_LIMIT
        assert ctx.recoverable is True

    def test_classify_timeout_error(self):
        """Test classification of timeout errors"""
        handler = ErrorHandler()
        exception = TimeoutError("Request timed out")
        ctx = handler.classify_error(exception)

        assert ctx.error_type == ErrorType.TIMEOUT
        assert ctx.recoverable is True

    def test_classify_mcp_connection_error(self):
        """Test classification of MCP connection errors"""
        handler = ErrorHandler()
        exception = ConnectionError("MCP server disconnected")
        ctx = handler.classify_error(exception)

        assert ctx.error_type == ErrorType.MCP_CONNECTION
        assert ctx.recoverable is True

    def test_classify_unknown_error(self):
        """Test classification of unknown errors"""
        handler = ErrorHandler()
        exception = RuntimeError("Something completely unexpected")
        ctx = handler.classify_error(exception)

        assert ctx.error_type == ErrorType.UNKNOWN

    def test_get_recovery_prompt_json_parse(self):
        """Test recovery prompt for JSON parse errors"""
        handler = ErrorHandler()
        ctx = ErrorContext(error_type=ErrorType.JSON_PARSE, message="Invalid JSON")
        prompt = handler.get_recovery_prompt(ctx)

        assert prompt is not None
        assert "JSON" in prompt

    def test_get_recovery_prompt_stuck_loop(self):
        """Test recovery prompt for stuck loop"""
        handler = ErrorHandler()
        ctx = ErrorContext(error_type=ErrorType.STUCK_LOOP, message="Stuck in loop")
        prompt = handler.get_recovery_prompt(ctx)

        assert prompt is not None
        assert "repeating" in prompt.lower()

    def test_error_history_recording(self):
        """Test that errors are recorded in history"""
        handler = ErrorHandler()

        handler.classify_error(ValueError("Error 1"))
        handler.classify_error(ValueError("Error 2"))

        errors = handler.get_recent_errors(limit=10)
        assert len(errors) == 2

    def test_error_history_filtering(self):
        """Test filtering errors by type"""
        handler = ErrorHandler()

        handler.classify_error(ValueError("JSON decode error"))
        handler.classify_error(TimeoutError("Request timeout"))

        json_errors = handler.get_recent_errors(error_type=ErrorType.JSON_PARSE)
        assert len(json_errors) == 1
        assert json_errors[0].error_type == ErrorType.JSON_PARSE

    def test_clear_history(self):
        """Test clearing error history"""
        handler = ErrorHandler()
        handler.classify_error(ValueError("Test error"))
        handler.clear_history()

        assert len(handler.get_recent_errors()) == 0


class TestTokenLimitExceeded:
    """Tests for TokenLimitExceeded exception"""

    def test_basic_exception(self):
        """Test basic exception creation"""
        exc = TokenLimitExceeded("Context too long")
        assert str(exc) == "Context too long"

    def test_exception_with_token_counts(self):
        """Test exception with token count information"""
        exc = TokenLimitExceeded(
            "Context too long",
            current_tokens=10000,
            max_tokens=8192
        )
        assert exc.current_tokens == 10000
        assert exc.max_tokens == 8192
