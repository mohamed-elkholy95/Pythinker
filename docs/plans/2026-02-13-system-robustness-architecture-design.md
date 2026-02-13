# System Robustness & Architecture Design

**Date:** 2026-02-13
**Approach:** Parallel Tracks (bug fixes + refactoring on separate branches)
**Context7 Validated:** FastAPI (96.8), Vue.js (84.8), Tenacity (95.5), Docker (88.5)

---

## Executive Summary

Comprehensive analysis of Pythinker's backend, frontend, sandbox, and Chrome browser subsystems reveals **6 critical**, **8 high**, and **6 medium** priority issues across 4 architectural domains. The system has strong foundations (DDD, retry framework, connection pooling, sandbox pool) but suffers from reliability gaps in SSE streaming, inconsistent error handling, God class/component sprawl, and missing test coverage.

**Parallel Tracks Strategy:**
- **Track A (Stability Branch):** Fix 6 critical runtime bugs - SSE heartbeat, error framework, retry coverage, session resilience
- **Track B (Architecture Branch):** Break apart God classes/components, extract reusable modules, add test infrastructure

---

## Part 1: Issue Registry (Exact Lines & Suggested Fixes)

### CRITICAL (P0) - Must Fix Immediately

---

#### ISSUE C1: SSE Stream Timeout During Browser Recovery

**Impact:** Users see "Chat stream timed out" while agent continues working invisibly. Duplicate requests created.

| File | Line(s) | Current Code |
|------|---------|--------------|
| `backend/app/application/services/agent_service.py` | 49 | `CHAT_EVENT_TIMEOUT_SECONDS = 120.0` |
| `backend/app/application/services/agent_service.py` | 689-701 | `except TimeoutError:` → yields ErrorEvent but doesn't cancel background tasks |
| `backend/app/interfaces/api/session_routes.py` | 385 | `heartbeat_interval_seconds = 15.0` |
| `backend/app/interfaces/api/session_routes.py` | 382 | `send_timeout = 60.0 if use_sse_v2 else None` |

**Root Cause:** During browser crash recovery (can take 60-180s), the domain service emits zero events. The SSE heartbeat at line 385 only fires when `asyncio.wait()` completes a heartbeat sleep task, but the event task itself blocks for 120s before timing out.

**Suggested Fix:**
1. **Emit progress events from browser retry loops** in `playwright_browser.py:1104-1268` (the `initialize()` method). Each retry iteration should yield a `ProgressEvent` like "Retrying browser connection (attempt 2/3)..."
2. **Add a dedicated heartbeat coroutine** in `session_routes.py:441` that runs independently of the event stream, sending SSE comments (`:heartbeat\n\n`) every 15s regardless of domain event flow
3. **Cancel background domain tasks** when SSE stream closes at `session_routes.py:510-520` - currently the stream just `break`s without cancelling the underlying `agent_domain_service.chat()` generator

**New Code Pattern (session_routes.py):**
```python
# Line ~441: Replace current heartbeat approach
async def heartbeat_sender():
    """Independent heartbeat that keeps SSE alive during long operations."""
    while True:
        await asyncio.sleep(15)
        yield ServerSentEvent(comment="heartbeat")

# Merge heartbeat_sender with event_stream using async_generator_merge
```

**Estimated Effort:** 2-3 days

---

#### ISSUE C2: Orphaned Background Tasks on SSE Disconnect

**Impact:** Agent continues consuming CPU/memory/LLM tokens after user disconnects. Redis task streams leak.

| File | Line(s) | Current Code |
|------|---------|--------------|
| `backend/app/application/services/agent_service.py` | 89 | `self._background_tasks: set[asyncio.Task] = set()` |
| `backend/app/application/services/agent_service.py` | 191-193 | `task = asyncio.create_task(...)` / `self._background_tasks.add(task)` |
| `backend/app/application/services/agent_service.py` | 724-726 | `finally: with contextlib.suppress(Exception): await stream_iter.aclose()` |

**Root Cause:** When SSE stream closes (timeout, user navigates away, network drop), the `finally` block at line 724 closes the stream iterator but does NOT cancel the underlying Redis task or domain service processing. The `_background_tasks` set tracks warmup tasks but not chat processing tasks.

