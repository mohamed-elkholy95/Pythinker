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
import os
import signal
import time
import xmlrpc.client

import httpx

logger = logging.getLogger(__name__)

# Supervisord group-qualified process name.
# Processes inside a [group:services] block require the "services:" prefix
# for XML-RPC startProcess/stopProcess calls.
CHROME_PROCESS_NAME = "services:chrome_cdp_only"


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

        If Chrome is already running (e.g., autostart was changed back to true
        or Chrome was started manually), transition to RUNNING so the idle
        checker can manage it.
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
        """Stop Chrome via supervisord RPC, then reap zombie processes."""
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
            # Reap any zombie (defunct) child processes left by Chrome.
            # Without this, zombie PIDs accumulate and eventually hit the
            # container PID limit, causing pthread_create EAGAIN errors.
            await asyncio.to_thread(self._reap_zombies)

    @staticmethod
    def _reap_zombies() -> int:
        """Reap zombie child processes via waitpid(WNOHANG).

        Returns the number of zombies reaped.  Safe to call even when no
        children exist — os.waitpid raises ChildProcessError which we catch.
        """
        reaped = 0
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                reaped += 1
            except ChildProcessError:
                break
        if reaped:
            logger.info("Reaped %d zombie process(es)", reaped)
        return reaped

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
        """Check if Chrome's CDP port is serving /json/version.

        Uses a lightweight TCP-level check via asyncio.open_connection
        followed by a quick HTTP GET, avoiding the overhead of creating
        a full httpx.AsyncClient on every poll.
        """
        try:
            # Fast TCP check first
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self._cdp_port),
                timeout=1.0,
            )
            writer.close()
            await writer.wait_closed()
        except Exception:
            return False

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

        Chrome's ``/json`` lists all targets.  We consider connections active if
        any page target exists with a URL other than ``about:blank`` or has a
        ``devtoolsFrontendUrl`` (indicating an attached debugger).

        Conservative: returns True on errors (safe default — don't stop Chrome
        if we can't determine status).
        """
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"http://127.0.0.1:{self._cdp_port}/json")
                if resp.status_code != 200:
                    return True  # Can't determine — assume active
                targets = resp.json()

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
        """Background loop that stops Chrome after idle timeout.

        Also reaps zombie processes periodically to prevent PID exhaustion.
        """
        while True:
            try:
                await asyncio.sleep(self._idle_check_interval)

                # Reap zombies on every tick regardless of Chrome state.
                # The xdotool window-pinning loop and Chrome crash handlers
                # can leave defunct processes even while Chrome is running.
                await asyncio.to_thread(self._reap_zombies)

                if self._state != ChromeState.RUNNING:
                    continue

                idle_seconds = time.monotonic() - self._last_touch
                if idle_seconds < self._idle_timeout:
                    continue

                # Check for active CDP connections before stopping
                if await self._has_active_cdp_connections():
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
    global _instance  # noqa: PLW0603
    _instance = ChromeLifecycleManager(
        supervisor_rpc=supervisor_rpc,
        idle_timeout=idle_timeout,
        ready_timeout=ready_timeout,
        idle_check_interval=idle_check_interval,
        cdp_port=cdp_port,
    )
    return _instance
