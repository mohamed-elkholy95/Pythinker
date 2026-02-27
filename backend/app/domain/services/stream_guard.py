"""Stream Guard service for resilient SSE event generation.

Wraps async generators with:
- Cancellation checks at configurable intervals
- Error classification into structured error codes
- Metrics collection for streaming health
- Graceful handling of client disconnects
"""

import asyncio
import logging
import time
from collections import Counter, deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from app.domain.models.event import BaseEvent, ErrorEvent, PlanningPhase, ProgressEvent
from app.domain.utils.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class StreamErrorCode(str, Enum):
    """Standardized error codes for streaming failures."""

    STREAM_TIMEOUT = "stream_timeout"
    AGENT_ERROR = "agent_error"
    SANDBOX_FAILURE = "sandbox_failure"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"
    CLIENT_DISCONNECT = "client_disconnect"
    CANCELLED = "cancelled"
    UPSTREAM_ERROR = "upstream_error"
    VALIDATION_ERROR = "validation_error"
    AUTH_ERROR = "auth_error"


class StreamErrorCategory(str, Enum):
    """Error categories for client retry policy."""

    TRANSPORT = "transport"  # Network-level issues, usually recoverable
    TIMEOUT = "timeout"  # Timeouts, may be recoverable with longer wait
    VALIDATION = "validation"  # Invalid request, not recoverable
    AUTH = "auth"  # Authentication issues, requires user action
    UPSTREAM = "upstream"  # LLM/API issues, transient
    DOMAIN = "domain"  # Business logic errors, may be recoverable
    INTERNAL = "internal"  # Unexpected errors, may need investigation


