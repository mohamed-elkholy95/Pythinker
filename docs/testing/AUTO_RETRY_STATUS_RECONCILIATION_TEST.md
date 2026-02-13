# Auto-Retry and Status Reconciliation Testing Guide

## Overview
This document provides step-by-step tests to verify the auto-retry mechanism and status reconciliation features.

---

## Test 1: Auto-Retry After SSE Timeout (Progressive Backoff)

### Setup
1. Start the development stack:
   ```bash
   ./dev.sh up -d
   ```
2. Open browser DevTools (F12) → Console tab
3. Navigate to http://localhost:5174

### Steps
1. **Start a simple task**:
   - Type: "What is 2+2?"
   - Click Send
   - Wait for response to start streaming

2. **Simulate network interruption**:
   - Open DevTools → Network tab
   - Select "Offline" from the throttling dropdown
   - Wait for SSE timeout (should happen within 5-10 seconds)

3. **Verify auto-retry behavior**:
   - Check Console for log: `[AutoRetry] Scheduling retry 1/3 in 5s`
   - Check UI: Timeout notice shows "Connection interrupted. Reconnecting automatically..."
   - After 5 seconds: Connection should auto-retry
   - If retry 1 fails (still offline), check for: `[AutoRetry] Scheduling retry 2/3 in 15s`
   - If retry 2 fails, check for: `[AutoRetry] Scheduling retry 3/3 in 45s`

4. **Re-enable network**:
   - Set throttling back to "No throttling"
   - Next auto-retry should succeed
   - Verify: responsePhase transitions to 'streaming' or 'settled'

5. **After 3 failed retries**:
   - Keep network offline through all 3 retries
   - Verify timeout notice changes to: "Connection interrupted. The agent may still be working."
   - Verify "Retry" button still visible for manual retry

### Expected Results
✅ Auto-retry attempts: 3 total with delays of 5s, 15s, 45s
✅ Console shows `[AutoRetry]` logs for each attempt
✅ UI message changes after max retries
✅ Manual "Retry" button always available
✅ Auto-retry stops after 3 attempts (no infinite loop)

### Console Logs to Check
```
[AutoRetry] Scheduling retry 1/3 in 5s
SSE connection closed. Reconnecting in Xs... (attempt 1/5)
[ResponsePhase] timed_out → connecting
[AutoRetry] Scheduling retry 2/3 in 15s
...
```

---

## Test 2: Status Reconciliation - Task Completes During Timeout

### Setup
Same as Test 1

