# Enhancement Plan: VNC/Browser Pre-Loading for Reduced Loading Time

## Implementation Status: COMPLETE ✓

All phases have been implemented:
- **Phase 0**: Sandbox pool enabled by default ✓
- **Phase 1**: Browser pre-warming during sandbox init ✓
- **Phase 2**: Fast path re-enabled for DIRECT_BROWSE ✓
- **Phase 3**: Parallel health checks ✓
- **Phase 4**: Frontend VNC pre-connection ✓

## Executive Summary

This document outlines a multi-phase plan to dramatically reduce VNC/browser loading time when users start a new task. Currently, cold start can take 20-32 seconds. The target is sub-3 second response time for browser-ready sessions.

## Current State Analysis

### Key Bottlenecks Identified

| Component | Current Behavior | Impact |
|-----------|-----------------|--------|
| **Sandbox Pool** | DISABLED (`sandbox_pool_enabled=False`) | 20-32s cold start per session |
| **Browser Init** | Lazy (first request) | +5-10s on first browser action |
| **Fast Path** | Disabled for DIRECT_BROWSE | Falls back to full workflow |
| **VNC Display** | Waits for browser action | User sees loading spinner |

### Timing Breakdown (Cold Start)

```
Session Creation    → 0s
├─ Session DB write → ~50ms
├─ Background sandbox warm-up starts
│   ├─ Docker container pull/start → 15-25s (MAIN BOTTLENECK)
│   ├─ Wait for services → 2-5s
│   └─ Sandbox health check → 1-2s
└─ Session returned to user → ~100ms

First Chat Message  → User waits...
├─ Sandbox may still be initializing
├─ Browser connection → 3-5s (if not pre-warmed)
└─ Page navigation → 2-3s
```

### With Sandbox Pool Enabled

```
Session Creation    → 0s
├─ Acquire pre-warmed sandbox from pool → ~100ms
├─ Session DB write → ~50ms
└─ Session returned with ready sandbox → ~200ms

First Chat Message  → Instant response
├─ Sandbox already healthy
├─ Browser already initialized → 0s
└─ Page navigation → 2-3s
```

---

## Phase 0: Enable Sandbox Pool (Immediate Win)

**Priority:** CRITICAL
**Estimated Improvement:** 20-32s → 2-5s cold start

### Current Configuration
```python
# backend/app/core/config.py:100
sandbox_pool_enabled: bool = False  # DISABLED
sandbox_pool_min_size: int = 2
sandbox_pool_max_size: int = 5
sandbox_pool_warmup_interval: int = 30
```

### Changes Required

1. **Enable Pool by Default (Development)**
   ```python
   # config.py
   sandbox_pool_enabled: bool = True  # Enable by default
   sandbox_pool_min_size: int = 2     # Maintain 2 ready sandboxes
   sandbox_pool_max_size: int = 4     # Cap at 4 to limit resource usage
   ```

2. **Environment Variable Override**
   ```bash
   # .env for production (resource-constrained)
   SANDBOX_POOL_ENABLED=false

   # .env for development/staging
   SANDBOX_POOL_ENABLED=true
   SANDBOX_POOL_MIN_SIZE=2
   ```

3. **Session Creation Integration**
   - Modify `AgentService.create_session()` to prefer pool acquisition
   - Fall back to on-demand creation if pool exhausted

### Files to Modify
- `backend/app/core/config.py` - Change default
- `backend/app/application/services/agent_service.py` - Use pool in session creation
- `backend/.env.example` - Document the setting

---

## Phase 1: Browser Pre-Warming During Sandbox Init

**Priority:** HIGH
**Estimated Improvement:** +3-5s saved on first browser action

### Problem
Currently, `sandbox.ensure_sandbox()` only verifies:
1. API responsiveness (`/health` endpoint)
2. Browser process running (CDP check at port 9222)

But it does NOT:
- Initialize a browser context
- Create a ready page
- Verify browser can actually navigate

### Solution

Add browser pre-warming to `_warm_sandbox_for_session()`:

