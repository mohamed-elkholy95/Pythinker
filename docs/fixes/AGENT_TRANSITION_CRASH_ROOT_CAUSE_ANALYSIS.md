# Agent Transition Crash - Root Cause Analysis

**Date**: 2026-02-12
**Status**: Phase 1 Investigation Complete
**Severity**: CRITICAL - UI crashes, agent gets stuck, sandbox/browser failures

---

## Executive Summary

The system experiences crashes and stuck states when transitioning between agent tasks. Root cause investigation reveals **three critical failure modes** in the agent stop/restart lifecycle:

1. **Frontend sends messages to COMPLETED sessions without re-initialization**
2. **Backend browser initialization fails for reused sandboxes**
3. **Race condition between sandbox cleanup and new message handling**

---

## Evidence Gathered

### 1. Backend Logs (Docker)

```
RuntimeError: Browser init failed for sandbox dev-sandbox-sandbox
```

**Context**: Browser initialization fails when trying to reuse a sandbox that has been partially cleaned up or is in an invalid state.

**Source**: `docker logs pythinker-backend-1`

### 2. Frontend Code (`frontend/src/pages/ChatPage.vue`)

**Lines 2088-2237: `chat()` function**

```typescript
const chat = async (
  message: string = '',
  files: FileInfo[] = [],
  options?: { skipOptimistic?: boolean }
) => {
  if (!sessionId.value) return;

  // Cancel any existing chat connection before starting a new one
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }

  // ❌ PROBLEM: No check if session is COMPLETED
  // ❌ PROBLEM: No check if sandbox/browser need re-initialization
  // ❌ PROBLEM: Directly calls agentApi.chatWithSession on potentially dead session

  cancelCurrentChat.value = await agentApi.chatWithSession(
    sessionId.value,
    normalizedMessage,
    lastEventId.value,
    // ...
  );
}
```

**Issue**: When user sends a new message after agent completes, the frontend:
- Does NOT check if `sessionStatus.value === SessionStatus.COMPLETED`
- Does NOT create a new session
- Directly sends chat request to the existing (completed) session
- Assumes sandbox/browser are still valid

### 3. Backend Code (`backend/app/application/services/agent_service.py`)

**Lines 134-232: `create_session()`**

```python
async def create_session(self, user_id: str, ...) -> Session:
    # Auto-stop any stale running sessions to release sandbox/browser resources
    await self._cleanup_stale_sessions(user_id)
    # ...
```

**Lines 234-285: `_cleanup_stale_sessions()`**

```python
async def _cleanup_stale_sessions(self, user_id: str) -> None:
    """Stop any stale sessions with active runtime state for this user.

    When a user starts a new task, any previously running sessions should be
    stopped to release sandbox and browser resources, preventing connection
    pool exhaustion (BROWSER_1004).
    """
    active_statuses = {SessionStatus.RUNNING, SessionStatus.INITIALIZING}
    sessions = await self._session_repository.find_by_user_id(user_id)
    stale = [s for s in sessions if s.status in active_statuses or s.sandbox_id]
    # ...
```

**Issue**: Cleanup only targets `RUNNING` or `INITIALIZING` sessions, but:
- COMPLETED sessions with sandbox_id are NOT cleaned up
- When new chat is sent to COMPLETED session, sandbox may be in invalid state
- Browser connection pool may still have stale connections

**Lines 558-832: `chat()` function**

```python
async def chat(
    self,
    session_id: str,
    user_id: str,
    message: str | None = None,
    # ...
) -> AsyncGenerator[AgentEvent, None]:
    # ❌ PROBLEM: No check if session is COMPLETED
    # ❌ PROBLEM: No sandbox/browser state validation
    # ❌ PROBLEM: Assumes session is ready to accept new messages
```

### 4. Domain Service (`backend/app/domain/services/agent_domain_service.py`)

**Lines 125-213: `acquire_sandbox_from_pool()`**

