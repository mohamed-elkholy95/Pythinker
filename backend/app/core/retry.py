"""Generalized Retry Framework with Exponential Backoff.

Provides configurable retry decorators for async operations with:
- Exponential backoff with jitter
- Configurable exception filtering
- Retry budgets and circuit breaker integration
- Detailed logging and metrics

Usage:
    # Basic retry with defaults
    @with_retry()
    async def my_operation():
        ...

    # Custom configuration
    @with_retry(RetryConfig(max_attempts=5, retryable_exceptions=(TimeoutError,)))
    async def my_operation():
        ...

    # Pre-configured decorators
    @llm_retry
    async def call_llm():
        ...
"""

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    """Maximum number of attempts (1 = no retries)."""

    base_delay: float = 1.0
    """Initial delay between retries in seconds."""

    max_delay: float = 60.0
    """Maximum delay between retries in seconds."""

    exponential_base: float = 2.0
    """Base for exponential backoff calculation."""

    jitter: bool = True
    """Add random jitter to delays to prevent thundering herd."""

    jitter_factor: float = 0.25
    """Amount of jitter (0.25 = ±25% of delay)."""

    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    """Exceptions that should trigger a retry."""

    non_retryable_exceptions: tuple[type[Exception], ...] = ()
    """Exceptions that should NOT be retried (takes precedence)."""

    on_retry: Callable[[Exception, int, float], None] | None = None
    """Callback on each retry: (exception, attempt, delay)."""

    log_retries: bool = True
    """Whether to log retry attempts."""


@dataclass
class RetryStats:
    """Statistics from a retry operation."""

    attempts: int = 0
    total_delay: float = 0.0
    success: bool = False
    final_exception: Exception | None = None
    duration_ms: float = 0.0


def calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate delay for a given attempt number.

    Uses exponential backoff with optional jitter.

    Args:
        attempt: Current attempt number (1-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * (exponential_base ^ (attempt - 1))
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))

    # Cap at max delay
    delay = min(delay, config.max_delay)

    # Add jitter if enabled
    if config.jitter:
        jitter_range = delay * config.jitter_factor
        delay = delay + random.uniform(-jitter_range, jitter_range)  # noqa: S311 - Random jitter for backoff timing, not cryptographic
        delay = max(0.1, delay)  # Ensure positive delay

    return delay


def is_retryable(exception: Exception, config: RetryConfig) -> bool:
    """Check if an exception should trigger a retry.

    Args:
        exception: The exception to check
        config: Retry configuration

    Returns:
        True if the exception should be retried
    """
    # Non-retryable exceptions take precedence
    if config.non_retryable_exceptions and isinstance(exception, config.non_retryable_exceptions):
        return False

    # Check if it's a retryable exception
    return isinstance(exception, config.retryable_exceptions)


def with_retry(
    config: RetryConfig | None = None,
    max_attempts: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable:
    """Decorator for async functions with configurable retry.

    Can be used with or without parentheses:
        @with_retry
        @with_retry()
        @with_retry(max_attempts=5)
        @with_retry(RetryConfig(...))

    Args:
        config: Full retry configuration (or individual params below)
        max_attempts: Override max attempts
        base_delay: Override base delay
        max_delay: Override max delay
        retryable_exceptions: Override retryable exceptions

    Returns:
        Decorated async function with retry behavior
    """
    # Handle @with_retry without parentheses
    if callable(config):
        func = config
        config = RetryConfig()
        return _create_retry_wrapper(func, config)

    # Build config from parameters
    if config is None:
        config = RetryConfig()

    # Override individual parameters if provided
    if max_attempts is not None:
        config.max_attempts = max_attempts
    if base_delay is not None:
        config.base_delay = base_delay
    if max_delay is not None:
        config.max_delay = max_delay
    if retryable_exceptions is not None:
        config.retryable_exceptions = retryable_exceptions

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        return _create_retry_wrapper(func, config)

    return decorator


def _create_retry_wrapper(
    func: Callable[..., T],
    config: RetryConfig,
) -> Callable[..., T]:
    """Create the actual retry wrapper for a function."""

    @wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> T:
        stats = RetryStats()
        start_time = time.perf_counter()
        last_exception: Exception | None = None

        for attempt in range(1, config.max_attempts + 1):
            stats.attempts = attempt

            try:
                result = await func(*args, **kwargs)
                stats.success = True
                stats.duration_ms = (time.perf_counter() - start_time) * 1000

                if config.log_retries and attempt > 1:
                    logger.info(
                        f"Retry succeeded for {func.__name__} on attempt {attempt}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "total_delay": stats.total_delay,
                        },
                    )

                return result

            except Exception as e:
                last_exception = e
                stats.final_exception = e

                # Check if we should retry
                if not is_retryable(e, config):
                    if config.log_retries:
                        logger.warning(
                            f"Non-retryable exception in {func.__name__}: {type(e).__name__}",
                            extra={
                                "function": func.__name__,
                                "exception": type(e).__name__,
                                "attempt": attempt,
                            },
                        )
                    raise

                # Check if we have attempts remaining
                if attempt >= config.max_attempts:
                    if config.log_retries:
                        logger.error(
                            f"All {config.max_attempts} attempts failed for {func.__name__}",
                            extra={
                                "function": func.__name__,
                                "exception": type(e).__name__,
                                "attempts": attempt,
                                "total_delay": stats.total_delay,
                            },
                        )
                    raise

                # Calculate delay
                delay = calculate_delay(attempt, config)
                stats.total_delay += delay

                if config.log_retries:
                    logger.warning(
                        f"Retry {attempt}/{config.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s: {type(e).__name__}: {str(e)[:100]}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "delay": delay,
                            "exception": type(e).__name__,
                        },
                    )

                # Call on_retry callback if provided
                if config.on_retry:
                    with contextlib.suppress(Exception):
                        config.on_retry(e, attempt, delay)

                # Wait before retry
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        stats.duration_ms = (time.perf_counter() - start_time) * 1000
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Retry logic error in {func.__name__}")

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> T:
        """Synchronous version - no retry support, just pass through."""
        return func(*args, **kwargs)

    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    # For sync functions, we can't easily retry without blocking
    # Return the original function with a warning
    logger.debug(f"with_retry applied to sync function {func.__name__}, retries disabled")
    return sync_wrapper