**Suggested Fix:**
1. **Track the domain chat task** in `_background_tasks` and cancel it in the `finally` block
2. **Add session-level cancellation** that propagates from SSE close → domain service → tools → browser
3. **Add Redis stream cleanup** on session stop/delete - purge `task:input:{task_id}` and `task:output:{task_id}`

**New Code Pattern (agent_service.py:724):**
```python
finally:
    # Cancel the domain processing task
    if hasattr(stream_iter, '_task') and not stream_iter._task.done():
        stream_iter._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stream_iter._task

    with contextlib.suppress(Exception):
        await stream_iter.aclose()

    # Clean up Redis task streams for this session
    await self._cleanup_redis_task_streams(session_id)
```

**Estimated Effort:** 2 days

---

#### ISSUE C3: God Component ChatPage.vue (3,218 lines)

**Impact:** Unmaintainable, untestable, every change risks regressions across 20+ features.

| File | Line(s) | Responsibility |
|------|---------|----------------|
| `frontend/src/pages/ChatPage.vue` | 476-610 | ResponsePhase state machine (6 states, transition logic) |
| `frontend/src/pages/ChatPage.vue` | 2218-2363 | SSE event dispatch (20+ event types) |
| `frontend/src/pages/ChatPage.vue` | 2371-2497 | SSE connection management (onClose, retry, restore) |
| `frontend/src/pages/ChatPage.vue` | 1400-1780 | Message/tool/step event handlers |
| `frontend/src/pages/ChatPage.vue` | 2498-2547 | Session restore logic |
| `frontend/src/pages/ChatPage.vue` | 934, 1743, 2240, 2471, 2878 | Debug telemetry (MUST REMOVE) |

**Suggested Fix:** Extract into composables:
1. **`useResponsePhase.ts`** - State machine with typed transitions (lines 476-610)
2. **`useSSEConnection.ts`** - SSE lifecycle, heartbeat detection, reconnection (lines 2371-2547)
3. **`useEventDispatcher.ts`** - Event routing and handler registry (lines 2218-2363)
4. **`useSessionRestore.ts`** - Page refresh restoration (lines 2498-2547)
5. **Remove all debug fetch calls** at lines 934, 1743, 2240, 2471, 2878

**Estimated Effort:** 3-4 days

---

#### ISSUE C4: God Class agent_service.py (1,378 lines)

**Impact:** Single class handles session CRUD, chat orchestration, sandbox warmup, intent classification, direct responses, MCP connectors, event resumption.

| File | Line(s) | Responsibility |
|------|---------|----------------|
| `backend/app/application/services/agent_service.py` | 100-230 | Session creation + sandbox warmup |
| `backend/app/application/services/agent_service.py` | 234-260 | Stale session cleanup |
| `backend/app/application/services/agent_service.py` | 561-735 | Chat orchestration |
| `backend/app/application/services/agent_service.py` | 736-804 | Lightweight direct responses |
| `backend/app/application/services/agent_service.py` | 806-900 | Session CRUD operations |

**Suggested Fix:** Extract into focused services:
1. **`SessionLifecycleService`** - Create, delete, restore, cleanup stale (lines 100-260, 806-900)
2. **`ChatOrchestrationService`** - Chat stream, event resumption, timeout handling (lines 561-735)
3. **`DirectResponseService`** - Pattern matching for trivial prompts (lines 736-804)
4. **`SandboxWarmupService`** - Background warmup, lock management (lines 191-218)

**Estimated Effort:** 2-3 days

---

#### ISSUE C5: God Class playwright_browser.py (2,800+ lines)

**Impact:** Navigation, crash recovery, element extraction, memory monitoring, VNC positioning all in one class.

| File | Line(s) | Responsibility |
|------|---------|----------------|
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 93-104 | Crash signature detection |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 475-522 | Memory pressure monitoring |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 527-623 | VNC window positioning |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 1085-1270 | Browser initialization |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 1276-1360 | Resource cleanup |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 1602-1900 | Page content extraction |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 1897-2148 | Navigation with crash recovery |

