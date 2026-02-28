"""Concrete LLM middleware implementations.

Each middleware handles one cross-cutting concern and delegates to
``next_handler`` for the rest of the chain.

Assembly order (outermost → innermost):
    ConcurrencyMiddleware      — gate on max-concurrent slots
    RetryMiddleware            — per-provider retry + backoff
    RetryBudgetMiddleware      — cross-layer retry cap per task
    CircuitBreakerMiddleware   — open/close on sustained failures
    KeyRotationMiddleware      — rotate API key on 401/429
    MessageNormalizerMiddleware — provider-specific message fixups
    MetricsMiddleware          — latency + token Prometheus counters

Import this module only from infrastructure — domain layer must not depend
on it.  The factory assembles the pipeline when
``feature_llm_middleware_pipeline=True``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.domain.services.llm.middleware import LLMCallable, LLMMiddleware, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


# ─────────────────────────── Phase 1: Concurrency ────────────────────────────


class ConcurrencyMiddleware(LLMMiddleware):
    """Gate LLM calls through the existing LLMConcurrencyLimiter semaphore.

    Falls back to a passthrough if concurrency limiting is disabled via
    ``llm_concurrency_enabled=False``.
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        from app.core.config import get_settings
        from app.domain.services.concurrency.llm_limiter import LLMConcurrencyLimiter

        settings = get_settings()
        if not getattr(settings, "llm_concurrency_enabled", True):
            return await next_handler(request)

        limiter = LLMConcurrencyLimiter.get_instance()
        async with limiter.acquire():
            return await next_handler(request)


# ─────────────────────────── Phase 1: Metrics ────────────────────────────────


class MetricsMiddleware(LLMMiddleware):
    """Record latency and token usage via Prometheus (lazy import, never raises).

    Adds to ``response.metadata``:
    - ``latency_ms``: wall-clock time of the inner chain
    - ``provider``: taken from ``request.metadata.get("provider", "unknown")``
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        provider = request.metadata.get("provider", "unknown")
        start = time.monotonic()
        error_occurred = False
        try:
            response = await next_handler(request)
        except Exception:
            error_occurred = True
            raise
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._record(provider, elapsed_ms, error_occurred, request, locals().get("response"))

        response.metadata["latency_ms"] = elapsed_ms
        response.metadata.setdefault("provider", provider)
        return response

    def _record(
        self,
        provider: str,
        elapsed_ms: float,
        error: bool,
        request: LLMRequest,
        response: LLMResponse | None,
    ) -> None:
        try:
            from app.infrastructure.external.observability.prometheus import get_prometheus_metrics

            metrics = get_prometheus_metrics()
            # Record latency histogram if available
            if hasattr(metrics, "record_llm_latency"):
                metrics.record_llm_latency(provider=provider, latency_ms=elapsed_ms)
            if error and hasattr(metrics, "increment_llm_error"):
                metrics.increment_llm_error(provider=provider)
            if response and response.usage and hasattr(metrics, "record_llm_tokens"):
                metrics.record_llm_tokens(
                    provider=provider,
                    prompt_tokens=response.usage.get("prompt_tokens", 0),
                    completion_tokens=response.usage.get("completion_tokens", 0),
                )
        except Exception as exc:
            # Metrics must never break LLM calls
            logger.debug("MetricsMiddleware: recording skipped: %s", exc)


# ─────────────────────────── Phase 2: Retry ──────────────────────────────────


class RetryMiddleware(LLMMiddleware):
    """Provider-aware exponential-backoff retry.

    Consults ``PROVIDER_RETRY_CONFIGS`` from ``core/retry.py`` and falls
    back to the generic ``llm_retry`` config when the provider is unknown.

    The provider name is read from ``request.metadata["provider"]``.
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        import asyncio

        from app.core.retry import PROVIDER_RETRY_CONFIGS, RetryConfig, calculate_delay, is_retryable

        provider = request.metadata.get("provider", "default")
        config: RetryConfig = PROVIDER_RETRY_CONFIGS.get(provider, PROVIDER_RETRY_CONFIGS["default"])

        last_exc: Exception | None = None
        for attempt in range(1, config.max_attempts + 1):
            try:
                return await next_handler(request)
            except Exception as exc:
                last_exc = exc
                if attempt >= config.max_attempts:
                    break
                if not is_retryable(exc, config):
                    raise
                delay = calculate_delay(attempt, config)
                logger.warning(
                    "LLM retry %d/%d for provider=%s after %.1fs: %s",
                    attempt,
                    config.max_attempts,
                    provider,
                    delay,
                    type(exc).__name__,
                )
                if config.on_retry:
                    config.on_retry(exc, attempt, delay)
                await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]


# ─────────────────────────── Phase 2: Retry Budget ───────────────────────────


