# SSE Heartbeat Implementation

**Status**: ✅ Implemented (2026-02-12)
**Related Issues**: [SSE Timeout and UX Bugs](./SSE_TIMEOUT_AND_UX_BUGS.md)

## Overview

This document describes the SSE heartbeat implementation that prevents stream timeouts during long-running agent operations. The heartbeat mechanism ensures the frontend can detect stale connections and automatically reconnect when needed.

## Architecture

### Backend (already implemented)

The backend sends heartbeat events every 30 seconds during long operations:

```python
# backend/app/interfaces/api/session_routes.py
heartbeat = ProgressEvent(
    phase=PlanningPhase.HEARTBEAT,
    message="",
    progress_percent=None,
)
```

### Frontend Implementation

#### 1. Client-Side Heartbeat Detection (`frontend/src/api/client.ts`)

The SSE client silently handles heartbeat events and emits custom events for tracking:

```typescript
// Handle heartbeat events silently (update lastEventTime via custom event)
if (event.event === 'progress') {
  const progressData = parsedData as { phase?: string };
  if (progressData.phase === 'heartbeat') {
    // Emit custom event for heartbeat tracking without UI notification
    window.dispatchEvent(new CustomEvent('sse:heartbeat', { detail: { eventId } }));
    // Don't pass heartbeat to onMessage callback - it's silent
    return;
  }
}
```

**Key Features**:
- Heartbeat events are filtered out before reaching the UI
- Custom `sse:heartbeat` events are emitted for tracking
- Event IDs are tracked for proper stream resumption

#### 2. Connection State Management (`frontend/src/composables/useSSEConnection.ts`)

The composable tracks heartbeat events and detects stale connections:

```typescript
export interface SSEConnectionConfig {
  staleThresholdMs?: number  // Default: 60000ms (60 seconds)
  onStaleDetected?: () => void
}

// Key features:
- lastEventTime: timestamp of any event (including heartbeat)
- lastHeartbeatTime: timestamp of last heartbeat specifically
- isConnectionStale(thresholdMs): checks if connection is stale
- startStaleDetection(): begins monitoring for stale connection
- stopStaleDetection(): stops monitoring
```

**Stale Detection Logic**:
1. Checks connection state every 10 seconds
2. Only monitors when `connectionState === 'connected'` and at least one event received
3. Triggers `onStaleDetected` callback if no events for `staleThresholdMs`
4. Heartbeat events reset the staleness timer

#### 3. ChatPage Integration (`frontend/src/pages/ChatPage.vue`)

ChatPage integrates heartbeat tracking with automatic reconnection:

```typescript
// Stale connection handler
const handleStaleConnection = () => {
  console.warn('[SSE] Connection stale detected - attempting reconnection')
  if (cancelCurrentChat.value && sessionId.value) {
    cancelCurrentChat.value()
    cancelCurrentChat.value = null
    setTimeout(() => {
      chat('', [], { skipOptimistic: true })
    }, 1000)
  }
}

// Initialize with stale detection
const { startStaleDetection, stopStaleDetection } = useSSEConnection({
  staleThresholdMs: 60000,
  onStaleDetected: handleStaleConnection
})

// Start/stop detection in SSE lifecycle
{
  onOpen: () => {
    startStaleDetection()
  },
  onMessage: ({ event, data }) => {
    updateLastEventTime()  // Track all events
    handleEvent({ event, data })
  },
  onClose: () => {
    stopStaleDetection()
  }
}
```

## Behavior

### Normal Operation
1. Backend sends heartbeat every 30 seconds during long operations
2. Frontend receives heartbeat via `sse:heartbeat` custom event
3. `lastEventTime` and `lastHeartbeatTime` are updated
4. Stale detection timer is reset
5. Stream stays alive, no reconnection needed