**Suggested Fix:** Extract into focused modules:
1. **`browser_health.py`** - Memory monitoring, crash detection, health checks (lines 93-104, 475-522, 988-1000)
2. **`browser_vnc.py`** - Window positioning, VNC display management (lines 527-623)
3. **`browser_extraction.py`** - Element extraction, content parsing (lines 1602-1900)
4. **`browser_navigation.py`** - Navigate, navigate_fast, crash recovery (lines 1897-2148)
5. Keep **`playwright_browser.py`** as thin orchestrator composing the above modules

**Estimated Effort:** 3-4 days

---

#### ISSUE C6: Zero Frontend Tests

**Impact:** No regression safety net for the 3,218-line ChatPage or any composable.

| File | Evidence |
|------|----------|
| `frontend/src/` | Zero `.test.ts` or `.spec.ts` files found |
| `frontend/package.json` | Vitest configured (line 13-15) but no tests written |
| `frontend/package.json` | `@vue/test-utils` installed (line 72) but unused |

**Suggested Fix:**
1. Create `frontend/src/composables/__tests__/` directory
2. Priority test targets after composable extraction:
   - `useResponsePhase.test.ts` - Test all state transitions
   - `useSSEConnection.test.ts` - Test reconnection, timeout, restore
   - `useEventDispatcher.test.ts` - Test event routing
3. Add `useSessionRestore.test.ts` - Test page refresh scenarios
4. Target: 80%+ coverage on extracted composables

**Estimated Effort:** 3-4 days

---

### HIGH (P1) - Fix Within 2 Weeks

---

#### ISSUE H1: HTTPClientPool Not Enforced (14+ Violations)

**Impact:** Connection pool exhaustion, bypassed retry logic, inconsistent timeout handling.

| File | Line(s) | Violation |
|------|---------|-----------|
| `backend/app/core/sandbox_manager.py` | ~278 | `httpx.AsyncClient(base_url=..., timeout=2.0)` - direct creation |
| `backend/app/application/services/connector_service.py` | ~194 | `async with httpx.AsyncClient(timeout=10.0) as client:` |
| `backend/app/application/services/connector_service.py` | ~216 | `async with httpx.AsyncClient(timeout=10.0) as client:` |
| `backend/app/infrastructure/external/image_generation.py` | ~31 | `self._client = httpx.AsyncClient(base_url="https://api.fal.ai")` |
| `backend/app/infrastructure/external/llm/ollama_llm.py` | ~301 | `async with httpx.AsyncClient(timeout=120.0) as client:` |
| `backend/app/infrastructure/external/llm/ollama_llm.py` | ~440 | `async with httpx.AsyncClient(timeout=120.0) as client:` |

**Suggested Fix:**
1. Replace all direct `httpx.AsyncClient` with `HTTPClientPool.get_client("service-name")`
2. Add ruff custom rule or pre-commit hook to detect `httpx.AsyncClient(` pattern
3. Register named clients in pool: `sandbox-api`, `connector`, `image-gen`, `ollama`

**Estimated Effort:** 1 day

---

#### ISSUE H2: Retry Decorators Under-Utilized

**Impact:** Transient failures (network blips, DNS hiccups, container restarts) cause user-visible errors.

| File | Line(s) | Missing Retry |
|------|---------|---------------|
| `backend/app/core/sandbox_manager.py` | ~411 | Health check HTTP call - no retry, timeout=2.0 |
| `backend/app/application/services/connector_service.py` | ~194 | MCP config fetch - no retry |
| `backend/app/infrastructure/external/llm/ollama_llm.py` | ~301 | Ollama API call - no retry |
| `backend/app/infrastructure/external/image_generation.py` | ~31 | fal.ai API call - no retry |

**Existing Framework:** `backend/app/core/retry.py` provides `@http_retry`, `@sandbox_retry`, `@llm_retry` (lines 309-462).

**Suggested Fix:** Apply existing decorators:
```python
# sandbox_manager.py health check
@sandbox_retry  # 3 attempts, 2-30s exponential backoff
async def _check_sandbox_health(self, address: str) -> bool:

# connector_service.py
@http_retry  # 3 attempts, 1-15s exponential backoff
async def get_user_mcp_configs(self, user_id: str) -> list:

# ollama_llm.py
@llm_retry  # 3 attempts, 2-30s exponential backoff
async def _call_ollama(self, messages: list, ...) -> str:
```

**Estimated Effort:** 0.5 days

---

#### ISSUE H3: Debug Telemetry Left in Production Code