```python
# agent_service.py
async def _warm_sandbox_for_session(self, session_id: str) -> None:
    try:
        await self._session_repository.update_status(session_id, SessionStatus.INITIALIZING)
        sandbox = await self._sandbox_cls.create()

        session = await self._session_repository.find_by_id(session_id)
        if session and not session.sandbox_id:
            session.sandbox_id = sandbox.id
            await self._session_repository.save(session)

            # Existing: ensure sandbox services are ready
            if hasattr(sandbox, 'ensure_sandbox'):
                await sandbox.ensure_sandbox()

            # NEW: Pre-warm browser context and page
            await self._prewarm_browser(sandbox, session_id)

            logger.info(f"Sandbox {sandbox.id} fully ready with browser for session {session_id}")

        await self._session_repository.update_status(session_id, SessionStatus.PENDING)
    except Exception as e:
        logger.warning(f"Failed to pre-warm sandbox: {e}")
        # Reset to PENDING - first chat will create sandbox

async def _prewarm_browser(self, sandbox, session_id: str) -> None:
    """Pre-warm browser so it's ready for immediate use."""
    try:
        from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

        # Get CDP URL from sandbox
        cdp_url = f"ws://{sandbox.ip_address}:9222"

        # Create browser instance and connect
        browser = PlaywrightBrowser(cdp_url=cdp_url)
        await browser.connect()

        # Navigate to blank page to fully initialize
        await browser.navigate("about:blank", timeout=5000)

        # Store browser instance for later use
        # (This requires adding browser tracking to session or sandbox)
        logger.info(f"Browser pre-warmed for session {session_id}")

    except Exception as e:
        logger.warning(f"Browser pre-warm failed (non-fatal): {e}")
```

### Files to Modify
- `backend/app/application/services/agent_service.py` - Add `_prewarm_browser()`
- `backend/app/core/sandbox_pool.py` - Add browser pre-warm to `_create_and_verify_sandbox()`

---

## Phase 2: Re-Enable Fast Path for Browser Operations

**Priority:** HIGH
**Estimated Improvement:** Instant response for "open X" commands

### Problem
Fast path for `DIRECT_BROWSE` was disabled because browser wasn't ready during `INITIALIZING` status, causing "Target page, context or browser has been closed" errors.

### Solution

With Phase 0 and Phase 1 complete, we can safely re-enable fast path:

```python
# plan_act.py - In _should_use_fast_path()
async def _should_use_fast_path(
    self, session: Session, message: str
) -> tuple[bool, QueryIntent | None, dict[str, Any]]:
    """Check if this query can use fast path."""

    # Fast path only for PENDING sessions (fully initialized)
    if session.status != SessionStatus.PENDING:
        return False, None, {}

    # Classify intent
    intent, params = self._fast_path_router.classify(message)

    # All fast path intents are now safe with pre-warmed browser
    if intent in (QueryIntent.DIRECT_BROWSE, QueryIntent.WEB_SEARCH, QueryIntent.KNOWLEDGE):
        # Verify browser is actually ready before committing to fast path
        if intent in (QueryIntent.DIRECT_BROWSE, QueryIntent.WEB_SEARCH):
            if not await self._verify_browser_ready(session):
                logger.info("Browser not ready, falling back to normal workflow")
                return False, None, {}

        return True, intent, params

    return False, None, {}

async def _verify_browser_ready(self, session: Session) -> bool:
    """Quick check if browser is ready for fast path."""
    if not session.sandbox_id:
        return False
    try:
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            return False
        # Quick health check - should be instant if pre-warmed
        return await sandbox.browser_health_check()
    except Exception:
        return False
```

### Files to Modify
- `backend/app/domain/services/flows/plan_act.py` - Re-enable DIRECT_BROWSE fast path
- `backend/app/domain/services/flows/fast_path.py` - Remove redundant browser checks

---

## Phase 3: Parallel Health Checks & Optimizations

**Priority:** MEDIUM
**Estimated Improvement:** 1-2s saved during initialization

### Current Sequential Flow
```
API health check → wait → Browser health check → wait → VNC health check → wait
```

### Optimized Parallel Flow
```python
async def health_check(self) -> bool:
    """Perform health checks in parallel."""
    api_task = asyncio.create_task(self._check_api_health())
    browser_task = asyncio.create_task(self._check_browser_health())
    vnc_task = asyncio.create_task(self._check_vnc_health())

    results = await asyncio.gather(api_task, browser_task, vnc_task, return_exceptions=True)

    self.health.api_responsive = results[0] is True
    self.health.browser_responsive = results[1] is True
    self.health.vnc_responsive = results[2] is True

    return self.health.is_healthy
```

### Additional Optimizations

1. **Reduce Health Check Timeout**
   ```python
   # Current: 5s per check
   # Proposed: 2s per check (parallel = 2s total instead of 15s)
   response = await self.api_client.get("/health", timeout=2.0)
   ```

2. **Skip VNC Check in Pool Pre-warm**
   - VNC is optional for health determination
   - Only check API + Browser for faster pool replenishment

3. **Lazy MCP Initialization** (already enabled)
   - `mcp_lazy_init: bool = True`

### Files to Modify
- `backend/app/core/sandbox_manager.py` - Parallel health checks
- `backend/app/core/sandbox_pool.py` - Optimized pre-warm