### Stale Connection Detection
1. No events (including heartbeat) received for 60 seconds
2. Stale check interval (every 10s) detects staleness
3. `onStaleDetected` callback triggered
4. Current SSE connection cancelled
5. Automatic reconnection initiated after 1 second delay
6. Reconnection resumes from last event ID

### Stream Resumption
- Event IDs are persisted to sessionStorage
- Reconnection includes `Last-Event-ID` header
- Backend resumes streaming from last acknowledged event
- No duplicate events shown to user

## Testing

### Unit Tests

**`useSSEConnection.test.ts`** (10 tests):
- ✅ Track connection state
- ✅ Track last event time
- ✅ Track last heartbeat time
- ✅ Detect stale connections
- ✅ Detect stale heartbeat
- ✅ Call onStaleDetected when stale
- ✅ Not detect stale before any events
- ✅ Handle heartbeat custom events
- ✅ Stop stale detection on cleanup
- ✅ Persist and restore lastEventId

**`client-heartbeat.test.ts`** (5 tests):
- ✅ Emit heartbeat event for heartbeat phase
- ✅ Not emit for non-heartbeat progress events
- ✅ Track heartbeat time
- ✅ Prevent stale detection with heartbeats
- ✅ Trigger stale detection when heartbeats stop

### Manual Testing

1. **Start a long-running task** (e.g., browser navigation)
2. **Monitor console** for heartbeat events (should not appear in UI)
3. **Verify no timeout** after 60+ seconds with heartbeats
4. **Kill backend** to simulate network failure
5. **Verify reconnection** after 60 seconds of no heartbeats

## Timeline

- **Backend heartbeat**: Already implemented (30s interval)
- **Frontend heartbeat detection**: ✅ Completed (2026-02-12)
- **ChatPage integration**: ✅ Completed (2026-02-12)
- **Unit tests**: ✅ Completed (2026-02-12)
- **Integration tests**: ✅ Completed (2026-02-12)

## Configuration

### Backend
```python
# backend/app/interfaces/api/session_routes.py
HEARTBEAT_INTERVAL = 30  # seconds
```

### Frontend
```typescript
// frontend/src/pages/ChatPage.vue
const { startStaleDetection } = useSSEConnection({
  staleThresholdMs: 60000,  // 60 seconds
  onStaleDetected: handleStaleConnection
})
```

**Recommended Values**:
- Heartbeat interval: 30s (backend)
- Stale threshold: 60s (frontend) - allows 1 missed heartbeat
- Stale check interval: 10s (composable)

## Exponential Backoff

Reconnection respects existing exponential backoff in `client.ts`:

```typescript
const baseDelay = 1000  // 1 second
const maxDelay = 45000  // 45 seconds
const maxRetries = 7

// Exponential backoff with 25% jitter
const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay)
const jitter = delay * 0.25 * Math.random()
```

## Edge Cases Handled

1. **No events before staleness**: Stale detection only starts after first event
2. **Multiple reconnections**: Backoff prevents thundering herd
3. **Session completion**: Stale detection stopped on `onClose`
4. **Manual stop**: User can cancel and prevent reconnection
5. **Event deduplication**: Event IDs tracked to prevent duplicates

## Related Documentation

- [SSE Timeout and UX Bugs](./SSE_TIMEOUT_AND_UX_BUGS.md) - Root cause analysis
- [SSE Timeout Quick Reference](./SSE_TIMEOUT_QUICK_REFERENCE.md) - Summary
- [Page Refresh Session Persistence](./PAGE_REFRESH_SESSION_PERSISTENCE.md) - Event ID persistence

## Next Steps (Future Enhancements)

1. ✅ **Phase 1 (Completed)**: Heartbeat tracking and stale detection
2. **Phase 2**: Progress events during tool retries (in progress)
3. **Phase 3**: Fix "Suggested follow-ups" logic (only show when status=COMPLETED)
4. **Phase 4**: UI indicator for reconnection attempts
5. **Phase 5**: Metrics for heartbeat delivery and stale detection rates