```python
async def acquire_sandbox_from_pool() -> Sandbox:
    # Acquires sandbox from pool
    # ...

# Line 207: Browser init failure point
if not browser_init_successful:
    raise RuntimeError(f"Browser init failed for sandbox {target_sandbox.id}")
```

**Issue**: When browser initialization fails:
- Sandbox may be in partially initialized state
- No retry mechanism
- No cleanup of failed browser connections
- Throws exception that crashes the chat flow

---

## Root Cause Analysis

### Root Cause #1: Missing Session State Validation (Frontend)

**Location**: `frontend/src/pages/ChatPage.vue` - `chat()` function (lines 2088-2237)

**Problem**:
- Frontend does NOT check if session is COMPLETED before sending new message
- Assumes session can always accept new messages
- No logic to create new session for followup tasks

**Impact**:
- New messages sent to completed sessions with dead sandbox/browser
- Backend fails to initialize browser for stale sandbox
- UI crashes when backend returns error

**Evidence**:
```typescript
// ❌ Missing validation:
if (sessionStatus.value === SessionStatus.COMPLETED) {
  // Should create new session here
}
```

### Root Cause #2: Browser Re-initialization Failure (Backend)

**Location**: `backend/app/domain/services/agent_domain_service.py` - Browser init (line 207)

**Problem**:
- Browser initialization fails for reused sandboxes
- No retry mechanism
- No cleanup of failed state
- Exception crashes entire chat flow

**Impact**:
- `RuntimeError: Browser init failed for sandbox dev-sandbox-sandbox`
- Chat flow terminates
- Frontend receives error, UI crashes

**Evidence**:
```
RuntimeError: Browser init failed for sandbox dev-sandbox-sandbox
```

### Root Cause #3: Incomplete Cleanup Logic (Backend)

**Location**: `backend/app/application/services/agent_service.py` - `_cleanup_stale_sessions()` (lines 234-285)

**Problem**:
- Only cleans up RUNNING/INITIALIZING sessions
- COMPLETED sessions with sandbox_id are NOT cleaned up
- Browser connection pool may have stale connections
- Sandbox may be in partially cleaned state

**Impact**:
- Race condition: new message arrives while old sandbox is being cleaned
- Sandbox in invalid state when reused
- Browser connections not properly closed

**Evidence**:
```python
active_statuses = {SessionStatus.RUNNING, SessionStatus.INITIALIZING}
# ❌ COMPLETED sessions with sandbox_id NOT included
```

---

## Failure Modes

### Mode 1: User Sends New Message After Agent Completes

**Sequence**:
1. Agent completes task → Session status = COMPLETED
2. User sends new message (either typing or clicking followup)
3. Frontend calls `chat()` without checking session status
4. Backend receives chat request for COMPLETED session
5. Backend tries to reuse existing sandbox (may be partially cleaned)
6. Browser initialization fails → `RuntimeError`
7. Frontend receives error → UI crashes

**Frequency**: HIGH (every new task after completion)

### Mode 2: User Clicks Suggested Followup

**Sequence**:
1. Agent shows followup suggestions
2. User clicks suggestion → `handleSuggestionSelect()` called (line 1893)
3. Calls `handleSubmit()` → calls `chat()`
4. Same failure as Mode 1 (no session state check)

**Frequency**: HIGH (every followup click)

### Mode 3: Page Refresh on Running Session

**Sequence** (handled better, but still has issues):
1. Page refreshes during RUNNING session
2. `restoreSession()` called (line 2248)
3. Reconnects to existing session with lastEventId
4. BUT: If session transitioned to COMPLETED during refresh, same issues apply

**Frequency**: MEDIUM (page refreshes during transitions)

---

## Multi-Component System Diagnostic

Following Phase 1 guidelines for multi-component systems, here's the data flow:

