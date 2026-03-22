# On-Demand Chrome Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate 100% of idle Chrome CPU usage by starting Chrome on-demand when browser operations are requested and stopping it after an idle timeout.

**Architecture:** A `ChromeLifecycleManager` singleton in the sandbox API manages Chrome via supervisord XML-RPC. The backend calls `POST /api/v1/browser/ensure` before browser operations. A background idle checker stops Chrome after 60s of inactivity with no active CDP connections. The display stack (Xvfb/Openbox/D-Bus) stays always-on (near-zero idle CPU).

**Tech Stack:** Python 3.12, FastAPI, supervisord XML-RPC, asyncio, pydantic-settings

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `sandbox/app/services/chrome_lifecycle.py` | Chrome lifecycle manager (start/stop/idle detection) |
| Create | `sandbox/app/api/v1/browser.py` | Browser ensure/status API endpoints |
| Modify | `sandbox/app/api/router.py` | Register browser router |
| Modify | `sandbox/app/main.py` | Add lifespan for idle checker, update health endpoint |
| Modify | `sandbox/app/core/config.py` | Add Chrome on-demand settings |
| Modify | `sandbox/supervisord.conf` | Set `autostart=false` for `chrome_cdp_only` |
| Modify | `backend/app/infrastructure/external/sandbox/docker_sandbox.py` | Call ensure endpoint before browser operations |
| Modify | `backend/app/core/sandbox_manager.py` | Health check tolerates intentionally-stopped Chrome |
| Modify | `backend/app/core/config_sandbox.py` | Add `chrome_on_demand` config flag |
| Create | `tests/sandbox/test_chrome_lifecycle.py` | Unit tests for lifecycle manager |

---

### Task 1: Add Chrome On-Demand Configuration (Sandbox Side)

**Files:**
- Modify: `sandbox/app/core/config.py`

- [ ] **Step 1: Add Chrome on-demand settings to sandbox Settings**

Add these fields to the `Settings` class in `sandbox/app/core/config.py`:

```python
# Chrome on-demand lifecycle (reduces idle CPU to zero)
CHROME_ON_DEMAND: bool = True  # Enable on-demand Chrome lifecycle
CHROME_IDLE_TIMEOUT: int = 60  # Seconds of inactivity before stopping Chrome
CHROME_READY_TIMEOUT: int = 30  # Max seconds to wait for Chrome startup
CHROME_IDLE_CHECK_INTERVAL: int = 15  # Seconds between idle checks
CHROME_CDP_PORT: int = 8222  # Chrome's local CDP port (before socat)
```

