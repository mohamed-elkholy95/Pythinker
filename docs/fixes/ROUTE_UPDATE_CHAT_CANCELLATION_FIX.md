# Route Update Chat Cancellation Bug - Fixed

**Date:** 2026-02-13
**Status:** ✅ Fixed
**Severity:** 🔴 Critical - Caused sessions to be cancelled prematurely

## Problem

Active chat sessions were being automatically cancelled when Vue Router updated the route, even when staying on the same session. This happened when:
- Clicking on session title or other UI elements that trigger route updates
- Browser navigation (back/forward)
- Any programmatic route change within ChatPage
- URL parameter changes

### Symptoms

- User sees "Chat stream cancelled for session X (client disconnected)" in backend logs
- Session stops mid-execution with status "0/4" (no steps completed)
- UI shows contradictory state: "Task completed" + "0/4" + "searching"
- User didn't manually click stop button
- Happened after 5-77 seconds into execution

### Root Cause

**File:** `frontend/src/pages/ChatPage.vue`
**Location:** `onBeforeRouteUpdate` hook (lines 2857-2887)

The hook unconditionally called `resetState()` on **every** route update, which cancelled the active SSE connection:

```javascript
onBeforeRouteUpdate(async (to, from, next) => {
  // ...
  resetState();  // ❌ ALWAYS called, even when staying on same session
  // ...
})
```

`resetState()` cancels the chat:
```javascript
const resetState = () => {
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();  // Aborts SSE connection
  }
  // ...
}
```

### Evidence

**Session a68eedfc2cae4269:**
- Cancelled after 5.5 seconds (3 events)
- Log: `"Chat stream cancelled for session a68eedfc2cae4269 (client disconnected)"`

**Session dfeec63d25e546ba:**
- Cancelled after 77 seconds (26 events)
- Log: `"Chat stream cancelled for session dfeec63d25e546ba (client disconnected)"`
- Agent was actively executing step 1, tools working successfully

Both showed client-initiated disconnection when route updated.

## Solution

**Modified:** `frontend/src/pages/ChatPage.vue` (lines 2867-2892)

Only reset state and cancel chat when **actually switching to a different session**:

```javascript
onBeforeRouteUpdate(async (to, from, next) => {
  if (skipNextRouteReset.value) {
    skipNextRouteReset.value = false;
    if (to.params.sessionId) {
      sessionId.value = String(to.params.sessionId);
    }
    next();
    return;
  }

  // ✅ NEW: Check if actually switching sessions
  const prevSessionId = from.params.sessionId as string | undefined;
  const nextSessionId = to.params.sessionId as string | undefined;
  const isSwitchingSession = prevSessionId !== nextSessionId;

  // ✅ Only stop session when switching to different session
  if (isSwitchingSession && prevSessionId && shouldStopSessionOnExit(sessionStatus.value)) {
    try {
      await agentApi.stopSession(prevSessionId);
      emitStatusChange(prevSessionId, SessionStatus.COMPLETED);
    } catch {
      // Non-critical — backend safety net will clean up
    }
  }

  // ✅ Only reset state when actually switching sessions
  if (isSwitchingSession) {
    toolPanel.value?.clearContent();
    hideFilePanel();
    resetState();  // Only cancel chat when switching sessions
    if (nextSessionId) {
      messages.value = [];
      sessionId.value = nextSessionId;
      restoreSession();
    }
  }
  next();
})
```

### Key Changes

1. **Session comparison:** Check if `prevSessionId !== nextSessionId`
2. **Conditional reset:** Only call `resetState()` when `isSwitchingSession === true`
3. **Conditional stop:** Only stop backend session when actually switching
4. **Preserve chat:** Route updates within same session no longer cancel the active chat

## Testing

### Manual Test Steps

1. Start a long-running research task (e.g., "Research best IDE coding agents 2026")
2. While agent is executing, click various UI elements:
   - Session title at top of chat
   - Browser back/forward buttons
   - Sidebar elements
   - Any clickable UI that might trigger route updates
3. Verify chat continues running (not cancelled)
4. Check backend logs - should NOT see "client disconnected"

### Expected Behavior

**Before fix:**
- ❌ Chat cancelled on any route update
- ❌ Session stops mid-execution
- ❌ UI shows "0/4" with confusing status

**After fix:**
- ✅ Chat continues running on same-session route updates
- ✅ Chat only cancelled when switching to different session
- ✅ Progress tracked correctly through completion

## Verification Commands

```bash
# Frontend linting
cd frontend && bun run lint

# TypeScript type check
cd frontend && bun run type-check

# Manual testing
# 1. Start dev server: ./dev.sh up -d
# 2. Navigate to http://localhost:5174
# 3. Start a research task
# 4. Click around UI while task runs
# 5. Verify task continues (not cancelled)
```

## Related Issues

- SSE Stream Timeout (docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md)
- Page Refresh Session Persistence (docs/fixes/PAGE_REFRESH_SESSION_PERSISTENCE.md)
- Browser Retry Progress Events (docs/fixes/BROWSER_RETRY_PROGRESS_EVENTS.md)

## Impact

- **Users affected:** All users running long tasks (>10 seconds)
- **Fix priority:** P0 - Critical UX bug
- **Deployment:** Frontend rebuild required
- **Backward compatibility:** Yes - no breaking changes