**Impact:** Privacy leak - sends page state to hardcoded localhost endpoint. Performance overhead.

| File | Line(s) | Debug Call |
|------|---------|------------|
| `frontend/src/pages/ChatPage.vue` | 934 | `fetch('http://127.0.0.1:7243/ingest/1df5c82e-...')` in cleanupStreamingState |
| `frontend/src/pages/ChatPage.vue` | 1743 | `fetch('http://127.0.0.1:7243/ingest/1df5c82e-...')` in handleProgressEvent |
| `frontend/src/pages/ChatPage.vue` | 2240 | `fetch('http://127.0.0.1:7243/ingest/1df5c82e-...')` in done event handler |
| `frontend/src/pages/ChatPage.vue` | 2471 | `fetch('http://127.0.0.1:7243/ingest/1df5c82e-...')` in SSE onClose |
| `frontend/src/pages/ChatPage.vue` | 2878 | `fetch('http://127.0.0.1:7243/ingest/1df5c82e-...')` in retryOnClose |

**Suggested Fix:** Delete all 5 debug fetch blocks. They are wrapped in `// #region agent log` / `// #endregion` comments, making them easy to find and remove.

**Estimated Effort:** 15 minutes

---

#### ISSUE H4: No Docker Health Checks for Sandbox

**Impact:** Docker can't auto-restart unhealthy sandbox containers. Orchestrators (Dokploy) can't detect failures.

| File | Line(s) | Evidence |
|------|---------|----------|
| `sandbox/Dockerfile` | entire file | No `HEALTHCHECK` instruction |
| `docker-compose-development.yml` | sandbox service | No `healthcheck:` configuration |

**Suggested Fix:**
```dockerfile
# sandbox/Dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
```

```yaml
# docker-compose-development.yml - sandbox service
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  start_period: 60s
  retries: 3
```

**Estimated Effort:** 0.5 days

---

#### ISSUE H5: SSE Reconnection Without Exponential Backoff

**Impact:** Rapid reconnection attempts on server issues create thundering herd.

| File | Line(s) | Current Logic |
|------|---------|---------------|
| `frontend/src/api/client.ts` | 336-339 | `retryCount = 0; maxRetries = 7; baseDelay = 1000; maxDelay = 45000` |
| `frontend/src/api/client.ts` | 396 | `setTimeout(() => createConnection().catch(console.error), 1000)` - FIXED 1s delay |

**Root Cause:** Line 396 uses a fixed 1000ms delay instead of exponential backoff with the configured `baseDelay`/`maxDelay`.

**Suggested Fix:**
```typescript
// Line 396: Replace fixed 1000ms with exponential backoff
const retryDelay = Math.min(baseDelay * Math.pow(2, retryCount), maxDelay);
const jitter = retryDelay * 0.25 * Math.random();
setTimeout(() => createConnection().catch(console.error), retryDelay + jitter);
retryCount++;
```

**Estimated Effort:** 0.5 days

---

#### ISSUE H6: No Unified Error Boundary in Frontend

**Impact:** Unhandled exceptions in event handlers crash the entire page.

| File | Line(s) | Evidence |
|------|---------|----------|
| `frontend/src/pages/ChatPage.vue` | 2218-2363 | 20+ event handlers with no error boundary |
| `frontend/src/` | N/A | No `onErrorCaptured` hook anywhere |

**Suggested Fix (per Context7 Vue.js best practices):**
```typescript
// In ChatPage.vue or parent layout
onErrorCaptured((err, instance, info) => {
  logger.error('Component error captured:', { err, info });
  // Show user-friendly error toast instead of crashing
  showErrorToast('Something went wrong. Please try again.');
  return false; // Stop propagation
});
```

**Estimated Effort:** 0.5 days

---

#### ISSUE H7: Session Cleanup Only Runs at Startup

**Impact:** Stale sessions accumulate during long-running server lifecycle.

| File | Line(s) | Current Code |
|------|---------|--------------|
| `backend/app/main.py` | 406-413 | `await maintenance_service.cleanup_stale_running_sessions(stale_threshold_minutes=5)` |

**Root Cause:** Cleanup only runs once at startup. No periodic background task.