- [ ] **Step 2: Verify settings load correctly**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python3 -c "from app.core.config import settings; print(settings.CHROME_ON_DEMAND, settings.CHROME_IDLE_TIMEOUT)"`
Expected: `True 60`

- [ ] **Step 3: Commit**

```bash
git add sandbox/app/core/config.py
git commit -m "feat(sandbox): add Chrome on-demand lifecycle configuration"
```

---

### Task 2: Create ChromeLifecycleManager

**Files:**
- Create: `sandbox/app/services/chrome_lifecycle.py`

- [ ] **Step 1: Create the ChromeLifecycleManager module**

```python
"""On-demand Chrome lifecycle management.

Starts Chrome via supervisord XML-RPC on first browser request, stops it after
an idle timeout with no active CDP connections.  Eliminates 100% of idle Chrome
CPU usage while keeping startup latency to ~2-5 seconds.

The display stack (Xvfb, Openbox, D-Bus) stays always-on because it has
near-zero idle CPU and is needed instantly when Chrome starts.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
import xmlrpc.client
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CHROME_PROCESS_NAME = "chrome_cdp_only"


class ChromeState(enum.StrEnum):
    """Chrome process lifecycle states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class ChromeLifecycleManager:
    """Manages Chrome lifecycle via supervisord XML-RPC.

    Thread-safe singleton — use ``get_chrome_lifecycle()`` to obtain the instance.

    Lifecycle:
        STOPPED → (ensure_running) → STARTING → RUNNING
        RUNNING → (idle timeout) → STOPPING → STOPPED

    Idle detection:
        Every ``idle_check_interval`` seconds, checks whether:
        1. Chrome has been idle longer than ``idle_timeout``
        2. No active CDP debugger connections exist (via /json endpoint)
        If both conditions are met, Chrome is stopped.
    """

    def __init__(
        self,
        *,
        supervisor_rpc: xmlrpc.client.ServerProxy,
        idle_timeout: int = 60,
        ready_timeout: int = 30,
        idle_check_interval: int = 15,
        cdp_port: int = 8222,
    ) -> None:
        self._rpc = supervisor_rpc
        self._idle_timeout = idle_timeout
        self._ready_timeout = ready_timeout
        self._idle_check_interval = idle_check_interval
        self._cdp_port = cdp_port

        self._state = ChromeState.STOPPED
        self._last_touch: float = 0.0
        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task | None = None
        self._startup_count: int = 0
        self._stop_count: int = 0

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def state(self) -> ChromeState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == ChromeState.RUNNING

    @property
    def stats(self) -> dict:
        return {
            "state": self._state.value,
            "startup_count": self._startup_count,
            "stop_count": self._stop_count,
            "idle_seconds": round(time.monotonic() - self._last_touch, 1)
            if self._last_touch
            else None,
            "idle_timeout": self._idle_timeout,
        }

    def touch(self) -> None:
        """Reset the idle timer.  Called on every ``ensure_running()``."""
        self._last_touch = time.monotonic()

    async def ensure_running(self) -> dict:
        """Start Chrome if stopped, return when CDP is ready.

        Returns:
            dict with keys: cold_start (bool), startup_ms (float | None), state (str)
        """
        self.touch()

        if self._state == ChromeState.RUNNING:
            # Fast path — Chrome is already up
            if await self._is_cdp_responsive():
                return {"cold_start": False, "startup_ms": None, "state": "running"}
            # Chrome process exists but CDP not responding — restart
            logger.warning("Chrome marked RUNNING but CDP unresponsive, restarting")
            await self._stop_chrome()

        async with self._lock:
            # Double-check after acquiring lock
            if self._state == ChromeState.RUNNING:
                return {"cold_start": False, "startup_ms": None, "state": "running"}

            start = time.monotonic()
            self._state = ChromeState.STARTING
            try:
                await self._start_chrome()
                await self._wait_for_cdp()
                self._state = ChromeState.RUNNING
                self._startup_count += 1
                elapsed_ms = round((time.monotonic() - start) * 1000, 1)
                logger.info(
                    "Chrome started on-demand in %.1fms (startup #%d)",
                    elapsed_ms,
                    self._startup_count,
                )
                self.touch()
                return {
                    "cold_start": True,
                    "startup_ms": elapsed_ms,
                    "state": "running",
                }
            except Exception:
                self._state = ChromeState.STOPPED
                raise

    async def stop(self) -> None:
        """Stop Chrome gracefully."""
        if self._state in (ChromeState.STOPPED, ChromeState.STOPPING):
            return
        async with self._lock:
            if self._state in (ChromeState.STOPPED, ChromeState.STOPPING):
                return
            await self._stop_chrome()

    async def start_idle_checker(self) -> None:
        """Start the background idle-detection loop."""
        if self._idle_task is not None:
            return
        self._idle_task = asyncio.create_task(
            self._idle_check_loop(), name="chrome-idle-checker"
        )

    async def stop_idle_checker(self) -> None:
        """Cancel the background idle-detection loop."""
        if self._idle_task is not None:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
            self._idle_task = None

    async def sync_state_from_supervisor(self) -> None:
        """Read actual Chrome process state from supervisord on startup.

        If Chrome is already running (e.g., ``autostart=true`` or manual start),
        transition to RUNNING so the idle checker can manage it.
        """
        try:
            info = await asyncio.to_thread(
                self._rpc.supervisor.getProcessInfo, CHROME_PROCESS_NAME
            )
            supervisor_state = info.get("statename", "")
            if supervisor_state == "RUNNING":
                self._state = ChromeState.RUNNING
                self.touch()
                logger.info(
                    "Chrome already running in supervisord — synced state to RUNNING"
                )
            else:
                self._state = ChromeState.STOPPED
                logger.info(
                    "Chrome not running in supervisord (state=%s) — synced to STOPPED",
                    supervisor_state,
                )
        except Exception as e:
            logger.warning("Failed to sync Chrome state from supervisord: %s", e)
            self._state = ChromeState.STOPPED

    # ── Private helpers ─────────────────────────────────────────────────

    async def _start_chrome(self) -> None:
        """Start Chrome via supervisord RPC."""
        try:
            await asyncio.to_thread(
                self._rpc.supervisor.startProcess, CHROME_PROCESS_NAME
            )
        except xmlrpc.client.Fault as e:
            if "ALREADY_STARTED" in str(e):
                logger.debug("Chrome already started (race condition, OK)")
                return
            raise RuntimeError(f"Failed to start Chrome: {e}") from e

    async def _stop_chrome(self) -> None:
        """Stop Chrome via supervisord RPC."""
        self._state = ChromeState.STOPPING
        try:
            await asyncio.to_thread(
                self._rpc.supervisor.stopProcess, CHROME_PROCESS_NAME
            )
            self._stop_count += 1
            logger.info("Chrome stopped (stop #%d)", self._stop_count)
        except xmlrpc.client.Fault as e:
            if "NOT_RUNNING" in str(e):
                logger.debug("Chrome already stopped")
            else:
                logger.error("Failed to stop Chrome: %s", e)
        finally:
            self._state = ChromeState.STOPPED

    async def _wait_for_cdp(self) -> None:
        """Poll Chrome's CDP endpoint until responsive or timeout."""
        deadline = time.monotonic() + self._ready_timeout
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            if await self._is_cdp_responsive():
                logger.debug("CDP responsive after %d attempts", attempt)
                return
            await asyncio.sleep(0.3)
        raise TimeoutError(
            f"Chrome CDP not responsive after {self._ready_timeout}s "
            f"({attempt} attempts)"
        )

    async def _is_cdp_responsive(self) -> bool:
        """Check if Chrome's CDP port is serving /json/version."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"http://127.0.0.1:{self._cdp_port}/json/version"
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def _has_active_cdp_connections(self) -> bool:
        """Check if any CDP debugger sessions are attached.

        Chrome exposes ``/json`` which lists all targets.  Targets with a
        non-empty ``webSocketDebuggerUrl`` that are being debugged will have
        their ``attached`` field set to true (Chrome 128+).  For older versions,
        we check if a ``devtoolsFrontendUrl`` is present.

        As a conservative fallback, any page target counts as "potentially
        active" — we only declare no connections when the target list is empty
        or contains only the default ``about:blank`` with no debugger attached.
        """
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"http://127.0.0.1:{self._cdp_port}/json")
                if resp.status_code != 200:
                    return True  # Can't determine — assume active
                targets = resp.json()

            # No targets at all → no connections
            if not targets:
                return False

            # Filter to page targets only (ignore service workers, etc.)
            page_targets = [t for t in targets if t.get("type") == "page"]
            if not page_targets:
                return False

            # If all pages are about:blank with no frontend URL → no active sessions
            for target in page_targets:
                url = target.get("url", "")
                has_frontend = bool(target.get("devtoolsFrontendUrl"))
                if url != "about:blank" or has_frontend:
                    return True

            return False

        except Exception:
            return True  # Can't determine — assume active (safe default)

    async def _idle_check_loop(self) -> None:
        """Background loop that stops Chrome after idle timeout."""
        while True:
            try:
                await asyncio.sleep(self._idle_check_interval)

                if self._state != ChromeState.RUNNING:
                    continue

                idle_seconds = time.monotonic() - self._last_touch
                if idle_seconds < self._idle_timeout:
                    continue

                # Check for active CDP connections before stopping
                if await self._has_active_cdp_connections():
                    # Extend the timeout — something is still connected
                    logger.debug(
                        "Chrome idle %.0fs but has active CDP connections, extending",
                        idle_seconds,
                    )
                    self.touch()
                    continue

                logger.info(
                    "Chrome idle for %.0fs with no CDP connections, stopping",
                    idle_seconds,
                )
                await self.stop()

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in Chrome idle checker")


# ── Singleton ───────────────────────────────────────────────────────────

_instance: ChromeLifecycleManager | None = None


def get_chrome_lifecycle() -> ChromeLifecycleManager | None:
    """Return the global ChromeLifecycleManager, or None if not initialized."""
    return _instance


def init_chrome_lifecycle(
    supervisor_rpc: xmlrpc.client.ServerProxy,
    *,
    idle_timeout: int = 60,
    ready_timeout: int = 30,
    idle_check_interval: int = 15,
    cdp_port: int = 8222,
) -> ChromeLifecycleManager:
    """Create and register the global ChromeLifecycleManager."""
    global _instance
    _instance = ChromeLifecycleManager(
        supervisor_rpc=supervisor_rpc,
        idle_timeout=idle_timeout,
        ready_timeout=ready_timeout,
        idle_check_interval=idle_check_interval,
        cdp_port=cdp_port,
    )
    return _instance
```

- [ ] **Step 2: Verify module imports correctly**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python3 -c "from app.services.chrome_lifecycle import ChromeLifecycleManager, ChromeState; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sandbox/app/services/chrome_lifecycle.py
git commit -m "feat(sandbox): add ChromeLifecycleManager for on-demand browser lifecycle"
```

---

### Task 3: Create Browser API Endpoints

**Files:**
- Create: `sandbox/app/api/v1/browser.py`
- Modify: `sandbox/app/api/router.py`

- [ ] **Step 1: Create browser API router**

Create `sandbox/app/api/v1/browser.py`:

```python
"""Browser lifecycle API endpoints.

