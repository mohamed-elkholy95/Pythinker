# Streaming Resilience Framework (Frontend + Backend)

## Purpose
This document defines the production-grade reliability model for SSE streaming between the front-end and back-end in Pythinker, including error protocol, retry controls, data integrity, observability, and fallback UX behavior.

## 1) Error Detection Mechanisms

### Server-side detection
Implemented in `backend/app/interfaces/api/session_routes.py` and `backend/app/application/services/agent_service.py`.

- Connection/disconnect detection
  - Uses `Request.is_disconnected()` checks during stream loop.
- Soft idle timeout detection
  - Logs warnings when no domain event arrives for `CHAT_EVENT_TIMEOUT_SECONDS`.
- Hard idle timeout detection
  - Emits structured timeout `ErrorEvent` after `CHAT_EVENT_HARD_TIMEOUT_SECONDS`.
- SSE send timeout detection
  - Uses bounded send timeout when `feature_sse_v2` is enabled.
- Stream exception detection
  - Catches unexpected exceptions and emits schema-compliant recoverable error event.

### Client-side detection
Implemented in `frontend/src/api/client.ts` and `frontend/src/pages/ChatPage.vue`.

- HTTP status inspection on stream open
  - Distinguishes retriable vs non-retriable status codes.
- Transport error inspection
  - Classifies fatal transport failures (validation/auth/forbidden) vs retryable.
- Stream close classification
  - Normal completion, retrying close, aborted, max retries, and no-events-after-message.
- Heartbeat-based stale detection
  - Detects stale stream feeling and signals instability in UI.

## 2) Adaptive Retry Strategy

### Policy model
Implemented in `frontend/src/api/client.ts` via `SSERetryPolicy`.

- Parameters
  - `maxRetries`
  - `baseDelayMs`
  - `maxDelayMs`
  - `jitterRatio`
- Defaults
  - `maxRetries=7`, `baseDelayMs=1000`, `maxDelayMs=45000`, `jitterRatio=0.25`
- Formula
  - Exponential backoff with bounded equal-jitter:
  - `delay = min(baseDelayMs * 2^attempt, maxDelayMs)`
  - `jittered = (delay - delay*jitterRatio) + random(0..delay*jitterRatio)`

### Adaptive overrides
- Server can override retry behavior via response headers:
  - `X-Pythinker-SSE-Retry-Max-Attempts`
  - `X-Pythinker-SSE-Retry-Base-Delay-Ms`
  - `X-Pythinker-SSE-Retry-Max-Delay-Ms`
  - `X-Pythinker-SSE-Retry-Jitter-Ratio`
- Per-error delay hint:
  - `retry_after_ms` in error event payload.
- HTTP `Retry-After` is parsed and mapped to reconnect delay.

## 3) Stream Interruption Recovery + Data Integrity

### Automatic reconnection
- Reconnect triggered on recoverable close/error with bounded retries.
- Offline-aware retry waits for browser `online` event before reconnecting.

### Resume protocol
- Client sends resume cursor in two ways:
  - request body `event_id`
  - `Last-Event-ID` header
- Backend skips already-seen events up to resume cursor.

### Integrity controls
- Duplicate event suppression via bounded `seenEventIds` cache.
- Stale resume cursor fail-safe (server)
  - Skip mode is disabled if cursor is not found after max skipped events or max skip time, preserving forward progress.

## 4) Standard Error + Status Communication Protocol

### Protocol headers
Server emits protocol metadata on chat SSE response (`session_routes.py`):

- `X-Pythinker-SSE-Protocol-Version`
- `X-Pythinker-SSE-Heartbeat-Interval-Seconds`
- `X-Pythinker-SSE-Retry-Max-Attempts`
- `X-Pythinker-SSE-Retry-Base-Delay-Ms`
- `X-Pythinker-SSE-Retry-Max-Delay-Ms`
- `X-Pythinker-SSE-Retry-Jitter-Ratio`

### Standard error envelope
Defined in:
- `backend/app/domain/models/event.py`
- `backend/app/interfaces/schemas/event.py`
- `frontend/src/types/event.ts`

Fields:
- `error` (required user-facing message)
- `error_type`
- `recoverable`
- `retry_hint`
- `error_code` (stable machine-readable code)
- `error_category` (`transport|timeout|validation|auth|upstream|domain`)
- `severity` (`info|warning|error|critical`)
- `retry_after_ms`
- `can_resume`
- `details` (structured diagnostics)

## 5) Logging + Monitoring

### Metrics (Prometheus)
Implemented in `backend/app/infrastructure/observability/prometheus_metrics.py`.

