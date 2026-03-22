# SSE Reconnection Race Condition Fix

**Date:** 2026-03-03
**Status:** Approved
**Severity:** P0 — Sessions falsely marked as interrupted while agent is still running

## Problem

When a long-running research session's SSE stream exhausts (agent still working, but current batch of events has been yielded), the route-level cleanup calls `request_cancellation()`, which triggers `_teardown_session_runtime()` and clears `task_id` from MongoDB. When the frontend reconnects 30+ seconds later, the domain service can't find the task and falsely marks the session as CANCELLED with the error:

> "Session task was interrupted before completion (for example by cancellation or service reload). Please retry."

### Root Cause Chain

```
SSE stream exhausts (close_reason = "stream_exhausted_non_terminal")
  → session_routes.py:1315-1319 calls request_cancellation(session_id)
    → agent_service sets cancel_event
      → domain service cancel_token fires in event loop
        → _teardown_session_runtime() clears task_id in MongoDB
          → Frontend reconnects 46s later
            → _get_task() returns None (task_id cleared)
              → session_age (46s) > 30s threshold
                → "interrupted" error + CANCELLED
                  → Agent asyncio task still running, orphaned
```

### Observed Timeline (Session 6865679e)

| Time | Event |
|------|-------|
| 11:24:01 | Session created, agent starts planning |
| 11:24:37 | Plan verified, execution begins (Step 1 of 4) |
| 11:24:51 | `POST /chat` returns after 50.4s (21 events) — SSE stream ends |
| 11:24:51 | Route calls `request_cancellation()` — task_id cleared |
| 11:24:51→11:25:09 | Agent keeps running (searches, browser navigation) |
| 11:25:37 | Frontend reconnects — task_id is None, session_age=46s |
| 11:25:37 | Domain service: "interrupted" error, marks CANCELLED |
| 11:25:39→11:26:20 | Agent still running, all events orphaned |

## Design

### Approach: Route-Level Fix with Configurable Grace Period

Minimal change across 3 files that directly addresses the root cause without altering the domain service architecture.

### Changes

#### 1. `session_routes.py` — Defer cancellation on non-terminal stream exhaustion

**Current (line 1315-1319):**
```python
else:
    _cancel_pending_disconnect_cancellation(session_id)
    with contextlib.suppress(Exception):
        request_cancellation(session_id)
```

**Fixed:**
```python
elif close_reason in ("stream_exhausted_non_terminal",):
    # Agent still running — schedule deferred cancel, not immediate.
    # Frontend reconnect at line 777 cancels the pending teardown.
    _schedule_disconnect_cancellation(
        session_id=session_id,
        agent_service=agent_service,
        grace_seconds=settings.sse_disconnect_non_terminal_grace_seconds,
    )
else:
    _cancel_pending_disconnect_cancellation(session_id)
    with contextlib.suppress(Exception):
        request_cancellation(session_id)
```

#### 2. `agent_domain_service.py` — Increase reconnect-race guard threshold

**Current (line 766):**
```python
if session_age < 30.0:
```

**Fixed:**
```python
if session_age < 180.0:
```

180s provides margin above the 120s grace period for network delays and frontend retry backoff.

#### 3. `config_features.py` — Configurable grace period

```python
sse_disconnect_non_terminal_grace_seconds: float = 120.0
```

### Data Flow (Fixed)

```
Frontend SSE connects → agent runs → yields events → SSE stream exhausts
  → route schedules 120s deferred cancel (NOT immediate)
  → frontend reconnects within 120s
  → _cancel_pending_disconnect_cancellation() fires (line 777)
  → domain service finds task via task_id (still set!)
  → resumes event streaming seamlessly
```

### Error Handling

- Frontend never reconnects: 120s deferred cancel fires → teardown → cleanup
- Agent finishes during grace period: DoneEvent persisted → next reconnect sees COMPLETED
- Multiple rapid reconnects: each new connection cancels previous deferred cancel (existing behavior)

### What Does NOT Change

- Explicit user stop (`stop_session`) — still immediate
- Client disconnect detection — still immediate cancel
- Generator cancellation (CancelledError) — still 5s grace period
- Terminal event handling (DoneEvent/ErrorEvent) — unchanged
- Sandbox lifecycle — unchanged

## Files Modified

| File | Change |
|------|--------|
| `backend/app/interfaces/api/session_routes.py` | Defer cancellation for non-terminal stream exhaustion |
| `backend/app/domain/services/agent_domain_service.py` | Increase session_age threshold from 30s to 180s |
| `backend/app/core/config_features.py` | Add `sse_disconnect_non_terminal_grace_seconds` setting |
| `backend/tests/` | Update/add tests for the reconnection grace period |
