# Monitoring Issues Found - Session Analysis

**Monitoring Started**: 2026-02-11 17:48 UTC
**Session Monitored**: Multiple sessions (3fe0e4aa90dc410c, 711b8cf8a3454148, 85f3e189cb1f4888)

---

## 🔴 CRITICAL ISSUES

### 1. **Sandbox Unreachable Failures**
**Severity**: CRITICAL
**Frequency**: Multiple occurrences
**Impact**: Session initialization failures

**Evidence**:
```
[error] Sandbox unreachable after 7 attempts, giving up (session 3446abe6760742ad)
[error] Sandbox unreachable after 6 attempts, giving up (session 85f3e189cb1f4888)
[warning] Sandbox unreachable (attempt 3/30, 4/30, 5/30, 6/30, 7/30)
[warning] Failed to pre-warm sandbox for session 3446abe6760742ad: Sandbox unreachable after 7 connection attempts
[warning] Failed to pre-warm sandbox for session 85f3e189cb1f4888: Sandbox unreachable after 6 connection attempts
```

**Root Cause Analysis Needed**:
- Why are sandboxes becoming unreachable during initialization?
- Is this a Docker networking issue?
- Are sandbox containers starting correctly?
- Is the health check too aggressive (7-attempt limit)?

**Monitoring Queries**:
```promql
# Check sandbox creation failures
pythinker_sandbox_creation_failures_total

# Check sandbox health
rate(pythinker_sandbox_unreachable_total[5m])
```

---

### 2. **Session Not Found Errors (404s)**
**Severity**: HIGH
**Frequency**: Multiple per session
**Impact**: Frontend errors, UX degradation

**Evidence**:
```
[error] Session 85f3e189cb1f4888 not found for user anonymous
[warning] GET /api/v1/sessions/85f3e189cb1f4888 - 404 (3.15ms)
[warning] POST /api/v1/sessions/85f3e189cb1f4888/stop - 404 (1.70ms)
```

**Pattern**:
- Frontend trying to access stale session IDs
- Sessions being stopped before initialization completes
- Race condition between session creation and access?

**Investigation Needed**:
- Check frontend session state management
- Verify session ID persistence in localStorage
- Review session lifecycle (INITIALIZING → ACTIVE → STOPPED)

---

### 3. **Stale Session Auto-Stop**
**Severity**: MEDIUM
**Frequency**: Occasional
**Impact**: User sessions interrupted unexpectedly

**Evidence**:
```
[info] Auto-stopping stale session 3fe0e4aa90dc410c (status=SessionStatus.INITIALIZING) for user anonymous
[info] Destroyed owned sandbox sandbox-25fda99b for session 3fe0e4aa90dc410c
[info] Cleaned up 1 stale session(s) for user anonymous
```

**Analysis**:
- Session 3fe0e4aa90dc410c created at 17:48:09, auto-stopped at 17:48:11 (2 seconds)
- Why is a session considered "stale" after only 2 seconds?
- Is the stale detection threshold too aggressive?
- Was this session still warming up?

**Code Location**: `backend/app/application/services/agent_service.py`

---

## 🟡 WARNINGS

### 4. **Sandbox Service Startup Delays**
**Severity**: MEDIUM
**Pattern**: Services taking multiple attempts to start

**Evidence**:
```
[info] Waiting for services... Non-running: app(STARTING), chrome(STARTING), framework(STARTING), openbox(STARTING), socat(STARTING), websockify(STARTING), x11vnc(STARTING), xvfb(STARTING) (attempt 2/30)
[info] Waiting for services... Non-running: chrome(STARTING), xvfb(STARTING) (attempt 3/30, 4/30, 5/30, 6/30)
[info] Waiting for services... Non-running: chrome(STARTING) (attempt 5/30)
```

**Observations**:
- Services eventually start (chrome, xvfb last to complete)
- Multiple polling attempts needed (up to 6+ attempts)
- This contributes to overall session initialization delay

**Performance Impact**:
- Session warm-up time: ~3 seconds
- User waiting time increased

---

### 5. **Chat Lock Waiting**
**Severity**: LOW
**Impact**: Chat delay

**Evidence**:
```
[info] Waiting up to 10.0s for sandbox warm-up lock before chat (session 3fe0e4aa90dc410c)
```

**Analysis**:
- System correctly waiting for sandbox warm-up before processing chat
- This is expected behavior, but indicates sandbox wasn't ready
- Contributes to perceived latency

---

## 🧪 TEST INPUTS DETECTED

### 6. **XSS and Special Character Testing**
**Evidence**:
```
[info] Starting chat with session 3fe0e4aa90dc410c: Hello! <script>alert('xss')</script>
	 émojis ${...
```

**Good News**:
- System logged the input correctly
- This appears to be intentional testing
- No evidence of XSS execution in logs

**Recommendation**:
- Verify XSS sanitization in frontend
- Confirm emoji support works correctly
- Check if special characters are handled properly

---

## 📊 METRICS SUMMARY

### Current State
- **Active Sessions**: TBD (Prometheus query needed)
- **Stuck Detections**: TBD
- **Tool Errors**: TBD
- **Session Failures**: At least 2 sandbox failures observed

### Request Timings
- Session creation: 3063.51ms (session 3fe0e4aa90dc410c)
- Session list GET: 73-144ms
- Metrics endpoint: ~1.5ms

---

## 🔍 RECOMMENDED INVESTIGATIONS

### Immediate (Priority 1)
1. **Debug sandbox unreachability**:
   - Check Docker container logs: `docker logs <sandbox-container-id>`
   - Verify network connectivity: `docker network inspect pythinker-network`
   - Review sandbox health check logic in `docker_sandbox.py`

2. **Fix session not found errors**:
   - Review frontend session state management (`useSession.ts`)
   - Check localStorage session ID handling
   - Verify session cleanup logic

3. **Review stale session detection**:
   - Check stale timeout threshold in `agent_service.py`
   - Verify session status transitions
   - Consider increasing grace period for INITIALIZING sessions

### Medium Priority
4. **Optimize sandbox startup**:
   - Profile service startup times
   - Consider parallel service initialization
   - Review Chrome startup flags

5. **Add monitoring alerts**:
   - Alert on sandbox unreachable rate > 10%
   - Alert on session 404 errors
   - Alert on stale session auto-stops

---

## 📈 GRAFANA DASHBOARD QUERIES

Add these to track issues:

```logql
# Sandbox failures
{container_name="pythinker-backend-1"} |= "Sandbox unreachable after"

# Session 404s
{container_name="pythinker-backend-1"} |= "Session" |= "not found"

# Stale sessions
{container_name="pythinker-backend-1"} |= "Auto-stopping stale session"

# Service startup delays
{container_name="pythinker-backend-1"} |= "Waiting for services"
```

---

## 🎯 ACTION ITEMS

- [ ] Investigate sandbox unreachability root cause
- [ ] Fix frontend session ID handling
- [ ] Review and adjust stale session timeout
- [ ] Add Prometheus alerts for critical failures
- [ ] Create Grafana dashboard for session health
- [ ] Document sandbox initialization sequence
- [ ] Add retry logic for sandbox connection attempts?
- [ ] Consider exponential backoff for service health checks

---

**Next Steps**:
1. Start a fresh session with known good input
2. Monitor from creation to first interaction
3. Capture full trace with session_id filtering
4. Compare with failed sessions