- `pythinker_sse_stream_open_total`
- `pythinker_sse_stream_close_total`
- `pythinker_sse_stream_heartbeat_total`
- `pythinker_sse_stream_error_total`
- `pythinker_sse_stream_retry_suggested_total`
- `pythinker_sse_stream_duration_seconds`
- `pythinker_sse_stream_active`

### Operational signals
- Close reasons are labeled (`completed`, `client_disconnected`, `send_timeout`, `stream_exception`, etc.).
- Stream-level error types are labeled for alert routing.
- Retry suggestions are counted to identify systemic instability.

## 6) Fail-safe Fallback Procedures

### Frontend fallback state machine
Implemented in `frontend/src/pages/ChatPage.vue`.

- `timed_out` state is recoverable (not terminal error) for timeout-like interruptions.
- Automatic reconnect with progressive delay sequence.
- After retry budget exhaustion, fallback session-status polling starts.

### Session status fallback
- Polls session status at bounded interval/attempt count.
- If backend reports `completed`/`failed`, UI converges to stable terminal state.
- Preserves user experience when stream transport fails but backend work continues.

### Circuit breaker protection
Implemented via `getSseCircuitBreaker()`.

- Prevents reconnect storms during sustained transport failure.
- Blocks new stream attempts until cooldown window allows probe.

## 7) Fault-tolerant Pseudocode

### Server stream loop (simplified)
```python
open_stream_metrics()
try:
    emit_instant_ack()
    while True:
        if request_disconnected():
            close_reason = "client_disconnected"
            break

        event_or_heartbeat = wait_first(next_domain_event, heartbeat_timer)

        if is_heartbeat(event_or_heartbeat):
            send_heartbeat_comment()
            record_heartbeat_metric()
            continue

        event = map_to_sse(event_or_heartbeat)
        send_with_timeout(event)

except SendTimeout:
    record_stream_error("send_timeout")
    emit_recoverable_error_event(code="stream_send_timeout", retry_after_ms=1500)
except Exception as e:
    record_stream_error(type(e))
    emit_recoverable_error_event(code="stream_exception", can_resume=True)
finally:
    record_close_metrics(close_reason)
```

### Client reconnection loop (simplified)
```typescript
onOpen(response):
  applyServerRetryHeaders(response.headers)
  if response.status is retriable_error:
    scheduleReconnect(delayFromRetryAfterOrBackoff())
    stopCurrentAttempt()

onMessage(event):
  dedupeByEventId(event.event_id)
  updateResumeCursor(event.event_id)
  if event is recoverable_error:
    setRetryHint(event.retry_after_ms)

onClose(info):
  if completed: return
  if shouldRetry(info): scheduleReconnect(computeBackoff())
  else failGracefully()

onError(err):
  if fatal: stop_and_surface_error()
  else scheduleReconnect(computeBackoff())
```

## 8) Robustness Testing Recommendations

## Unit tests
- Retry math
  - backoff growth, cap enforcement, jitter bounds.
- Protocol parsing
  - header parsing, retry-after parsing, error envelope parsing.
- Resume handling
  - stale cursor skip cutoff, id-less event behavior.

## Integration tests
- End-to-end reconnect with resume cursor
  - Verify no duplicate user-visible events.
- Stream interruption mid-task
  - Close TCP/SSE and ensure backend continues and UI recovers via reconnect/polling.
- Recoverable vs fatal error classification
  - Ensure retries only for expected classes.

## Chaos/fault injection tests
- Injected failures
  - 429/503 storms
  - intermittent packet loss
  - delayed heartbeats
  - forced backend send timeout
  - abrupt backend process termination
- Validate
  - retry budget respected
  - no reconnect storm
  - session reaches consistent final state

## Load and soak tests
- Many concurrent streams with periodic disconnects.
- Monitor:
  - error rate
  - retry-suggested rate
  - active-stream gauge leaks
  - p95/p99 stream duration

## Suggested alert baselines
- High `sse_stream_error_total` rate over rolling window.
- Spike in `sse_stream_retry_suggested_total`.
- `sse_stream_active` not returning to baseline after traffic drop.
- Elevated `send_timeout` close reason share.

## Current implementation references
- Backend service loop: `backend/app/application/services/agent_service.py`
- Backend SSE route/protocol: `backend/app/interfaces/api/session_routes.py`
- Backend metrics: `backend/app/infrastructure/observability/prometheus_metrics.py`
- Frontend SSE client: `frontend/src/api/client.ts`
- Frontend timeout/fallback UX: `frontend/src/pages/ChatPage.vue`
- Frontend event schema: `frontend/src/types/event.ts`
- Key tests:
  - `backend/tests/application/services/test_agent_service_latency_guards.py`
  - `backend/tests/interfaces/api/test_session_routes.py`
  - `frontend/tests/api/client.sse-close.spec.ts`