class StreamMetrics:
    """Collects metrics for a streaming session."""

    def __init__(self, session_id: str, endpoint: str = "unknown"):
        self.session_id = session_id
        self.endpoint = endpoint
        self.start_time = time.monotonic()
        self.events_sent = 0
        self.errors: list[dict[str, Any]] = []
        self.cancellation_count = 0
        self.waiting_events = 0
        self.waiting_stage_counts: Counter[str] = Counter()
        self.last_event_time: float | None = None
        self.event_latencies: list[float] = []

    def record_event(self, event: BaseEvent) -> None:
        """Record an event being sent."""
        self.events_sent += 1
        if isinstance(event, ProgressEvent) and event.phase == PlanningPhase.WAITING:
            self.waiting_events += 1
            waiting_stage = (event.wait_stage or "unknown").strip().lower() or "unknown"
            self.waiting_stage_counts[waiting_stage] += 1
        now = time.monotonic()
        if self.last_event_time is not None:
            self.event_latencies.append(now - self.last_event_time)
        self.last_event_time = now

    def record_error(
        self,
        error_code: StreamErrorCode,
        error_category: StreamErrorCategory,
        recoverable: bool,
        message: str,
    ) -> None:
        """Record an error occurrence."""
        self.errors.append(
            {
                "code": error_code.value,
                "category": error_category.value,
                "recoverable": recoverable,
                "message": message[:200],
                "time": time.monotonic() - self.start_time,
            }
        )

    def record_cancellation(self) -> None:
        """Record a client-initiated cancellation."""
        self.cancellation_count += 1

    @property
    def duration_seconds(self) -> float:
        """Total streaming duration."""
        return time.monotonic() - self.start_time

    @property
    def events_per_second(self) -> float:
        """Average event rate."""
        if self.duration_seconds == 0:
            return 0.0
        return self.events_sent / self.duration_seconds

    @property
    def avg_event_latency_ms(self) -> float | None:
        """Average time between events in ms."""
        if not self.event_latencies:
            return None
        return (sum(self.event_latencies) / len(self.event_latencies)) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dict."""
        return {
            "session_id": self.session_id,
            "endpoint": self.endpoint,
            "duration_seconds": round(self.duration_seconds, 3),
            "events_sent": self.events_sent,
            "events_per_second": round(self.events_per_second, 2),
            "avg_event_latency_ms": round(self.avg_event_latency_ms, 2) if self.avg_event_latency_ms else None,
            "error_count": len(self.errors),
            "errors": self.errors,
            "cancellation_count": self.cancellation_count,
            "waiting_events": self.waiting_events,
            "waiting_stage_counts": dict(self.waiting_stage_counts),
        }


class StreamGuard:
    """Wraps async generators with cancellation, error handling, and metrics.

    Usage:
        async def my_event_generator():
            yield MessageEvent(...)

        guard = StreamGuard(
            session_id="session-123",
            cancel_token=cancel_token,
        )

        async for event in guard.wrap(my_event_generator()):
            yield event

        metrics = guard.get_metrics()
    """

    def __init__(
        self,
        session_id: str,
        endpoint: str = "unknown",
        cancel_token: CancellationToken | None = None,
        check_interval: float = 0.1,  # Check cancellation every 100ms
        on_cancellation: Callable[[], Any] | None = None,
        on_error: Callable[[Exception], Any] | None = None,
    ):
        self.session_id = session_id
        self.endpoint = endpoint
        self.cancel_token = cancel_token or CancellationToken.null()
        self.check_interval = check_interval
        self.on_cancellation = on_cancellation
        self.on_error = on_error
        self.metrics = StreamMetrics(session_id=session_id, endpoint=endpoint)
        self._last_cancel_check = time.monotonic()

    async def wrap(
        self,
        generator: AsyncGenerator[BaseEvent, None],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Wrap an async generator with cancellation checks and error handling."""
        stream_key = await register_active_stream(session_id=self.session_id, endpoint=self.endpoint)
        try:
            async for event in generator:
                # Periodic cancellation check
                now = time.monotonic()
                if now - self._last_cancel_check >= self.check_interval:
                    self._last_cancel_check = now
                    if self.cancel_token.is_cancelled():
                        logger.info(
                            "StreamGuard: cancellation detected for session %s, stopping stream",
                            self.session_id,
                        )
                        self.metrics.record_cancellation()
                        if self.on_cancellation:
                            try:
                                result = self.on_cancellation()
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception as e:
                                logger.warning("StreamGuard on_cancellation callback error: %s", e)

                        # Emit a cancellation error event before stopping
                        yield ErrorEvent(
                            error="Stream cancelled by client disconnect",
                            error_type="cancelled",
                            error_code=StreamErrorCode.CANCELLED.value,
                            error_category=StreamErrorCategory.TRANSPORT.value,
                            recoverable=True,
                            can_resume=True,
                            retry_hint="Your session was interrupted. Reconnecting will resume from where you left off.",
                        )
                        return

                # Record metrics for each event
                self.metrics.record_event(event)
                yield event

        except asyncio.CancelledError:
            logger.debug("StreamGuard: generator cancelled for session %s", self.session_id)
            self.metrics.record_cancellation()
            self.metrics.record_error(
                StreamErrorCode.CANCELLED,
                StreamErrorCategory.TRANSPORT,
                recoverable=True,
                message="Stream cancelled",
            )
            if self.on_cancellation:
                try:
                    result = self.on_cancellation()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.warning("StreamGuard on_cancellation callback error: %s", e)
            raise

        except TimeoutError as e:
            error_event = self._classify_error(e, "Stream timeout")
            self.metrics.record_error(
                StreamErrorCode.STREAM_TIMEOUT,
                StreamErrorCategory.TIMEOUT,
                error_event.recoverable,
                str(e)[:200],
            )
            if self.on_error:
                try:
                    cb_result = self.on_error(e)
                    if asyncio.iscoroutine(cb_result):
                        await cb_result
                except Exception as cb_error:
                    logger.warning("StreamGuard on_error callback error: %s", cb_error)
            yield error_event

        except Exception as e:
            error_event = self._classify_error(e, str(e))
            error_code = self._to_error_code(error_event.error_code)
            error_category = self._to_error_category(error_event.error_category)
            self.metrics.record_error(
                error_code,
                error_category,
                error_event.recoverable,
                str(e)[:200],
            )
            if self.on_error:
                try:
                    cb_result = self.on_error(e)
                    if asyncio.iscoroutine(cb_result):
                        await cb_result
                except Exception as cb_error:
                    logger.warning("StreamGuard on_error callback error: %s", cb_error)
            yield error_event
        finally:
            await unregister_active_stream(stream_key)

    def _classify_error(self, error: Exception, message: str) -> ErrorEvent:
        """Classify an exception into a structured ErrorEvent."""
        error_str = str(error).lower()
        error_type = type(error).__name__

        # Classification rules
        if "timeout" in error_str or "timed out" in error_str:
            return ErrorEvent(
                error=message,
                error_type="timeout",
                error_code=StreamErrorCode.STREAM_TIMEOUT.value,
                error_category=StreamErrorCategory.TIMEOUT.value,
                recoverable=True,
                can_resume=True,
                retry_after_ms=5000,
                retry_hint="The operation timed out. Please try again.",
            )

        if "rate" in error_str or "limit" in error_str or "429" in error_str:
            return ErrorEvent(
                error=message,
                error_type="rate_limit",
                error_code=StreamErrorCode.RATE_LIMITED.value,
                error_category=StreamErrorCategory.UPSTREAM.value,
                recoverable=True,
                can_resume=True,
                retry_after_ms=60000,
                retry_hint="Rate limit exceeded. Please wait a moment and try again.",
            )

        if "unauthorized" in error_str or "401" in error_str or "auth" in error_str:
            return ErrorEvent(
                error=message,
                error_type="auth",
                error_code=StreamErrorCode.AUTH_ERROR.value,
                error_category=StreamErrorCategory.AUTH.value,
                recoverable=False,
                can_resume=False,
                retry_hint="Authentication required. Please log in again.",
            )

        if "validation" in error_str or "422" in error_str or "invalid" in error_str:
            return ErrorEvent(
                error=message,
                error_type="validation",
                error_code=StreamErrorCode.VALIDATION_ERROR.value,
                error_category=StreamErrorCategory.VALIDATION.value,
                recoverable=False,
                can_resume=False,
                retry_hint="The request was invalid. Please check your input.",
            )

        if "sandbox" in error_str or "container" in error_str or "docker" in error_str:
            return ErrorEvent(
                error=message,
                error_type="sandbox",
                error_code=StreamErrorCode.SANDBOX_FAILURE.value,
                error_category=StreamErrorCategory.INTERNAL.value,
                recoverable=True,
                can_resume=True,
                retry_after_ms=10000,
                retry_hint="A sandbox error occurred. The system will attempt to recover.",
            )

        if "cancelled" in error_str or "cancel" in error_str:
            return ErrorEvent(
                error=message,
                error_type="cancelled",
                error_code=StreamErrorCode.CANCELLED.value,
                error_category=StreamErrorCategory.TRANSPORT.value,
                recoverable=True,
                can_resume=True,
                retry_hint="The operation was cancelled. Reconnecting will resume from where you left off.",
            )

        # Default: internal error
        return ErrorEvent(
            error=message,
            error_type=error_type,
            error_code=StreamErrorCode.INTERNAL_ERROR.value,
            error_category=StreamErrorCategory.INTERNAL.value,
            recoverable=True,
            can_resume=True,
            retry_after_ms=5000,
            retry_hint="An unexpected error occurred. Please try again.",
            details={"exception_type": error_type},
        )

    @staticmethod
    def _to_error_code(raw_error_code: str | None) -> StreamErrorCode:
        if not raw_error_code:
            return StreamErrorCode.INTERNAL_ERROR
        try:
            return StreamErrorCode(raw_error_code)
        except ValueError:
            return StreamErrorCode.INTERNAL_ERROR

    @staticmethod
    def _to_error_category(raw_error_category: str | None) -> StreamErrorCategory:
        if not raw_error_category:
            return StreamErrorCategory.INTERNAL
        try:
            return StreamErrorCategory(raw_error_category)
        except ValueError:
            return StreamErrorCategory.INTERNAL

    def get_metrics(self) -> StreamMetrics:
        """Get the collected metrics for this stream."""
        return self.metrics