```
┌──────────────────┐
│   Frontend       │
│   ChatPage.vue   │  ❌ No session state validation
└────────┬─────────┘
         │ chat() → agentApi.chatWithSession()
         ▼
┌──────────────────┐
│   Backend API    │
│ session_routes   │  ✓ Receives request
└────────┬─────────┘
         │ POST /api/v1/sessions/{id}/chat
         ▼
┌──────────────────┐
│  Agent Service   │  ❌ No COMPLETED session check
│  agent_service   │  ❌ No sandbox state validation
└────────┬─────────┘
         │ chat()
         ▼
┌──────────────────┐
│  Domain Service  │  ❌ Browser init fails
│  agent_domain    │  ❌ No retry mechanism
└────────┬─────────┘
         │ acquire_sandbox_from_pool()
         ▼
┌──────────────────┐
│  Sandbox Pool    │  ⚠️ Returns sandbox (may be stale)
│  sandbox_pool    │
└────────┬─────────┘
         │ acquire()
         ▼
┌──────────────────┐
│   Docker         │  ❌ Browser init fails
│   Sandbox        │  → RuntimeError
└──────────────────┘
```

**Failure Point**: Browser initialization in Docker sandbox (deepest layer)
**Propagation**: Error propagates up → crashes entire chat flow → frontend UI crashes

---

## Pattern Analysis (Phase 2)

### Working Examples (for comparison):

1. **Create New Session** (`agent_service.py:134-232`)
   - Calls `_cleanup_stale_sessions()` FIRST
   - Creates fresh session
   - Initializes sandbox from pool
   - ✓ Works correctly

2. **Stop Session** (`agent_service.py:842-852`)
   - Cancels warmup tasks
   - Calls domain service stop
   - ✓ Works correctly

### Broken Example:

**Chat on COMPLETED Session** (`ChatPage.vue:2088-2237` + `agent_service.py:558-832`)
- No session state validation
- No cleanup of old sandbox/browser
- No re-initialization logic
- ❌ Fails catastrophically

### Differences:

| Working (create_session)        | Broken (chat on completed)      |
|---------------------------------|---------------------------------|
| Cleanup stale sessions first    | No cleanup                      |
| Fresh sandbox from pool         | Reuses stale sandbox            |
| Browser pre-warmed              | Browser init fails              |
| State validation               | No state validation             |

---

## Next Steps (Phase 3: Hypothesis and Testing)

### Hypothesis #1: Frontend State Validation

**Theory**: Adding session state check in frontend `chat()` will prevent sending messages to completed sessions.

**Test**:
1. Add check for `sessionStatus.value === SessionStatus.COMPLETED`
2. If completed, create new session before sending message
3. Verify no more browser init errors

### Hypothesis #2: Backend Sandbox Cleanup

**Theory**: Cleaning up COMPLETED sessions' sandboxes will prevent stale state.

**Test**:
1. Modify `_cleanup_stale_sessions()` to include COMPLETED sessions with sandbox_id
2. Verify sandbox/browser are properly cleaned before reuse
3. Monitor for browser init failures

### Hypothesis #3: Browser Init Retry Mechanism

**Theory**: Adding retry logic for browser initialization will handle transient failures.

**Test**:
1. Add retry loop (max 2-3 attempts) for browser init
2. Add proper cleanup between retries
3. Verify reduced browser init failures

---

## Recommendations

### Immediate Fixes (Priority: CRITICAL)

1. **Frontend Session State Validation** (ChatPage.vue)
   - Check session status before sending message
   - Create new session if current session is COMPLETED
   - Preserve sandbox_id for potential reuse

2. **Backend COMPLETED Session Cleanup** (agent_service.py)
   - Include COMPLETED sessions in `_cleanup_stale_sessions()`
   - Properly close browser connections
   - Release sandbox back to pool or destroy

3. **Browser Init Retry Logic** (agent_domain_service.py)
   - Add max 2 retry attempts for browser initialization
   - Clean up failed browser instances between retries
   - Log failures for monitoring

### Medium-Term Improvements