class RetryBudgetMiddleware(LLMMiddleware):
    """Enforce a per-task retry cap across all middleware layers.

    Reads ``task_id`` from ``request.metadata``.  If the global retry
    budget for the task is exhausted, raises ``RuntimeError`` immediately
    (before attempting the call), preventing cascading retries from
    consuming excessive quota.
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        from app.core.config import get_settings

        settings = get_settings()
        if not getattr(settings, "feature_llm_retry_budget", False):
            return await next_handler(request)

        from app.domain.services.llm.retry_budget import get_retry_budget

        task_id = request.metadata.get("task_id", "unknown")
        budget = get_retry_budget()

        if not budget.can_retry(task_id):
            raise RuntimeError(
                f"Retry budget exhausted for task_id={task_id}. "
                "Refusing further LLM retry attempts."
            )

        try:
            return await next_handler(request)
        except Exception as exc:
            provider = request.metadata.get("provider", "unknown")
            budget.record_retry(task_id, provider, type(exc).__name__)
            raise


# ─────────────────────────── Phase 2: Key Rotation ───────────────────────────


class KeyRotationMiddleware(LLMMiddleware):
    """Rotate the active API key via ``APIKeyPool`` on 401/429 errors.

    After rotation the request is NOT retried here — the ``RetryMiddleware``
    above this in the chain handles the retry loop.  This middleware only
    signals the pool so the next attempt picks up a healthy key.
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        try:
            return await next_handler(request)
        except Exception as exc:
            await self._handle_key_error(exc, request)
            raise

    async def _handle_key_error(self, exc: Exception, request: LLMRequest) -> None:
        try:
            from app.infrastructure.external.key_pool import APIKeyPool

            pool: APIKeyPool | None = request.metadata.get("key_pool")
            if pool is None:
                return

            current_key: str | None = request.metadata.get("current_key")
            if current_key is None:
                return

            err_str = str(exc).lower()
            if "401" in err_str or "unauthorized" in err_str or "invalid" in err_str:
                await pool.mark_invalid(current_key)
            elif "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                await pool.mark_exhausted(current_key, ttl_seconds=3600)
        except Exception as exc:
            logger.debug("KeyRotationMiddleware: key error handling skipped: %s", exc)


# ─────────────────────────── Phase 3: Circuit Breaker ────────────────────────


class CircuitBreakerMiddleware(LLMMiddleware):
    """Wrap each provider in a circuit breaker.

    Uses the existing ``CircuitBreakerRegistry`` from ``core/``.
    The circuit name is ``llm:{provider}``.
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        from app.core.config import get_settings

        settings = get_settings()
        if not getattr(settings, "feature_llm_provider_fallback", False):
            return await next_handler(request)

        from app.core.circuit_breaker_registry import CircuitBreakerRegistry

        provider = request.metadata.get("provider", "unknown")
        cb = CircuitBreakerRegistry.get_or_create(f"llm:{provider}")

        async with cb.execute():
            return await next_handler(request)


# ─────────────────────────── Phase 4: Message Normalizer ─────────────────────


class MessageNormalizerMiddleware(LLMMiddleware):
    """Normalise messages for the target provider before the call.

    Uses ``ProviderCapabilities`` (Phase 3) and ``normalize_for_provider``
    from the message normalizer module.  Safe no-op when Phase 1 or Phase 4
    flags are off.
    """

    async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
        from app.core.config import get_settings

        settings = get_settings()
        if not getattr(settings, "feature_llm_middleware_pipeline", False):
            return await next_handler(request)

        try:
            from app.domain.external.llm_capabilities import get_capabilities
            from app.infrastructure.external.llm.message_normalizer import normalize_for_provider

            provider_type = request.metadata.get("provider", "openai")
            caps = get_capabilities(request.model or "", request.metadata.get("api_base"))
            request.messages = normalize_for_provider(request.messages, caps, provider_type)
        except Exception as exc:
            logger.debug("MessageNormalizerMiddleware skipped: %s", exc)

        return await next_handler(request)


# ─────────────────────────── Factory helper ──────────────────────────────────


def build_default_pipeline(handler: LLMCallable) -> Any:
    """Assemble the default middleware stack around a base handler.

    Import this from ``factory.py`` when ``feature_llm_middleware_pipeline``
    is True.

    Stack (outermost → innermost):
        ConcurrencyMiddleware
        RetryBudgetMiddleware
        CircuitBreakerMiddleware
        KeyRotationMiddleware
        RetryMiddleware
        MessageNormalizerMiddleware
        MetricsMiddleware
    """
    from app.domain.services.llm.middleware import LLMPipeline

    middlewares: list[LLMMiddleware] = [
        ConcurrencyMiddleware(),
        RetryBudgetMiddleware(),
        CircuitBreakerMiddleware(),
        KeyRotationMiddleware(),
        RetryMiddleware(),
        MessageNormalizerMiddleware(),
        MetricsMiddleware(),
    ]
    return LLMPipeline(middlewares=middlewares, handler=handler)