**Suggested Fix:**
```python
# In lifespan() after startup:
async def periodic_session_cleanup():
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        try:
            result = await maintenance_service.cleanup_stale_running_sessions(
                stale_threshold_minutes=30,
                dry_run=False,
            )
            if result.cleaned > 0:
                logger.info("Periodic cleanup: %d stale sessions cleaned", result.cleaned)
        except Exception as e:
            logger.warning("Periodic session cleanup failed: %s", e)

cleanup_task = asyncio.create_task(periodic_session_cleanup())
```

**Estimated Effort:** 0.5 days

---

#### ISSUE H8: Swallowed Exceptions in Session Routes

**Impact:** Silent failures in cleanup operations mask underlying issues.

| File | Line(s) | Current Code |
|------|---------|--------------|
| `backend/app/interfaces/api/session_routes.py` | ~197-203 | `except Exception as e: logger.warning(...)` then returns success |

**Suggested Fix:** Track cleanup failures as non-blocking warnings in the response:
```python
cleanup_warnings: list[str] = []
try:
    deleted = await screenshot_query_service.delete_by_session(session_id)
except Exception as e:
    cleanup_warnings.append(f"Screenshot cleanup failed: {e}")
    logger.warning("Failed to cleanup screenshots for session %s: %s", session_id, e)

return APIResponse.success(data={"warnings": cleanup_warnings} if cleanup_warnings else None)
```

**Estimated Effort:** 0.5 days

---

### MEDIUM (P2) - Fix Within 4 Weeks

---

#### ISSUE M1: CDP Session Not Pooled

| File | Line(s) | Evidence |
|------|---------|----------|
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 488, 548, 1179 | `await self.context.new_cdp_session(self.page)` - created per operation |

**Fix:** Create a CDP session manager that reuses sessions within a browser lifecycle.

---

#### ISSUE M2: Browser Memory Restart Deferred

| File | Line(s) | Evidence |
|------|---------|----------|
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 2039-2056 | Memory check after navigation, restart deferred to next nav |

**Fix:** When memory is critical (>800MB), restart immediately instead of deferring.

---

#### ISSUE M3: Rate Limit Fallback Memory Leak

| File | Line(s) | Evidence |
|------|---------|----------|
| `backend/app/main.py` | 137 | `_fallback_storage: ClassVar[dict] = {}` - cleaned only every 100 requests |

**Fix:** Add time-based cleanup (e.g., every 60s) in addition to request-count-based cleanup.

---

#### ISSUE M4: No Structured Error Response for Generic Exception

| File | Line(s) | Evidence |
|------|---------|----------|
| `backend/app/interfaces/errors/exception_handlers.py` | 212 | Generic Exception handler exists but may not include correlation IDs |

**Fix:** Ensure generic handler includes `request_id`, sanitized error message, and records Prometheus metric.

---

#### ISSUE M5: Sandbox Dockerfile Missing HEALTHCHECK

| File | Line(s) | Evidence |
|------|---------|----------|
| `sandbox/Dockerfile` | N/A | No HEALTHCHECK instruction |

**Fix:** Add `HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:8080/health || exit 1`

---

#### ISSUE M6: Frontend Package Name Still Generic

| File | Line(s) | Evidence |
|------|---------|----------|
| `frontend/package.json` | 2 | `"name": "vite-vue-typescript-starter"` - should be `"pythinker-frontend"` |

**Fix:** Rename to `"pythinker-frontend"`.

---

## Part 2: Parallel Tracks Implementation Plan

### Track A: Stability Branch (`fix/system-robustness`)

**Goal:** Fix all critical runtime bugs. No architectural changes.

| Phase | Issues | Duration | Dependencies |
|-------|--------|----------|--------------|
| A1 | C1 (SSE heartbeat), C2 (orphaned tasks) | 3 days | None |
| A2 | H1 (HTTP pool enforcement), H2 (retry coverage) | 1.5 days | None |
| A3 | H3 (debug removal), H5 (SSE backoff), H6 (error boundary) | 1 day | None |
| A4 | H4 (Docker health), H7 (periodic cleanup), H8 (swallowed exceptions) | 1 day | None |
| A5 | M1-M6 (medium issues) | 2 days | A1-A4 |
| A6 | Integration testing, soak test | 2 days | A1-A5 |

**Total Track A:** ~10.5 days

### Track B: Architecture Branch (`refactor/architecture-cleanup`)