4. **Sandbox State Machine**
   - Implement proper state transitions (IDLE → WARMING → READY → IN_USE → CLEANUP)
   - Validate state before allocation
   - Prevent allocation of sandboxes in invalid states

5. **Browser Connection Pool Monitoring**
   - Add metrics for stale connections
   - Implement connection health checks
   - Auto-cleanup of dead connections

6. **UI Loading States**
   - Show clear "Starting new session..." message
   - Prevent duplicate clicks during transitions
   - Better error messaging for users

---

## Supporting Files

- Frontend: `frontend/src/pages/ChatPage.vue` (lines 2088-2237, 1893-1898, 2248-2313)
- Backend Service: `backend/app/application/services/agent_service.py` (lines 134-285, 558-832)
- Domain Service: `backend/app/domain/services/agent_domain_service.py` (lines 125-213)
- Sandbox Pool: `backend/app/core/sandbox_pool.py` (lines 346-443)

---

## Conclusion

This is NOT a simple bug - it's an **architectural issue** with session lifecycle management across frontend/backend boundaries. The fix requires coordinated changes in multiple layers:

1. Frontend state machine (session status transitions)
2. Backend cleanup logic (COMPLETED session handling)
3. Sandbox/browser initialization (retry + validation)

**Estimated Fix Complexity**: HIGH
**Estimated Risk**: MEDIUM (requires careful testing)
**Estimated Time**: 4-6 hours (including testing)

Following Phase 4 guidelines: We need to create failing test cases BEFORE implementing fixes.

---

## Addendum - Follow-up Investigation (2026-02-12)

This addendum captures a deeper code-level review of the current branch state. It does not claim implementation of fixes yet; it records verified findings only.

### Investigation Scope (Completed)

- Frontend lifecycle and transition handling:
  - `frontend/src/pages/ChatPage.vue`
  - `frontend/src/api/client.ts`
  - `frontend/src/types/event.ts`
  - `frontend/src/components/Suggestions.vue`
- Backend transition/reinitialization paths:
  - `backend/app/interfaces/api/session_routes.py`
  - `backend/app/application/services/agent_service.py`
  - `backend/app/domain/services/agent_domain_service.py`
  - `backend/app/domain/services/agent_task_runner.py`
- Existing tests relevant to this surface:
  - `backend/tests/application/services/test_agent_service_latency_guards.py`
  - `backend/tests/interfaces/api/test_session_routes.py`

### Confirmed Findings (Current Code Snapshot)

1. Route-level short-circuit blocks reactivation for completed sessions even with fresh user input.
   - Evidence: `backend/app/interfaces/api/session_routes.py:351` to `backend/app/interfaces/api/session_routes.py:358`
   - Behavior: `POST /sessions/{id}/chat` exits early for `completed/failed` and emits a synthetic `done` event.
   - Impact: New task/follow-up messages are never forwarded to `agent_service.chat(...)`, so domain-level reactivation logic is bypassed.

2. Chat route emits manual SSE payloads that do not match the typed event schema expected by frontend handlers.
   - Evidence:
     - `backend/app/interfaces/api/session_routes.py:356` emits `{"message":"Session already completed"}`
     - `backend/app/interfaces/api/session_routes.py:433` emits `{"message":"Stream error: ..."}`
     - Frontend error shape requires `error`: `frontend/src/types/event.ts:108` to `frontend/src/types/event.ts:110`
     - Frontend renderer reads only `errorData.error`: `frontend/src/pages/ChatPage.vue:1411` to `frontend/src/pages/ChatPage.vue:1419`
   - Impact: Error/done branches can produce malformed UI state or blank error message rendering.

3. SSE client JSON parsing is not guarded against malformed payloads.
   - Evidence: `frontend/src/api/client.ts:440` performs `JSON.parse(event.data)` with no local try/catch in `onmessage`.
   - Impact: A malformed payload can throw during stream handling and force error/reconnect paths; this is a plausible contributor to transition instability.