### Steps
1. **Start a long-running task**:
   - Type: "Search the web for the latest news about AI and summarize it"
   - Click Send
   - Wait for task to start (you'll see browser tool or search tool)

2. **Simulate network interruption**:
   - Open DevTools → Network tab
   - Select "Offline" from throttling
   - Wait for SSE timeout

3. **Wait for task to complete in background**:
   - Check backend logs: `docker logs pythinker-backend-1 --tail 50 -f`
   - Look for "Chat completed" or DoneEvent in logs
   - Keep network offline so frontend doesn't receive completion

4. **Re-enable network and retry**:
   - Set throttling back to "No throttling"
   - Click "Retry" button (or wait for auto-retry)

5. **Verify status reconciliation**:
   - Check Console for: "Status reconciliation: if session already completed/failed, skip SSE and settle"
   - Verify: responsePhase transitions directly to 'completing' → 'settled'
   - Verify: NO "connecting" flash (instant completion)
   - Verify: Suggestions appear immediately
   - Verify: Screenshots loaded (if any)

### Expected Results
✅ Status check happens BEFORE SSE reconnect
✅ Completed session detected instantly
✅ NO SSE reconnection attempted (status reconciliation short-circuits)
✅ Direct transition to 'completing' → 'settled'
✅ Suggestions appear without delay
✅ Console shows status reconciliation log

### Console Logs to Check
```
[RESTORE] Session: <id> Status: completed LastEventId: <event-id>
[ResponsePhase] timed_out → connecting
[ResponsePhase] connecting → completing
[ResponsePhase] completing → settled
```

---

## Test 3: Manual Retry During Auto-Retry Countdown

### Setup
Same as Test 1

### Steps
1. Start a task and trigger timeout (go offline)
2. Wait for auto-retry countdown to start (5s delay for first retry)
3. **Before auto-retry fires**: Click "Retry" button manually
4. Verify:
   - Auto-retry timer is cancelled
   - Manual retry starts immediately
   - No duplicate retry attempts

### Expected Results
✅ Manual retry cancels pending auto-retry timer
✅ Only one retry attempt happens (not two)
✅ Console shows timer cleared: line 2795-2797 in handleRetryConnection

---

## Test 4: State Machine Transition Guards

### Setup
Same as Test 1

### Steps
1. Open Console
2. Manually call invalid transitions:
   ```javascript
   // Get a reference to the ChatPage component (run in console)
   // This will fail with a warning - that's expected!
   ```

3. Trigger normal flow and watch Console:
   - Send message → look for `[ResponsePhase] idle → connecting`
   - Wait for response → `[ResponsePhase] connecting → streaming`
   - Wait for completion → `[ResponsePhase] streaming → completing → settled`

4. Try to manually trigger invalid transition (via browser console):
   - While in 'streaming' state, try to go to 'idle'
   - Should see: `[ResponsePhase] BLOCKED: streaming → idle (allowed: completing, settled, timed_out, error, stopped)`

### Expected Results
✅ Valid transitions allowed
✅ Invalid transitions blocked with console warning
✅ No JavaScript errors during normal flow

---

## Test 5: Error Classification and Recovery Hints

### Setup
1. Configure backend to trigger specific errors (optional)
2. Or use network throttling to trigger SSE errors

### Steps
1. **Trigger max retry error**:
   - Go offline
   - Wait for 3 auto-retries to fail
   - Then wait for SSE client's 5 retry attempts to exhaust
   - Verify error notice shows: "Max reconnection attempts reached" with hint: "Refresh the page"

2. **Trigger rate limit error** (if backend supports):
   - Send many rapid requests
   - Look for error type: 'rate_limit'
   - Verify: recoverable=false (no Retry button)
   - Verify hint: "Wait a minute"

3. **Trigger backend error event**:
   - Send a request that causes backend error
   - Check error notice displays:
     - Error message from backend
     - Error type (if provided)
     - Recovery hint (if provided)
     - Retry button (if recoverable=true)

### Expected Results
✅ Different error types shown differently
✅ Recovery hints displayed when available
✅ Retry button only shown when recoverable=true
✅ Error notice styled correctly (red border/background)

---

## Test 6: Preserve Session on Navigation

### Setup
Same as Test 1

### Steps
1. **Start a long task in Session A**:
   - Create new chat
   - Send: "Write a detailed essay about quantum computing"
   - Wait for task to start running

2. **Navigate to different session**:
   - Click "New Chat" in sidebar
   - This creates Session B
   - Verify Session A is still in sidebar

3. **Check Session A continues**:
   - In terminal: `docker logs pythinker-backend-1 --tail 100 | grep "Session A ID"`
   - Verify: Task still running (no "stopping session" log)
   - Verify: Events still being generated

4. **Return to Session A**:
   - Click Session A in sidebar
   - Verify: Events resume from where you left off
   - Verify: lastEventId used (check Console logs)
   - Verify: No duplicate events

### Expected Results
✅ RUNNING session continues when navigating away
✅ Backend task keeps executing
✅ Returning to session resumes correctly
✅ Event deduplication works (no duplicate messages)
✅ lastEventId preserved in sessionStorage

### Backend Logs to Check
```bash
docker logs pythinker-backend-1 --tail 100 -f | grep -E "(Session|stopping|task)"
```
Should NOT see: "stopping session" when navigating between RUNNING sessions

---

## Test 7: Auto-Retry Counter Reset

### Setup
Same as Test 1

### Steps
1. Trigger timeout and let auto-retry run (1 or 2 attempts)
2. Before max retries, re-enable network
3. Let connection succeed (responsePhase → 'streaming')
4. Trigger timeout again
5. Verify: Auto-retry count resets (starts from 1/3 again, not continuing from previous)

### Expected Results
✅ autoRetryCount resets to 0 when entering 'streaming' (line 597-599)
✅ New timeout starts fresh with 5s delay (not 15s or 45s)

---

## Test 8: Page Refresh During RUNNING Session

### Setup
Same as Test 1

### Steps
1. Start a long task
2. While task is running: Press F5 (page refresh)
3. Verify:
   - Page reloads
   - Events replay quickly (realTime=false)
   - SSE reconnects automatically
   - Task continues (no prompt resubmission)
   - lastEventId used for resumption

### Expected Results
✅ Session restores correctly
✅ No duplicate message sent
✅ Events resume from last received
✅ Backend duplicate detection works (5-minute window)

### Console Logs to Check
```
[RESTORE] Loaded lastEventId from sessionStorage: <event-id>
[RESTORE] Session: <id> Status: running LastEventId: <event-id>
[RESTORE] No stop flag, auto-resuming session
```

---

## Monitoring Commands

### Real-time Backend Logs
```bash
docker logs pythinker-backend-1 -f | grep -E "(timeout|reconnect|heartbeat|Session)"
```

### Check Prometheus Metrics (if available)
```bash
curl http://localhost:9090/api/v1/query?query=pythinker_sse_timeouts_total
```

### Check Session Status via API
```bash
# Get session ID from browser Console: sessionId.value
curl http://localhost:8000/sessions/<SESSION_ID>/status \
  -H "Authorization: Bearer <TOKEN>"
```

---

## Debugging Tips

### Enable Verbose Logging
Add to browser Console:
```javascript
localStorage.setItem('debug', 'pythinker:*')
```

### Check State in Console
```javascript
// Get current response phase
responsePhase.value

// Get auto-retry count
autoRetryCount.value

// Get last error
lastError.value

// Get session status
sessionStatus.value
```

### Force State Transitions (Dev Only)
```javascript
// Don't do this in production!
transitionTo('timed_out')
transitionTo('error')
```

---

## Expected Test Results Summary

| Test | Feature | Expected Outcome |
|------|---------|------------------|
| 1 | Auto-retry progressive backoff | 3 retries at 5s, 15s, 45s intervals |
| 2 | Status reconciliation | Instant completion without SSE reconnect |
| 3 | Manual retry cancels auto-retry | Only one retry attempt |
| 4 | State machine guards | Invalid transitions blocked |
| 5 | Error classification | Different errors show different hints |
| 6 | Session persistence | RUNNING sessions continue on navigation |
| 7 | Retry counter reset | Counter resets after successful streaming |
| 8 | Page refresh | Session resumes without resubmission |

---

## Troubleshooting

### Auto-retry not triggering
- Check: `autoRetryCount.value` in Console (should be < 3)
- Check: responsePhase is 'timed_out'
- Check: No JavaScript errors in Console

### Status reconciliation not working
- Check: Network is back online when retry happens
- Check: Backend session actually completed (check logs)
- Check: getSessionStatus API call succeeds

### Invalid transition warnings
- These are intentional guards - not errors
- Only concern if blocking valid user flows
- Check Console for full transition path

---

## Success Criteria

✅ All 8 tests pass
✅ No JavaScript errors in Console
✅ No `[ResponsePhase] BLOCKED` warnings during normal usage
✅ Backend logs show no unexpected session stops
✅ ESLint and TypeScript checks pass
✅ User experience feels smooth and resilient
