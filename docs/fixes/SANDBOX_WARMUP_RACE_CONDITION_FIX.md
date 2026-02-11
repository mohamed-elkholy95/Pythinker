# Sandbox Warmup Race Condition Fix

**Date**: 2026-02-11
**Phase**: 6 - Operations Hardening
**Issue**: Sandbox containers failing health checks during warmup, causing ~30-40% false-positive "unreachable" errors
**Severity**: High

---

## Problem Analysis

### Symptoms
- `ERROR: Sandbox unreachable after 6 attempts, giving up`
- `WARNING: HTTP request failed for sandbox-XXX: GET .../supervisor/status - All connection attempts failed`
- Sessions failing to initialize despite sandbox containers being healthy
- ~30-40% failure rate during sandbox warm-up

### Root Cause

The backend was checking sandbox health **too aggressively** during container initialization:

1. **No Grace Period**: Health checks started immediately (t=0s) when container was created
2. **Fixed Retry Interval**: Used constant 2-second delays between retries (no exponential backoff)
3. **Impatient Threshold**: Gave up after only 6 connection failures (~12 seconds)
4. **Race Condition**: Sandboxes need 5-6 seconds to fully initialize all services

**Timeline of Failure**:
```
t=0s:  Container created, supervisor starting
t=0s:  Backend checks http://172.18.0.11:8080/status → Connection refused (too early!)
t=2s:  Backend retry → Connection refused (services still starting)
t=4s:  Backend retry → Connection refused (Chrome still initializing)
t=6s:  Backend retry → Connection might succeed, but...
t=8s:  Backend retry #5 → Still initializing
t=10s: Backend retry #6 → Failed, gives up
Result: "Sandbox unreachable after 6 attempts" (sandbox was actually fine!)
```

**Actual Sandbox Startup**:
```
t=0s:   supervisord starts
t=1s:   app, framework enter RUNNING
t=2s:   openbox, x11vnc, websockify, socat enter RUNNING
t=3s:   xvfb enters RUNNING
t=5-6s: chrome enters RUNNING (fully ready)
```

The backend was racing against the normal startup sequence!

---

## Solution

### 1. Warmup Grace Period (3 seconds)
Wait before the first health check to let services initialize:
```python
# Wait 3 seconds before first health check
await asyncio.sleep(warmup_grace_period)
```

**Result**: Backend checks at t=3s instead of t=0s

### 2. Exponential Backoff
Use increasing delays between retries:
```python
retry_delay = 1.0  # Start with 1 second
retry_delay = min(retry_delay * 1.5, 3.0)  # Increase by 1.5x, cap at 3s
```

**Retry Pattern**:
- Attempt 1: wait 1.0s
- Attempt 2: wait 1.5s
- Attempt 3: wait 2.25s
- Attempt 4+: wait 3.0s (capped)

### 3. Increased Failure Tolerance
More patient during warmup window:
```python
connection_failure_threshold = 12  # Up from 6
in_warmup_window = elapsed < 10.0  # First 10 seconds are warmup
```

### 4. Better Logging
Added elapsed time tracking:
```python
logger.info(
    f"Sandbox fully ready: {len(services)} services running, "
    f"browser healthy (warmup took {elapsed:.1f}s)"
)
```

---

## Configuration Options

New environment variables (added to `.env.example`):

```bash
# Sandbox warmup optimization (Phase 6)
SANDBOX_WARMUP_GRACE_PERIOD=3.0              # Wait before first health check
SANDBOX_WARMUP_INITIAL_RETRY_DELAY=1.0       # Initial delay between retries
SANDBOX_WARMUP_MAX_RETRY_DELAY=3.0           # Maximum delay between retries
SANDBOX_WARMUP_BACKOFF_MULTIPLIER=1.5        # Exponential backoff multiplier
SANDBOX_WARMUP_CONNECTION_FAILURE_THRESHOLD=12  # Max connection failures
```

**Defaults are production-ready** - no configuration changes required.

---

## Files Modified

1. **`backend/app/infrastructure/external/sandbox/docker_sandbox.py`**
   - `ensure_sandbox()` method refactored with warmup grace period
   - Added exponential backoff retry strategy
   - Increased connection failure tolerance during warmup
   - Enhanced logging with elapsed time tracking

2. **`backend/app/core/config.py`**
   - Added 5 new configuration parameters for warmup behavior
   - Default values optimized for typical sandbox startup time

3. **`.env.example`**
   - Documented new warmup configuration options
   - Added inline comments explaining each parameter

4. **`docs/fixes/SANDBOX_WARMUP_RACE_CONDITION_FIX.md`** (this file)
   - Comprehensive documentation of issue and fix

---

## Expected Results

### Before Fix
```
INFO: Sandbox unreachable (attempt 1/30)
INFO: Sandbox unreachable (attempt 2/30)
INFO: Sandbox unreachable (attempt 3/30)
INFO: Sandbox unreachable (attempt 4/30)
INFO: Sandbox unreachable (attempt 5/30)
ERROR: Sandbox unreachable after 6 attempts, giving up
```
**Failure Rate**: ~30-40%

### After Fix
```
DEBUG: Waiting 3.0s warmup grace period before first health check...
INFO: Waiting for services... Non-running: chrome(STARTING) (attempt 1/30, 3.5s elapsed)
INFO: All supervisor services running, verifying browser health...
INFO: Sandbox fully ready: 11 services running, browser healthy (warmup took 6.2s)
```
**Expected Failure Rate**: <5% (only genuine failures)

---

## Testing

### Manual Test
```bash
# Restart backend to apply changes
docker-compose restart backend

# Create new session and monitor logs
docker logs pythinker-backend-1 --tail 100 -f

# Look for new log format:
# "Waiting 3.0s warmup grace period..."
# "Sandbox fully ready... (warmup took X.Xs)"
```

### Metrics to Monitor
- `pythinker_sandbox_warm_up_failures_total` - Should decrease significantly
- Average sandbox warmup time - Should remain 5-7 seconds
- Session creation success rate - Should increase to >95%

### Expected Behavior
1. **Grace period logged**: "Waiting 3.0s warmup grace period..."
2. **Services check after warmup**: First check happens at t≥3s
3. **Exponential backoff**: Increasing delays if services not ready
4. **Success within 10s**: Most sandboxes ready in 6-8 seconds total
5. **Detailed logging**: Elapsed time tracked for debugging

---

## Rollback Plan

If issues occur, revert by setting:
```bash
SANDBOX_WARMUP_GRACE_PERIOD=0.0  # Disable grace period
SANDBOX_WARMUP_CONNECTION_FAILURE_THRESHOLD=6  # Restore old threshold
```

Or revert the commits:
```bash
git revert HEAD  # Revert this fix
docker-compose restart backend
```

---

## Related Issues

- **Initial Diagnosis**: `docs/fixes/AGENT_NOT_WORKING_DIAGNOSIS.md`
- **Monitoring Stack**: `docs/monitoring/MONITORING_STACK_GUIDE.md`
- **HTTP Client Pooling**: `docs/architecture/HTTP_CLIENT_POOLING.md`

---

## Success Criteria

- [ ] Sandbox warmup success rate >95%
- [ ] No "unreachable after 6 attempts" errors for healthy containers
- [ ] Average warmup time remains 5-7 seconds (no performance regression)
- [ ] Logs show grace period and elapsed time
- [ ] All existing tests pass

---

## Author

Claude Sonnet 4.5 (via Mohamed Elkholy)
**Issue Identified**: 2026-02-11 via log analysis
**Fix Implemented**: 2026-02-11
**Status**: Ready for Testing
