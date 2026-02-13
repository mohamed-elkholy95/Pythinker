# SSE Heartbeat Frontend Implementation - Changes Summary

**Date**: 2026-02-12
**Status**: ✅ Completed and Tested

## Overview

Implemented SSE heartbeat handling in the frontend to prevent stream timeouts during long-running agent operations. The backend already sends heartbeat events every 30 seconds - this implementation adds frontend tracking, stale detection, and automatic reconnection.

## Changes Made

### 1. Client-Side Heartbeat Detection
**File**: `frontend/src/api/client.ts`

**Changes**:
- Added heartbeat event filtering in `onmessage` handler
- Heartbeat events (progress events with `phase: "heartbeat"`) are now filtered out before reaching UI
- Emits custom `sse:heartbeat` window event for tracking without UI notification
- Event IDs are still tracked for proper stream resumption

**Code**:
```typescript
// Handle heartbeat events silently
if (event.event === 'progress') {
  const progressData = parsedData as { phase?: string };
  if (progressData.phase === 'heartbeat') {
    window.dispatchEvent(new CustomEvent('sse:heartbeat', { detail: { eventId } }));
    return; // Don't pass to onMessage callback
  }
}
```

### 2. Connection State Management
**File**: `frontend/src/composables/useSSEConnection.ts`

**New Features**:
- Added `SSEConnectionConfig` interface for configuration
- Added `lastHeartbeatTime` tracking
- Added `updateLastHeartbeatTime()` function
- Added `isHeartbeatStale()` function
- Added `startStaleDetection()` and `stopStaleDetection()` lifecycle functions
- Automatic heartbeat event listener registration/cleanup
- Stale connection detection with configurable threshold (default 60s)
- Callback support for `onStaleDetected` handler

**New API**:
```typescript
export interface SSEConnectionConfig {
  staleThresholdMs?: number       // Default: 60000ms
  onStaleDetected?: () => void
}

const {
  lastHeartbeatTime,              // New: timestamp of last heartbeat
  updateLastHeartbeatTime,        // New: update heartbeat timestamp
  isHeartbeatStale,               // New: check heartbeat staleness
  startStaleDetection,            // New: start monitoring
  stopStaleDetection,             // New: stop monitoring
} = useSSEConnection(config)
```

**Behavior**:
- Checks connection every 10 seconds
- Only monitors when connected and at least one event received
- Triggers callback when no events for threshold duration
- Heartbeat events reset staleness timer

### 3. ChatPage Integration
**File**: `frontend/src/pages/ChatPage.vue`

**Changes**:
- Added `handleStaleConnection` callback for automatic reconnection
- Configured `useSSEConnection` with 60s stale threshold
- Added `startStaleDetection()` call in `onOpen` handler
- Added `stopStaleDetection()` call in `onClose` and `onError` handlers
- Added `updateLastEventTime()` call in `onMessage` handler
- Applied same pattern to `handleRetryConnection` function

**Reconnection Logic**:
```typescript
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
```

### 4. Unit Tests
**File**: `frontend/src/composables/__tests__/useSSEConnection.test.ts`

**New Tests** (6 additional tests):
1. ✅ `should track last heartbeat time`
2. ✅ `should detect stale heartbeat`
3. ✅ `should call onStaleDetected when connection becomes stale`
4. ✅ `should not detect stale before receiving any events`
5. ✅ `should handle heartbeat custom events`
6. ✅ `should stop stale detection on cleanup`

**Total**: 10 tests (all passing)

### 5. Integration Tests
**File**: `frontend/src/api/__tests__/client-heartbeat.test.ts` (NEW)

**Tests** (5 tests):
1. ✅ `should emit heartbeat event when receiving progress event with heartbeat phase`
2. ✅ `should not emit heartbeat event for non-heartbeat progress events`
3. ✅ `should track heartbeat time when receiving heartbeat events`
4. ✅ `should prevent stale connection detection when heartbeats are received`
5. ✅ `should trigger stale detection when heartbeats stop`

