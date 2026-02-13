# SSE Timeout Suggestions Fix

**Date**: 2026-02-12
**Issue**: Suggested follow-ups appear on timeout instead of completion
**Status**: ✅ Fixed

## Problem

When SSE streams timeout (120s without events), the frontend would show:
1. ❌ "Suggested follow-ups" UI (premature - agent may still be working)
2. ❌ Contradictory state: "Connection interrupted" + "browsing" status
3. ❌ No way to distinguish timeout from actual completion

This created a confusing UX where users saw "done" UI elements even though the agent was still running in the background.

## Root Cause

**Previous logic** (`canShowSuggestions`):
```typescript
const canShowSuggestions = computed(() =>
  isSettled.value && suggestions.value.length > 0 && !isSummaryStreaming.value
)
```

**Problem**: Only checked `responsePhase === 'settled'`, not `sessionStatus === COMPLETED`.

**Why this failed**:
- SSE timeout → `responsePhase = 'timed_out'` (NOT settled)
- BUT suggestions were already populated by `ensureCompletionSuggestions()`
- When auto-retry succeeded → `responsePhase = 'settled'`
- Suggestions showed even if session was still RUNNING (not COMPLETED)

## Solution

### 1. Enhanced `canShowSuggestions` Logic

**New logic**:
```typescript
const canShowSuggestions = computed(() =>
  isSettled.value &&
  sessionStatus.value === SessionStatus.COMPLETED && // ← NEW: Backend confirmation
  suggestions.value.length > 0 &&
  !isSummaryStreaming.value
)
```

**Requirements (ALL must be true)**:
1. `responsePhase === 'settled'` (response lifecycle complete)
2. `sessionStatus === COMPLETED` (backend confirmed completion)
3. `suggestions.length > 0` (have suggestions to show)
4. `!isSummaryStreaming` (summary is done streaming)

### 2. Added `stopped` Phase

**Updated `ResponsePhase` type**:
```typescript
export type ResponsePhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'completing'
  | 'settled'
  | 'error'
  | 'timed_out'
  | 'stopped' // ← NEW
```

**Benefits**:
- Clear distinction between user-initiated stop vs. timeout
- `handleStop()` already used `transitionTo('stopped')`, now properly typed
- No suggestions on manual stop (per existing logic)

### 3. Timeout UI Clarity

**Existing UI** (kept as-is, already clear):
```vue
<div v-if="responsePhase === 'timed_out'" class="timeout-notice">
  <span>
    {{ autoRetryCount < 4
      ? 'Connection interrupted. Reconnecting automatically...'
      : 'Connection interrupted. The agent may still be working.'
    }}
  </span>
  <button @click="handleRetryConnection">Retry</button>
</div>
```

**Key message**: "The agent may still be working" (NOT "Task completed")

## State Transitions

### Normal Completion Flow
```
connecting → streaming → completing → settled
                                       ↓
                                 COMPLETED status
                                       ↓
                                  Show suggestions ✅
```

### Timeout + Retry Flow
```
connecting → streaming → timed_out (no suggestions ⚠️)
                              ↓
                         User clicks Retry
                              ↓
                         connecting → streaming → completing → settled
                                                                ↓
                                                          COMPLETED status
                                                                ↓
                                                           Show suggestions ✅
```

### Manual Stop Flow
```
connecting → streaming → stopped (no suggestions ❌)
                              ↓
                         COMPLETED status
                              ↓
                    NO suggestions (user stopped)
```

## Files Modified

### Core Logic
1. **`frontend/src/composables/useResponsePhase.ts`**
   - Added `'stopped'` to `ResponsePhase` type
   - Exported `isStopped` computed property

2. **`frontend/src/pages/ChatPage.vue`**
   - Fixed `canShowSuggestions` to check `sessionStatus === COMPLETED`
   - Added `isStopped` to destructuring (TypeScript completeness)

### Tests
3. **`frontend/src/composables/__tests__/useResponsePhase.test.ts`**
   - Added tests for `timed_out`, `stopped`, `error` phases
   - Verified `isLoading` is false for terminal states
   - Verified computed properties work correctly

4. **`frontend/tests/pages/ChatPage.suggestions-visibility.spec.ts`** (NEW)
   - 14 comprehensive tests for suggestions visibility logic
   - Tests all state transitions (normal, timeout, retry, stop)
   - Tests edge cases (error, failed status, empty suggestions)

## Test Results

```bash
✓ useResponsePhase tests (13 tests) - All passing
✓ ChatPage suggestions visibility (14 tests) - All passing
✓ Type checking - No errors
✓ Linting - No errors
```

## User Experience After Fix

### ✅ Timeout State
```
┌─────────────────────────────────────────────┐
│ ⚠️  Connection interrupted.                  │
│     Reconnecting automatically...      [Retry]│
└─────────────────────────────────────────────┘
```
- Clear "reconnecting" message
- Manual retry option
- NO "Suggested follow-ups" (agent may still be working)

### ✅ Completed State
```
┌─────────────────────────────────────────────┐
│ ✓ Task completed                            │
│                                              │
│ Suggested follow-ups:                       │
│ → What are the best next steps?             │
│ → Can you give me a practical example?      │
└─────────────────────────────────────────────┘
```
- Green checkmark
- Suggestions ONLY when `sessionStatus === COMPLETED`
- Clear "done" state

## Related Issues

- **SSE Timeout Quick Reference**: `docs/fixes/SSE_TIMEOUT_QUICK_REFERENCE.md`
- **Full Analysis**: `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md`
- **Session Persistence**: `docs/fixes/PAGE_REFRESH_SESSION_PERSISTENCE.md`

## Next Steps (Follow-on Work)

1. **Add SSE Heartbeat** (P0 - prevents timeouts during retries)
2. **Emit progress events during retries** (P0 - user visibility)
3. **Add stream reconnection support** (P1 - resume after timeout)
4. **Cancel background tasks on SSE close** (P1 - prevent orphaned work)

## Validation

**Before Fix**:
- ❌ Suggestions appear on timeout (contradictory UX)
- ❌ User sees "done" UI while agent is still working
- ❌ Duplicate requests triggered due to confusion

**After Fix**:
- ✅ Suggestions ONLY on `sessionStatus === COMPLETED`
- ✅ Clear timeout UI distinct from completion
- ✅ Proper state machine transitions
- ✅ Comprehensive test coverage (27 tests)

---

**Commit**: Included in timeout handling improvements
**Testing**: All tests passing (useResponsePhase + suggestions visibility)