**Goal:** Break apart God classes/components. Add test infrastructure.

| Phase | Issues | Duration | Dependencies |
|-------|--------|----------|--------------|
| B1 | C3 (ChatPage.vue decomposition) | 3 days | None |
| B2 | C6 (Frontend test infrastructure) | 3 days | B1 |
| B3 | C4 (agent_service.py decomposition) | 2 days | None |
| B4 | C5 (playwright_browser.py decomposition) | 3 days | None |
| B5 | Backend tests for new services | 2 days | B3, B4 |
| B6 | Integration, merge conflict resolution | 2 days | B1-B5, Track A |

**Total Track B:** ~15 days (parallel with Track A)

### Merge Strategy

```
main ─────────────────────────────────────────────────────→
  │                                                        │
  ├─ fix/system-robustness ──────── merge back ──────────→ │
  │   (Track A: bug fixes)         (Week 2)                │
  │                                                        │
  ├─ refactor/architecture-cleanup ── rebase on A ── merge→│
  │   (Track B: refactoring)         (Week 3)              │
```

1. Track A merges first (smaller, critical fixes)
2. Track B rebases on updated main (resolves conflicts)
3. Track B merges second (larger architectural changes)

---

## Part 3: Error Handling Framework Design

### Backend Error Hierarchy (Enhanced)

```
BaseError (abstract)
├── DomainError
│   ├── BrowserError (recoverable flag, error_code)
│   │   ├── BrowserCrashedError
│   │   ├── BrowserTimeoutError
│   │   └── BrowserMemoryError
│   ├── SandboxError
│   │   ├── SandboxNotReadyError
│   │   ├── SandboxOOMError
│   │   └── SandboxTimeoutError
│   ├── LLMError
│   │   ├── LLMTimeoutError
│   │   ├── LLMRateLimitError
│   │   └── LLMValidationError
│   └── SessionError
│       ├── SessionNotFoundError
│       ├── SessionExpiredError
│       └── SessionConflictError
├── ApplicationError (HTTP status mapping)
│   ├── NotFoundError (404)
│   ├── BadRequestError (400)
│   ├── UnauthorizedError (401)
│   └── ServerError (500)
└── InfrastructureError
    ├── DatabaseError
    ├── CacheError
    └── ExternalServiceError
```

### Frontend Error Handling

```typescript
// Error boundary composable
export function useErrorBoundary() {
  const lastError = ref<AppError | null>(null)

  onErrorCaptured((err, instance, info) => {
    lastError.value = normalizeError(err)
    reportError(err, info)
    return false
  })

  return { lastError, clearError: () => lastError.value = null }
}

// SSE error recovery
export function useSSEResilience() {
  const connectionState = ref<'connected' | 'reconnecting' | 'failed'>('connected')
  const retryCount = ref(0)
  const maxRetries = 7

  function scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(2, retryCount.value), 45000)
    const jitter = delay * 0.25 * Math.random()
    connectionState.value = 'reconnecting'
    setTimeout(reconnect, delay + jitter)
    retryCount.value++
  }
}
```

---

## Part 4: Retry Logic Design

### Retry Decision Matrix

| Operation | Max Attempts | Base Delay | Max Delay | Retryable Errors | Non-Retryable |
|-----------|-------------|------------|-----------|-------------------|---------------|
| LLM API Call | 3 | 2s | 30s | Timeout, 429, 500, 502, 503, 504 | 400, 401, 403 |
| Browser Navigation | 3 | 1s | 10s | Crash, Timeout, Connection | Permission denied |
| Sandbox Health Check | 3 | 2s | 30s | Connection, Timeout | N/A |
| MongoDB Operation | 3 | 0.5s | 5s | Connection, Timeout, ServerSelection | Duplicate key |
| Redis Operation | 3 | 0.5s | 5s | Connection, Timeout | N/A |
| HTTP External API | 3 | 1s | 15s | 429, 500, 502, 503, 504 | 400, 401, 403, 404 |
| SSE Reconnection | 7 | 1s | 45s | Network error, Close | User cancel |

### Circuit Breaker Pattern (Already Exists for Screenshots)