Provides ``POST /api/v1/browser/ensure`` for the backend to request Chrome
startup, and ``GET /api/v1/browser/status`` for observability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.response import Response
from app.services.chrome_lifecycle import get_chrome_lifecycle

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ensure", response_model=Response)
async def ensure_browser():
    """Ensure Chrome is running and CDP is ready.

    Idempotent — if Chrome is already running, returns immediately (~1ms).
    If Chrome is stopped, starts it and waits for CDP readiness (~2-5s).

    Called by the backend before every browser operation.
    """
    lifecycle = get_chrome_lifecycle()
    if lifecycle is None:
        # On-demand disabled — Chrome is always-on
        return Response(
            success=True,
            message="Chrome on-demand disabled (always-on mode)",
            data={"cold_start": False, "startup_ms": None, "state": "always_on"},
        )

    try:
        result = await lifecycle.ensure_running()
        msg = (
            f"Chrome started in {result['startup_ms']}ms"
            if result["cold_start"]
            else "Chrome already running"
        )
        return Response(success=True, message=msg, data=result)
    except TimeoutError as e:
        logger.error("Chrome startup timeout: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Chrome startup failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Chrome startup failed: {e}")


@router.get("/status", response_model=Response)
async def browser_status():
    """Get Chrome lifecycle status and stats."""
    lifecycle = get_chrome_lifecycle()
    if lifecycle is None:
        return Response(
            success=True,
            message="Chrome on-demand disabled",
            data={"mode": "always_on"},
        )

    return Response(
        success=True,
        message=f"Chrome is {lifecycle.state.value}",
        data=lifecycle.stats,
    )
