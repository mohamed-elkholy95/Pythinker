# Page Refresh Session Persistence - Analysis & Fix

## Problem Statement

User reports that clicking refresh on the page stops the session or agent. The agent should continue running async in the sandbox, executing backend commands and tasks, even when the frontend is refreshed.

## Current Architecture (How It Should Work)

### Frontend Flow on Page Refresh

1. **SSE Connection Drops**: When page refreshes, the SSE connection to `/sessions/{id}/chat` is lost
2. **Page Reloads**: Vue app reinitializes
3. **Session Restoration** (`ChatPage.vue:1844-1890`):
   - `watch(sessionId, ...)` triggers on mount (line 653)
   - Calls `refreshSessionStatus()` to fetch session from backend
   - Calls `restoreSession()` which:
     - Fetches session data via `getSession(sessionId)`
     - Replays all events to rebuild UI state
     - **Key Logic (lines 1861-1884)**: If session status is `RUNNING` or `PENDING`:
       - Checks localStorage for `pythinker-stopped-{sessionId}` flag
       - If NOT manually stopped in last 60 seconds → calls `chat()` to auto-resume
       - Passes `lastEventId.value` for event stream resumption

### Backend Flow on Reconnect

1. **Chat Endpoint** (`session_routes.py:281-375`):
   - Receives chat request with `event_id` parameter
   - Passes to `agent_service.chat()` → `agent_domain_service.chat()`

2. **Domain Service** (`agent_domain_service.py:657-996`):
   - **Duplicate Detection** (lines 685-744): Detects reconnection when:
     - Same message sent within 5 minutes
     - Session status is `RUNNING`
   - **Event Stream Resumption** (line 946):
     ```python
     event_id, event_str = await task.output_stream.get(start_id=latest_event_id, block_ms=0)
     ```
   - Streams events from `latest_event_id` forward

3. **SSE Disconnect Handling** (`session_routes.py:366-369`):
   ```python
   except asyncio.CancelledError:
       logger.warning(f"Chat stream cancelled for session {session_id} (client disconnected)")
       raise  # Does NOT stop the session!
   ```

### Expected Behavior

✅ **Agent continues running** - SSE disconnect does NOT stop the session
✅ **Event resumption** - Backend resumes streaming from last event ID
✅ **UI restoration** - Frontend replays events and reconnects

## Potential Issues & Fixes

### Issue 1: Session Status Not Set to RUNNING

**Problem**: Session might be in `INITIALIZING` state when page refreshes, causing `restoreSession()` to skip auto-resume.

**Check**:
```bash
# Monitor session status transitions
docker logs pythinker-backend-1 --tail 200 | grep -i "session.*status\|RUNNING\|INITIALIZING"
```

**Fix**: Ensure session status is set to `RUNNING` when task starts executing.

**Location**: `backend/app/domain/services/agent_domain_service.py`

```python
# After task.run() is called, should set status to RUNNING
await self._session_repository.update_status(session_id, SessionStatus.RUNNING)
```

### Issue 2: localStorage "stopped" Flag Not Cleared

**Problem**: The `pythinker-stopped-{sessionId}` flag might persist incorrectly.

**Check**:
```javascript
// In browser console on chat page
Object.keys(localStorage).filter(k => k.includes('stopped'))
```

**Fix**: Add defensive cleanup in `restoreSession()`:

**Location**: `frontend/src/pages/ChatPage.vue:1861-1884`

```typescript
if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
  const stoppedKey = `pythinker-stopped-${sessionId.value}`;
  const stoppedTimestamp = localStorage.getItem(stoppedKey);

  if (stoppedTimestamp) {
    const elapsed = Date.now() - Number(stoppedTimestamp);
    if (elapsed < 60_000) {
      // Recently stopped - verify with backend before skipping resume
      localStorage.removeItem(stoppedKey);
      await new Promise(resolve => setTimeout(resolve, 1000));
      const refreshedSession = await agentApi.getSession(sessionId.value!);
      sessionStatus.value = refreshedSession.status as SessionStatus;

      // Only skip if backend confirms completion
      if (sessionStatus.value === SessionStatus.COMPLETED || sessionStatus.value === SessionStatus.FAILED) {
        replay.loadScreenshots();
        return;  // Don't resume
      }
    }
    // Stale or backend says still running - proceed with resume
    localStorage.removeItem(stoppedKey);
  }

  // Resume connection
  await chat();
}
```

### Issue 3: lastEventId Not Persisted