4. Incomplete-task transition guidance is inconsistent across terminal paths.
   - Evidence:
     - Completion suggestions are only guaranteed on `done`: `frontend/src/pages/ChatPage.vue:2005` to `frontend/src/pages/ChatPage.vue:2008`
     - `onClose` and `onError` reset loading flags but do not ensure follow-up guidance: `frontend/src/pages/ChatPage.vue:2201` to `frontend/src/pages/ChatPage.vue:2238`
     - Manual stop does not call `ensureCompletionSuggestions()`: `frontend/src/pages/ChatPage.vue:2530` to `frontend/src/pages/ChatPage.vue:2558`
     - Suggestions UI label currently reads `"Suggested follow-ups"`: `frontend/src/components/Suggestions.vue:4`
   - Impact: After interruption/error/stop, users can be left without a clear next action prompt (`send a new task` vs `use follow-ups`).

5. Domain fallback can mark ambiguous no-output executions as successful completion.
   - Evidence: `backend/app/domain/services/agent_domain_service.py:1033` to `backend/app/domain/services/agent_domain_service.py:1058`
   - Behavior: When `received_events` is false but new input exists, code emits `DoneEvent(... summary="Session completed.")`.
   - Impact: Silent/incomplete execution may be reported as completed, hiding underlying runtime failure.

6. Application timeout path reports timeout but does not force runtime teardown/recovery.
   - Evidence: `backend/app/application/services/agent_service.py:686` to `backend/app/application/services/agent_service.py:698`
   - Behavior: Emits recoverable `ErrorEvent` and returns.
   - Impact: Session/task runtime may remain in an indeterminate state after timeout, increasing lock-up risk on next transition.

7. Test coverage gap on chat-route transition behavior.
   - Evidence: `backend/tests/interfaces/api/test_session_routes.py` currently validates utility endpoints only and does not cover `/chat` terminal branches.
   - Impact: Regressions in completed-session reentry and SSE payload contract are currently unguarded.

### Corrected Points vs Earlier Sections in This Document

These earlier assumptions are no longer accurate against the current code snapshot:

- "Completed sessions are not cleaned in stale cleanup" is outdated.
  - Current behavior includes any session with `sandbox_id`: `backend/app/application/services/agent_service.py:247`
- "No browser init retry/recycle path" is outdated.
  - Current create-task path retries via sandbox recycle on browser init failure/timeouts: `backend/app/domain/services/agent_domain_service.py:232` to `backend/app/domain/services/agent_domain_service.py:289`
- "No frontend SSE reconnect support" is outdated.
  - Current SSE client includes retry/backoff and max retry handling: `frontend/src/api/client.ts:466` to `frontend/src/api/client.ts:500`

### Remediation Status (Factual)

| Area | Status | Notes |
|---|---|---|
| Root-cause investigation and evidence collection | Completed | Findings above are verified against current source files |
| Transition/reinit code fixes (frontend/backend) | Not Started | No code changes merged in this addendum |
| `/chat` route reactivation + schema-safe SSE payload fixes | Not Started | Pending implementation |
| Timeout teardown/recovery hardening | Not Started | Pending implementation |
| Incomplete-task UX guidance (`new task` vs follow-ups) | Not Started | Pending implementation |
| Regression tests for `/chat` transition paths | Not Started | Pending implementation |

### Proposed Next Fix Sequence

1. Backend route guard fix first: allow `/chat` to proceed for completed/failed sessions when fresh input is present; keep short-circuit only for pure reconnect/no-input calls.
2. Replace manual SSE JSON strings with `EventMapper`-mapped `DoneEvent`/`ErrorEvent` payloads to preserve schema consistency.
3. Harden frontend SSE parsing and error display fallback (`error` + legacy `message`) to avoid stream-handling crashes.
4. Update frontend terminal-path UX: when task ends incomplete/stopped/error, explicitly prompt user to send a new task or use the follow-up suggestions section.
5. Add backend route tests for completed-session reentry and SSE payload schema compliance.
