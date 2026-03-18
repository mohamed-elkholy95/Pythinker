"""
Tests for the error handler module.
"""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.errors.exceptions import BadRequestError, NotFoundError
from app.domain.services.agents.error_handler import (
    ErrorContext,
    ErrorHandler,
    ErrorType,
    TokenLimitExceededError,
)
from app.interfaces.errors.exception_handlers import register_exception_handlers


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
        ctx = ErrorContext(error_type=ErrorType.JSON_PARSE, message="Test error", retry_count=0, max_retries=3)
        assert ctx.can_retry() is True

    def test_can_retry_at_limit(self):
        """Test retry check at limit"""
        ctx = ErrorContext(error_type=ErrorType.JSON_PARSE, message="Test error", retry_count=3, max_retries=3)
        assert ctx.can_retry() is False

    def test_can_retry_non_recoverable(self):
        """Test non-recoverable errors cannot retry"""
        ctx = ErrorContext(error_type=ErrorType.UNKNOWN, message="Test error", recoverable=False, retry_count=0)
        assert ctx.can_retry() is False

    def test_increment_retry(self):
        """Test retry counter increment"""
        ctx = ErrorContext(error_type=ErrorType.JSON_PARSE, message="Test error", retry_count=0)
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


class TestTokenLimitExceededError:
    """Tests for TokenLimitExceededError exception"""

    def test_basic_exception(self):
        """Test basic exception creation"""
        exc = TokenLimitExceededError("Context too long")
        assert str(exc) == "Context too long"

    def test_exception_with_token_counts(self):
        """Test exception with token count information"""
        exc = TokenLimitExceededError("Context too long", current_tokens=10000, max_tokens=8192)
        assert exc.current_tokens == 10000
        assert exc.max_tokens == 8192


class TestApiExceptionHandlers:
    """Tests for HTTP exception handler registration behavior."""

    def _build_app(self) -> FastAPI:
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/not-found")
        async def _not_found():
            raise NotFoundError("Session not found")

        @app.get("/bad-request")
        async def _bad_request():
            raise BadRequestError("Bad input")

        return app

    def test_not_found_is_mapped_to_404_without_warning_pollution(self, caplog):
        app = self._build_app()
        client = TestClient(app)

        with caplog.at_level(logging.INFO):
            response = client.get("/not-found")

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == 404
        assert body["msg"] == "Session not found"

        warning_or_error_logs = [
            record
            for record in caplog.records
            if record.levelno >= logging.WARNING and "Session not found" in record.message
        ]
        assert warning_or_error_logs == []

    def test_non_404_app_error_keeps_warning_level(self, caplog):
        app = self._build_app()
        client = TestClient(app)

        with caplog.at_level(logging.INFO):
            response = client.get("/bad-request")

        assert response.status_code == 400
        warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert warning_logs, "Expected warning logs for non-404 AppError paths"
