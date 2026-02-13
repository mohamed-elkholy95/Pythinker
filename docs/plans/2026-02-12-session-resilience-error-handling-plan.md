# Plan: Session Resilience, Error Handling, and SSE Connection Management

## Context

Users experience three related issues when using Pythinker:
1. **Prompt resubmission/task restart on page refresh** - The page goes blank, replays events, and appears to restart the task (perception issue + SSE reconnection gap)
2. **SSE timeout after 120 seconds** - Backend continues working but frontend disconnects with no auto-recovery
3. **Frontend/backend state desynchronization** - After timeout/disconnect, frontend doesn't reconcile with backend status, shows incorrect state, emits premature COMPLETED notifications

**Root causes**: Missing auto-retry after timeout, no status reconciliation before reconnection, premature COMPLETED emissions on transient errors, RUNNING sessions killed on sidebar navigation, and the frontend `ErrorEventData` interface missing fields the backend already sends.

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/pages/ChatPage.vue` | Status reconciliation, auto-retry, state machine guards, cleanup extraction, error state |
| `frontend/src/types/event.ts` | Extend `ErrorEventData` to match backend schema |
| `frontend/src/utils/sessionLifecycle.ts` | Remove RUNNING from `shouldStopSessionOnExit` |
| `frontend/src/api/client.ts` | Add `onRetry` callback, improve error notification flow |

No backend changes needed - backend already has heartbeats, error classification, and event resumption.

---

## Implementation Steps

### Step 1: Extend `ErrorEventData` interface to match backend
**File**: `frontend/src/types/event.ts:108-110`

Add the three fields the backend already sends (`backend/app/interfaces/schemas/event.py:228-232`):
```typescript
export interface ErrorEventData extends BaseEventData {
  error: string;
  error_type?: string;     // "timeout" | "token_limit" | "tool_execution" | "llm_api"
  recoverable?: boolean;   // Whether retry makes sense
  retry_hint?: string;     // User-facing recovery guidance
}
```

### Step 2: Add error state and auto-retry state to `createInitialState()`
**File**: `ChatPage.vue:436-481`

Add three new fields:
```typescript
lastError: null as { message: string; type: string | null; recoverable: boolean; hint: string | null } | null,
autoRetryCount: 0,
autoRetryTimer: null as ReturnType<typeof setTimeout> | null,
```

Add to destructured refs block (line 487-531) and include in the template.

### Step 3: Add state machine transition guards to `transitionTo()`
**File**: `ChatPage.vue:541-555`

Replace the current permissive transition function with one that validates transitions against an allowlist:

```typescript
const VALID_TRANSITIONS: Record<ResponsePhase, ResponsePhase[]> = {
  idle:       ['connecting'],
  connecting: ['streaming', 'completing', 'settled', 'timed_out', 'error', 'stopped'],
  streaming:  ['completing', 'settled', 'timed_out', 'error', 'stopped'],
  completing: ['settled'],
  settled:    ['connecting', 'idle'],
  timed_out:  ['connecting', 'completing', 'settled', 'error', 'stopped'],
  error:      ['connecting', 'idle'],
  stopped:    ['connecting', 'idle'],
};
```

Block invalid transitions with `console.warn`, allow self-transitions as no-ops. Reset `lastError` on non-error transitions. Reset `autoRetryCount` when entering `streaming`.

### Step 4: Extract shared `cleanupStreamingState()` helper
**File**: `ChatPage.vue` (new function near line 860)

Deduplicate the 8-line cleanup block that appears in 4 places (`chat().onClose`, `chat().onError`, `handleRetryConnection().onClose`, `handleRetryConnection().onError`):

```typescript
const cleanupStreamingState = () => {
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;
  allowStandaloneSummaryOnNextAssistant.value = false;
  isInitializing.value = false;
  planningProgress.value = null;
  stopPlanningMessageCycle();
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value = null;
  }
};
```

Replace all 4 duplicate blocks with `cleanupStreamingState()`.

### Step 5: Status reconciliation in `handleRetryConnection()`
**File**: `ChatPage.vue:2719-2781`

Before attempting SSE reconnect, check backend status via `agentApi.getSessionStatus()`:
- If session is `completed` or `failed`: skip SSE, transition directly to `completing` -> `settled`, emit status change, load screenshots
- If status check fails (network error): fall through to SSE reconnect (which has its own retry logic)
- If session is still `running`: proceed with SSE reconnect as before

This eliminates the "connecting flash" when retrying after a task that already completed.

### Step 6: Auto-retry after timeout
**File**: `ChatPage.vue` (new watcher, near line 960)

Add a watcher on `responsePhase` that automatically triggers `handleRetryConnection()` when entering `timed_out`:
- Progressive backoff: 5s, 15s, 45s delays
- Max 3 auto-retries before requiring manual "Retry" click
- Show "Reconnecting automatically..." message during auto-retry period
- Reset `autoRetryCount` on successful streaming or new message
- Clean up timer in `onUnmounted`

Update timeout notice template (line 173-191):
- During auto-retry: "Connection interrupted. Reconnecting automatically..."
- After max retries: "Connection interrupted. The agent may still be working."
- Always show "Retry Now" button for manual trigger

### Step 7: Remove premature COMPLETED emit from `onError`
**File**: `ChatPage.vue:2372-2374`

Remove `emitStatusChange(sessionId.value, SessionStatus.COMPLETED)` from the `chat()` `onError` callback. Transient SSE errors don't mean the session ended. Status reconciliation (Step 5) and auto-retry (Step 6) handle proper completion detection.

### Step 8: Structured error handling with `lastError`
**File**: `ChatPage.vue`

Update `handleErrorEvent()` (line ~1504) to populate `lastError` with structured data from the backend:
```typescript
lastError.value = {
  message: errorData.error || 'An unexpected error occurred',
  type: errorData.error_type ?? null,
  recoverable: errorData.recoverable ?? true,
  hint: errorData.retry_hint ?? null,
};
```

Classify SSE transport errors in `onError` callbacks:
- "Max reconnection attempts" -> type: `max_retries`, hint: "Refresh the page"
- "Rate limit" -> type: `rate_limit`, recoverable: false, hint: "Wait a minute"
- "validation failed" -> type: `validation`, recoverable: false

Add error notice in template (after timeout notice, line ~191):
```html
<div v-if="responsePhase === 'error' && lastError" class="error-notice ...">
  <span>{{ lastError.message }}</span>
  <span v-if="lastError.hint">{{ lastError.hint }}</span>
  <button v-if="lastError.recoverable" @click="handleRetryConnection">Retry</button>