```

- [ ] **Step 2: Register browser router in api/router.py**

Add the import and include_router to `sandbox/app/api/router.py`:

```python
from app.api.v1 import (
    shell,
    supervisor,
    file,
    workspace,
    git,
    code_dev,
    test_runner,
    export,
    screenshot,
    screencast,
    input,
    navigation,
    browser,  # Add this
)

# ... existing routers ...
api_router.include_router(browser.router, prefix="/browser", tags=["browser"])
```

- [ ] **Step 3: Commit**

```bash
git add sandbox/app/api/v1/browser.py sandbox/app/api/router.py
git commit -m "feat(sandbox): add browser ensure/status API endpoints"
```

---

### Task 4: Wire Lifecycle Into Sandbox Lifespan and Health Check

**Files:**
- Modify: `sandbox/app/main.py`

- [ ] **Step 1: Add FastAPI lifespan to initialize ChromeLifecycleManager**

Replace the module-level app initialization in `sandbox/app/main.py` with a lifespan context manager. The lifespan should:

1. Check `settings.CHROME_ON_DEMAND`
2. If enabled, create a supervisord XML-RPC connection (reusing the existing `SupervisorService` pattern from `sandbox/app/services/supervisor.py`)
3. Call `init_chrome_lifecycle()` with settings
4. Call `sync_state_from_supervisor()` to detect if Chrome is already running
5. Start the idle checker background task
6. On shutdown, stop the idle checker

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize Chrome lifecycle manager."""
    from app.services.chrome_lifecycle import init_chrome_lifecycle, get_chrome_lifecycle

    lifecycle = None
    if settings.CHROME_ON_DEMAND:
        import xmlrpc.client
        from urllib.parse import quote

        username = quote(settings.SUPERVISOR_RPC_USERNAME, safe="")
        password = quote(settings.SUPERVISOR_RPC_PASSWORD, safe="")

        # Reuse the same Unix socket transport as SupervisorService
        from app.services.supervisor import UnixStreamTransport

        rpc = xmlrpc.client.ServerProxy(
            f"http://{username}:{password}@localhost",
            transport=UnixStreamTransport("/tmp/supervisor.sock"),
        )

        lifecycle = init_chrome_lifecycle(
            rpc,
            idle_timeout=settings.CHROME_IDLE_TIMEOUT,
            ready_timeout=settings.CHROME_READY_TIMEOUT,
            idle_check_interval=settings.CHROME_IDLE_CHECK_INTERVAL,
            cdp_port=settings.CHROME_CDP_PORT,
        )
        await lifecycle.sync_state_from_supervisor()
        await lifecycle.start_idle_checker()
        logger.info(
            "Chrome on-demand lifecycle enabled (idle_timeout=%ds)",
            settings.CHROME_IDLE_TIMEOUT,
        )
    else:
        logger.info("Chrome on-demand disabled — Chrome is always-on")

    yield

    if lifecycle is not None:
        await lifecycle.stop_idle_checker()
        logger.info("Chrome lifecycle manager shut down")
```

