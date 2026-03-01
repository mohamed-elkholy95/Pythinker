import time
import uuid
from collections.abc import Callable
from typing import ClassVar

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.infrastructure.storage.redis import get_redis
from app.infrastructure.structured_logging import get_logger, request_id_var, set_request_id

logger = get_logger(__name__)
settings = get_settings()


class RequestLoggingMiddleware:
    """Middleware to log HTTP requests and add correlation IDs"""

    # Paths to exclude from logging (health checks, static files)
    EXCLUDED_PATHS: ClassVar[set[str]] = {"/health", "/api/v1/health", "/favicon.ico"}
    # Sensitive headers to redact
    SENSITIVE_HEADERS: ClassVar[set[str]] = {"authorization", "cookie", "x-api-key"}

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Skip logging for excluded paths
        if path in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        # Generate request ID
        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])
        start_time = time.time()

        # Store request_id in state for access in handlers
        scope["state"] = scope.get("state", {})
        scope["state"]["request_id"] = request_id

        # Propagate request_id to structlog for correlation
        request_id_token = set_request_id(request_id)

        # Log request (sanitized)
        client_ip = request.client.host if request.client else "unknown"
        logger.info("request_started", method=request.method, path=path, client_ip=client_ip)

        # Capture response status
        response_status = 500

        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                # Add request ID to response headers
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.error("request_failed", exc_info=True)
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            log_kw = {
                "method": request.method,
                "path": path,
                "status": response_status,
                "duration_ms": round(duration_ms, 2),
            }
            if response_status < 400:
                logger.info("request_completed", **log_kw)
            else:
                logger.warning("request_completed", **log_kw)
            # Reset ContextVar to avoid request_id leaking into the next
            # request processed by the same asyncio task.
            request_id_var.reset(request_id_token)


