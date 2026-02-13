# Browser Crash Detection and Recovery Hardening

## Problem Statement

Chrome crashes during complex operations take >120s to detect and recover, with no progress feedback to users. Connection pool can get exhausted with zombie connections (BROWSER_1004).

## Root Causes

1. **Slow Crash Detection** - No proactive health checks before operations; crashes detected only after 30s+ timeouts
2. **No Progress Feedback** - Users see no events during 120s+ recovery attempts
3. **No Circuit Breaker** - Repeated crashes can loop indefinitely
4. **Connection Pool Issues** - Pool can get exhausted with zombie connections

## Solution Overview

### Phase 1: Crash Detection Hardening (This PR)

1. **Pre-operation Health Checks** (<5s fast-path)
   - Quick health check before navigate/click/type operations
   - Fail-fast if browser is already crashed
   - Reduce detection time from 120s to <5s

2. **Circuit Breaker** (3 crashes in 5 min = fail-fast)
   - Track crash history with timestamps
   - Open circuit after 3 crashes in 5 minute window
   - Prevent infinite retry loops
   - Auto-close circuit after cooldown period

3. **Progress Events During Recovery**
   - Emit "Browser crashed, recovering..." events
   - Show retry attempt (1/3, 2/3, 3/3)
   - Keep SSE stream alive during recovery

4. **Connection Pool Cleanup**
   - Mark connections unhealthy on crash
   - Trigger immediate pool cleanup
   - Prevent BROWSER_1004 pool exhaustion

### Implementation Details

#### Circuit Breaker State Machine

```python
# Track crash history
self._crash_history: list[float] = []  # Timestamps of recent crashes
self._crash_window_seconds: float = 300.0  # 5 minute window
self._crash_threshold: int = 3  # Max crashes in window
self._circuit_open_until: float = 0.0  # Circuit open timestamp

# Check circuit state
def _check_circuit_breaker(self) -> bool:
    """Check if circuit breaker is open (too many crashes)."""
    now = time.time()

    # Circuit explicitly open?
    if now < self._circuit_open_until:
        return False  # Circuit open, reject operation

    # Clean old crashes outside window
    cutoff = now - self._crash_window_seconds
    self._crash_history = [ts for ts in self._crash_history if ts > cutoff]

    # Check threshold
    if len(self._crash_history) >= self._crash_threshold:
        # Open circuit for cooldown period
        self._circuit_open_until = now + 60.0  # 1 min cooldown
        logger.error(
            f"Circuit breaker OPEN: {len(self._crash_history)} crashes in "
            f"{self._crash_window_seconds}s. Cooldown: 60s"
        )
        return False

    return True  # Circuit closed, allow operation

# Record crash
def _record_crash(self) -> None:
    """Record a crash for circuit breaker tracking."""
    now = time.time()
    self._crash_history.append(now)
    logger.warning(
        f"Crash recorded: {len(self._crash_history)} crashes in last "
        f"{self._crash_window_seconds}s"
    )
```

#### Fast Pre-Operation Health Check

```python
async def _quick_health_check(self) -> bool:
    """Quick health check before operations (<5s).

    Returns:
        True if healthy, False if crashed/unhealthy
    """
    try:
        if not self.page or self.page.is_closed():
            return False

        # Fast evaluation with short timeout
        await asyncio.wait_for(
            self.page.evaluate("() => true"),
            timeout=3.0  # Fail fast
        )
        return True
    except asyncio.TimeoutError:
        logger.warning("Quick health check timed out (3s)")
        return False
    except Exception as e:
        if self._is_crash_error(e):
            logger.error(f"Browser crash detected in health check: {e}")
            self._connection_healthy = False
            self._record_crash()
        return False
```

#### Progress Events During Recovery

```python
# In initialize() retry loop
for attempt in range(max_retries):
    try:
        # Emit progress event
        if attempt > 0:
            logger.info(f"Browser recovery attempt {attempt + 1}/{max_retries}")
            # TODO: Emit ProgressEvent here when event emitter is available
            # await self._emit_progress(
            #     f"Browser crashed, recovering... (attempt {attempt + 1}/{max_retries})"
            # )

        # ... initialization logic ...

    except Exception as e:
        if attempt < max_retries - 1:
            backoff = min(retry_delay * 2, 4)
            logger.info(f"Retrying in {backoff}s...")
            # TODO: Emit ProgressEvent
            # await self._emit_progress(
            #     f"Retrying browser connection in {backoff}s..."
            # )
            await asyncio.sleep(backoff)
```

### Configuration

Add to `backend/app/core/config.py`:

```python
# Browser crash circuit breaker
browser_crash_circuit_breaker_enabled: bool = True
browser_crash_window_seconds: float = 300.0  # 5 min window
browser_crash_threshold: int = 3  # Max crashes before circuit opens
browser_crash_cooldown_seconds: float = 60.0  # Circuit open duration

# Browser health check
browser_quick_health_check_enabled: bool = True
browser_quick_health_check_timeout: float = 3.0  # Fast timeout
```

### Testing

```python
# Test circuit breaker
async def test_circuit_breaker_opens_after_threshold():
    browser = PlaywrightBrowser()

    # Simulate 3 crashes
    for _ in range(3):
        browser._record_crash()

    # Circuit should be open
    assert not browser._check_circuit_breaker()

# Test quick health check
async def test_quick_health_check_detects_crash():
    browser = PlaywrightBrowser()
    await browser.initialize()

    # Kill Chrome
    subprocess.run(["pkill", "-9", "chrome"])

    # Health check should detect crash
    is_healthy = await browser._quick_health_check()
    assert not is_healthy
    assert not browser._connection_healthy
```

## Metrics

Track via Prometheus:

```python
browser_crashes_total = Counter(
    "browser_crashes_total",
    "Total browser crashes detected",
    ["cdp_url"]
)

browser_circuit_breaker_opens_total = Counter(
    "browser_circuit_breaker_opens_total",
    "Circuit breaker openings",
    ["reason"]
)

browser_recovery_duration_seconds = Histogram(
    "browser_recovery_duration_seconds",
    "Time to recover from crash",
    buckets=[5, 10, 20, 30, 60, 120]
)
```

## Success Criteria

- [ ] Crash detection time <30s (down from 120s+)
- [ ] Progress events emitted during recovery
- [ ] Circuit breaker prevents infinite loops
- [ ] Connection pool cleanup on crash
- [ ] No BROWSER_1004 pool exhaustion errors

## Phase 2: Advanced Recovery (Future)

1. **Sandbox Health Monitoring** - Proactive Docker container health checks
2. **Automatic Sandbox Replacement** - Replace crashed containers automatically
3. **Session State Persistence** - Resume from last known good state
4. **User Notification** - Toast notifications for crash recovery status
