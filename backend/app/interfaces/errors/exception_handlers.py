import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.application.errors.exceptions import AppError
from app.domain.exceptions.browser import (
    BrowserError,
    ConnectionPoolExhaustedError,
)
from app.infrastructure.observability.prometheus_metrics import record_error
from app.interfaces.schemas.base import APIResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers"""

    @app.exception_handler(ConnectionPoolExhaustedError)
    async def connection_pool_exhausted_handler(request: Request, exc: ConnectionPoolExhaustedError) -> JSONResponse:
        """Handle browser connection pool exhaustion.

        This error occurs when all browser connections are in use and
        no connection became available within the timeout period.
        Returns a 503 Service Unavailable with recovery hints.
        """
        # Record error metric for monitoring
        record_error("connection_pool_exhausted", "browser")

        logger.error(
            f"Connection pool exhausted: {exc.message}",
            extra={
                "cdp_url": exc.context.cdp_url,
                "pool_size": exc.pool_size,
                "in_use_count": exc.in_use_count,
                "timeout": exc.timeout,
                "session_id": exc.context.session_id,
            },
        )

        response_data: dict[str, Any] = {
            "code": 503,
            "msg": "Browser connection temporarily unavailable",
            "data": {
                "error_code": exc.code.value,
                "recoverable": exc.recoverable,
                "recovery_hint": exc.recovery_hint,
                "retry_after_seconds": 5,
            },
        }

        return JSONResponse(
            status_code=503,
            content=response_data,
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(BrowserError)
    async def browser_error_handler(request: Request, exc: BrowserError) -> JSONResponse:
        """Handle browser-related errors.

        These are recoverable errors related to browser operations.
        Returns appropriate status codes based on error type.
        """
        # Record error metric for monitoring
        record_error(exc.code.value, "browser")

        logger.warning(
            f"Browser error: {exc.message}",
            extra={
                "error_code": exc.code.value,
                "cdp_url": exc.context.cdp_url,
                "sandbox_id": exc.context.sandbox_id,
                "session_id": exc.context.session_id,
                "recoverable": exc.recoverable,
            },
        )

        # Map error codes to HTTP status codes
        status_code = 503 if exc.recoverable else 500

        response_data: dict[str, Any] = {
            "code": status_code,
            "msg": exc.message,
            "data": {
                "error_code": exc.code.value,
                "recoverable": exc.recoverable,
                "recovery_hint": exc.recovery_hint,
            },
        }

        return JSONResponse(
            status_code=status_code,
            content=response_data,
        )

    @app.exception_handler(AppError)
    async def api_exception_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle custom API exceptions"""
        # Record error metric for monitoring
        record_error("app_error", "api")

        if exc.status_code == 404:
            logger.info(f"NotFound: {exc.msg}")
        else:
            logger.warning(f"APIException: {exc.msg}")
        return JSONResponse(
            status_code=exc.status_code,
            content=APIResponse(code=exc.code, msg=exc.msg, data=None).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handle HTTP exceptions"""
        logger.warning(f"HTTPException: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content=APIResponse(code=exc.status_code, msg=exc.detail, data=None).model_dump(),
        )

    @app.exception_handler(TimeoutError)
    async def timeout_exception_handler(request: Request, exc: TimeoutError) -> JSONResponse:
        """Handle timeout exceptions"""
        # Record error metric for monitoring
        record_error("timeout", "api")

        logger.error(f"Timeout error: {exc!s}")
        return JSONResponse(
            status_code=504,
            content=APIResponse(
                code=504,
                msg=str(exc) if str(exc) else "Operation timed out",
                data={"recoverable": True, "retry_after_seconds": 5},
            ).model_dump(),
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all uncaught exceptions"""
        # Record error metric for monitoring
        record_error("unhandled_exception", "api")

        logger.exception(f"Unhandled exception: {exc!s}")
        return JSONResponse(
            status_code=500,
            content=APIResponse(code=500, msg="Internal server error", data=None).model_dump(),
        )