Pass `lifespan=lifespan` to the `FastAPI()` constructor.

- [ ] **Step 2: Update health check to be Chrome-on-demand-aware**

Modify the `/health` endpoint. When `CHROME_ON_DEMAND` is enabled and Chrome is intentionally stopped, the CDP check should report `"on_demand_stopped"` instead of `False`, and overall health should remain `"healthy"`:

```python
@app.get("/health")
async def health_check(response: Response):
    from app.services.chrome_lifecycle import get_chrome_lifecycle

    async def _check_port(host: str, port: int) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    lifecycle = get_chrome_lifecycle()

    checks: dict = {
        "api": True,
        "framework": await _check_port("127.0.0.1", 8082),
    }

    if lifecycle is not None:
        # On-demand mode: Chrome being stopped is healthy
        if lifecycle.is_running:
            checks["cdp"] = await _check_port("127.0.0.1", 9222)
        else:
            checks["cdp"] = "on_demand_stopped"
    else:
        # Always-on mode: CDP must be responsive
        checks["cdp"] = await _check_port("127.0.0.1", 9222)

    # Determine health — "on_demand_stopped" is healthy, only False is unhealthy
    unhealthy = any(v is False for v in checks.values())
    if unhealthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "service": "sandbox", "checks": checks}

    return {"status": "healthy", "service": "sandbox", "checks": checks}
```

- [ ] **Step 3: Commit**

```bash
git add sandbox/app/main.py
git commit -m "feat(sandbox): wire Chrome lifecycle into lifespan and health check"
```

---

### Task 5: Set Chrome autostart=false in supervisord

**Files:**
- Modify: `sandbox/supervisord.conf`

- [ ] **Step 1: Change chrome_cdp_only autostart to false**

In `sandbox/supervisord.conf`, change the `chrome_cdp_only` program:

```ini
[program:chrome_cdp_only]
command=/bin/bash /app/scripts/run_chrome.sh
autostart=false
```

Change `autostart=true` → `autostart=false`. Keep all other settings (autorestart, stopasgroup, killasgroup, etc.) unchanged.

- [ ] **Step 2: Commit**

```bash
git add sandbox/supervisord.conf
git commit -m "feat(sandbox): disable Chrome autostart for on-demand lifecycle"
```

---

### Task 6: Backend — Call ensure Before Browser Operations

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- Modify: `backend/app/core/config_sandbox.py`

- [ ] **Step 1: Add chrome_on_demand config to backend**

