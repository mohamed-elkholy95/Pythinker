"""Tests for ErrorHandlerMiddleware."""

import pytest

from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
)
from app.domain.services.agents.middleware_adapters.error_handler import (
    ErrorHandlerMiddleware,
)


@pytest.fixture
def mw():
    return ErrorHandlerMiddleware()


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestErrorHandlerName:
    def test_name(self, mw):
        assert mw.name == "error_handler"


class TestOnError:
    @pytest.mark.asyncio
    async def test_retryable_error_returns_continue(self, mw, ctx):
        """Timeout is a recoverable error — should return CONTINUE."""
        error = TimeoutError("Connection timed out")
        result = await mw.on_error(ctx, error)
        assert result.signal == MiddlewareSignal.CONTINUE
        assert result.metadata.get("error_type") is not None

    @pytest.mark.asyncio
    async def test_non_retryable_error_returns_abort(self, mw, ctx):
        """UNKNOWN errors are not recoverable — should return ABORT."""
        error = RuntimeError("completely unknown failure XYZ")
        result = await mw.on_error(ctx, error)
        # UNKNOWN errors are non-recoverable → ABORT
        assert result.signal == MiddlewareSignal.ABORT

    @pytest.mark.asyncio
    async def test_result_includes_error_type_metadata(self, mw, ctx):
        error = TimeoutError("timed out")
        result = await mw.on_error(ctx, error)
        assert "error_type" in result.metadata
