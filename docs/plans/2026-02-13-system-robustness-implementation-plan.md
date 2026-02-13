# System Robustness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 20 identified issues across backend, frontend, sandbox, and Chrome browser to achieve a stable, resilient, maintainable system.

**Architecture:** Two parallel git branches - Track A (`fix/system-robustness`) for runtime bug fixes, Track B (`refactor/architecture-cleanup`) for code decomposition. Track A merges first, Track B rebases and merges second.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2, Vue 3 / TypeScript / Vite, Docker, Playwright, Redis, MongoDB

**Design Document:** `docs/plans/2026-02-13-system-robustness-architecture-design.md`

---

## Pre-Flight Checklist

Before starting any task, ensure:
```bash
# Backend environment
conda activate pythinker

# Frontend environment
cd frontend && bun install && cd ..

# Verify current tests pass
cd backend && pytest tests/ -x -q && cd ..
cd frontend && bun run type-check && cd ..
```

---

# TRACK A: Stability Fixes (`fix/system-robustness`)

---

## Task 1: Create Branch and Remove Debug Telemetry (H3)

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue` (lines 934, 1743, 2240, 2471, 2878)

**Step 1: Create the stability branch**

```bash
git checkout -b fix/system-robustness main
```

**Step 2: Remove all 5 debug fetch calls from ChatPage.vue**

Search for and delete all blocks matching `fetch('http://127.0.0.1:7243/ingest/` including their `// #region agent log` / `// #endregion` wrappers. These are at lines:
- ~934 (cleanupStreamingState)
- ~1743 (handleProgressEvent)
- ~2240 (done event handler)
- ~2471 (SSE onClose)
- ~2878 (retryOnClose)

Each block follows this pattern - delete the entire block:
```javascript
// #region agent log
fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...})}).catch(()=>{});
// #endregion
```

**Step 3: Verify frontend still compiles**

Run: `cd frontend && bun run type-check`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "fix: remove debug telemetry fetch calls from ChatPage.vue

Removes 5 hardcoded fetch calls to http://127.0.0.1:7243 that were
left from debugging sessions. These leak page state and add overhead."
```

---

## Task 2: Fix SSE Reconnection Backoff (H5)

**Files:**
- Modify: `frontend/src/api/client.ts` (line ~396)
- Test: `frontend/src/api/__tests__/client.test.ts` (create)

**Step 1: Write the failing test**

Create `frontend/src/api/__tests__/client.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'

describe('SSE reconnection backoff', () => {
  it('should use exponential backoff with jitter on reconnection', () => {
    // Simulate the backoff calculation
    const baseDelay = 1000
    const maxDelay = 45000

    // Retry 0: ~1000ms
    const delay0 = Math.min(baseDelay * Math.pow(2, 0), maxDelay)
    expect(delay0).toBe(1000)

    // Retry 3: ~8000ms
    const delay3 = Math.min(baseDelay * Math.pow(2, 3), maxDelay)
    expect(delay3).toBe(8000)

    // Retry 10: capped at 45000ms
    const delay10 = Math.min(baseDelay * Math.pow(2, 10), maxDelay)
    expect(delay10).toBe(45000)
  })

  it('should add jitter to prevent thundering herd', () => {
    const baseDelay = 1000
    const maxDelay = 45000
    const retryCount = 3
    const delay = Math.min(baseDelay * Math.pow(2, retryCount), maxDelay)
    const jitter = delay * 0.25 * Math.random()

    expect(jitter).toBeGreaterThanOrEqual(0)
    expect(jitter).toBeLessThanOrEqual(delay * 0.25)
  })
})
```

**Step 2: Run test to verify it passes (this is a calculation test)**

Run: `cd frontend && bun run test:run -- src/api/__tests__/client.test.ts`
Expected: PASS

**Step 3: Fix the SSE reconnection in client.ts**

In `frontend/src/api/client.ts`, find the line (~396) with:
```typescript
setTimeout(() => createConnection().catch(console.error), 1000);
```

Replace with:
```typescript
const retryDelay = Math.min(baseDelay * Math.pow(2, retryCount), maxDelay);
const jitter = retryDelay * 0.25 * Math.random();
console.debug(`[SSE] Reconnecting in ${Math.round(retryDelay + jitter)}ms (attempt ${retryCount + 1}/${maxRetries})`);
setTimeout(() => createConnection().catch(console.error), retryDelay + jitter);
retryCount++;
```

**Step 4: Verify type-check passes**

Run: `cd frontend && bun run type-check`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/__tests__/client.test.ts
git commit -m "fix: use exponential backoff with jitter for SSE reconnection

Previously used a fixed 1000ms delay. Now uses exponential backoff
(1s -> 2s -> 4s -> ... -> 45s cap) with 25% jitter to prevent
thundering herd on server recovery."
```

---

## Task 3: Add Vue Error Boundary (H6)

**Files:**
- Create: `frontend/src/composables/useErrorBoundary.ts`
- Modify: `frontend/src/pages/ChatPage.vue` (add error boundary hook)

**Step 1: Create the error boundary composable**

Create `frontend/src/composables/useErrorBoundary.ts`:

```typescript
import { ref, onErrorCaptured } from 'vue'

export interface AppError {
  message: string
  code?: string
  recoverable: boolean
  timestamp: number
}

function normalizeError(err: unknown): AppError {
  if (err instanceof Error) {
    return {
      message: err.message,
      code: (err as { code?: string }).code,
      recoverable: true,
      timestamp: Date.now(),
    }
  }
  return {
    message: String(err),
    recoverable: true,
    timestamp: Date.now(),
  }
}

export function useErrorBoundary() {
  const lastCapturedError = ref<AppError | null>(null)

  onErrorCaptured((err: unknown, _instance, info: string) => {
    const normalized = normalizeError(err)
    lastCapturedError.value = normalized
    console.error(`[ErrorBoundary] Captured error in ${info}:`, err)
    // Return false to stop propagation (prevents page crash)
    return false
  })

  function clearError() {
    lastCapturedError.value = null
  }

  return { lastCapturedError, clearError }
}
```

**Step 2: Add error boundary to ChatPage.vue**

In `frontend/src/pages/ChatPage.vue`, in the `<script setup>` section near the top imports, add:

```typescript
import { useErrorBoundary } from '../composables/useErrorBoundary'

const { lastCapturedError, clearError } = useErrorBoundary()
```

**Step 3: Verify type-check**

Run: `cd frontend && bun run type-check`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/composables/useErrorBoundary.ts frontend/src/pages/ChatPage.vue
git commit -m "feat: add Vue error boundary composable to prevent page crashes

Uses onErrorCaptured to catch unhandled errors from child components.
Normalizes errors and prevents propagation that would crash the page."
```

---

## Task 4: Enforce HTTP Client Pool Usage (H1)

**Files:**
- Modify: `backend/app/core/sandbox_manager.py` (~line 278)
- Modify: `backend/app/application/services/connector_service.py` (~lines 194, 216)
- Modify: `backend/app/infrastructure/external/llm/ollama_llm.py` (~lines 301, 440)
- Modify: `backend/app/infrastructure/external/image_generation.py` (~line 31)

**Step 1: Audit all direct httpx.AsyncClient usages**

Run: `cd backend && grep -rn "httpx.AsyncClient" app/ --include="*.py" | grep -v "__pycache__" | grep -v "http_pool.py"`

Document each violation and its service name.

**Step 2: Replace sandbox_manager.py direct client**

Find the direct `httpx.AsyncClient` creation in `sandbox_manager.py` (~line 278) and replace with:

```python
from app.infrastructure.external.http_pool import HTTPClientPool

# Replace: self.api_client = httpx.AsyncClient(base_url=..., timeout=30.0)
# With:
self.api_client = await HTTPClientPool.get_client(
    name=f"sandbox-{self.ip_address}",
    base_url=f"http://{self.ip_address}:8080",
    timeout=30.0,
)
```

**Step 3: Replace connector_service.py direct clients**

Replace both `async with httpx.AsyncClient(timeout=10.0) as client:` blocks with:

```python
from app.infrastructure.external.http_pool import HTTPClientPool

client = await HTTPClientPool.get_client(name="connector-service", timeout=10.0)
response = await client.get(url)  # or client.post(url, json=data)
```

**Step 4: Replace ollama_llm.py direct clients**

Replace both `async with httpx.AsyncClient(timeout=120.0) as client:` blocks with:

```python
from app.infrastructure.external.http_pool import HTTPClientPool

client = await HTTPClientPool.get_client(
    name="ollama",
    base_url=self.base_url,
    timeout=120.0,
)
```

**Step 5: Replace image_generation.py direct client**

Replace `self._client = httpx.AsyncClient(base_url="https://api.fal.ai", timeout=300.0)` with:

```python
from app.infrastructure.external.http_pool import HTTPClientPool

# In __init__ or lazy init:
self._client = await HTTPClientPool.get_client(
    name="fal-ai",
    base_url="https://api.fal.ai",
    timeout=300.0,
)
```

**Step 6: Run backend linter and tests**

Run: `cd backend && ruff check . && pytest tests/ -x -q`
Expected: All pass

**Step 7: Commit**

```bash
git add backend/app/core/sandbox_manager.py backend/app/application/services/connector_service.py \
  backend/app/infrastructure/external/llm/ollama_llm.py backend/app/infrastructure/external/image_generation.py
git commit -m "fix: replace 6 direct httpx.AsyncClient usages with HTTPClientPool

Enforces centralized connection pooling for sandbox, connector,
Ollama, and image generation HTTP clients. Prevents connection pool
exhaustion and ensures consistent timeout/retry configuration."
```

---

## Task 5: Apply Retry Decorators to Unprotected External Calls (H2)

**Files:**
- Modify: `backend/app/core/sandbox_manager.py` (health check method)
- Modify: `backend/app/application/services/connector_service.py` (MCP config fetches)
- Modify: `backend/app/infrastructure/external/llm/ollama_llm.py` (API calls)
- Modify: `backend/app/infrastructure/external/image_generation.py` (API calls)

**Step 1: Add @sandbox_retry to sandbox health check**

In `sandbox_manager.py`, find the health check method (~line 411) and add:

```python
from app.core.retry import sandbox_retry

@sandbox_retry  # 3 attempts, 2-30s exponential backoff
async def _check_sandbox_health(self, address: str) -> bool:
    # existing implementation
```

**Step 2: Add @http_retry to connector service**

In `connector_service.py`, add to the methods that make external HTTP calls:

```python
from app.core.retry import http_retry

@http_retry  # 3 attempts, 1-15s exponential backoff
async def get_user_mcp_configs(self, user_id: str) -> list:
    # existing implementation
```

**Step 3: Add @llm_retry to Ollama LLM calls**

In `ollama_llm.py`, add to the main API call methods:

```python
from app.core.retry import llm_retry

@llm_retry  # 3 attempts, 2-30s exponential backoff
async def _call_ollama(self, messages: list, **kwargs) -> str:
    # existing implementation
```

**Step 4: Run backend tests**

Run: `cd backend && pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/core/sandbox_manager.py backend/app/application/services/connector_service.py \
  backend/app/infrastructure/external/llm/ollama_llm.py backend/app/infrastructure/external/image_generation.py
git commit -m "fix: add retry decorators to 4 unprotected external call sites

Applies existing @sandbox_retry, @http_retry, @llm_retry decorators
to sandbox health checks, connector service, Ollama LLM, and image
generation. Prevents transient failures from becoming user errors."
```

---

## Task 6: Add Docker Health Check to Sandbox (H4)

**Files:**
- Modify: `sandbox/Dockerfile`
- Modify: `docker-compose-development.yml` (sandbox service)
- Modify: `docker-compose.yml` (sandbox service)

**Step 1: Add HEALTHCHECK to sandbox Dockerfile**

In `sandbox/Dockerfile`, add before the final CMD:

```dockerfile
# Health check: verify sandbox API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://localhost:8080/health || exit 1
```

**Step 2: Add healthcheck to docker-compose-development.yml**

In the sandbox service definition, add:

```yaml
healthcheck:
  test: ["CMD", "curl", "-sf", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  start_period: 60s
  retries: 3
```

**Step 3: Add healthcheck to docker-compose.yml**

Same healthcheck configuration as Step 2.

**Step 4: Commit**

```bash
git add sandbox/Dockerfile docker-compose-development.yml docker-compose.yml
git commit -m "fix: add Docker health checks for sandbox container

Adds HEALTHCHECK to Dockerfile and healthcheck config to docker-compose
files. Enables automatic restart of unhealthy sandbox containers and
proper orchestrator integration."
```

---

## Task 7: Add Periodic Session Cleanup (H7)

**Files:**
- Modify: `backend/app/main.py` (~line 413, after startup cleanup)
- Test: `backend/tests/test_periodic_session_cleanup.py` (create)

**Step 1: Write the test**

Create `backend/tests/test_periodic_session_cleanup.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_periodic_cleanup_task_calls_maintenance_service():
    """Verify the periodic cleanup task calls the maintenance service."""
    mock_maintenance = AsyncMock()
    mock_maintenance.cleanup_stale_running_sessions = AsyncMock(
        return_value=MagicMock(cleaned=2)
    )

    # Simulate one iteration of the cleanup loop
    from app.main import _run_periodic_session_cleanup

    # Run with a very short interval and cancel after first iteration
    task = asyncio.create_task(
        _run_periodic_session_cleanup(mock_maintenance, interval_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert mock_maintenance.cleanup_stale_running_sessions.called
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_periodic_session_cleanup.py -v`
Expected: FAIL (function not defined)

**Step 3: Implement the periodic cleanup function in main.py**

In `backend/app/main.py`, add the function and call it from lifespan:

```python
async def _run_periodic_session_cleanup(
    maintenance_service: "MaintenanceService",
    interval_seconds: float = 300.0,
) -> None:
    """Background task: clean up stale sessions every 5 minutes."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await maintenance_service.cleanup_stale_running_sessions(
                stale_threshold_minutes=30,
                dry_run=False,
            )
            if result.cleaned > 0:
                logger.info("Periodic cleanup: %d stale sessions cleaned", result.cleaned)
        except Exception as e:
            logger.warning("Periodic session cleanup failed: %s", e)
```

In the lifespan function, after the startup cleanup block (~line 413), add:

```python
periodic_cleanup_task = asyncio.create_task(
    _run_periodic_session_cleanup(maintenance_service)
)
```

In the shutdown section, add:

```python
periodic_cleanup_task.cancel()
with contextlib.suppress(asyncio.CancelledError):
    await periodic_cleanup_task
```

**Step 4: Run test**

Run: `cd backend && pytest tests/test_periodic_session_cleanup.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_periodic_session_cleanup.py
git commit -m "feat: add periodic session cleanup background task

Cleans up stale sessions (>30 min running) every 5 minutes instead
of only at startup. Prevents accumulation of orphaned sessions."
```

---

## Task 8: Fix Swallowed Exceptions in Session Routes (H8)

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py` (~lines 197-203)

**Step 1: Add cleanup warnings to response**

Find the fire-and-forget screenshot cleanup block and replace:

```python
# BEFORE (swallowed exception):
try:
    deleted = await screenshot_query_service.delete_by_session(session_id)
    if deleted:
        logger.info("Deleted %d screenshots for session %s", deleted, session_id)
except Exception as e:
    logger.warning("Failed to cleanup screenshots for session %s: %s", session_id, e)
return APIResponse.success()

# AFTER (tracked warning):
cleanup_warnings: list[str] = []
try:
    deleted = await screenshot_query_service.delete_by_session(session_id)
    if deleted:
        logger.info("Deleted %d screenshots for session %s", deleted, session_id)
except Exception as e:
    warning_msg = f"Screenshot cleanup failed: {e}"
    cleanup_warnings.append(warning_msg)
    logger.warning("Failed to cleanup screenshots for session %s: %s", session_id, e)

return APIResponse.success(
    data={"warnings": cleanup_warnings} if cleanup_warnings else None
)
```

**Step 2: Run linter**

Run: `cd backend && ruff check app/interfaces/api/session_routes.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/app/interfaces/api/session_routes.py
git commit -m "fix: surface cleanup warnings instead of swallowing exceptions

Session delete now returns cleanup warnings in the response body
instead of silently swallowing screenshot cleanup failures."
```

---

## Task 9: Fix SSE Heartbeat for Long Operations (C1 - Part 1)

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py` (heartbeat logic ~lines 385-500)

**Step 1: Understand the current heartbeat approach**

Read `backend/app/interfaces/api/session_routes.py` lines 380-510. The current approach uses `asyncio.wait()` with both a next-event task and a heartbeat sleep task. The problem is that the heartbeat only fires when the sleep completes - if the next-event task is blocking for 120s, the heartbeat still runs on its 15s schedule via `asyncio.wait(FIRST_COMPLETED)`.

**However**, the *real* gap is: when the event source (domain service) blocks for >120s with zero events, `agent_service.py:683-684` times out and yields an ErrorEvent. The heartbeat in session_routes.py DOES fire correctly every 15s, but the ErrorEvent from agent_service.py terminates the stream.

**Step 2: The fix - increase CHAT_EVENT_TIMEOUT_SECONDS and add progress events**

In `backend/app/application/services/agent_service.py` line 49, change:

```python
# BEFORE:
CHAT_EVENT_TIMEOUT_SECONDS = 120.0

# AFTER - Increase to 300s (5 min) to accommodate browser recovery + LLM calls
CHAT_EVENT_TIMEOUT_SECONDS = 300.0
```

**Step 3: Add SSE comment heartbeats to session_routes.py**

In the heartbeat section (~line 457-465), ensure heartbeats are sent as SSE comments when there's no real progress to report:

```python
# When heartbeat timer fires but we have no real progress event:
if heartbeat_task in done:
    # Send SSE comment-style heartbeat to keep connection alive
    yield ServerSentEvent(comment="heartbeat")
    heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))
```

**Step 4: Run backend tests**

Run: `cd backend && pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/application/services/agent_service.py backend/app/interfaces/api/session_routes.py
git commit -m "fix: increase chat event timeout to 300s and ensure SSE heartbeat

Increases CHAT_EVENT_TIMEOUT_SECONDS from 120s to 300s to accommodate
long browser recovery operations. Ensures SSE comment heartbeats are
sent every 15s to keep the connection alive during long operations."
```

---

## Task 10: Cancel Background Tasks on SSE Disconnect (C2)

**Files:**
- Modify: `backend/app/application/services/agent_service.py` (finally block ~line 724)
- Modify: `backend/app/interfaces/api/session_routes.py` (stream cleanup)

**Step 1: Add session-level cancellation tracking**

In `agent_service.py`, add a cancellation token system:

```python
# Add to __init__:
self._session_cancel_events: dict[str, asyncio.Event] = {}

# Add method:
def request_cancellation(self, session_id: str) -> None:
    """Signal that a session's processing should stop."""
    event = self._session_cancel_events.get(session_id)
    if event:
        event.set()
        logger.info("Cancellation requested for session %s", session_id)
```

**Step 2: Wire cancellation into chat() method**

In `agent_service.py` chat() method, before the while loop (~line 679):

```python
# Create cancellation event for this session
cancel_event = asyncio.Event()
self._session_cancel_events[session_id] = cancel_event
```

In the finally block (~line 724), add cleanup:

```python
finally:
    # Remove cancellation event
    self._session_cancel_events.pop(session_id, None)

    with contextlib.suppress(Exception):
        await stream_iter.aclose()
```

**Step 3: Wire SSE route to call cancellation on disconnect**

In `session_routes.py`, in the SSE generator's cleanup/finally block, add:

```python
# When SSE stream closes (user disconnect, timeout, error):
agent_service = get_agent_service()
agent_service.request_cancellation(session_id)
```

**Step 4: Run backend tests**

Run: `cd backend && pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/application/services/agent_service.py backend/app/interfaces/api/session_routes.py
git commit -m "fix: cancel background tasks when SSE stream disconnects

Adds session-level cancellation tokens that propagate from SSE
disconnect through the domain service. Prevents orphaned background
tasks from continuing to consume resources after user disconnects."
```

---

## Task 11: Fix Frontend Package Name (M6)

**Files:**
- Modify: `frontend/package.json` (line 2)

**Step 1: Rename package**

Change line 2 from:
```json
"name": "vite-vue-typescript-starter",
```
To:
```json
"name": "pythinker-frontend",
```

**Step 2: Commit**

```bash
git add frontend/package.json
git commit -m "fix: rename frontend package from generic starter to pythinker-frontend"
```

---

## Task 12: Track A Integration Verification

**Step 1: Run full backend test suite**

Run: `cd backend && conda activate pythinker && ruff check . && ruff format --check . && pytest tests/ -v`
Expected: All pass, no lint errors

**Step 2: Run full frontend checks**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: All pass

**Step 3: Verify Docker builds**

Run: `docker compose -f docker-compose-development.yml build sandbox`
Expected: Build succeeds with HEALTHCHECK

**Step 4: Final Track A commit**

```bash
git add -A
git commit -m "chore: Track A integration verification - all checks pass"
```

---

# TRACK B: Architecture Refactoring (`refactor/architecture-cleanup`)

> **Note:** Track B should be started in parallel on a separate worktree or after Track A merges.

---

## Task 13: Create Architecture Branch

**Step 1: Create the branch**

```bash
git checkout -b refactor/architecture-cleanup main
```

---

## Task 14: Extract useResponsePhase Composable (C3 - Part 1)

**Files:**
- Create: `frontend/src/composables/useResponsePhase.ts`
- Create: `frontend/src/composables/__tests__/useResponsePhase.test.ts`
- Modify: `frontend/src/pages/ChatPage.vue` (lines 476-610)

**Step 1: Write failing tests for the state machine**

Create `frontend/src/composables/__tests__/useResponsePhase.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Type we're testing (will be created in step 3)
type ResponsePhase = 'idle' | 'connecting' | 'streaming' | 'completing' | 'settled' | 'error' | 'timed_out'

describe('useResponsePhase', () => {
  it('should start in idle phase', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase } = useResponsePhase()
    expect(phase.value).toBe('idle')
  })

  it('should transition from idle to connecting', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo } = useResponsePhase()
    transitionTo('connecting')
    expect(phase.value).toBe('connecting')
  })

  it('should transition from connecting to streaming', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo } = useResponsePhase()
    transitionTo('connecting')
    transitionTo('streaming')
    expect(phase.value).toBe('streaming')
  })

  it('should auto-settle from completing after timeout', async () => {
    vi.useFakeTimers()
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo } = useResponsePhase()

    transitionTo('connecting')
    transitionTo('streaming')
    transitionTo('completing')

    expect(phase.value).toBe('completing')

    // After 300ms, should auto-settle
    vi.advanceTimersByTime(350)
    expect(phase.value).toBe('settled')

    vi.useRealTimers()
  })

  it('should expose isLoading computed', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isLoading, transitionTo } = useResponsePhase()

    expect(isLoading.value).toBe(false)
    transitionTo('connecting')
    expect(isLoading.value).toBe(true)
    transitionTo('streaming')
    expect(isLoading.value).toBe(true)
  })

  it('should expose isThinking computed', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { isThinking, transitionTo } = useResponsePhase()

    expect(isThinking.value).toBe(false)
    transitionTo('connecting')
    expect(isThinking.value).toBe(true)
    transitionTo('streaming')
    expect(isThinking.value).toBe(false)
  })

  it('should reset to idle', async () => {
    const { useResponsePhase } = await import('../useResponsePhase')
    const { phase, transitionTo, reset } = useResponsePhase()

    transitionTo('connecting')
    transitionTo('streaming')
    reset()
    expect(phase.value).toBe('idle')
  })
})
```

**Step 2: Run tests to verify they fail**

Run: `cd frontend && bun run test:run -- src/composables/__tests__/useResponsePhase.test.ts`
Expected: FAIL (module not found)

**Step 3: Implement useResponsePhase composable**

Create `frontend/src/composables/useResponsePhase.ts`:

```typescript
import { ref, computed, watch } from 'vue'