</div>
```

### Step 9: Don't stop RUNNING sessions on navigation
**File**: `frontend/src/utils/sessionLifecycle.ts`

Remove `SessionStatus.RUNNING` and `SessionStatus.WAITING` from the stop list:
```typescript
export const shouldStopSessionOnExit = (status?: SessionStatus): boolean => {
  if (!status) return false;
  return [SessionStatus.INITIALIZING, SessionStatus.PENDING].includes(status);
};
```

Update `onBeforeRouteUpdate` in ChatPage.vue (line 2469-2498) to cancel SSE connection (stop receiving events) without calling `stopSession()` for RUNNING sessions. This preserves background task execution while freeing the frontend.

### Step 10: Preserve `lastEventId` on navigation
**File**: `ChatPage.vue:866-881`

Remove `cleanupSessionStorage()` from `resetState()`. Event resume data should persist so that navigating away and back resumes from the correct position. Instead, only call `cleanupSessionStorage()` in:
- `handleStop()` (already done at line 2689)
- `done` event handler (add at line ~2137, after session status update)
- Explicit session deletion (handled externally)

### Step 11: Add `onRetry` callback to SSE client
**File**: `frontend/src/api/client.ts`

Add optional `onRetry` to `SSECallbacks` interface:
```typescript
onRetry?: (attempt: number, maxAttempts: number) => void;
```

Call it in `onclose` and `onerror` before starting the retry timer. This lets ChatPage show intermediate retry status without treating retries as terminal errors. Move the `onError` call in `onerror` handler to only fire when max retries are exhausted (terminal failure).

---

## Verification

### Manual Testing
1. **Page refresh during RUNNING session**: Refresh page -> session restores, events replay, SSE reconnects, no prompt resubmission
2. **SSE timeout recovery**: Start long task, throttle network in DevTools -> see "Reconnecting automatically..." -> auto-retry succeeds or shows "Retry Now" after 3 attempts
3. **Status reconciliation**: Start task, disconnect network until task completes, re-enable network -> click Retry -> instant completion (no "connecting" flash)
4. **Sidebar navigation**: Start RUNNING task in session A, click session B in sidebar -> verify session A continues (check `docker logs pythinker-backend-1 --tail 50`)
5. **Error display**: Trigger a token limit error -> verify structured error message with recovery hint appears
6. **State machine**: Open browser console, verify no `[ResponsePhase] BLOCKED` warnings during normal usage

### Automated Checks
```bash
cd frontend && bun run lint && bun run type-check
```

### Monitoring
```bash
# After deploying, watch for SSE timeouts (should decrease significantly)
docker logs pythinker-backend-1 -f | grep -E "(timeout|reconnect|heartbeat)"
```
