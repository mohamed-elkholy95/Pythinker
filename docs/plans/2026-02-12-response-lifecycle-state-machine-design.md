# Response Lifecycle State Machine + Visual Polish

**Date:** 2026-02-12
**Status:** Approved
**Approach:** #2 - Response Lifecycle State Machine + Visual Polish

---

## Problem Statement

The frontend UI has several interrelated issues:

1. **Premature Suggested Follow-ups**: `ensureCompletionSuggestions()` is called on SSE `onClose()` and `onError()`, which fire on timeout — not just on actual task completion. This causes suggestions to appear while the backend is still working.
2. **Fast Path Suggestions**: Greeting fast-path responses show generic fallback suggestions that look out of place.
3. **No Progress Feedback**: During long operations (browser actions, research), the UI shows no indication the agent is still working — it looks frozen.
4. **Independent State Booleans**: `isResponseSettled`, `isLoading`, `isThinking`, `isWaitingForReply` operate independently, causing contradictory UI states.
5. **Generic Timeout Error**: The "Chat stream timed out" error is alarming and shows suggestions alongside it.

## Root Cause Analysis

The core issue is that the frontend has no unified state machine for the response lifecycle. Multiple independent booleans (`isResponseSettled`, `isLoading`, `isThinking`) are toggled by different triggers (SSE events, transport callbacks), leading to impossible state combinations.

Key finding: The backend already sends 15-second heartbeat events (`PlanningPhase.HEARTBEAT`), but the frontend doesn't use them visually.

---

## Design

### Section 1: Response Lifecycle State Machine

Replace independent booleans with a single `responsePhase` state:

```
IDLE → CONNECTING → STREAMING → COMPLETING → SETTLED
                  ↘ TIMED_OUT (timeout, no 'done' received)
                  ↘ ERROR (error event or SSE error)
                  ↘ STOPPED (user clicked stop)
```

**State definitions:**

| State | Triggered by | UI behavior |
|-------|-------------|-------------|
| `IDLE` | Initial / after reset | Input enabled, no indicators |
| `CONNECTING` | User sends message | Thinking indicator, input disabled |
| `STREAMING` | First SSE event received | Loading indicator, tool activity shown |
| `COMPLETING` | `'done'` event received | Brief completion animation |
| `SETTLED` | After `COMPLETING` delay (300ms) | Suggestions shown (if any), input enabled |
| `TIMED_OUT` | SSE timeout/close WITHOUT `'done'` | "Connection lost" banner, retry button, NO suggestions |
| `ERROR` | Error event | Error message shown, NO suggestions |
| `STOPPED` | User stop action | Input enabled, NO suggestions |

**Key rule: Suggestions ONLY render in `SETTLED` state.**

**Implementation:**

```typescript
type ResponsePhase = 'idle' | 'connecting' | 'streaming' | 'completing' | 'settled' | 'timed_out' | 'error' | 'stopped'

const responsePhase = ref<ResponsePhase>('idle')

// Backward-compatible computed properties
const isLoading = computed(() => ['connecting', 'streaming'].includes(responsePhase.value))
const isThinking = computed(() => responsePhase.value === 'connecting')
const isResponseSettled = computed(() => responsePhase.value === 'settled')
const canShowSuggestions = computed(() =>
  responsePhase.value === 'settled' && suggestions.value.length > 0 && !isSummaryStreaming.value
)
```

### Section 2: Suggestions Logic Fix

**Remove `ensureCompletionSuggestions()` from `onClose()` and `onError()` callbacks entirely.**

Only generate suggestions in these cases:
- `'done'` event received → check if backend sent `SuggestionEvent`. If not, generate contextual fallback (but NOT for greetings).
- `'suggestion'` event received from backend → store directly (already works).

**Fast path suggestion rules:**

| Fast Path Intent | Show Suggestions? | Source |
|-----------------|-------------------|--------|
| Greeting | No | - |
| Knowledge | Yes | Backend `SuggestionEvent` or contextual fallback |
| Browse/Search | Yes | Backend `SuggestionEvent` or contextual fallback |
| Complex Task | Yes | Backend `SuggestionEvent` (always generated after summarization) |

**Track `receivedDoneEvent` flag:**
- `onClose()`: If `receivedDoneEvent === true` → `SETTLED`. If `false` → `TIMED_OUT`.

**Fallback suggestion filtering:** Enhance `buildCompletionFallbackSuggestions()` to return empty array for greeting responses.

### Section 3: Heartbeat Visual Integration

The backend sends heartbeat events every 15 seconds (`PlanningPhase.HEARTBEAT`).

1. **Track heartbeat** via `lastHeartbeatAt` timestamp.
2. **"Still working" indicator** - When in `STREAMING` state, no real event for >5s but heartbeats arriving, show subtle pulsing "Working..." indicator.
3. **Stale detection** - No heartbeat AND no event for >30s → "Connection may be unstable..." warning.
4. **Handle heartbeat in `handleEvent()`** - Update timestamp only, don't change `responsePhase`.

### Section 4: Visual Polish

**CONNECTING:** Thinking dots animation (already exists), input disabled with "Pythinker is thinking..."

**STREAMING:** Pulse animation on loading indicator when heartbeats arrive (proves liveness). Smooth fade-in for messages.

**COMPLETING:** Brief checkmark/fade transition. Suggestions fade in after 300ms delay.

**TIMED_OUT:** Clean banner: "Connection interrupted. The agent may still be working." + Retry button. Amber/yellow styling, NOT red. NO suggestions.

**ERROR:** Current error display. NO suggestions.

**STOPPED:** Brief "Stopped" indicator. Input re-enabled. NO suggestions.

### Section 5: Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/pages/ChatPage.vue` | Add `responsePhase` state machine, replace independent booleans with computed properties, fix `onClose`/`onError` callbacks, update suggestion display condition, handle heartbeat events |
| `frontend/src/components/Suggestions.vue` | Add fade-in transition animation (CSS only) |
| `frontend/src/components/ui/LoadingIndicator.vue` | Add heartbeat pulse variant, "still working" text mode |

**Not modified:** Backend (heartbeat mechanism already works, suggestion events already generated properly). Frontend-only fix.

---

## What This Fixes

| Problem | Fix |
|---------|-----|
| Suggestions appear on SSE timeout | Only show in `SETTLED` state (requires `'done'` event) |
| Suggestions appear during fast path greetings | Skip fallback suggestions for greeting responses |
| UI looks frozen during long operations | Heartbeat-driven "still working" indicator |
| Loading indicators appear/disappear incorrectly | Single `responsePhase` state machine drives all indicators |
| Chat feels laggy with layout shifts | CSS transitions on state changes |
| Timeout shows generic error | Clean "connection interrupted" banner with retry, no suggestions |