@dataclass(frozen=True)
class ActiveStreamInfo:
    stream_key: str
    session_id: str
    endpoint: str
    started_monotonic: float
    started_unix: float


# Global stream telemetry collectors for health endpoint.
_stream_metrics: deque[StreamMetrics] = deque(maxlen=500)
_active_streams: dict[str, ActiveStreamInfo] = {}
_reconnection_events: deque[tuple[float, str]] = deque()
_metrics_lock = asyncio.Lock()
_RECONNECTION_WINDOW_SECONDS = 300.0  # 5 minutes


def _prune_reconnection_events(now_monotonic: float) -> None:
    while _reconnection_events and now_monotonic - _reconnection_events[0][0] > _RECONNECTION_WINDOW_SECONDS:
        _reconnection_events.popleft()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


async def register_active_stream(session_id: str, endpoint: str) -> str:
    """Register a stream as active and return its tracking key."""
    stream_key = f"{session_id}:{endpoint}:{uuid4()}"
    now_monotonic = time.monotonic()
    now_unix = time.time()
    async with _metrics_lock:
        _active_streams[stream_key] = ActiveStreamInfo(
            stream_key=stream_key,
            session_id=session_id,
            endpoint=endpoint,
            started_monotonic=now_monotonic,
            started_unix=now_unix,
        )
    return stream_key


async def unregister_active_stream(stream_key: str) -> None:
    """Remove a stream from the active registry."""
    async with _metrics_lock:
        _active_streams.pop(stream_key, None)


