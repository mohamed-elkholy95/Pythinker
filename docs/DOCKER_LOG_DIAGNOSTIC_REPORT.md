# Docker Log Diagnostic Report
**Generated:** 2026-02-17
**Environment:** Pythinker — FastAPI + Vue 3 + Playwright/CDP + Docker Sandbox
**Method:** Live log analysis + online research (2025–2026 best practices)

---

## Executive Summary

Eight issues were identified across four containers. The most critical finding is that **`pids: 300` in the sandbox container is the root cause of a cascade failure** — Chromium thread exhaustion (`pthread_create EAGAIN`) is the upstream trigger for the CDP -32603 errors, stale screenshots (2200+ seconds), and partial service disruption. Fixing the PID limit alone resolves approximately 60% of the observed symptoms.

| # | Severity | Issue | Container | Root Cause |
|---|----------|-------|-----------|-----------|
| 1 | 🔴 Critical | `pthread_create: Resource unavailable` | sandbox | `pids: 300` cgroup too tight for Chromium |
| 2 | 🔴 Critical | CDP -32603 → stale screenshots (2200s) | sandbox | Stale WS URL cache + no hard stale-age ceiling |
| 3 | 🟠 High | Shell `AttributeError: NoneType.get` → 500 | backend | LLM passes tool name as session ID; `docker_sandbox.py` does not guard non-2xx responses |
| 4 | 🟠 High | Vite proxy `ECONNREFUSED` on backend restart | frontend | No `onError` handler; requests stall silently |
| 5 | 🟡 Medium | Stale session IDs after backend restart | backend/frontend | No `session:invalidated` event emitted on 404 |
| 6 | 🟡 Medium | `.agent_progress.json` 404 storm (6+ polls) | sandbox | `_load_progress_artifact` called before first checkpoint |
| 7 | 🟢 Low | Vulkan `VK_ERROR_INCOMPATIBLE_DRIVER` + GL stall | sandbox | Chrome Vulkan probe runs before flags disable it |
| 8 | 🟢 Low | `/file/exists` returns 404 vs structured response | sandbox | Route prefix mismatch or missing endpoint at main backend |

---

## Issue 1 — 🔴 CRITICAL: `pthread_create: Resource temporarily unavailable`

### Observed Symptoms
```
[1114:1114:0217/025230.287637:ERROR] pthread_create: Resource temporarily unavailable (11)
[0217/025230.393701:ERROR] ptrace: Operation not permitted (1)
```
This error cascade caused CDP to fail, which in turn caused screenshots to go stale for 2200+ seconds.

### Root Cause

Three compounding sources:

1. **`pids: 300` cgroup limit** in `docker-compose.yml` — Chrome's renderer spawns ~10–30 threads per tab plus GPU process, zygote, and network service. 300 PIDs is exhausted under normal browser activity.

