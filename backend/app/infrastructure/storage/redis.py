import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import lru_cache
from typing import Any, TypeVar

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import get_settings
from app.core.retry import RetryConfig, calculate_delay

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation - requests flow through
    OPEN = "open"  # Failing - reject requests immediately
    HALF_OPEN = "half_open"  # Testing recovery - allow limited requests


@dataclass
class CircuitBreaker:
    """Circuit breaker for Redis connection resilience.

    Prevents cascade failures by tracking connection errors and temporarily
    blocking requests when the failure threshold is exceeded.
    """

    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: float = 30.0  # Seconds before attempting recovery
    half_open_max_calls: int = 3  # Successful calls to close circuit

    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    last_failure_time: datetime | None = field(default=None)
    half_open_successes: int = field(default=0)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def can_execute(self) -> bool:
        """Check if request can proceed through the circuit."""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    logger.info("Circuit breaker transitioning to HALF_OPEN for recovery test")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_successes = 0
                    return True
                return False

            # HALF_OPEN - allow limited calls to test recovery
            return True

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return True
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)

    async def record_success(self) -> None:
        """Record a successful operation."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_successes += 1
                if self.half_open_successes >= self.half_open_max_calls:
                    logger.info("Circuit breaker CLOSED after successful recovery")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.half_open_successes = 0
            elif self.state == CircuitState.CLOSED:
                # Decay failure count on success
                self.failure_count = max(0, self.failure_count - 1)

    async def record_failure(self) -> None:
        """Record a failed operation."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery - back to OPEN
                logger.warning("Circuit breaker OPEN - recovery attempt failed")
                self.state = CircuitState.OPEN
                self.half_open_successes = 0
            elif self.failure_count >= self.failure_threshold:
                logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")
                self.state = CircuitState.OPEN

    def get_state_info(self) -> dict[str, Any]:
        """Get circuit breaker state information for monitoring."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "half_open_successes": self.half_open_successes,
        }


class RedisClient:
    """Redis client with circuit breaker, auto-reconnection, and connection health monitoring."""

    def __init__(self, role: str = "runtime"):
        if role not in {"runtime", "cache"}:
            raise ValueError(f"Unsupported Redis client role: {role}")
        self._role = role
        self._client: Redis | None = None
        self._settings = get_settings()
        self._host = (
            getattr(self._settings, "redis_cache_host", self._settings.redis_host)
            if self._role == "cache"
            else self._settings.redis_host
        )
        self._port = (
            getattr(self._settings, "redis_cache_port", self._settings.redis_port)
            if self._role == "cache"
            else self._settings.redis_port
        )
        self._db = (
            getattr(self._settings, "redis_cache_db", self._settings.redis_db)
            if self._role == "cache"
            else self._settings.redis_db
        )
        self._password = (
            getattr(self._settings, "redis_cache_password", self._settings.redis_password)
            if self._role == "cache"
            else self._settings.redis_password
        )
        self._max_connections = (
            getattr(self._settings, "redis_cache_max_connections", self._settings.redis_max_connections)
            if self._role == "cache"
            else self._settings.redis_max_connections
        )
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=getattr(self._settings, "redis_circuit_breaker_threshold", 5),
            recovery_timeout=getattr(self._settings, "redis_circuit_breaker_recovery_timeout", 30.0),
        )
        self._connection_lock = asyncio.Lock()
        self._last_health_check: datetime | None = None
        self._health_check_interval = 10  # seconds

    async def initialize(self) -> None:
        """Initialize Redis connection with auto-reconnection support."""
        async with self._connection_lock:
            if self._client is not None:
                # Check if existing connection is healthy
                if await self._is_healthy():
                    return
                # Connection dead, close and reconnect
                logger.warning("Redis connection unhealthy, reconnecting...")
                await self._close_client()

            await self._connect()

    async def _connect(self) -> None:
        """Internal connection method with circuit breaker protection."""
        if not await self._circuit_breaker.can_execute():
            raise ConnectionError(
                f"Redis circuit breaker is {self._circuit_breaker.state.value}, "
                f"will retry after {self._circuit_breaker.recovery_timeout}s"
            )

        try:
            self._client = Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                decode_responses=True,
                max_connections=self._max_connections,
                socket_timeout=self._settings.redis_socket_timeout,
                socket_connect_timeout=self._settings.redis_socket_connect_timeout,
                health_check_interval=self._settings.redis_health_check_interval,
                retry_on_timeout=self._settings.redis_retry_on_timeout,
            )
            await self._client.ping()
            await self._circuit_breaker.record_success()
            self._last_health_check = datetime.now()
            logger.info(
                "Successfully connected to Redis (%s) at %s:%s/%s",
                self._role,
                self._host,
                self._port,
                self._db,
            )
        except Exception as e:
            await self._circuit_breaker.record_failure()
            logger.error("Failed to connect to Redis (%s): %s", self._role, e)
            raise

    async def _is_healthy(self) -> bool:
        """Check if the current connection is healthy."""
        if self._client is None:
            return False

        # Throttle health checks to avoid overhead
        now = datetime.now()
        if self._last_health_check and (now - self._last_health_check).total_seconds() < self._health_check_interval:
            return True

        try:
            await asyncio.wait_for(self._client.ping(), timeout=2.0)
            self._last_health_check = now
            return True
        except Exception:
            return False

    async def _close_client(self) -> None:
        """Safely close the Redis client."""
        if self._client:
            try:
                await asyncio.wait_for(self._client.close(), timeout=5.0)
            except Exception as e:
                logger.debug(f"Error closing Redis client: {e}")
            finally:
                self._client = None

    async def shutdown(self) -> None:
        """Shutdown Redis connection."""
        async with self._connection_lock:
            await self._close_client()
            logger.info("Disconnected from Redis (%s)", self._role)
        if self._role == "cache":
            get_cache_redis.cache_clear()
        else:
            get_redis.cache_clear()

    @property
    def client(self) -> Redis:
        """Return initialized Redis client."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized. Call initialize() first.")
        return self._client

    @property
    def role(self) -> str:
        """Redis client role (`runtime` or `cache`)."""
        return self._role

    async def call(
        self,
        method_name: str,
        *args: Any,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> Any:
        """Execute a Redis command method with retry and reconnection.

        Example:
            await get_redis().call("setex", key, ttl, value)
        """

        async def _operation() -> Any:
            method = getattr(self.client, method_name)
            return await method(*args, **kwargs)

        return await self.execute_with_retry(
            _operation,
            max_retries=max_retries,
            operation_name=method_name.lower(),
        )

    async def execute_with_retry(
        self,
        operation: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
        operation_name: str = "unknown",
        **kwargs: Any,
    ) -> T:
        """Execute a Redis operation with automatic retry and reconnection.

        Args:
            operation: The async Redis operation to execute
            *args: Positional arguments for the operation
            max_retries: Maximum number of retry attempts
            **kwargs: Keyword arguments for the operation

        Returns:
            The result of the operation

        Raises:
            ConnectionError: If circuit breaker is open
            Exception: If all retries fail
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                # Ensure connection is initialized and healthy
                await self.initialize()

                # Execute the operation
                result = await operation(*args, **kwargs)
                await self._circuit_breaker.record_success()
                return result

            except (RedisConnectionError, RedisTimeoutError, OSError) as e:
                last_error = e
                await self._circuit_breaker.record_failure()
                try:
                    from app.core.prometheus_metrics import redis_operation_retries_total

                    redis_operation_retries_total.inc({"role": self._role, "operation": operation_name})
                except Exception:
                    logger.debug("Failed to emit redis retry metric", exc_info=True)

                if attempt < max_retries - 1:
                    # Use centralized exponential backoff
                    retry_config = RetryConfig(
                        base_delay=0.1,
                        exponential_base=2.0,
                        max_delay=1.0,  # Cap at 1s
                        jitter=True,
                    )
                    backoff = calculate_delay(attempt + 1, retry_config)
                    logger.warning(
                        "Redis operation '%s' failed (attempt %s/%s), retrying in %.2fs: %s",
                        operation_name,
                        attempt + 1,
                        max_retries,
                        backoff,
                        e,
                    )
                    await self._close_client()  # Force reconnection on next attempt
                    await asyncio.sleep(backoff)
                else:
                    logger.error("Redis operation '%s' failed after %s attempts: %s", operation_name, max_retries, e)
                    try:
                        from app.core.prometheus_metrics import redis_operation_failures_total

                        redis_operation_failures_total.inc({"role": self._role, "error_type": type(e).__name__})
                    except Exception:
                        logger.debug("Failed to emit redis failure metric", exc_info=True)

            except Exception as e:
                # Non-connection errors don't trigger circuit breaker
                logger.error(f"Redis operation error (non-connection): {e}")
                raise

        raise last_error or ConnectionError("Redis operation failed after all retries")

    def get_circuit_breaker_state(self) -> dict[str, Any]:
        """Get circuit breaker state for monitoring/health checks."""
        return self._circuit_breaker.get_state_info()


@lru_cache
def get_redis() -> RedisClient:
    """Get the Redis client singleton instance."""
    return RedisClient(role="runtime")


@lru_cache
def get_cache_redis() -> RedisClient:
    """Get the cache Redis client singleton instance."""
    return RedisClient(role="cache")