Add to `BrowserSettingsMixin` in `backend/app/core/config_sandbox.py`:

```python
# Chrome on-demand lifecycle (sandbox-side feature)
# When enabled, backend calls /api/v1/browser/ensure before browser operations
chrome_on_demand: bool = True
chrome_ensure_timeout: float = 35.0  # Timeout for ensure call (slightly > CHROME_READY_TIMEOUT)
```

- [ ] **Step 2: Add _ensure_chrome method to DockerSandbox**

In `backend/app/infrastructure/external/sandbox/docker_sandbox.py`, add a method that calls the sandbox's ensure endpoint before browser operations:

```python
async def _ensure_chrome_running(self) -> None:
    """Request the sandbox to ensure Chrome is running (on-demand lifecycle).

    No-op when chrome_on_demand is disabled.  Idempotent — safe to call
    before every browser operation.
    """
    settings = get_settings()
    if not getattr(settings, "chrome_on_demand", False):
        return

    try:
        client = await self.get_client()
        timeout = getattr(settings, "chrome_ensure_timeout", 35.0)
        resp = await client.post(
            f"{self.base_url}/api/v1/browser/ensure",
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "Chrome ensure returned %d: %s",
                resp.status_code,
                resp.text[:200],
            )
        else:
            data = resp.json().get("data", {})
            if data.get("cold_start"):
                logger.info(
                    "Chrome cold-started in %sms for sandbox %s",
                    data.get("startup_ms"),
                    self.id,
                )
    except Exception as e:
        logger.warning("Chrome ensure failed for sandbox %s: %s", self.id, e)
```

- [ ] **Step 3: Call _ensure_chrome_running in get_browser**

In the `get_browser` method (around line 1419), add the ensure call before CDP verification:

```python
async def get_browser(self, block_resources=True, verify_connection=True, clear_session=False, use_pool=True):
    # Ensure Chrome is running (on-demand lifecycle)
    await self._ensure_chrome_running()

    # ... rest of existing get_browser logic ...
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/infrastructure/external/sandbox/docker_sandbox.py backend/app/core/config_sandbox.py
git commit -m "feat(backend): call sandbox browser/ensure before browser operations"
```

---

### Task 7: Backend — Health Check Tolerates Stopped Chrome

**Files:**
- Modify: `backend/app/core/sandbox_manager.py`

- [ ] **Step 1: Update health check to accept on_demand_stopped**

Modify `_check_browser_health` and `health_check` in `sandbox_manager.py` to recognize that Chrome being intentionally stopped is healthy:

In `health_check()` (around line 428), change the browser_responsive handling:

```python
async def health_check(self) -> bool:
    try:
        self.health.last_check = datetime.now(UTC)

        settings = get_settings()
        use_taskgroup = settings.feature_taskgroup_enabled
        chrome_on_demand = getattr(settings, "chrome_on_demand", False)

        api_task = asyncio.create_task(self._check_api_health())
        health_tasks: list[asyncio.Task[Any]] = [api_task]

        if chrome_on_demand:
            # In on-demand mode, check via sandbox health endpoint
            # which reports "on_demand_stopped" for intentionally stopped Chrome
            browser_task = asyncio.create_task(self._check_browser_health_on_demand())
        else:
            browser_task = asyncio.create_task(self._check_browser_health())
        health_tasks.append(browser_task)

        results = await gather_compat(
            *health_tasks,
            return_exceptions=True,
            use_taskgroup=use_taskgroup,
        )

        self.health.api_responsive = results[0] is True
        self.health.browser_responsive = results[1] is True

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                check_names = ["API", "Browser"]
                logger.debug(f"{check_names[i]} health check exception: {result}")

        return self.health.is_healthy

    except Exception as e:
        logger.warning(f"Health check failed for sandbox {self.session_id}: {e}")
        return False
```

Add the new on-demand health check method:

```python
@sandbox_retry
async def _check_browser_health_on_demand(self) -> bool:
    """Check browser health in on-demand mode.

    The sandbox health endpoint returns cdp="on_demand_stopped" when Chrome
    is intentionally stopped.  This is considered healthy.
    """
    response = await self.api_client.get("/health", timeout=2.0)
    if response.status_code != 200:
        return False
    data = response.json()
    checks = data.get("checks", {})
    cdp_status = checks.get("cdp")
    # "on_demand_stopped" or True are both healthy
    return cdp_status is True or cdp_status == "on_demand_stopped"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/sandbox_manager.py
git commit -m "feat(backend): health check tolerates on-demand stopped Chrome"
```