**Total**: 5 tests (all passing)

### 6. Documentation
**Files Created**:
- `docs/fixes/SSE_HEARTBEAT_IMPLEMENTATION.md` - Comprehensive implementation guide
- `docs/fixes/SSE_HEARTBEAT_CHANGES.md` - This file (changes summary)

## Test Results

### All Tests Passing ✅
```
✓ src/api/__tests__/client-heartbeat.test.ts (5 tests)
✓ src/composables/__tests__/useSSEConnection.test.ts (10 tests)

Test Files  2 passed (2)
Tests  15 passed (15)
```

### Linting ✅
```bash
$ bun run lint
✓ No errors
```

### Type Checking ✅
```bash
$ bun run type-check
✓ No errors
```

## Configuration

### Backend (Already Configured)
```python
# Heartbeat sent every 30 seconds
HEARTBEAT_INTERVAL = 30
```

### Frontend (New Configuration)
```typescript
// Stale detection threshold: 60 seconds
const { ... } = useSSEConnection({
  staleThresholdMs: 60000,
  onStaleDetected: handleStaleConnection
})
```

**Rationale**:
- Backend sends heartbeat every 30s
- Frontend allows 60s before declaring stale
- Allows 1 missed heartbeat before reconnection
- Prevents false positives from network jitter

## Benefits

1. **No More Timeouts**: Stream stays alive during long operations (browser crash recovery, etc.)
2. **Automatic Recovery**: Stale connections detected and reconnected automatically
3. **Silent Operation**: Heartbeat events don't create UI noise
4. **Event Resumption**: Reconnection resumes from last event ID (no duplicates)
5. **Exponential Backoff**: Reconnection respects existing retry logic
6. **Configurable**: Thresholds can be tuned per use case

## Edge Cases Handled

1. ✅ No events before staleness (detection starts only after first event)
2. ✅ Multiple reconnections (exponential backoff prevents thundering herd)
3. ✅ Session completion (stale detection stopped on close)
4. ✅ Manual stop (user can cancel and prevent reconnection)
5. ✅ Event deduplication (event IDs tracked to prevent duplicates)

## Backward Compatibility

✅ **Fully backward compatible**:
- Works with existing SSE infrastructure
- No changes to backend API
- Heartbeat events already sent by backend
- Frontend silently handles heartbeat without affecting existing flows
- Existing tests continue to pass

## Files Modified

1. ✅ `frontend/src/api/client.ts` - Heartbeat event filtering
2. ✅ `frontend/src/composables/useSSEConnection.ts` - Stale detection logic
3. ✅ `frontend/src/pages/ChatPage.vue` - Reconnection integration
4. ✅ `frontend/src/composables/__tests__/useSSEConnection.test.ts` - Enhanced tests
5. ✅ `frontend/src/api/__tests__/client-heartbeat.test.ts` - New integration tests

## Files Created

1. ✅ `docs/fixes/SSE_HEARTBEAT_IMPLEMENTATION.md` - Implementation guide
2. ✅ `docs/fixes/SSE_HEARTBEAT_CHANGES.md` - Changes summary

## Next Steps

### Immediate (Phase 2)
- [ ] Add progress events during browser connection retries
- [ ] Emit "Retrying browser connection (1/3)..." to user

### Near-term (Phase 3)
- [ ] Fix "Suggested follow-ups" logic (only show when status=COMPLETED)
- [ ] Add UI indicator for reconnection attempts

### Long-term (Phase 4)
- [ ] Add metrics for heartbeat delivery rates
- [ ] Add metrics for stale detection rates
- [ ] Dashboard for connection health monitoring

## Related Documentation

- [SSE Timeout and UX Bugs](./SSE_TIMEOUT_AND_UX_BUGS.md) - Root cause analysis
- [SSE Timeout Quick Reference](./SSE_TIMEOUT_QUICK_REFERENCE.md) - Quick reference
- [Page Refresh Session Persistence](./PAGE_REFRESH_SESSION_PERSISTENCE.md) - Event ID persistence
