import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.application.errors.exceptions import AppError
from app.core.prometheus_metrics import record_error
from app.domain.exceptions.base import (
    AuthenticationException,
    AuthorizationException,
    ConfigurationException,
    DomainException,
    IntegrationException,
    InvalidStateException,
    ResourceLimitExceeded,
    ResourceNotFoundException,
    SecurityViolation,
    ToolNotFoundException,
)
from app.domain.exceptions.browser import (
    BrowserError,
    ConnectionPoolExhaustedError,
)
from app.domain.models.recovery import (
    MalformedResponseError,
    RecoveryBudgetExhaustedError,
)
from app.interfaces.schemas.base import APIResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers"""

    # ── Domain Exception Handlers ─────────────────────────────────

    @app.exception_handler(ResourceNotFoundException)
    async def resource_not_found_handler(request: Request, exc: ResourceNotFoundException) -> JSONResponse:
        """Handle domain resource-not-found errors. Returns 404."""
        record_error("resource_not_found", exc.resource_type)
        logger.info(f"Resource not found: {exc.message}")
        return JSONResponse(
            status_code=404,
            content=APIResponse(code=404, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(InvalidStateException)
    async def invalid_state_handler(request: Request, exc: InvalidStateException) -> JSONResponse:
        """Handle invalid state errors. Returns 409 Conflict."""
        record_error("invalid_state", "domain")
        logger.warning(f"Invalid state: {exc.message}")
        return JSONResponse(
            status_code=409,
            content=APIResponse(code=409, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(ResourceLimitExceeded)
    async def resource_limit_handler(request: Request, exc: ResourceLimitExceeded) -> JSONResponse:
        """Handle resource limit exceeded errors. Returns 429."""
        record_error("resource_limit_exceeded", "domain")
        logger.warning(f"Resource limit exceeded: {exc.message}")
        return JSONResponse(
            status_code=429,
            content=APIResponse(code=429, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(AuthenticationException)
    async def authentication_handler(request: Request, exc: AuthenticationException) -> JSONResponse:
        """Handle authentication failures. Returns 401."""
        record_error("authentication_failed", "auth")
        logger.warning(f"Authentication failed: {exc.message}")
        return JSONResponse(
            status_code=401,
            content=APIResponse(code=401, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(AuthorizationException)
    async def authorization_handler(request: Request, exc: AuthorizationException) -> JSONResponse:
        """Handle authorization failures. Returns 403."""
        record_error("authorization_failed", "auth")
        logger.warning(f"Authorization failed: {exc.message}")
        return JSONResponse(
            status_code=403,
            content=APIResponse(code=403, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(SecurityViolation)
    async def security_violation_handler(request: Request, exc: SecurityViolation) -> JSONResponse:
        """Handle security violations (path traversal, injection, etc.). Returns 403."""
        record_error("security_violation", "security")
        logger.error(f"Security violation: {exc.message}")
        return JSONResponse(
            status_code=403,
            content=APIResponse(code=403, msg="Access denied", data=None).model_dump(),
        )

    @app.exception_handler(ConfigurationException)
    async def configuration_handler(request: Request, exc: ConfigurationException) -> JSONResponse:
        """Handle configuration errors. Returns 503."""
        record_error("configuration_error", "config")
        logger.error(f"Configuration error: {exc.message}")
        return JSONResponse(
            status_code=503,
            content=APIResponse(code=503, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(ToolNotFoundException)
    async def tool_not_found_handler(request: Request, exc: ToolNotFoundException) -> JSONResponse:
        """Handle tool-not-found errors. Returns 400."""
        record_error("tool_not_found", "tools")
        logger.warning(f"Tool not found: {exc.message}")
        return JSONResponse(
            status_code=400,
            content=APIResponse(code=400, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(IntegrationException)
    async def integration_handler(request: Request, exc: IntegrationException) -> JSONResponse:
        """Handle external integration failures. Returns 502."""
        record_error("integration_error", exc.service)
        logger.error(f"Integration error ({exc.service}): {exc.message}")
        return JSONResponse(
            status_code=502,
            content=APIResponse(code=502, msg=exc.message, data=None).model_dump(),
        )

    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
        """Catch-all handler for domain exceptions not caught by more specific handlers.

        Returns 400 Bad Request as a safe default.
        """
        record_error("domain_error", "domain")
        logger.warning(f"Domain error [{exc.error_code}]: {exc.message}")
        return JSONResponse(
            status_code=400,
            content=APIResponse(code=400, msg=exc.message, data=None).model_dump(),
        )

    # ── Browser Exception Handlers ────────────────────────────────

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
                msg=str(exc) or "Operation timed out",
                data={"recoverable": True, "retry_after_seconds": 5},
            ).model_dump(),
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(RecoveryBudgetExhaustedError)
    async def recovery_budget_exhausted_handler(request: Request, exc: RecoveryBudgetExhaustedError) -> JSONResponse:
        """Handle recovery budget exhaustion.

        Returns 429 Too Many Requests with retry-after hint.
        """
        # Record error metric for monitoring
        record_error("recovery_budget_exhausted", "agent")

        logger.warning(f"Recovery budget exhausted: {exc.attempt_count} attempts (reason: {exc.recovery_reason.value})")

        response_data: dict[str, Any] = {
            "code": 429,
            "msg": "Agent recovery attempts exhausted",
            "data": {
                "error": "recovery_budget_exhausted",
                "message": str(exc),
                "attempt_count": exc.attempt_count,
                "max_retries": exc.max_retries,
                "recovery_reason": exc.recovery_reason.value,
                "retry_after_seconds": exc.cooldown_seconds,
                "recoverable": True,
                "recovery_hint": "Wait before retrying the task",
            },
        }

        return JSONResponse(
            status_code=429,
            content=response_data,
            headers={"Retry-After": str(exc.cooldown_seconds)},
        )

    @app.exception_handler(MalformedResponseError)
    async def malformed_response_handler(request: Request, exc: MalformedResponseError) -> JSONResponse:
        """Handle malformed LLM responses.

        Returns 422 Unprocessable Entity for validation/format errors.
        """
        # Record error metric for monitoring
        record_error("malformed_response", "agent")

        logger.error(
            f"Malformed response detected: {exc.detection_reason.value}",
            extra={
                "detection_reason": exc.detection_reason.value,
                "response_preview": exc.response_text[:200],
            },
        )

        response_data: dict[str, Any] = {
            "code": 422,
            "msg": "LLM response is malformed and could not be processed",
            "data": {
                "error": "malformed_response",
                "message": str(exc),
                "detection_reason": exc.detection_reason.value,
                "response_preview": exc.response_text[:200],
                "recoverable": True,
                "recovery_hint": "Retry the request with modified input",
            },
        }

        return JSONResponse(
            status_code=422,
            content=response_data,
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