Extend to browser and sandbox operations:
```python
# backend/app/core/circuit_breaker.py (new file)
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.state: Literal["closed", "open", "half_open"] = "closed"
        self.failure_count: int = 0
        self.last_failure_time: float = 0
```

---

## Part 5: Session Management Design

### Session State Machine (Enhanced)

```
PENDING → INITIALIZING → READY → RUNNING → COMPLETING → COMPLETED
                                    ↓          ↓
                                  PAUSED     FAILED
                                    ↓
                                  RUNNING (resume)

EXPIRED (TTL-based, any state)
```

### Session Resilience Features

1. **Event ID Persistence** (already implemented at `ChatPage.vue:2505`)
2. **Auto-Resume on Page Refresh** (already at `ChatPage.vue:2498-2547`)
3. **Periodic Session Cleanup** (NEW - add background task in `main.py`)
4. **Redis TTL for Task Streams** (NEW - set TTL when creating streams)
5. **Graceful Degradation on DB Failure** (NEW - cache recent events in Redis)

### Session Timeout Configuration

```python
# New settings in config.py
session_max_duration_minutes: int = 120  # Hard cap on session lifetime
session_idle_timeout_minutes: int = 30   # Idle timeout (no events)
session_cleanup_interval_seconds: int = 300  # Periodic cleanup interval
redis_task_stream_ttl_seconds: int = 3600  # Auto-expire Redis task streams
```

---

## Part 6: Monitoring & Observability Enhancements

### New Prometheus Metrics

```python
# Error tracking
error_total = Counter("pythinker_errors_total", "Total errors", ["error_type", "layer", "recoverable"])

# SSE reliability
sse_heartbeat_sent_total = Counter("pythinker_sse_heartbeat_sent_total", "SSE heartbeats sent")
sse_timeout_total = Counter("pythinker_sse_timeout_total", "SSE stream timeouts")
sse_reconnection_total = Counter("pythinker_sse_reconnection_total", "SSE client reconnections")

# Background task tracking
background_task_active = Gauge("pythinker_background_tasks_active", "Active background tasks")
background_task_orphaned_total = Counter("pythinker_background_tasks_orphaned_total", "Orphaned tasks detected")

# Session lifecycle
session_duration_seconds = Histogram("pythinker_session_duration_seconds", "Session duration")
session_stale_cleanup_total = Counter("pythinker_session_stale_cleanup_total", "Stale sessions cleaned")
```

### Grafana Dashboard Additions

1. **SSE Health Panel:** Heartbeat rate, timeout rate, reconnection rate
2. **Background Task Panel:** Active count, orphaned count, cleanup rate
3. **Session Lifecycle Panel:** Duration histogram, stale cleanup rate
4. **Error Rate Panel:** By type, layer, recoverability

---

## Part 7: Testing Strategy

### Backend Test Priorities

| Test Target | Type | Coverage Goal |
|-------------|------|---------------|
| `ChatOrchestrationService` (extracted from agent_service) | Unit | 90% |
| SSE heartbeat/timeout in session_routes | Integration | 85% |
| Retry decorators with failure simulation | Unit | 95% |
| Circuit breaker state transitions | Unit | 95% |
| Session lifecycle state machine | Unit | 90% |
| Background task cancellation | Integration | 80% |

### Frontend Test Priorities

| Test Target | Type | Coverage Goal |
|-------------|------|---------------|
| `useResponsePhase` composable | Unit | 95% |
| `useSSEConnection` composable | Unit | 90% |
| `useEventDispatcher` composable | Unit | 85% |
| `useSessionRestore` composable | Unit | 90% |
| Error boundary behavior | Unit | 80% |

---

## Appendix: File Size Report (God Class Candidates)

| File | Lines | Verdict |
|------|-------|---------|
| `frontend/src/pages/ChatPage.vue` | 3,218 | **CRITICAL** - Must decompose |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | 2,800+ | **CRITICAL** - Must decompose |
| `backend/app/application/services/agent_service.py` | 1,378 | **CRITICAL** - Must decompose |
| `backend/app/core/config.py` | 824 | Acceptable (configuration file, well-organized) |
| `backend/app/main.py` | 829 | Acceptable (entry point with middleware) |
| `frontend/src/api/client.ts` | 633 | Acceptable (API client with SSE) |
| `backend/app/core/retry.py` | 463 | Good (focused on retry logic) |
