"""Middleware adapter for ErrorHandler."""

from __future__ import annotations

from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.error_handler import ErrorHandler
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
)


class ErrorHandlerMiddleware(BaseMiddleware):
    """Classifies errors and determines retry/abort strategy."""

    def __init__(self, handler: ErrorHandler | None = None) -> None:
        self._handler = handler or ErrorHandler()

    @property
    def name(self) -> str:
        return "error_handler"

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult:
        error_context = self._handler.classify_error(error)
        error_type_value = (
            error_context.error_type.value
            if hasattr(error_context.error_type, "value")
            else str(error_context.error_type)
        )
        if error_context.recoverable:
            return MiddlewareResult(
                signal=MiddlewareSignal.CONTINUE,
                message=error_context.message,
                metadata={
                    "error_type": error_type_value,
                    "retry_delay": error_context.get_retry_delay(),
                },
            )
        return MiddlewareResult(
            signal=MiddlewareSignal.ABORT,
            message=error_context.message,
            metadata={"error_type": error_type_value},
        )