---

### Task 8: Unit Tests for ChromeLifecycleManager

**Files:**
- Create: `tests/sandbox/test_chrome_lifecycle.py`

- [ ] **Step 1: Write unit tests**

```python
"""Tests for on-demand Chrome lifecycle management."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time

import pytest

from app.services.chrome_lifecycle import (
    ChromeLifecycleManager,
    ChromeState,
    init_chrome_lifecycle,
    get_chrome_lifecycle,
)


@pytest.fixture
def mock_rpc():
    """Create a mock supervisord XML-RPC proxy."""
    rpc = MagicMock()
    rpc.supervisor.startProcess = MagicMock(return_value=True)
    rpc.supervisor.stopProcess = MagicMock(return_value=True)
    rpc.supervisor.getProcessInfo = MagicMock(
        return_value={"statename": "STOPPED", "state": 0}
    )
    return rpc


@pytest.fixture
def lifecycle(mock_rpc):
    """Create a ChromeLifecycleManager with mocked dependencies."""
    return ChromeLifecycleManager(
        supervisor_rpc=mock_rpc,
        idle_timeout=5,
        ready_timeout=3,
        idle_check_interval=1,
        cdp_port=8222,
    )


class TestChromeState:
    def test_initial_state_is_stopped(self, lifecycle):
        assert lifecycle.state == ChromeState.STOPPED
        assert not lifecycle.is_running

    def test_stats_when_stopped(self, lifecycle):
        stats = lifecycle.stats
        assert stats["state"] == "stopped"
        assert stats["startup_count"] == 0
        assert stats["stop_count"] == 0


class TestEnsureRunning:
    @pytest.mark.asyncio
    async def test_cold_start(self, lifecycle):
        """Chrome starts when ensure_running is called and it's stopped."""
        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=True
        ):
            result = await lifecycle.ensure_running()
            assert result["cold_start"] is True
            assert result["startup_ms"] is not None
            assert lifecycle.state == ChromeState.RUNNING

    @pytest.mark.asyncio
    async def test_warm_hit(self, lifecycle):
        """Already-running Chrome returns immediately."""
        lifecycle._state = ChromeState.RUNNING
        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=True
        ):
            result = await lifecycle.ensure_running()
            assert result["cold_start"] is False
            assert result["startup_ms"] is None

    @pytest.mark.asyncio
    async def test_timeout_raises(self, lifecycle):
        """Raises TimeoutError if CDP never becomes responsive."""
        lifecycle._ready_timeout = 1  # 1 second timeout
        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=False
        ):
            with pytest.raises(TimeoutError, match="CDP not responsive"):
                await lifecycle.ensure_running()
            assert lifecycle.state == ChromeState.STOPPED

    @pytest.mark.asyncio
    async def test_restart_on_unresponsive_running(self, lifecycle):
        """Restarts Chrome if marked RUNNING but CDP unresponsive."""
        lifecycle._state = ChromeState.RUNNING

        call_count = 0

        async def mock_cdp_responsive():
            nonlocal call_count
            call_count += 1
            # First call: unresponsive (triggers restart)
            # Subsequent calls: responsive (startup succeeds)
            return call_count > 1

        with patch.object(lifecycle, "_is_cdp_responsive", side_effect=mock_cdp_responsive):
            result = await lifecycle.ensure_running()
            assert result["cold_start"] is True


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_running_chrome(self, lifecycle):
        lifecycle._state = ChromeState.RUNNING
        await lifecycle.stop()
        assert lifecycle.state == ChromeState.STOPPED
        assert lifecycle.stats["stop_count"] == 1

    @pytest.mark.asyncio
    async def test_stop_already_stopped_is_noop(self, lifecycle):
        await lifecycle.stop()
        assert lifecycle.stats["stop_count"] == 0


class TestIdleChecker:
    @pytest.mark.asyncio
    async def test_stops_chrome_when_idle(self, lifecycle):
        """Idle checker stops Chrome after timeout with no active connections."""
        lifecycle._state = ChromeState.RUNNING
        lifecycle._last_touch = time.monotonic() - 10  # 10s ago, timeout is 5s
        lifecycle._idle_timeout = 1

        with (
            patch.object(
                lifecycle,
                "_has_active_cdp_connections",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(lifecycle, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            # Run one iteration manually
            await lifecycle.start_idle_checker()
            await asyncio.sleep(1.5)  # Wait for one check cycle
            await lifecycle.stop_idle_checker()
            mock_stop.assert_called()

    @pytest.mark.asyncio
    async def test_extends_when_cdp_active(self, lifecycle):
        """Idle checker extends timeout when CDP connections exist."""
        lifecycle._state = ChromeState.RUNNING
        lifecycle._last_touch = time.monotonic() - 10
        lifecycle._idle_timeout = 1

        with (
            patch.object(
                lifecycle,
                "_has_active_cdp_connections",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(lifecycle, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            await lifecycle.start_idle_checker()
            await asyncio.sleep(1.5)
            await lifecycle.stop_idle_checker()
            mock_stop.assert_not_called()


class TestSyncState:
    @pytest.mark.asyncio
    async def test_syncs_running_state(self, lifecycle, mock_rpc):
        mock_rpc.supervisor.getProcessInfo.return_value = {
            "statename": "RUNNING",
            "state": 20,
        }
        await lifecycle.sync_state_from_supervisor()
        assert lifecycle.state == ChromeState.RUNNING

    @pytest.mark.asyncio
    async def test_syncs_stopped_state(self, lifecycle, mock_rpc):
        mock_rpc.supervisor.getProcessInfo.return_value = {
            "statename": "STOPPED",
            "state": 0,
        }
        await lifecycle.sync_state_from_supervisor()
        assert lifecycle.state == ChromeState.STOPPED


class TestSingleton:
    def test_init_and_get(self, mock_rpc):
        init_chrome_lifecycle(mock_rpc)
        instance = get_chrome_lifecycle()
        assert instance is not None
        assert isinstance(instance, ChromeLifecycleManager)
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python3 -m pytest tests/sandbox/test_chrome_lifecycle.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/sandbox/test_chrome_lifecycle.py
git commit -m "test(sandbox): add unit tests for ChromeLifecycleManager"
```