class RateLimitMiddleware:
    """Middleware to implement rate limiting using Redis with in-memory fallback.

    Security: If Redis is unavailable, falls back to in-memory rate limiting
    to prevent authentication bypass attacks.
    """

    # Auth endpoints have stricter limits
    AUTH_PATHS: ClassVar[set[str]] = {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/send-verification-code",
        "/api/v1/auth/reset-password",
    }

    # Exempt paths: SSE long-poll, health checks, lightweight status polls
    EXEMPT_PATHS: ClassVar[set[str]] = {"/api/v1/auth/status", "/health"}

    # In-memory fallback storage: {key: (count, window_start_time)}
    _fallback_storage: ClassVar[dict] = {}
    _fallback_cleanup_counter: ClassVar[int] = 0
    _fallback_cleanup_interval: ClassVar[int] = 100  # Cleanup every N requests
    _fallback_last_cleanup_time: ClassVar[float] = 0.0  # Last cleanup timestamp
    _fallback_cleanup_time_interval: ClassVar[float] = 60.0  # Cleanup every 60 seconds
    _RATE_LIMIT_WINDOW_SCRIPT: ClassVar[str] = """
    local current = redis.call("INCR", KEYS[1])
    if current == 1 then
        redis.call("EXPIRE", KEYS[1], tonumber(ARGV[1]))
    end
    local ttl = redis.call("TTL", KEYS[1])
    return {current, ttl}
    """

    def __init__(self, app: Callable):
        self.app = app
        # Initialize cleanup timestamp on first instantiation
        if RateLimitMiddleware._fallback_last_cleanup_time == 0.0:
            RateLimitMiddleware._fallback_last_cleanup_time = time.time()

    async def _increment_window_counter(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Atomically increment request counter and return (current_count, ttl_seconds)."""
        redis_client = get_redis()
        await redis_client.initialize()
        # Always re-register: redis-py Script objects are cheaply re-created
        # and must be bound to the current client instance after reconnects.
        script = redis_client.client.register_script(self._RATE_LIMIT_WINDOW_SCRIPT)

        async def _execute_script():
            return await script(keys=[key], args=[window_seconds], client=redis_client.client)

        result = await redis_client.execute_with_retry(
            _execute_script,
            operation_name="rate_limit_window_script",
        )
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError(f"Unexpected rate limit script result: {result!r}")

        current = int(result[0])
        ttl = int(result[1]) if result[1] is not None else window_seconds
        if ttl <= 0:
            ttl = window_seconds
        return current, ttl

    def _cleanup_fallback_storage(self) -> None:
        """Remove expired entries from fallback storage to prevent memory growth.

        Each key stores its own window_seconds to avoid cross-bucket eviction
        when auth and general endpoints use different rate-limit windows.
        """
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, window_start, key_window) in self._fallback_storage.items()
            if current_time - window_start > key_window
        ]
        for key in expired_keys:
            del self._fallback_storage[key]

    def _fallback_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """In-memory rate limiting fallback when Redis is unavailable.

        Returns:
            tuple of (is_allowed, current_count)
        """
        current_time = time.time()

        # Periodic cleanup to prevent memory growth
        # Triggers on either: 100 requests OR 60 seconds (whichever comes first)
        self._fallback_cleanup_counter += 1
        time_since_last_cleanup = current_time - self._fallback_last_cleanup_time
        should_cleanup = (
            self._fallback_cleanup_counter >= self._fallback_cleanup_interval
            or time_since_last_cleanup >= self._fallback_cleanup_time_interval
        )
        if should_cleanup:
            self._cleanup_fallback_storage()
            self._fallback_cleanup_counter = 0
            self._fallback_last_cleanup_time = current_time

        if key in self._fallback_storage:
            count, window_start, _key_window = self._fallback_storage[key]

            # Check if window has expired
            if current_time - window_start > window_seconds:
                # Start new window
                self._fallback_storage[key] = (1, current_time, window_seconds)
                return True, 1
            # Increment count in current window
            new_count = count + 1
            self._fallback_storage[key] = (new_count, window_start, window_seconds)
            return new_count <= max_requests, new_count
        # New key, start window
        self._fallback_storage[key] = (1, current_time, window_seconds)
        return True, 1

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path
        method = request.method

        # Exempt health checks and auth status from rate limiting
        if path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Lightweight session status polling (GET /sessions/{id}/status) - high frequency, low payload
        if method == "GET" and path.endswith("/status") and "/sessions/" in path:
            await self.app(scope, receive, send)
            return

        # SSE endpoints (POST /sessions for session list, POST /sessions/{id}/chat)
        # are long-lived streaming connections — exempt from rate limiting
        if method == "POST" and (path == "/api/v1/sessions" or "/chat" in path):
            await self.app(scope, receive, send)
            return

        # Determine rate limit based on path
        if path in self.AUTH_PATHS:
            max_requests = settings.rate_limit_auth_requests_per_minute
        else:
            max_requests = settings.rate_limit_requests_per_minute

        # Get client identifier (IP or user ID from token)
        client_id = request.client.host if request.client else "unknown"
        # Use method + normalized path for granular buckets
        # Strip session IDs to group per-endpoint (e.g., GET /sessions/* → one bucket)
        parts = path.split("/")
        if len(parts) > 4:
            # Normalize: /api/v1/sessions/{id}/action → sessions:action
            bucket = f"{parts[3]}:{parts[-1]}"
        elif len(parts) > 3:
            bucket = parts[3]
        else:
            bucket = "default"
        key = f"rate_limit:{client_id}:{method}:{bucket}"

        rate_limit_exceeded = False
        using_fallback = False
        window_seconds = max(1, settings.rate_limit_window_seconds)
        retry_after_seconds = window_seconds

        try:
            # Atomically increment counter and preserve TTL window.
            # Context7/Redis docs recommend this pattern to avoid INCR/EXPIRE race windows.
            current, ttl = await self._increment_window_counter(key, window_seconds)

            # Check if rate limit exceeded
            if current > max_requests:
                rate_limit_exceeded = True
                retry_after_seconds = max(1, ttl)

        except Exception as e:
            # SECURITY FIX: Fall back to in-memory rate limiting instead of allowing all requests
            logger.warning(f"Redis unavailable for rate limiting, using in-memory fallback: {e}")
            using_fallback = True
            try:
                from app.core.prometheus_metrics import rate_limit_fallback_total

                rate_limit_fallback_total.inc({"reason": "redis_unavailable"})
            except Exception:
                logger.debug("Failed to emit rate-limit fallback metric", exc_info=True)

            is_allowed, current = self._fallback_rate_limit(key, max_requests, window_seconds)
            if not is_allowed:
                rate_limit_exceeded = True
                # In-memory: estimate remaining from window
                if key in self._fallback_storage:
                    _, window_start, _key_window = self._fallback_storage[key]
                    retry_after_seconds = max(1, int(window_seconds - (time.time() - window_start)))

        if rate_limit_exceeded:
            logger.warning(
                f"Rate limit exceeded for {client_id} on {path}{' (fallback mode)' if using_fallback else ''}"
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Too many requests. Retry after {retry_after_seconds} seconds.",
                        "retry_after": retry_after_seconds,
                    },
                },
                headers={"Retry-After": str(retry_after_seconds)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