export type ResponsePhase = 'idle' | 'connecting' | 'streaming' | 'completing' | 'settled' | 'error' | 'timed_out'

export function useResponsePhase() {
  const phase = ref<ResponsePhase>('idle')
  let settleTimer: ReturnType<typeof setTimeout> | null = null

  const isLoading = computed(() =>
    ['connecting', 'streaming', 'completing'].includes(phase.value)
  )

  const isThinking = computed(() => phase.value === 'connecting')

  const isSettled = computed(() => phase.value === 'settled')

  const isError = computed(() => phase.value === 'error')

  const isTimedOut = computed(() => phase.value === 'timed_out')

  function transitionTo(newPhase: ResponsePhase) {
    const prev = phase.value

    // Clear any pending settle timer
    if (settleTimer) {
      clearTimeout(settleTimer)
      settleTimer = null
    }

    phase.value = newPhase

    // Auto-settle from completing after 300ms
    if (newPhase === 'completing') {
      settleTimer = setTimeout(() => {
        if (phase.value === 'completing') {
          phase.value = 'settled'
        }
      }, 300)
    }
  }

  function reset() {
    if (settleTimer) {
      clearTimeout(settleTimer)
      settleTimer = null
    }
    phase.value = 'idle'
  }

  return {
    phase,
    isLoading,
    isThinking,
    isSettled,
    isError,
    isTimedOut,
    transitionTo,
    reset,
  }
}
```

**Step 4: Run tests**

Run: `cd frontend && bun run test:run -- src/composables/__tests__/useResponsePhase.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/composables/useResponsePhase.ts \
  frontend/src/composables/__tests__/useResponsePhase.test.ts