async def has_active_stream(session_id: str, endpoint: str | None = None) -> bool:
    """Return whether a session currently has any active stream (optionally by endpoint)."""
    async with _metrics_lock:
        for stream in _active_streams.values():
            if stream.session_id != session_id:
                continue
            if endpoint is not None and stream.endpoint != endpoint:
                continue
            return True
    return False


async def record_stream_reconnection(session_id: str, endpoint: str) -> None:
    """Record that a client attempted to resume/reconnect an SSE stream."""
    now_monotonic = time.monotonic()
    async with _metrics_lock:
        _reconnection_events.append((now_monotonic, endpoint))
        _prune_reconnection_events(now_monotonic)
    logger.debug("Recorded stream reconnection: session_id=%s endpoint=%s", session_id, endpoint)


async def record_stream_metrics(metrics: StreamMetrics) -> None:
    """Record completed stream metrics for health monitoring."""
    async with _metrics_lock:
        _stream_metrics.append(metrics)


async def get_aggregate_stream_metrics() -> dict[str, Any]:
    """Get aggregate streaming metrics for health endpoint."""
    async with _metrics_lock:
        now_monotonic = time.monotonic()
        _prune_reconnection_events(now_monotonic)

        all_metrics = list(_stream_metrics)
        total_events = sum(m.events_sent for m in all_metrics)
        total_errors = sum(len(m.errors) for m in all_metrics)
        total_cancellations = sum(m.cancellation_count for m in all_metrics)
        total_waiting_events = sum(m.waiting_events for m in all_metrics)
        avg_events_per_second = sum(m.events_per_second for m in all_metrics) / len(all_metrics) if all_metrics else 0.0

        latency_samples_ms: list[float] = []
        error_category_counts: Counter[str] = Counter()
        for metrics in all_metrics:
            latency_samples_ms.extend(latency * 1000 for latency in metrics.event_latencies)
            for error_entry in metrics.errors:
                category = str(error_entry.get("category") or StreamErrorCategory.INTERNAL.value)
                error_category_counts[category] += 1

        p50_latency_ms = _percentile(latency_samples_ms, 0.50)
        p95_latency_ms = _percentile(latency_samples_ms, 0.95)
        p99_latency_ms = _percentile(latency_samples_ms, 0.99)
        avg_latency_ms = (sum(latency_samples_ms) / len(latency_samples_ms)) if latency_samples_ms else None

        active_by_endpoint = Counter(stream.endpoint for stream in _active_streams.values())
        reconnections_by_endpoint = Counter(endpoint for _, endpoint in _reconnection_events)
        waiting_stage_counts: Counter[str] = Counter()
        for metrics in all_metrics:
            waiting_stage_counts.update(metrics.waiting_stage_counts)

        error_rate_by_category: dict[str, float] = {}
        if total_errors > 0:
            error_rate_by_category = {
                category: count / total_errors for category, count in sorted(error_category_counts.items())
            }

        return {
            "active_connections": len(_active_streams),
            "active_connections_by_endpoint": dict(sorted(active_by_endpoint.items())),
            "total_sessions": len(all_metrics),
            "total_events": total_events,
            "avg_events_per_session": (total_events / len(all_metrics)) if all_metrics else 0.0,
            "avg_events_per_second": round(avg_events_per_second, 2),
            "error_rate": (total_errors / total_events) if total_events > 0 else 0.0,
            "error_count_by_category": dict(sorted(error_category_counts.items())),
            "error_rate_by_category": error_rate_by_category,
            "cancellation_rate": (total_cancellations / len(all_metrics)) if all_metrics else 0.0,
            "waiting_events_total": total_waiting_events,
            "avg_waiting_events_per_session": (total_waiting_events / len(all_metrics)) if all_metrics else 0.0,
            "waiting_event_ratio": (total_waiting_events / total_events) if total_events > 0 else 0.0,
            "waiting_stage_counts": dict(sorted(waiting_stage_counts.items())),
            "latency_ms": {
                "avg": round(avg_latency_ms, 2) if avg_latency_ms is not None else None,
                "p50": round(p50_latency_ms, 2) if p50_latency_ms is not None else None,
                "p95": round(p95_latency_ms, 2) if p95_latency_ms is not None else None,
                "p99": round(p99_latency_ms, 2) if p99_latency_ms is not None else None,
                "sample_count": len(latency_samples_ms),
            },
            "reconnections_last_5m": len(_reconnection_events),
            "reconnection_rate_per_min": round(len(_reconnection_events) / 5.0, 3),
            "reconnections_last_5m_by_endpoint": dict(sorted(reconnections_by_endpoint.items())),
            "metrics_window_seconds": _RECONNECTION_WINDOW_SECONDS,
        }