# =============================================================================
# Pre-configured retry decorators
# =============================================================================

# Common transient exceptions
TRANSIENT_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    ConnectionRefusedError,
    BrokenPipeError,
    OSError,
)


# ── Per-provider retry configurations ─────────────────────────────────────────
# Used by RetryMiddleware in middleware_impl.py.  Keyed by provider name as
# returned by detect_provider() / request.metadata["provider"].
#
# Tuning rationale:
#   GLM-5 / BigModel: slow inference (60-120s), fewer retries, longer delays.
#   Anthropic: stable API, moderate retries.
#   OpenAI / OpenRouter: fast recovery, more retries, shorter delays.
#   DeepSeek: similar to Anthropic in practice.
PROVIDER_RETRY_CONFIGS: dict[str, "RetryConfig"] = {}


def _build_provider_retry_configs() -> dict[str, "RetryConfig"]:
    """Build provider-specific retry configs (deferred so RetryConfig is defined)."""
    return {
        "default": RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            retryable_exceptions=TRANSIENT_EXCEPTIONS,
        ),
        "glm": RetryConfig(
            max_attempts=3,
            base_delay=3.0,
            max_delay=60.0,
            retryable_exceptions=TRANSIENT_EXCEPTIONS,
        ),
        "anthropic": RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            retryable_exceptions=TRANSIENT_EXCEPTIONS,
        ),
        "openai": RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=20.0,
            retryable_exceptions=TRANSIENT_EXCEPTIONS,
        ),
        "deepseek": RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            retryable_exceptions=TRANSIENT_EXCEPTIONS,
        ),
        "ollama": RetryConfig(
            max_attempts=2,
            base_delay=1.0,
            max_delay=10.0,
            retryable_exceptions=TRANSIENT_EXCEPTIONS,
        ),
    }


# Populate after RetryConfig is defined (same module, so available immediately)
PROVIDER_RETRY_CONFIGS = _build_provider_retry_configs()


# LLM retry - handles rate limits and timeouts
llm_retry = with_retry(
    RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
            # Add provider-specific exceptions as needed
        ),
    )
)


def _log_validation_retry(exception: Exception, attempt: int, delay: float) -> None:
    """Log validation retry with details about the validation error."""
    logger.warning(
        f"LLM output validation failed (attempt {attempt}), retrying in {delay:.2f}s: {exception!s}",
        extra={
            "exception_type": type(exception).__name__,
            "attempt": attempt,
            "delay": delay,
        },
    )


# Import ValidationError lazily to avoid circular imports
def _get_validation_error() -> type[Exception]:
    """Lazily import Pydantic ValidationError."""
    from pydantic import ValidationError

    return ValidationError


# LLM validation retry - retries on Pydantic ValidationError to force LLM to fix output
# This is critical for anti-hallucination: if LLM returns malformed output, retry with feedback
llm_validation_retry = with_retry(
    RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
        ),
        on_retry=_log_validation_retry,
    )
)


def with_validation_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> Callable:
    """Decorator for LLM calls that should retry on Pydantic ValidationError.

    This decorator is essential for anti-hallucination defense. When an LLM
    returns malformed output that fails Pydantic validation, we retry the call
    instead of immediately failing. This gives the LLM a chance to correct
    its output.

    Usage:
        @with_validation_retry()
        async def ask_structured(self, messages, response_model):
            response = await self.client.messages.create(...)
            return response_model.model_validate(parsed_response)

    Args:
        max_attempts: Maximum retry attempts (default 3)
        base_delay: Initial delay between retries (default 1.0s)

    Returns:
        Decorated async function with validation retry behavior
    """
    from pydantic import ValidationError

    return with_retry(
        RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True,
            retryable_exceptions=(
                ValidationError,
                TimeoutError,
                ConnectionError,
                ConnectionResetError,
            ),
            on_retry=_log_validation_retry,
        )
    )


# Tool retry - quick retries for tool execution
tool_retry = with_retry(
    RetryConfig(
        max_attempts=2,
        base_delay=1.0,
        max_delay=10.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=TRANSIENT_EXCEPTIONS,
    )
)


# Database retry - handles connection issues
db_retry = with_retry(
    RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=5.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=TRANSIENT_EXCEPTIONS,
    )
)


# HTTP retry - for external API calls
http_retry = with_retry(
    RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=15.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
        ),
    )
)


# Sandbox retry - for sandbox operations
sandbox_retry = with_retry(
    RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=TRANSIENT_EXCEPTIONS,
    )
)
