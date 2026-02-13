# Timeout vs Completion - Quick Reference

**Last Updated**: 2026-02-12

## The Golden Rule

**Suggestions = Backend confirms COMPLETED status + Frontend confirms settled phase**

```typescript
// ✅ CORRECT: Both backend and frontend must agree
const canShowSuggestions = computed(() =>
  isSettled.value &&                          // Frontend: response phase is settled
  sessionStatus.value === SessionStatus.COMPLETED &&  // Backend: session is COMPLETED
  suggestions.value.length > 0 &&             // Have suggestions
  !isSummaryStreaming.value                   // Summary is done
)
```

```typescript
// ❌ WRONG: Only checking frontend phase (OLD CODE)
const canShowSuggestions = computed(() =>
  isSettled.value && suggestions.value.length > 0
)
```

## State Matrix

| Response Phase | Session Status | Show Suggestions? | User Message |
|----------------|---------------|-------------------|--------------|
| `timed_out` | `RUNNING` | ❌ NO | "Connection interrupted. Reconnecting..." |
| `settled` | `RUNNING` | ❌ NO | (Loading or thinking) |
| `settled` | `COMPLETED` | ✅ YES | "Task completed" + suggestions |
| `stopped` | `COMPLETED` | ❌ NO | (User stopped - no suggestions) |
| `error` | `FAILED` | ❌ NO | Error message + retry |

## Common Scenarios

### Scenario 1: Normal Completion
```
Event: done → Phase: settled + Status: COMPLETED
Result: Show suggestions ✅
```

### Scenario 2: Timeout + Background Work
```
Event: SSE timeout → Phase: timed_out + Status: RUNNING
Result: Show timeout UI, NO suggestions ⚠️
```

### Scenario 3: Timeout + Retry + Success
```
Event: Retry successful → Phase: settled + Status: COMPLETED
Result: Show suggestions ✅
```

### Scenario 4: User Stops
```
Event: Stop button → Phase: stopped + Status: COMPLETED
Result: NO suggestions (intentional) ❌
```

## Why Two Checks?

### Backend Status (`sessionStatus`)
- **Source**: MongoDB session document
- **Updated by**: Backend API (`/session/{id}/status`)
- **Authoritative**: Backend knows if task actually completed
- **Values**: `PENDING`, `INITIALIZING`, `RUNNING`, `WAITING`, `COMPLETED`, `FAILED`

### Frontend Phase (`responsePhase`)
- **Source**: SSE stream lifecycle
- **Updated by**: Frontend event handlers
- **Purpose**: UI state management
- **Values**: `idle`, `connecting`, `streaming`, `completing`, `settled`, `error`, `timed_out`, `stopped`

**Problem if only checking frontend**:
- SSE timeout → reconnect → settled phase
- BUT session is still RUNNING (not COMPLETED)
- Suggestions would show prematurely ❌

**Solution**:
- Check BOTH: `isSettled.value && sessionStatus.value === COMPLETED`
- Only show when backend AND frontend agree ✅

## Developer Checklist

When implementing features that depend on completion state:

- [ ] Check `sessionStatus === COMPLETED` (backend confirmation)
- [ ] Check `responsePhase === 'settled'` (frontend confirmation)
- [ ] Handle timeout state separately (don't show "done" UI)
- [ ] Write tests for all state combinations
- [ ] Test timeout + retry flow

## Testing

```typescript
// ✅ Test timeout doesn't show suggestions
it('should NOT show suggestions when timed_out', () => {
  const isSettled = ref(false) // timed_out is NOT settled
  const sessionStatus = ref(SessionStatus.RUNNING)
  const suggestions = ref(['Suggestion 1'])

  const canShowSuggestions = computed(() =>
    isSettled.value &&
    sessionStatus.value === SessionStatus.COMPLETED &&
    suggestions.value.length > 0
  )

  expect(canShowSuggestions.value).toBe(false)
})
```

## Related Files

- **Logic**: `frontend/src/pages/ChatPage.vue` (line ~584)
- **State Machine**: `frontend/src/composables/useResponsePhase.ts`
- **Types**: `frontend/src/types/response.ts`
- **Tests**: `frontend/tests/pages/ChatPage.suggestions-visibility.spec.ts`

## Visual Reference

```
┌─────────────────────────────────────────────┐
│         Timeout (timed_out)                 │
│  ⚠️  Connection interrupted.                 │
│      Reconnecting automatically...    [Retry]│
│                                              │
│  Status: RUNNING                            │
│  Show suggestions: NO ❌                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         Completed (settled)                 │
│  ✓ Task completed                           │
│                                              │
│  Suggested follow-ups:                      │
│  → What are the best next steps?            │
│  → Can you give me a practical example?     │
│                                              │
│  Status: COMPLETED                          │
│  Show suggestions: YES ✅                    │
└─────────────────────────────────────────────┘
```

---

**See Also**:
- Full analysis: `docs/fixes/SSE_TIMEOUT_SUGGESTIONS_FIX.md`
- SSE timeout handling: `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md`
