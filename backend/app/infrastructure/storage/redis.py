import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import lru_cache
from typing import Any, Callable, TypeVar

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import get_settings

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

    def __init__(self):
        self._client: Redis | None = None
        self._settings = get_settings()
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
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                db=self._settings.redis_db,
                password=self._settings.redis_password,
                decode_responses=True,
                max_connections=self._settings.redis_max_connections,
                socket_timeout=self._settings.redis_socket_timeout,
                socket_connect_timeout=self._settings.redis_socket_connect_timeout,
                health_check_interval=self._settings.redis_health_check_interval,
                retry_on_timeout=self._settings.redis_retry_on_timeout,
            )
            await self._client.ping()
            await self._circuit_breaker.record_success()
            self._last_health_check = datetime.now()
            logger.info("Successfully connected to Redis")
        except Exception as e:
            await self._circuit_breaker.record_failure()
            logger.error(f"Failed to connect to Redis: {e!s}")
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
            logger.info("Disconnected from Redis")
        get_redis.cache_clear()

    @property
    def client(self) -> Redis:
        """Return initialized Redis client."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized. Call initialize() first.")
        return self._client

    async def execute_with_retry(
        self,
        operation: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
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

                if attempt < max_retries - 1:
                    backoff = 0.1 * (2**attempt)  # Exponential backoff: 0.1, 0.2, 0.4s
                    logger.warning(f"Redis operation failed (attempt {attempt + 1}/{max_retries}), retrying in {backoff}s: {e}")
                    await self._close_client()  # Force reconnection on next attempt
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Redis operation failed after {max_retries} attempts: {e}")

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
    return RedisClient()