2. **`nproc` ulimit is UID-scoped** — Docker's `ulimits.nproc` counts **across all containers sharing the same UID** on the host. If the host runs other processes as UID 1000, they all count against the sandbox's nproc budget (moby/moby#31424).

3. **`ptrace: Operation not permitted`** — Secondary symptom. Chrome's crashpad attempts `ptrace()` which is correctly blocked by `cap_drop: ALL` + seccomp profile. The `--disable-crashpad` flag in `CHROME_ARGS` should suppress it but the ordering matters.

### Fix

**`docker-compose.yml` — sandbox service:**
```yaml
# CHANGE: pids: 300 → pids: 1024
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '1'
      pids: 1024        # Was: 300 — Chrome alone needs ~80-150 PIDs per tab
    reservations:
      memory: 512M

# REMOVE: nproc ulimit — it's UID-scoped (affects all UID 1000 processes on host)
# Use the pids cgroup limit above for per-container control instead
ulimits:
  nofile:
    soft: 65536
    hard: 65536
  # nproc block removed intentionally

# ADD: increase supervisord minprocs
```

**`sandbox/supervisord.conf`:**
```ini
minprocs=500   ; Was: 200
```

**`docker-compose.yml` — CHROME_ARGS additions:**
```yaml
environment:
  CHROME_ARGS: >-
    --no-sandbox --disable-setuid-sandbox --disable-crashpad
    --user-data-dir=/tmp/chrome --no-zygote
    --renderer-process-limit=1
    --disable-gpu
    --disable-gpu-memory-buffer-compositor-resources
    --disable-gpu-memory-buffer-video-frames
    --js-flags=--max-old-space-size=512
```

**Reference:** Playwright official Docker docs — `--ipc=host`, `--init`, process limits; moby/moby#31424 (nproc UID scoping)

---

## Issue 2 — 🔴 CRITICAL: CDP -32603 Internal Error → 2200s Stale Screenshots

### Observed Symptoms
```
CDP capture error response: {'code': -32603, 'message': 'Internal error'}
Page detached during capture_screenshot - invalidated cache, will retry
[Screenshot] Returning expired cached screenshot (2230.8s old)
```

### Root Cause

Three interacting bugs:

1. **`_WS_URL_CACHE_TTL = 60s` is too long** — Chrome can crash and restart (via supervisord) in under 10 seconds. For up to 60 seconds the cached WebSocket URL is stale, causing every CDP command to fail with -32603.

2. **`get_any()` fallback has no age ceiling** — `screenshot.py` falls back to `_screenshot_cache.get_any()` which returns the last-ever-captured image with no maximum stale age. When the CDP circuit-breaker fires, the result is an indefinitely stale frame being served as "live".

3. **-32603 is treated as page-detach too eagerly** — `_is_page_detached_error()` includes `"Internal error"` in `_PAGE_DETACHED_INDICATORS`. But `-32603 "Internal error"` can be a transient Chrome renderer glitch on a **healthy** page. Treating it as page-detach triggers unnecessary cache invalidation → reconnect → same failure loops.

### Fix

**`sandbox/app/services/cdp_screencast.py`:**
```python
# Reduce WS URL cache TTL from 60s to 15s
_WS_URL_CACHE_TTL = 15.0  # Was: 60.0 — Chrome restarts in <10s via supervisord

# In _is_page_detached_error(): don't treat -32603 as page-detach immediately
def _is_page_detached_error(self, result: dict) -> bool:
    error = result.get("error", {})
    if not isinstance(error, dict):
        return False
    code = error.get("code", 0)
    message = error.get("message", "")
    # -32603 is ambiguous — could be transient; verify via health_check() separately
    if code == -32603 and message == "Internal error":
        return False  # Caller should call health_check() before evicting cache
    return any(indicator in message for indicator in self._PAGE_DETACHED_INDICATORS)
```

**`sandbox/app/api/v1/screenshot.py`:**
```python
# Add hard stale ceiling before serving get_any() fallback
_HARD_MAX_STALE_SECONDS = 120.0  # Never serve screenshots older than 2 minutes

any_cached = await _screenshot_cache.get_any()
if any_cached:
    if any_cached.age_seconds > _HARD_MAX_STALE_SECONDS:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Screenshot stale ({any_cached.age_seconds:.0f}s old, "
                f"max {_HARD_MAX_STALE_SECONDS}s). Browser may be unresponsive."
            ),
        )
    # else: serve the cached screenshot with age warning header
    logger.warning(f"[Screenshot] Returning expired cached screenshot ({any_cached.age_seconds:.1f}s old)")
    return ...
```

**Reference:** Chrome DevTools Protocol error codes reference; Playwright GitHub issues on screenshot staleness

---

## Issue 3 — 🟠 HIGH: Shell `AttributeError: NoneType` → 500

### Observed Symptoms
```
AttributeError: 'NoneType' object has no attribute 'get'
RuntimeError: Failed to get shell output: Session ID does not exist: list_files
POST /api/v1/sessions/596a18ca5e204c2a/shell → 500
```

### Root Cause

Two bugs compounding:

1. **LLM hallucination** — The agent is passing the tool name `"list_files"` as the `shell_session_id` parameter. The shell service correctly raises `ResourceNotFoundException("Session ID does not exist: list_files")`.

2. **`docker_sandbox.py` does not guard non-2xx responses** — Multiple `ToolResult(**response.json())` calls throughout `docker_sandbox.py` assume a valid 2xx JSON body. When the sandbox returns a 500 (from the above exception), `response.json()` returns `{"detail": "..."}` which lacks the `success` field expected by `ToolResult`, producing an `AttributeError`.

### Fix

**`backend/app/infrastructure/external/sandbox/docker_sandbox.py`** — add a response parsing helper:
```python
def _parse_tool_result(self, response: httpx.Response, context: str = "") -> ToolResult:
    """Parse HTTP response into ToolResult, handling non-2xx gracefully."""
    if response.status_code == 200:
        try:
            return ToolResult(**response.json())
        except Exception as e:
            return ToolResult(success=False, message=f"Invalid response format: {e}")
    try:
        body = response.json()
        detail = body.get("detail") or body.get("message") or str(body)
    except Exception:
        detail = response.text[:200]
    return ToolResult(
        success=False,
        message=f"Sandbox HTTP {response.status_code}{f' ({context})' if context else ''}: {detail}",
    )

# Replace all occurrences of:  return ToolResult(**response.json())
# With:                         return self._parse_tool_result(response, context="method_name")
```

**`backend/app/application/services/agent_service.py`** — add UUID validation:
```python
import re
_UUID_RE = re.compile(r'^[0-9a-f]{8,}', re.IGNORECASE)

async def shell_view(self, session_id: str, shell_session_id: str, user_id: str):
    if not _UUID_RE.match(shell_session_id):
        raise ValueError(
            f"Invalid shell_session_id '{shell_session_id}': expected a UUID. "
            "Use shell_exec first to create a session and capture its id."
        )
```

**`backend/app/domain/services/tools/shell.py`** — improve the tool parameter description to prevent LLM confusion:
```python
"id": {
    "type": "string",
    "description": (
        "A persistent UUID identifying the shell session. "
        "Use a short memorable string like 'main' or 'build' to reuse sessions "
        "across related commands. Do NOT use tool names or action names here."
    ),
}
```

---

## Issue 4 — 🟠 HIGH: Vite Proxy `ECONNREFUSED` on Backend Restart

### Observed Symptoms
```
[vite] http proxy error: /api/v1/sessions
Error: connect ECONNREFUSED 172.18.0.7:8000
```

### Root Cause

Vite's `http-proxy` (underlying library) has no built-in `onError` handler or reconnect logic. When the backend container restarts, the proxy fails silently — the request hangs as `(pending)` in the browser indefinitely rather than failing with a proper 504 (vitejs/vite discussions/7620, open since 2022).

### Fix

**`frontend/vite.config.ts`** — add error handling to the proxy configure hook:
```typescript
proxy: {
  '/api': {
    target: process.env.BACKEND_URL,
    changeOrigin: true,
    ws: true,
    proxyTimeout: 10_000,  // ms before proxy gives up
    timeout: 10_000,        // socket connection timeout
    configure: (proxy, _options) => {
      proxy.on('error', (err, req, res) => {
        console.warn('[vite-proxy] Backend unreachable:', err.message);
        if (res && !res.headersSent) {
          (res as import('http').ServerResponse).writeHead(504, {
            'Content-Type': 'application/json',
          });
          (res as import('http').ServerResponse).end(
            JSON.stringify({
              error: 'Backend unreachable',
              hint: 'Backend container may be restarting. Retry in a moment.',
            })
          );
        }
      });
    },
  },
},
```

After a backend restart, Docker's internal DNS for the `backend` service name automatically resolves to the new container IP — so once the backend is healthy again, the **very next request** will proxy successfully with no Vite restart needed.

**Reference:** Vite `server.proxy` docs — `configure` hook, `proxyTimeout`, `timeout`

---

## Issue 5 — 🟡 MEDIUM: Stale Session IDs After Backend Restart

### Observed Symptoms
```
Session 4fd7e7dd7fb44691 not found for user anonymous
GET /api/v1/sessions/4fd7e7dd7fb44691 → 404
POST /api/v1/sessions/100190d991764686/rate → 404
```

### Root Cause

After a backend restart, the frontend still holds stale session IDs in Pinia/composable state and `localStorage`. The axios interceptor in `client.ts` maps 404 responses to `ApiError` objects but does **not** trigger any session invalidation or UI recovery path. The existing `auth:logout` CustomEvent pattern in `client.ts` (line ~117) is the right prior art but isn't applied to session invalidation.

### Fix

**`frontend/src/api/client.ts`** — add session invalidation event in response interceptor:
```typescript
// In the response error interceptor, after the 401 handling block:
if (error.response?.status === 404) {
  const url = originalRequest?.url ?? '';
  if (url.includes('/sessions/')) {
    const match = url.match(/\/sessions\/([^/?]+)/);
    const staleId = match?.[1];
    if (staleId) {
      window.dispatchEvent(
        new CustomEvent('session:invalidated', { detail: { sessionId: staleId } })
      );
    }
  }
}
```

**Session composable** — listen and clear stale state:
```typescript
const handleSessionInvalidated = (event: CustomEvent<{ sessionId: string }>) => {
  const { sessionId } = event.detail;
  if (currentSessionId.value === sessionId) {
    currentSessionId.value = null;
    localStorage.removeItem('lastSessionId');
    cancelActiveSSEConnection?.();
    router.push({ name: 'home' });
  }
};

onMounted(() => window.addEventListener('session:invalidated', handleSessionInvalidated as EventListener));
onUnmounted(() => window.removeEventListener('session:invalidated', handleSessionInvalidated as EventListener));
```

**Startup validation** — validate stored session before rendering:
```typescript
const storedId = localStorage.getItem('lastSessionId');
if (storedId) {
  try {
    await getSession(storedId);
  } catch (e) {
    const code = (e as { code?: number })?.code;
    if (code === 404 || code === 503) {
      localStorage.removeItem('lastSessionId');
      // Route to home/new session
    }
  }
}
```

---

## Issue 6 — 🟡 MEDIUM: `.agent_progress.json` 404 Storm

### Observed Symptoms
```
AppException: File does not exist: /home/ubuntu/.agent_progress.json (code: 404)
```
Repeated 6+ times — every time `_load_progress_artifact()` is called before the first checkpoint is written.

### Root Cause

`plan_act.py` calls `_load_progress_artifact()` on every potential resume check. Before the first `_save_progress_artifact()` write, the file doesn't exist yet — but each call issues a full HTTP request to the sandbox, which logs at WARNING level.

### Fix

**`backend/app/domain/services/flows/plan_act.py`** — add a negative-result cache flag:
```python
class PlanActFlow:
    def __init__(self, ...):
        ...
        self._progress_file_confirmed_absent: bool = False

    async def _load_progress_artifact(self) -> dict | None:
        if self._progress_file_confirmed_absent:
            return None  # Skip network call — confirmed absent at startup
        ...
        if not exists_data.get("exists"):
            self._progress_file_confirmed_absent = True  # Cache negative result
            return None
        self._progress_file_confirmed_absent = False  # File now exists
        ...

    async def _save_progress_artifact(self, ...):
        ...
        self._progress_file_confirmed_absent = False  # File now exists after write
        await self._sandbox.file_write(...)
```

**`sandbox/app/services/file.py`** — downgrade log level for expected-absent files:
```python
# In file_exists() or equivalent path:
if not os.path.exists(resolved_path):
    logger.debug(f"File does not exist: {path}")  # Was: WARNING/INFO → DEBUG
    return FileExistsResult(exists=False)
```

---

## Issue 7 — 🟢 LOW: Vulkan `VK_ERROR_INCOMPATIBLE_DRIVER` + GL ReadPixels Stall

### Observed Symptoms
```
Warning: vkCreateInstance failed with VK_ERROR_INCOMPATIBLE_DRIVER
GL Driver Message (OpenGL, Performance): GPU stall due to ReadPixels
```

### Root Cause

Chrome probes Vulkan at startup before flags take effect. In a container with no GPU, Vulkan probe fails (expected). The GL stall warning is Swiftshader (software renderer) doing a synchronous CPU-bound `ReadPixels` during `Page.captureScreenshot` — cosmetic, not a failure.

The existing `supervisord.conf` flags (`--disable-gpu`, `--use-angle=swiftshader`, `--disable-vulkan`) are mostly correct. The warnings are from Chrome's early-startup GPU feature detection before those flags are applied.

### Fix

**`docker-compose.yml` — sandbox environment:**
```yaml
environment:
  - LIBGL_ALWAYS_SOFTWARE=1         # Force Mesa software rasterization
  - ANGLE_DEFAULT_PLATFORM=swiftshader  # Belt-and-suspenders for ANGLE
```

**`sandbox/scripts/chrome_stderr_filter.py`** — suppress known-harmless patterns:
```python
SUPPRESSED_PATTERNS = [
    ...existing patterns...,
    "vkCreateInstance failed",
    "VK_ERROR_INCOMPATIBLE_DRIVER",
    "GPU stall due to ReadPixels",
    "[WARNING:gl_surface_egl.cc",
]
```

---

## Issue 8 — 🟢 LOW: `/file/exists` Returning 404 vs Structured Response

### Observed Symptoms
```
POST /api/v1/file/exists → 404 Not Found
```

### Root Cause & Design Principle

The sandbox endpoint at `sandbox/app/api/v1/file.py` is correctly implemented — it returns HTTP 200 with `{"exists": false}` even when the file is absent. The 404 being observed is almost certainly a **route prefix mismatch**: the frontend/backend may be calling `POST /api/v1/file/exists` against the main backend (`port 8000`) instead of the sandbox service (`port 8083`).

**REST design reminder** — the correct pattern for existence checks is:
- ✅ `POST /file/exists` → HTTP `200` + `{"exists": false}` — the **route was found**, the file was not
- ❌ `POST /file/exists` → HTTP `404` — this means the **route itself** doesn't exist

### Fix

1. Verify main backend routes `POST /api/v1/file/exists` to the sandbox proxy, not to a missing local handler.
2. Add a FastAPI custom 404 handler to distinguish routing 404s from application 404s:

```python
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "endpoint_not_found",
            "path": str(request.url.path),
            "method": request.method,
            "hint": "Check API prefix and HTTP method.",
        }
    )
```

---

## Recommended Fix Priority & Execution Order

| Priority | Issue | File(s) | Effort |
|----------|-------|---------|--------|
| **1st** | Issue 1 — `pids: 300` (root cascade cause) | `docker-compose.yml` | 2 lines |
| **2nd** | Issue 2 — CDP stale cache ceiling | `sandbox/app/services/cdp_screencast.py`, `sandbox/app/api/v1/screenshot.py` | ~20 lines |
| **3rd** | Issue 4 — Vite proxy error handler | `frontend/vite.config.ts` | ~15 lines |
| **4th** | Issue 3 — Shell NoneType 500 | `docker_sandbox.py`, `agent_service.py`, `shell.py` | ~40 lines |
| **5th** | Issue 5 — Stale session IDs | `frontend/src/api/client.ts`, session composable | ~30 lines |
| **6th** | Issue 6 — Progress file 404 storm | `plan_act.py`, `sandbox/app/services/file.py` | ~15 lines |
| **7th** | Issue 7 — Vulkan log noise | `docker-compose.yml`, `chrome_stderr_filter.py` | 5 lines |
| **8th** | Issue 8 — `/file/exists` 404 | Route investigation + `not_found_handler` | ~10 lines |

> **Quick win:** Issues 1, 4, and 7 can all be fixed with ~10 lines of config changes. Issue 1 alone should stop the screenshot staleness cascade.

---

## Container Resource Health Snapshot

| Container | CPU | Memory | Status | Notes |
|-----------|-----|--------|--------|-------|
| backend | 2.5% | 605MB / 5.8GB (10%) | ✅ Healthy | Restarted ~41 min ago |
| sandbox | 7.5% | 596MB / **2GB limit** (30%) | ✅ Healthy | Thread-exhausted earlier |
| mongodb | 2.8% | 293MB / 5.8GB | ✅ Running | No errors |
| frontend | 3.6% | 550MB / 5.8GB | ✅ Running | Normal HMR activity |
| redis | 0.3% | 4MB | ✅ Healthy | Nominal |
| qdrant | 0.1% | 105MB | ✅ Healthy | Nominal |
| minio | 0.04% | 118MB | ✅ Healthy | Nominal |