**Problem**: `lastEventId.value` is lost on page refresh (it's a ref, not localStorage).

**Check**: Verify if events are being re-delivered on reconnect.

**Fix**: Persist lastEventId to sessionStorage for resumption.

**Location**: `frontend/src/pages/ChatPage.vue`

Add after event processing:
```typescript
const saveLastEventId = (eventId: string) => {
  if (sessionId.value) {
    sessionStorage.setItem(`pythinker-last-event-${sessionId.value}`, eventId);
  }
};

const loadLastEventId = () => {
  if (sessionId.value) {
    const saved = sessionStorage.getItem(`pythinker-last-event-${sessionId.value}`);
    if (saved) {
      lastEventId.value = saved;
    }
  }
};

// In handleEventInternal() after setting lastEventId.value:
lastEventId.value = event.data.event_id;
saveLastEventId(event.data.event_id);

// In restoreSession() before replay loop:
loadLastEventId();
```

### Issue 4: Race Condition on Status Check

**Problem**: Frontend checks status before backend sets it to RUNNING.

**Fix**: Add retry logic in `restoreSession()`:

```typescript
// After replaying events, re-check status if it was INITIALIZING
if (sessionStatus.value === SessionStatus.INITIALIZING) {
  await waitForSessionIfInitializing();
}

// Add small delay + re-check for RUNNING sessions
if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
  // Small delay to allow backend to fully initialize
  await new Promise(resolve => setTimeout(resolve, 500));
  const recheck = await agentApi.getSession(sessionId.value!);
  sessionStatus.value = recheck.status as SessionStatus;

  // Now proceed with resume logic
  if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
    await chat();
  }
}
```

## Debugging Steps

### 1. Enable Detailed Logging

**Backend**:
```python
# In agent_domain_service.py chat() method, add:
logger.info(f"Chat called: session_id={session_id}, message={'<empty>' if not message else message[:50]}, latest_event_id={latest_event_id}, status={session.status}")
```

**Frontend**:
```typescript
// In restoreSession(), add:
console.log('[RESTORE] Session:', sessionId.value, 'Status:', sessionStatus.value, 'LastEventId:', lastEventId.value);
```

### 2. Monitor Session Lifecycle

```bash
# Terminal 1: Watch backend logs
docker logs -f pythinker-backend-1 | grep -i "session\|chat\|running\|disconnect"

# Terminal 2: Watch session status
watch -n 1 'curl -s -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/v1/sessions/SESSION_ID | jq ".data.status"'
```

### 3. Test Scenario

1. Start a long-running task (e.g., "Search for Python tutorials and summarize top 5")
2. Wait for agent to start executing
3. Open browser DevTools → Network tab → filter SSE
4. Note the last `event_id` received
5. Refresh page (F5)
6. Check:
   - Does SSE reconnect?
   - Is `lastEventId` passed in request?
   - Are events delivered from correct point?
   - Does agent continue in sandbox?

## Recommended Fix Priority

### Phase 1: Immediate Fixes (High Impact)
1. ✅ **Fix Session Status Transition**: Ensure status is set to `RUNNING` when task starts
2. ✅ **Persist lastEventId**: Save to sessionStorage for proper event resumption
3. ✅ **Clear stale localStorage flags**: Defensive cleanup of "stopped" flags

### Phase 2: Resilience Improvements (Medium Impact)
4. ⚠️ **Add status re-check logic**: Handle race conditions on refresh
5. ⚠️ **Improve duplicate message detection**: Better reconnection detection
6. ⚠️ **Add reconnection UI feedback**: Show "Reconnecting..." state

### Phase 3: Monitoring & Observability (Low Impact)
7. 📊 **Add metrics**: Track SSE reconnections, failed resumes
8. 📊 **Enhanced logging**: Structured logs for debugging
9. 📊 **User notification**: Optional toast "Agent still running" on refresh

## Verification Checklist

After implementing fixes:

- [ ] Page refresh during agent execution maintains connection
- [ ] Events are not duplicated on reconnect
- [ ] UI state is correctly restored (messages, tools, status)
- [ ] Agent task continues running in sandbox
- [ ] VNC/screencast connection survives refresh
- [ ] localStorage cleanup works correctly
- [ ] Manual stop button still works as expected
- [ ] 60-second stop window prevents unwanted resume

## Related Files

**Frontend**:
- `frontend/src/pages/ChatPage.vue` (lines 1716-1890) - Chat and restore logic
- `frontend/src/api/agent.ts` (line 182-214) - `chatWithSession()`
- `frontend/src/api/client.ts` (line 289-450) - SSE connection management

**Backend**:
- `backend/app/interfaces/api/session_routes.py` (line 281-375) - Chat endpoint
- `backend/app/application/services/agent_service.py` (line 490-600) - Chat service
- `backend/app/domain/services/agent_domain_service.py` (line 657-996) - Domain logic
- `backend/app/domain/repositories/session_repository.py` - Session persistence

## Testing Commands

```bash
# Frontend type check
cd frontend && bun run type-check

# Backend linting
cd backend && conda activate pythinker && ruff check .

# Run integration tests
cd backend && pytest tests/integration/test_agent_e2e.py -v -k session

# Check for session status issues
cd backend && pytest tests/domain/services/test_agent_domain_service_stop_session.py -v
```