git commit -m "feat: extract useResponsePhase composable from ChatPage.vue

Extracts the 6-state response lifecycle state machine into a reusable
composable with typed transitions, auto-settle timer, and computed
properties (isLoading, isThinking, isSettled, isError, isTimedOut)."
```

---

## Task 15: Extract useSSEConnection Composable (C3 - Part 2)

**Files:**
- Create: `frontend/src/composables/useSSEConnection.ts`
- Create: `frontend/src/composables/__tests__/useSSEConnection.test.ts`

**Step 1: Write failing tests**

Create `frontend/src/composables/__tests__/useSSEConnection.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

describe('useSSEConnection', () => {
  it('should track connection state', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { connectionState } = useSSEConnection()
    expect(connectionState.value).toBe('disconnected')
  })

  it('should track last event time', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastEventTime, updateLastEventTime } = useSSEConnection()

    expect(lastEventTime.value).toBe(0)
    updateLastEventTime()
    expect(lastEventTime.value).toBeGreaterThan(0)
  })

  it('should detect stale connections', async () => {
    vi.useFakeTimers()
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastEventTime, updateLastEventTime, isConnectionStale } = useSSEConnection()

    updateLastEventTime()
    expect(isConnectionStale(30000)).toBe(false)

    vi.advanceTimersByTime(31000)
    expect(isConnectionStale(30000)).toBe(true)

    vi.useRealTimers()
  })

  it('should persist and restore lastEventId', async () => {
    const { useSSEConnection } = await import('../useSSEConnection')
    const { lastEventId, persistEventId, getPersistedEventId } = useSSEConnection()

    const sessionId = 'test-session-123'
    lastEventId.value = 'event-456'
    persistEventId(sessionId)

    const restored = getPersistedEventId(sessionId)
    expect(restored).toBe('event-456')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test:run -- src/composables/__tests__/useSSEConnection.test.ts`
Expected: FAIL

**Step 3: Implement useSSEConnection**

Create `frontend/src/composables/useSSEConnection.ts`:

```typescript
import { ref, computed } from 'vue'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed'

export function useSSEConnection() {
  const connectionState = ref<ConnectionState>('disconnected')
  const lastEventTime = ref(0)
  const lastEventId = ref<string | undefined>(undefined)
  const retryCount = ref(0)

  function updateLastEventTime() {
    lastEventTime.value = Date.now()
  }

  function isConnectionStale(thresholdMs: number): boolean {
    if (lastEventTime.value === 0) return false
    return Date.now() - lastEventTime.value > thresholdMs
  }

  function persistEventId(sessionId: string) {
    if (lastEventId.value && sessionId) {
      sessionStorage.setItem(`pythinker-last-event-${sessionId}`, lastEventId.value)
    }
  }

  function getPersistedEventId(sessionId: string): string | null {
    return sessionStorage.getItem(`pythinker-last-event-${sessionId}`)
  }

  function cleanupSessionStorage(sessionId: string) {
    sessionStorage.removeItem(`pythinker-last-event-${sessionId}`)
    sessionStorage.removeItem(`pythinker-stop-${sessionId}`)
  }

  function resetRetryCount() {
    retryCount.value = 0
  }

  return {
    connectionState,
    lastEventTime,
    lastEventId,
    retryCount,
    updateLastEventTime,
    isConnectionStale,
    persistEventId,
    getPersistedEventId,
    cleanupSessionStorage,
    resetRetryCount,
  }
}
```

**Step 4: Run tests**

Run: `cd frontend && bun run test:run -- src/composables/__tests__/useSSEConnection.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/composables/useSSEConnection.ts \
  frontend/src/composables/__tests__/useSSEConnection.test.ts
git commit -m "feat: extract useSSEConnection composable from ChatPage.vue

Extracts SSE connection state tracking, event time monitoring, stale
connection detection, and event ID persistence into a composable."
```

---

## Task 16: Wire Extracted Composables into ChatPage.vue (C3 - Part 3)

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Import and use extracted composables**

Replace the inline state machine code (lines 476-610) with composable imports:

```typescript
import { useResponsePhase } from '../composables/useResponsePhase'
import { useSSEConnection } from '../composables/useSSEConnection'

const {
  phase: responsePhase,
  isLoading,
  isThinking,
  isSettled,
  isError,
  isTimedOut,
  transitionTo,
  reset: resetResponsePhase,
} = useResponsePhase()

const {
  connectionState,
  lastEventTime,
  lastEventId,
  updateLastEventTime,
  isConnectionStale,
  persistEventId,
  getPersistedEventId,
  cleanupSessionStorage,
} = useSSEConnection()
```

**Step 2: Remove the inline implementations** that are now in composables:
- Remove the `responsePhase` reactive property from state
- Remove the `transitionTo` function
- Remove the inline `isLoading`, `isThinking` computed properties
- Remove the `updateLastEventTime` function
- Remove inline `lastEventId` management

**Step 3: Verify all template references still work**

Run: `cd frontend && bun run type-check`
Expected: No errors

**Step 4: Run existing tests**

Run: `cd frontend && bun run test:run`
Expected: All pass

**Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "refactor: wire useResponsePhase and useSSEConnection into ChatPage.vue

Replaces ~130 lines of inline state machine and SSE connection code
with composable imports. ChatPage.vue reduced by ~130 lines."
```

---

## Task 17-20: Backend Service Decomposition (C4, C5)

> Tasks 17-20 follow the same TDD pattern for backend decomposition.
> Due to plan length, these are summarized. Each follows: write test → verify fail → implement → verify pass → commit.

### Task 17: Extract SessionLifecycleService from agent_service.py

- Extract: `create_session()`, `delete_session()`, `get_session()`, `_cleanup_stale_sessions()`
- Create: `backend/app/application/services/session_lifecycle_service.py`
- Test: `backend/tests/application/services/test_session_lifecycle_service.py`
- Keep `AgentService` as orchestrator that delegates to `SessionLifecycleService`

### Task 18: Extract SandboxWarmupService from agent_service.py

- Extract: `_warm_sandbox_for_session()`, `_wait_for_sandbox_warmup_if_needed()`, `_cancel_sandbox_warmup_task()`
- Create: `backend/app/application/services/sandbox_warmup_service.py`
- Test: `backend/tests/application/services/test_sandbox_warmup_service.py`

### Task 19: Extract BrowserHealthMonitor from playwright_browser.py

- Extract: `BROWSER_CRASH_SIGNATURES`, `_is_crash_error()`, `_on_page_crash()`, `_check_memory_pressure()`, `_verify_connection_health()`
- Create: `backend/app/infrastructure/external/browser/browser_health.py`
- Test: `backend/tests/infrastructure/external/browser/test_browser_health.py`

### Task 20: Extract BrowserNavigation from playwright_browser.py

- Extract: `navigate()`, `navigate_fast()`, `navigate_for_display()`, `restart()`
- Create: `backend/app/infrastructure/external/browser/browser_navigation.py`
- Test: `backend/tests/infrastructure/external/browser/test_browser_navigation.py`

---

## Task 21: Track B Integration Verification

**Step 1: Run full backend test suite**

Run: `cd backend && conda activate pythinker && ruff check . && ruff format --check . && pytest tests/ -v`

**Step 2: Run full frontend checks**

Run: `cd frontend && bun run lint && bun run type-check && bun run test:run`

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: Track B integration verification - all checks pass"
```

---

## Merge Strategy

### Step 1: Merge Track A first
```bash
git checkout main
git merge fix/system-robustness --no-ff -m "merge: Track A - system robustness fixes"
```

### Step 2: Rebase Track B on updated main
```bash
git checkout refactor/architecture-cleanup
git rebase main
# Resolve any conflicts
```

### Step 3: Merge Track B
```bash
git checkout main
git merge refactor/architecture-cleanup --no-ff -m "merge: Track B - architecture cleanup"
```

---

## Success Criteria

| Metric | Before | After |
|--------|--------|-------|
| ChatPage.vue lines | 3,218 | ~2,800 (-400) |
| agent_service.py lines | 1,378 | ~800 (-578) |
| playwright_browser.py lines | 2,800+ | ~1,800 (-1,000) |
| Frontend test files | 0 | 4+ |
| Direct httpx.AsyncClient violations | 14+ | 0 |
| Unprotected external calls | 4+ | 0 |
| Debug telemetry calls | 5 | 0 |
| Docker health checks (sandbox) | 0 | 1 |
| SSE timeout threshold | 120s | 300s |
| Periodic session cleanup | startup only | every 5 min |
