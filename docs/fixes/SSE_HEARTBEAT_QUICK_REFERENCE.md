# SSE Heartbeat - Quick Reference

**Status**: ✅ Implemented (2026-02-12)

## What is it?

SSE heartbeat keeps the connection alive during long-running operations (browser crash recovery, slow page loads, etc.) by sending periodic keep-alive events.

## How it works

```
Backend (every 30s)  →  heartbeat event  →  Frontend
                                            ↓
                                    Updates lastEventTime
                                            ↓
                                    Prevents timeout
                                            ↓
                                    (no UI notification)
```

## Configuration

### Backend (already configured)
```python
HEARTBEAT_INTERVAL = 30  # seconds
```

### Frontend
```typescript
const { startStaleDetection, stopStaleDetection } = useSSEConnection({
  staleThresholdMs: 60000,  // 60 seconds
  onStaleDetected: () => {
    // Reconnect logic
  }
})
```

## Usage in Components

```typescript
// 1. Configure on initialization
const handleStaleConnection = () => {
  console.warn('[SSE] Reconnecting...')
  // Cancel current connection
  // Reconnect after delay
}

const {
  startStaleDetection,
  stopStaleDetection,
  updateLastEventTime
} = useSSEConnection({
  staleThresholdMs: 60000,
  onStaleDetected: handleStaleConnection
})

// 2. Start/stop in SSE lifecycle
{
  onOpen: () => {
    startStaleDetection()
  },
  onMessage: ({ event, data }) => {
    updateLastEventTime()  // Track all events
    // Handle event...
  },
  onClose: () => {
    stopStaleDetection()
  },
  onError: () => {
    stopStaleDetection()
  }
}
```

## Testing

### Run Tests
```bash
# All heartbeat tests
bun run test:run src/composables/__tests__/useSSEConnection.test.ts src/api/__tests__/client-heartbeat.test.ts

# Unit tests only
bun run test:run src/composables/__tests__/useSSEConnection.test.ts

# Integration tests only
bun run test:run src/api/__tests__/client-heartbeat.test.ts
```

### Manual Testing
1. Start a long-running task
2. Open browser console
3. Wait 60+ seconds
4. Verify NO timeout message
5. Kill backend to test reconnection

## Behavior

### Normal Operation
- Backend sends heartbeat every 30s
- Frontend silently tracks heartbeat
- NO UI notification (silent)
- Stream stays alive

### Stale Detection
- No events for 60s → stale detected
- Automatic reconnection triggered
- Exponential backoff applied
- Stream resumes from last event ID

## Key Files

### Implementation
- `frontend/src/api/client.ts` - Heartbeat event filtering
- `frontend/src/composables/useSSEConnection.ts` - Stale detection
- `frontend/src/pages/ChatPage.vue` - Reconnection logic

### Tests
- `frontend/src/composables/__tests__/useSSEConnection.test.ts` - 10 unit tests
- `frontend/src/api/__tests__/client-heartbeat.test.ts` - 5 integration tests

### Documentation
- `docs/fixes/SSE_HEARTBEAT_IMPLEMENTATION.md` - Full guide
- `docs/fixes/SSE_HEARTBEAT_CHANGES.md` - Changes summary
- `docs/fixes/SSE_HEARTBEAT_QUICK_REFERENCE.md` - This file

## API Reference

### useSSEConnection()

```typescript
interface SSEConnectionConfig {
  staleThresholdMs?: number       // Default: 60000ms
  onStaleDetected?: () => void    // Callback when stale
}

const {
  // State
  connectionState,                // 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed'
  lastEventTime,                  // Timestamp of last event (including heartbeat)
  lastHeartbeatTime,              // Timestamp of last heartbeat
  lastEventId,                    // Last event ID received
  retryCount,                     // Current retry count

  // Actions
  updateLastEventTime,            // Update event timestamp
  updateLastHeartbeatTime,        // Update heartbeat timestamp
  isConnectionStale,              // Check if connection is stale
  isHeartbeatStale,               // Check if heartbeat is stale
  startStaleDetection,            // Start monitoring
  stopStaleDetection,             // Stop monitoring
  persistEventId,                 // Save to sessionStorage
  getPersistedEventId,            // Load from sessionStorage
  cleanupSessionStorage,          // Clear sessionStorage
  resetRetryCount,                // Reset retry counter
} = useSSEConnection(config)
```

### Heartbeat Custom Event

```typescript
// Emitted by client.ts when heartbeat received
window.dispatchEvent(new CustomEvent('sse:heartbeat', {
  detail: { eventId: 'evt-123' }
}))

// Automatically handled by useSSEConnection when stale detection is active
```

## Common Issues

### Issue: Heartbeat events showing in UI
**Cause**: Heartbeat events not filtered in client.ts
**Fix**: Verify `phase === 'heartbeat'` check in `onmessage` handler

### Issue: Stale detection not triggering
**Cause**: `startStaleDetection()` not called
**Fix**: Call in `onOpen` handler

### Issue: Reconnection not working
**Cause**: `onStaleDetected` callback not set
**Fix**: Pass callback in config

### Issue: Tests failing
**Cause**: Fake timers not used
**Fix**: Use `vi.useFakeTimers()` in tests

## Metrics (Future)

Planned metrics for monitoring:
- `heartbeat_received_total` - Total heartbeats received
- `heartbeat_missed_total` - Total heartbeats missed
- `stale_detection_total` - Total stale detections
- `reconnection_success_total` - Successful reconnections
- `reconnection_failure_total` - Failed reconnections

## Related Issues

- [SSE Timeout and UX Bugs](./SSE_TIMEOUT_AND_UX_BUGS.md)
- [Page Refresh Session Persistence](./PAGE_REFRESH_SESSION_PERSISTENCE.md)