---

### Task 9: Integration Verification

- [ ] **Step 1: Rebuild sandbox image**

Run: `cd /Users/panda/Desktop/Projects/Pythinker && docker compose -f docker-compose-development.yml build sandbox`

- [ ] **Step 2: Start stack and verify Chrome is NOT running on startup**

Run: `./dev.sh watch`

Then check Chrome status:
```bash
docker exec <sandbox-container> supervisorctl status chrome_cdp_only
```
Expected: `chrome_cdp_only STOPPED`

- [ ] **Step 3: Verify ensure endpoint starts Chrome**

```bash
curl -X POST http://localhost:8083/api/v1/browser/ensure
```
Expected: `{"success": true, "data": {"cold_start": true, "startup_ms": ...}}`

- [ ] **Step 4: Verify health endpoint is healthy with Chrome stopped**

```bash
# Stop Chrome first
docker exec <sandbox-container> supervisorctl stop chrome_cdp_only
# Check health
curl http://localhost:8083/health
```
Expected: `{"status": "healthy", "checks": {"cdp": "on_demand_stopped", ...}}`

- [ ] **Step 5: Verify Chrome stops after idle timeout**

Wait 60+ seconds with no browser operations, then:
```bash
docker exec <sandbox-container> supervisorctl status chrome_cdp_only
```
Expected: `chrome_cdp_only STOPPED`

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Chrome startup too slow (>5s) | `CHROME_READY_TIMEOUT=30` with 300ms poll interval; display stack stays warm |
| Idle checker kills Chrome mid-operation | Checks `/json` for active CDP connections before stopping |
| Supervisor RPC auth mismatch | Reuses `SupervisorService`'s `UnixStreamTransport` and same env vars |
| Backend retry storms on cold start | `chrome_ensure_timeout=35s` is generous; ensure is idempotent |
| Feature breaks existing deployments | `CHROME_ON_DEMAND=true` default but easily disabled with env var |