---

## Phase 4: Frontend VNC Pre-Connection

**Priority:** MEDIUM
**Estimated Improvement:** 500ms-1s perceived improvement

### Problem
Frontend only connects to VNC after receiving first `ToolEvent` with browser action.

### Solution
Pre-connect VNC WebSocket when session enters `PENDING` status:

```typescript
// frontend/src/composables/useSession.ts
watch(() => session.value?.status, async (newStatus) => {
  if (newStatus === 'PENDING' && session.value?.sandbox_id) {
    // Pre-connect VNC in background
    await vncStore.preConnect(session.value.id)
  }
})

// frontend/src/stores/vncStore.ts
async preConnect(sessionId: string) {
  if (this.isPreConnected) return

  try {
    // Establish WebSocket but don't render until needed
    await this.establishConnection(sessionId, { renderOnConnect: false })
    this.isPreConnected = true
  } catch (e) {
    console.warn('VNC pre-connect failed (non-fatal):', e)
  }
}
```

### Files to Modify
- `frontend/src/composables/useSession.ts`
- `frontend/src/stores/vncStore.ts` (or equivalent VNC handler)

---

## Phase 5: Intelligent Pool Scaling (Future)

**Priority:** LOW
**For future consideration**

### Concept
Dynamically adjust pool size based on usage patterns:

```python
class AdaptiveSandboxPool(SandboxPool):
    """Pool that scales based on demand."""

    async def _adaptive_maintenance(self):
        while not self._stopping:
            await asyncio.sleep(60)

            # Track acquisition rate over last 5 minutes
            acquisition_rate = self._get_acquisition_rate()

            if acquisition_rate > 0.8:  # Pool frequently exhausted
                self._min_size = min(self._min_size + 1, self._max_size)
                logger.info(f"Scaling up pool min_size to {self._min_size}")
            elif acquisition_rate < 0.2 and self._min_size > 1:
                self._min_size = max(self._min_size - 1, 1)
                logger.info(f"Scaling down pool min_size to {self._min_size}")
```

---

## Implementation Roadmap

### Week 1: Phase 0 (Critical)
- [ ] Enable sandbox pool by default
- [ ] Test pool behavior under load
- [ ] Add monitoring/metrics for pool utilization

### Week 2: Phase 1 + Phase 2
- [ ] Implement browser pre-warming
- [ ] Re-enable fast path for DIRECT_BROWSE
- [ ] Add browser readiness verification

### Week 3: Phase 3 + Phase 4
- [ ] Parallelize health checks
- [ ] Implement frontend VNC pre-connection
- [ ] End-to-end testing

### Future: Phase 5
- [ ] Adaptive pool scaling
- [ ] Usage analytics integration

---

## Configuration Reference

### Recommended Development Settings
```bash
# .env
SANDBOX_POOL_ENABLED=true
SANDBOX_POOL_MIN_SIZE=2
SANDBOX_POOL_MAX_SIZE=4
SANDBOX_POOL_WARMUP_INTERVAL=30
SANDBOX_EAGER_INIT=true
BROWSER_POOL_ENABLED=true
```

### Recommended Production Settings
```bash
# .env (resource-conscious)
SANDBOX_POOL_ENABLED=true
SANDBOX_POOL_MIN_SIZE=1
SANDBOX_POOL_MAX_SIZE=3
SANDBOX_POOL_WARMUP_INTERVAL=60
```

---

## Expected Results

| Metric | Before | After Phase 0 | After All Phases |
|--------|--------|---------------|------------------|
| Cold start time | 20-32s | 2-5s | 2-5s |
| First browser action | +5-10s | +3-5s | ~1s |
| Fast path "open X" | Disabled | Working | Sub-second |
| VNC visible | After action | After action | Pre-loaded |
| Total perceived time | 25-42s | 5-10s | 3-6s |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Memory usage from pool | Cap `max_size`, implement idle cleanup |
| Stale sandboxes in pool | Periodic health checks, max TTL |
| Browser context leaks | Proper cleanup on acquire/release |
| Pool exhaustion under load | On-demand fallback, async replenishment |

---

## Monitoring Recommendations

1. **Pool Metrics**
   - `sandbox_pool_size` (gauge)
   - `sandbox_pool_acquire_time` (histogram)
   - `sandbox_pool_exhausted_count` (counter)

2. **Browser Metrics**
   - `browser_prewarm_success` (counter)
   - `browser_prewarm_duration` (histogram)

3. **Fast Path Metrics**
   - `fast_path_used_count` by intent (counter)
   - `fast_path_fallback_count` (counter)
