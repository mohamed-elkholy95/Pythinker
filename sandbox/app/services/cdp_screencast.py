"""
CDP Screencast Service - Low-latency browser streaming via Chrome DevTools Protocol.

Provides real-time browser view streaming with 10-50ms latency, significantly
faster than traditional screenshot polling (50-200ms).

Features:
- Direct CDP connection to Chrome with automatic page target discovery
- JPEG frame streaming for low bandwidth
- Configurable quality and frame rate
- Persistent connection with smart auto-reconnect on page navigation/crash
- Cache invalidation on stale page targets (handles browser navigation/crash)
- Health checks to detect stale connections
- Exponential backoff for retry attempts

Architecture:
    Frontend → Backend proxy → Sandbox screencast API → CDP Service → Chrome
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Callable, ClassVar

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CDP connection settings (defaults from centralized config)
# ---------------------------------------------------------------------------
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
CDP_ENDPOINT = f"http://{CDP_HOST}:{CDP_PORT}"

# Connection management — read from Settings for env-var configurability
_WS_URL_CACHE_TTL = settings.CDP_WS_URL_CACHE_TTL
_HEALTH_CHECK_TIMEOUT = 2.0  # Quick health check (not worth externalizing)
_CAPTURE_COMMAND_TIMEOUT = settings.CDP_COMMAND_TIMEOUT
_CONNECT_TIMEOUT = settings.CDP_CONNECT_TIMEOUT
_PAGE_REDISCOVERY_DELAY = 0.3  # Brief pause for Chrome to register new page target
_MAX_RETRY_ATTEMPTS = 2  # Initial attempt + 1 retry after page re-discovery
_STREAM_FRAME_TIMEOUT = settings.CDP_STREAM_FRAME_TIMEOUT
_STREAM_HEALTH_CHECK_INTERVAL = settings.CDP_STREAM_HEALTH_CHECK_INTERVAL

# Page recovery thresholds
_PAGE_RECOVERY_FAILURE_THRESHOLD = 5   # Consecutive same-page failures before tab replacement
_CHROME_RESTART_FAILURE_THRESHOLD = 6  # Total failures before Chrome restart
_CHROME_RESTART_COOLDOWN = 30.0        # Minimum seconds between Chrome restarts
_SAME_URL_REDISCOVERY_THRESHOLD = 4    # Times same broken URL rediscovered after cache invalidation


@dataclass
class ScreencastConfig:
    """Configuration for CDP screencast streaming.

    Default dimensions match Playwright's browser viewport (1280x900)
    to ensure consistent rendering across the CDP screencast pipeline.
    """

    format: str = "jpeg"  # jpeg is faster than png
    quality: int = 80  # 80% is good balance of quality/bandwidth
    max_width: int = 1280
    max_height: int = 900  # Match Playwright DEFAULT_VIEWPORT height
    every_nth_frame: int = 1  # Capture every frame


@dataclass
class ScreencastFrame:
    """A single screencast frame from CDP."""

    data: bytes  # Raw image bytes (decoded from base64)
    session_id: int
    timestamp: float
    metadata: dict


class CDPScreencastService:
    """
    Service for streaming browser content via Chrome DevTools Protocol.

    Uses Page.startScreencast for low-latency frame streaming directly
    from Chrome's rendering pipeline.

    Key resilience features:
    - Automatic page target re-discovery when CDP pages become detached
      (e.g., after browser navigation, tab close, or page crash)
    - Cache invalidation ensures stale WebSocket URLs are never reused
    - Retry-once pattern: on detached errors, invalidate + re-discover + retry
    - Persistent connections with auto-reconnect for low-latency repeated captures

    Error Recovery Flow:
        CDP command → "Not attached to active page" error
            → invalidate_cache() (clears stale WS URL)
            → _cleanup_stale_connection() (closes dead WS)
            → sleep(0.3s) (let Chrome register new target)
            → get_ws_debugger_url() (fresh /json lookup)
            → connect to new page target
            → retry command (succeeds)
    """

    # CDP error messages that indicate the page target is stale/detached.
    # When any of these appear in an error response, we invalidate the cached
    # WebSocket URL and re-discover the active page target.
    # NOTE: "Internal error" removed — CDP -32603 is too broad (transient Chrome
    # hiccups). Use _is_internal_error() for code-based detection instead.
    _PAGE_DETACHED_INDICATORS = frozenset({
        "Not attached to an active page",
        "Target closed",
        "Session with given id not found",
    })

    def __init__(self, config: ScreencastConfig | None = None):
        self.config = config or ScreencastConfig()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._streaming = False
        self._frame_callback: Callable[[ScreencastFrame], None] | None = None
        self._msg_counter: int = 0

        # Serialize all CDP command send/receive cycles on the shared WebSocket
        # to prevent "Concurrent call to receive() is not allowed" errors.
        self._command_lock: asyncio.Lock = asyncio.Lock()

        # Serializes recovery actions (tab replacement / Chrome restart) to
        # prevent multiple concurrent coroutines from each triggering escalation.
        self._recovery_lock: asyncio.Lock = asyncio.Lock()

        # Connection caching
        self._cached_ws_url: str | None = None
        self._ws_url_cached_at: float = 0.0
        self._last_successful_capture: float = 0.0

        # Page recovery tracking — detects when the same broken page keeps
        # being re-discovered and escalates from tab replacement to Chrome restart.
        self._failing_page_url: str | None = None
        self._same_page_failure_count: int = 0
        self._total_consecutive_failures: int = 0
        self._last_chrome_restart: float = 0.0

        # Same-URL rediscovery tracking — detects when cache invalidation still
        # returns the same broken URL (Chrome renderer stuck on dead page).
        # Triggers escalation independently of the cache TTL heuristic.
        self._last_invalidated_url: str | None = None
        self._rediscovery_counter: int = 0

        # Tracks whether viewport has been set on the current page target.
        # Reset when the connection changes (cache invalidation, reconnect).
        self._viewport_set: bool = False

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket connection is alive."""
        return (
            self._ws is not None
            and not self._ws.closed
            and self._session is not None
            and not self._session.closed
        )

    # ------------------------------------------------------------------
    # Page target discovery & cache management
    # ------------------------------------------------------------------

    def _is_page_detached_error(self, result: dict) -> bool:
        """Check if a CDP error response indicates the page target is stale/detached.

        These errors occur when Chrome navigates to a new page, the tab is closed,
        or the renderer process crashes. The old page UUID becomes invalid but may
        still be returned by /json briefly.

        CDP -32603 ("Internal error") is treated as a page-detach only when
        the cached WS URL is stale (> TTL). Transient -32603 errors during
        heavy page loads should NOT trigger full page recovery.
        """
        error = result.get("error", {})
        if not isinstance(error, dict):
            return False
        message = error.get("message", "")
        # Direct indicator match (high-confidence page detachment)
        if any(indicator in message for indicator in self._PAGE_DETACHED_INDICATORS):
            return True
        # CDP -32603: only treat as detachment if the WS URL cache is already stale
        error_code = error.get("code")
        if error_code == -32603:
            cache_age = time.monotonic() - self._ws_url_cached_at
            if cache_age > _WS_URL_CACHE_TTL:
                logger.info(
                    "CDP -32603 with stale WS URL (age=%.1fs > TTL=%.1fs) — treating as page detach",
                    cache_age, _WS_URL_CACHE_TTL,
                )
                return True
            logger.debug(
                "CDP -32603 with fresh WS URL (age=%.1fs) — treating as transient error",
                cache_age,
            )
        return False

    def invalidate_cache(self) -> None:
        """Invalidate the cached WebSocket URL to force fresh page discovery.

        Call this when CDP commands fail with page-detached errors so the next
        connection attempt discovers the current active page target via /json.

        Stores the invalidated URL so _get_cached_ws_url() can detect when the
        same broken URL keeps being rediscovered after invalidation.
        """
        if self._cached_ws_url:
            logger.info(
                "Invalidating cached CDP URL (was: ...%s)", self._cached_ws_url[-20:]
            )
            # Remember the URL being invalidated for rediscovery detection
            self._last_invalidated_url = self._cached_ws_url
        self._cached_ws_url = None
        self._ws_url_cached_at = 0.0
        # Reset viewport flag — the new page target will need it set
        self._viewport_set = False

    async def _get_cached_ws_url(self) -> str | None:
        """Get WebSocket URL with caching to avoid repeated /json lookups.

        Tracks same-URL rediscovery: when cache invalidation returns the same
        broken URL, _rediscovery_counter increments. Reaching
        _SAME_URL_REDISCOVERY_THRESHOLD triggers escalation in capture_single_frame()
        even when the cache is fresh (bypasses the TTL-based heuristic).
        """
        now = time.monotonic()
        if self._cached_ws_url and (now - self._ws_url_cached_at) < _WS_URL_CACHE_TTL:
            return self._cached_ws_url

        url = await self.get_ws_debugger_url()
        if url:
            # Detect when cache invalidation keeps returning the same broken URL.
            # This happens when Chrome's renderer is stuck: the broken page target
            # remains registered in /json even after cache invalidation + rediscovery.
            if url == self._last_invalidated_url:
                self._rediscovery_counter += 1
                logger.warning(
                    "Same broken URL rediscovered after cache invalidation "
                    "(count=%d, url=...%s)",
                    self._rediscovery_counter,
                    url[-20:],
                )
            else:
                # New URL — reset rediscovery counter (Chrome registered a new target)
                if self._rediscovery_counter > 0:
                    logger.info(
                        "New URL discovered after %d rediscovery attempt(s) — "
                        "resetting rediscovery counter",
                        self._rediscovery_counter,
                    )
                self._rediscovery_counter = 0

            self._cached_ws_url = url
            self._ws_url_cached_at = now
        return url

    # URLs considered "idle" — not worth streaming over a page with real content.
    _IDLE_PAGE_URLS: ClassVar[frozenset[str]] = frozenset({
        "about:blank",
        "chrome://newtab/",
        "chrome://new-tab-page/",
    })
    # URL prefixes for default homepages (Google, data: URIs).
    _IDLE_PAGE_PREFIXES: ClassVar[tuple[str, ...]] = (
        "https://www.google.com/",
        "https://google.com/",
        "http://www.google.com/",
        "http://google.com/",
        "data:",
    )

    @classmethod
    def _is_idle_page_url(cls, url: str) -> bool:
        """Check if a page URL is an idle/default page (not real browsing content)."""
        if not url:
            return True
        if url in cls._IDLE_PAGE_URLS:
            return True
        return url.startswith(cls._IDLE_PAGE_PREFIXES)

    async def get_ws_debugger_url(self) -> str | None:
        """Get the WebSocket debugger URL for the active browser page.

        Queries Chrome's /json introspection endpoint to discover page targets.
        Filters for type="page" targets, preferring pages with real browsing
        content over idle/default pages (blank, new tab, Google homepage).
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CDP_ENDPOINT}/json",
                    timeout=aiohttp.ClientTimeout(total=_CONNECT_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        targets = await resp.json()
                        if not targets:
                            return None

                        # Collect all page-type targets
                        pages = [t for t in targets if t.get("type") == "page"]
                        if not pages:
                            # Fallback: use first target regardless of type
                            return targets[0].get("webSocketDebuggerUrl")

                        # Prefer pages with real browsing content (not idle/default)
                        for page in pages:
                            url = page.get("url", "")
                            if not self._is_idle_page_url(url):
                                return page.get("webSocketDebuggerUrl")

                        # All pages are idle — return the first one
                        return pages[0].get("webSocketDebuggerUrl")
        except Exception as e:
            logger.debug(f"Failed to get CDP WebSocket URL: {e}")
        return None

    async def _has_better_page_target(self) -> bool:
        """Check if a page with real browsing content exists that differs from the current target.

        Called during static-page timeouts to detect when Playwright has navigated
        a different tab than the one the screencast is streaming.  If a better
        target is found, the caller should break the stream so the reconnection
        logic picks up the active page.

        Returns True if switching is recommended.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CDP_ENDPOINT}/json",
                    timeout=aiohttp.ClientTimeout(total=_CONNECT_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        return False
                    targets = await resp.json()
                    if not targets:
                        return False

                    pages = [t for t in targets if t.get("type") == "page"]
                    if len(pages) < 2:
                        return False  # Only one page — nothing to switch to

                    # Find pages with real browsing content
                    for page in pages:
                        url = page.get("url", "")
                        ws_url = page.get("webSocketDebuggerUrl", "")
                        if (
                            not self._is_idle_page_url(url)
                            and ws_url != self._cached_ws_url
                        ):
                            logger.info(
                                "Better page target found: %s (current: ...%s)",
                                url[:80],
                                (self._cached_ws_url or "none")[-20:],
                            )
                            return True
        except Exception as e:
            logger.debug("Better page target check failed: %s", e)
        return False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def ensure_connected(self) -> bool:
        """Ensure connection is alive, reconnecting if needed.

        This is the primary entry point for persistent connection usage.
        Avoids full connect/disconnect overhead on every call.
        Serialized via _command_lock to prevent multiple callers from
        racing to reconnect (which causes unclosed client sessions).
        """
        if self.is_connected:
            return True

        async with self._command_lock:
            # Double-check after acquiring lock
            if self.is_connected:
                return True
            # Connection is dead or doesn't exist, try to reconnect
            await self._cleanup_stale_connection()
            return await self._connect_unlocked()

    async def _connect_unlocked(self) -> bool:
        """Connect to Chrome via CDP WebSocket (caller must hold _command_lock)."""
        ws_url = await self._get_cached_ws_url()
        if not ws_url:
            logger.debug("No CDP WebSocket URL available")
            return False

        try:
            self._session = aiohttp.ClientSession()
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(ws_url),
                timeout=_CONNECT_TIMEOUT,
            )
            logger.info(f"Connected to CDP at {ws_url}")
            # Reset viewport flag on every new WebSocket connection.
            # Emulation.setDeviceMetricsOverride must be re-applied after any
            # reconnect — even to the same page target — because the override
            # is scoped to the CDP session, not the page. A new WebSocket to
            # the same target is a new session with no inherited state.
            self._viewport_set = False
            return True
        except asyncio.TimeoutError:
            logger.warning("CDP WebSocket connection timed out")
            await self._cleanup_stale_connection()
            return False
        except Exception as e:
            logger.warning(f"Failed to connect to CDP: {e}")
            await self._cleanup_stale_connection()
            return False

    async def _cleanup_stale_connection(self) -> None:
        """Clean up any stale connection state without logging disconnect."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug("Ignoring error closing stale CDP WebSocket: %s", e)
            self._ws = None
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.debug("Ignoring error closing stale CDP session: %s", e)
            self._session = None
        # Reset viewport flag so _ensure_viewport() always re-applies it on the
        # next connection. Emulation.setDeviceMetricsOverride does not persist
        # across Chrome restarts, new tab creation, or certain page navigations.
        self._viewport_set = False

    async def _ensure_viewport(self) -> None:
        """Set viewport dimensions on the connected page via CDP.

        Sends Emulation.setDeviceMetricsOverride so screenshots and screencast
        frames render at the expected resolution (config.max_width × max_height)
        regardless of the actual browser window size.  This is critical for pages
        opened via /json/new or headless tabs that have tiny default viewports.

        Skips the command if the viewport was already set on the current connection
        (tracked via ``_viewport_set``).
        """
        if self._viewport_set:
            return
        if not self._ws or self._ws.closed:
            return
        result = await self._send_command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": self.config.max_width,
                "height": self.config.max_height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        if result and "error" not in result:
            self._viewport_set = True
            logger.info(
                "Set viewport to %dx%d via Emulation.setDeviceMetricsOverride",
                self.config.max_width,
                self.config.max_height,
            )
        else:
            logger.debug("Viewport override not applied: %s", result)

    async def _handle_page_detached(self, context: str) -> None:
        """Common handler for page-detached errors.

        Cleans up the stale connection and invalidates the URL cache so the
        next connection attempt discovers the current active page target.

        Args:
            context: Description of where the error occurred (for logging)
        """
        async with self._command_lock:
            await self._cleanup_stale_connection()
        self.invalidate_cache()
        logger.info(
            f"Page detached during {context} - invalidated cache, "
            f"will retry with fresh page discovery"
        )
        # Brief delay for Chrome to register the new page target
        await asyncio.sleep(_PAGE_REDISCOVERY_DELAY)

    # ------------------------------------------------------------------
    # Page & Chrome recovery
    # ------------------------------------------------------------------

    def _record_page_failure(self, ws_url: str | None) -> None:
        """Track consecutive failures on the same page target.

        When the same page URL fails repeatedly, the failure counters
        escalate recovery from cache-invalidation → tab replacement →
        Chrome restart.
        """
        self._total_consecutive_failures += 1
        if ws_url and ws_url == self._failing_page_url:
            self._same_page_failure_count += 1
        else:
            self._failing_page_url = ws_url
            self._same_page_failure_count = 1

    def _record_page_success(self) -> None:
        """Reset all failure tracking on a successful CDP operation."""
        self._failing_page_url = None
        self._same_page_failure_count = 0
        self._total_consecutive_failures = 0
        self._rediscovery_counter = 0
        self._last_invalidated_url = None

    async def _try_replace_broken_tab(self) -> bool:
        """Attempt to replace a broken browser tab without restarting Chrome.

        Uses the Chrome DevTools HTTP API to open a fresh tab (PUT /json/new).
        Does NOT close the old tab — Playwright may be actively using it from
        the backend.  The screencast simply needs a working page target to
        attach to; the old tab is harmless if left open.

        Returns True if a new healthy page target is now available.
        """
        logger.info("Attempting tab replacement for broken CDP page")
        try:
            async with aiohttp.ClientSession() as session:
                # Open a fresh tab
                async with session.put(
                    f"{CDP_ENDPOINT}/json/new",
                    timeout=aiohttp.ClientTimeout(total=_CONNECT_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"Failed to create new tab: HTTP {resp.status}"
                        )
                        return False
                    new_target = await resp.json()
                    logger.info(
                        f"Created new tab: {new_target.get('id', 'unknown')}"
                    )

                # NOTE: Old tab is intentionally NOT closed.  Playwright (running
                # in the backend) may be controlling it.  Closing it would crash
                # the agent's browser operations.

                # Invalidate everything so next connect picks up the new tab
                self.invalidate_cache()
                async with self._command_lock:
                    await self._cleanup_stale_connection()
                self._same_page_failure_count = 0
                self._rediscovery_counter = 0
                self._last_invalidated_url = None
                await asyncio.sleep(_PAGE_REDISCOVERY_DELAY)
                return True

        except Exception as e:
            logger.warning(f"Tab replacement failed: {e}")
            return False

    async def _try_restart_chrome(self) -> bool:
        """Restart Chrome via supervisord when tab replacement is insufficient.

        Uses supervisord's Unix-socket XML-RPC interface (via supervisorctl)
        to restart the chrome_cdp_only process. Includes a cooldown to
        prevent restart storms.

        Note: supervisorctl arguments are static strings — no user input is
        involved, so there is no command injection risk.

        Returns True if Chrome was successfully restarted.
        """
        now = time.monotonic()
        if (now - self._last_chrome_restart) < _CHROME_RESTART_COOLDOWN:
            remaining = _CHROME_RESTART_COOLDOWN - (now - self._last_chrome_restart)
            logger.info(
                f"Chrome restart cooldown active ({remaining:.0f}s remaining)"
            )
            return False

        logger.warning("Restarting Chrome via supervisord for CDP recovery")
        self._last_chrome_restart = now

        try:
            # All arguments are hardcoded constants — safe from injection.
            proc = await asyncio.create_subprocess_exec(
                "supervisorctl",
                "-s",
                "unix:///tmp/supervisor.sock",
                "restart",
                "chrome_cdp_only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=15.0
            )
            success = proc.returncode == 0
            if success:
                logger.info(
                    f"Chrome restarted successfully: "
                    f"{stdout.decode().strip()}"
                )
                # Full reset — give Chrome time to start and register targets
                self.invalidate_cache()
                async with self._command_lock:
                    await self._cleanup_stale_connection()
                self._record_page_success()  # Reset all failure counters
                await asyncio.sleep(3.0)  # Chrome needs ~2-3s to be ready
                return True
            else:
                logger.error(
                    f"Chrome restart failed (rc={proc.returncode}): "
                    f"{stderr.decode().strip()}"
                )
                return False
        except asyncio.TimeoutError:
            logger.error("Chrome restart timed out after 15s")
            return False
        except Exception as e:
            logger.error(f"Chrome restart error: {e}")
            return False

    async def _escalate_recovery(self) -> bool:
        """Decide and execute the appropriate recovery action based on
        the current failure state.

        Escalation ladder:
        1. Cache invalidation + page rediscovery (handled by caller)
        2. Tab replacement (same page fails >= _PAGE_RECOVERY_FAILURE_THRESHOLD,
           OR same broken URL rediscovered >= _SAME_URL_REDISCOVERY_THRESHOLD)
        3. Chrome restart (total failures >= _CHROME_RESTART_FAILURE_THRESHOLD)

        Protected by _recovery_lock to prevent multiple concurrent coroutines from
        each triggering independent recovery actions (which race and cancel each other).

        Returns True if recovery was attempted (caller should retry).
        Returns False if:
        - Another recovery is already in progress (caller should abort this attempt)
        - All thresholds cleared by a concurrent recovery (caller should retry normally)
        """
        # Fast path: if recovery is already running, skip this duplicate attempt.
        # The concurrent recovery will reset counters; this call should just abort.
        if self._recovery_lock.locked():
            logger.debug(
                "Recovery already in progress — skipping concurrent escalation attempt "
                "(same_page=%d, total=%d, rediscovery=%d)",
                self._same_page_failure_count,
                self._total_consecutive_failures,
                self._rediscovery_counter,
            )
            return False

        async with self._recovery_lock:
            # Double-check thresholds after acquiring lock — a concurrent recovery
            # may have already succeeded and reset counters while we waited.
            needs_tab_replace = (
                self._same_page_failure_count >= _PAGE_RECOVERY_FAILURE_THRESHOLD
                or self._rediscovery_counter >= _SAME_URL_REDISCOVERY_THRESHOLD
            )
            needs_chrome_restart = (
                self._total_consecutive_failures >= _CHROME_RESTART_FAILURE_THRESHOLD
            )

            if not (needs_tab_replace or needs_chrome_restart):
                logger.info(
                    "Recovery thresholds cleared by concurrent recovery — "
                    "no further action needed (same_page=%d, total=%d, rediscovery=%d)",
                    self._same_page_failure_count,
                    self._total_consecutive_failures,
                    self._rediscovery_counter,
                )
                return True  # Concurrent recovery already fixed things

            if needs_chrome_restart:
                logger.warning(
                    "Escalating to Chrome restart "
                    "(total_failures=%d >= threshold=%d)",
                    self._total_consecutive_failures,
                    _CHROME_RESTART_FAILURE_THRESHOLD,
                )
                return await self._try_restart_chrome()

            # Tab replacement (same page failing or same URL being rediscovered)
            if self._rediscovery_counter >= _SAME_URL_REDISCOVERY_THRESHOLD:
                logger.warning(
                    "Escalating to tab replacement: same broken URL rediscovered "
                    "%d times after cache invalidation (url=...%s)",
                    self._rediscovery_counter,
                    (self._last_invalidated_url or "unknown")[-20:],
                )
            else:
                logger.info(
                    "Escalating to tab replacement "
                    "(same_page_failures=%d >= threshold=%d)",
                    self._same_page_failure_count,
                    _PAGE_RECOVERY_FAILURE_THRESHOLD,
                )
            return await self._try_replace_broken_tab()

    async def _maybe_escalate(self, context: str) -> bool:
        """Check escalation thresholds inline and escalate if needed.

        Called immediately after every _record_page_failure() to ensure
        escalation fires within the current burst — without waiting for the
        next call's pre-check.  This is critical because concurrent callers
        all bypass the pre-check simultaneously (they all read count=0 at
        call start, before any failure is recorded).

        Args:
            context: Short description of where the failure occurred (for logging).

        Returns:
            True  — escalation was triggered (caller should retry or return None).
            False — thresholds not yet met (caller should use normal retry path).
        """
        needs_escalation = (
            self._same_page_failure_count >= _PAGE_RECOVERY_FAILURE_THRESHOLD
            or self._total_consecutive_failures >= _CHROME_RESTART_FAILURE_THRESHOLD
            or self._rediscovery_counter >= _SAME_URL_REDISCOVERY_THRESHOLD
        )
        if not needs_escalation:
            return False

        logger.warning(
            "Inline escalation triggered after %s "
            "(same_page=%d, total=%d, rediscovery=%d)",
            context,
            self._same_page_failure_count,
            self._total_consecutive_failures,
            self._rediscovery_counter,
        )
        await self._escalate_recovery()
        return True

    async def connect(self) -> bool:
        """Connect to Chrome via CDP WebSocket."""
        async with self._command_lock:
            return await self._connect_unlocked()

    async def disconnect(self):
        """Disconnect from CDP."""
        self._running = False
        await self._cleanup_stale_connection()
        logger.debug("Disconnected from CDP")

    async def health_check(self) -> bool:
        """Quick health check - verify Chrome is responsive via the /json endpoint.

        This is cheaper than a full WebSocket roundtrip and detects
        Chrome crashes or restarts without disturbing the WS connection.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CDP_ENDPOINT}/json/version",
                    timeout=aiohttp.ClientTimeout(total=_HEALTH_CHECK_TIMEOUT),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # CDP command transport
    # ------------------------------------------------------------------

    async def _send_command(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = _CAPTURE_COMMAND_TIMEOUT,
    ) -> dict | None:
        """Send a CDP command and wait for response with timeout.

        Serialized via _command_lock to prevent concurrent receive() calls
        on the shared WebSocket (aiohttp forbids this).
        """
        if not self._ws or self._ws.closed:
            return None

        async with self._command_lock:
            # Re-check after acquiring lock (connection may have been cleaned up)
            if not self._ws or self._ws.closed:
                return None

            self._msg_counter += 1
            msg_id = self._msg_counter

            message = {"id": msg_id, "method": method}
            if params:
                message["params"] = params

            try:
                await self._ws.send_json(message)
                logger.debug(f"Sent CDP command: {method} (id={msg_id})")

                # Wait for response with timeout
                start_time = asyncio.get_event_loop().time()
                while True:
                    remaining = timeout - (asyncio.get_event_loop().time() - start_time)
                    if remaining <= 0:
                        logger.warning(f"CDP command timed out: {method}")
                        return None

                    try:
                        msg = await asyncio.wait_for(
                            self._ws.receive(), timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"CDP command timed out waiting for response: {method}"
                        )
                        return None

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        # Check if this is our response
                        if data.get("id") == msg_id:
                            logger.debug(f"Got CDP response for {method}")
                            return data
                        # Otherwise it might be an event, continue waiting
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.warning(f"CDP WebSocket error: {msg.data}")
                        return None
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        logger.warning("CDP WebSocket closed unexpectedly")
                        return None

            except RuntimeError as e:
                # Transport can close during rapid restarts/teardown.
                if "closing transport" in str(e).lower():
                    logger.debug(f"CDP command skipped on closing transport: {method}")
                else:
                    logger.warning(f"CDP command error: {e}")
            except Exception as e:
                logger.warning(f"CDP command error: {e}")
            return None

    # ------------------------------------------------------------------
    # Screencast streaming
    # ------------------------------------------------------------------

    async def start_screencast(self) -> bool:
        """Start the screencast stream.

        On page-detached errors, invalidates the cache and retries once
        with fresh page discovery so the screencast recovers from navigation/crashes.
        """
        params = {
            "format": self.config.format,
            "quality": self.config.quality,
            "maxWidth": self.config.max_width,
            "maxHeight": self.config.max_height,
            "everyNthFrame": self.config.every_nth_frame,
        }

        for attempt in range(_MAX_RETRY_ATTEMPTS):
            if not self._ws:
                if not await self.connect():
                    if attempt == 0:
                        self.invalidate_cache()
                        continue
                    return False

            # Ensure proper viewport before starting screencast — headless
            # tabs opened via /json/new have tiny default viewports.
            await self._ensure_viewport()

            result = await self._send_command("Page.startScreencast", params)
            if result and "error" not in result:
                self._running = True
                # Screencast started successfully — page target is confirmed valid.
                # Reset all failure/rediscovery counters that may have accumulated
                # from preemption-driven cache invalidation cycles.
                self._record_page_success()
                logger.info(f"CDP screencast started with config: {self.config}")
                return True

            # Check for page-detached error and retry
            if result and self._is_page_detached_error(result) and attempt == 0:
                logger.warning(
                    f"Screencast start failed (page detached): {result.get('error')}"
                )
                await self._handle_page_detached("start_screencast")
                continue

            logger.error(f"Failed to start screencast: {result}")
            return False

        return False

    async def stop_screencast(self):
        """Stop the screencast stream."""
        self._running = False
        # Do not send a CDP command while the stream reader is active; that causes
        # concurrent receive() calls on the same websocket connection.
        if self._ws and not self._streaming and not self._ws.closed:
            await self._send_command("Page.stopScreencast")
        logger.info("CDP screencast stopped")

    async def ack_frame(self, session_id: int):
        """Acknowledge receipt of a frame to continue receiving frames."""
        if self._ws:
            await self._ws.send_json(
                {
                    "id": id(session_id),
                    "method": "Page.screencastFrameAck",
                    "params": {"sessionId": session_id},
                }
            )

    async def stream_frames(
        self,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[ScreencastFrame, None]:
        """
        Stream screencast frames as an async generator.

        Yields ScreencastFrame objects with decoded image data.
        Automatically acknowledges frames to keep the stream flowing.

        Args:
            cancel_event: Optional event that, when set, causes the stream to
                exit promptly. Used to propagate client disconnects so the
                stream doesn't linger for the full frame timeout cycle.

        Frame Timeout Watchdog:
            If no frame is received within _STREAM_FRAME_TIMEOUT seconds and
            Chrome's health check fails, the stream exits to trigger recovery.
            When the health check passes (page is simply static), the timeout
            counter resets and the stream continues waiting.

        Health Check:
            Every _STREAM_HEALTH_CHECK_INTERVAL seconds, a lightweight /json
            health check verifies Chrome is still responsive. If Chrome is dead,
            the stream exits early rather than waiting for the full frame timeout.
        """
        if not self._running:
            if not await self.start_screencast():
                return

        self._streaming = True
        last_health_check = time.monotonic()
        consecutive_timeouts = 0
        _MAX_CONSECUTIVE_TIMEOUTS = 2  # Exit after 2 consecutive failed health checks

        try:
            while self._running:
                # Check cancel signal at the top of each iteration
                if cancel_event and cancel_event.is_set():
                    logger.info("Stream cancelled by caller (client disconnect)")
                    break
                try:
                    # Wait for next message with timeout — prevents indefinite hang
                    # when Chrome stops producing frames
                    msg = await asyncio.wait_for(
                        self._ws.receive(), timeout=_STREAM_FRAME_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    # Check cancel before doing any timeout processing
                    if cancel_event and cancel_event.is_set():
                        logger.info("Stream cancelled during timeout wait")
                        break

                    consecutive_timeouts += 1
                    logger.info(
                        f"No CDP frame received in {_STREAM_FRAME_TIMEOUT}s "
                        f"(timeout {consecutive_timeouts}/{_MAX_CONSECUTIVE_TIMEOUTS}) — "
                        "static page or idle browser (health check will verify)"
                    )

                    if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                        logger.error(
                            "CDP stream appears dead — Chrome renderer may be hung. "
                            "Breaking stream to trigger recovery."
                        )
                        break

                    # Verify Chrome is still alive before escalating
                    if not await self.health_check():
                        logger.error(
                            "Chrome health check failed during stream timeout. "
                            "Breaking stream to trigger recovery."
                        )
                        break

                    # Chrome is alive — page is likely static (no visual changes
                    # means no compositor updates, so no screencast frames).
                    # Reset the counter: a passing health check is proof of life,
                    # so we should not escalate toward killing the stream.
                    consecutive_timeouts = 0
                    logger.info(
                        "Chrome health check passed — page likely static, "
                        "resetting timeout counter"
                    )

                    # Capture a fallback screenshot so the frontend has at
                    # least one frame to display for static pages.
                    try:
                        result = await self._send_command(
                            "Page.captureScreenshot",
                            {
                                "format": self.config.format,
                                "quality": self.config.quality,
                            },
                        )
                        if result and "result" in result:
                            frame_data = result["result"].get("data")
                            if frame_data:
                                image_bytes = base64.b64decode(frame_data)
                                yield ScreencastFrame(
                                    data=image_bytes,
                                    session_id=0,
                                    timestamp=time.monotonic(),
                                    metadata={"synthetic": True},
                                )
                                logger.debug(
                                    "Sent fallback screenshot for static page"
                                )
                    except Exception as e:
                        logger.debug(
                            f"Fallback screenshot capture failed: {e}"
                        )

                    # Check if Playwright is browsing on a different tab.
                    # If a page with real content exists, break the stream
                    # so the recovery loop reconnects to the active page.
                    if await self._has_better_page_target():
                        logger.info(
                            "Breaking stream to switch to active page target"
                        )
                        # Invalidate so reconnection discovers the better page
                        self.invalidate_cache()
                        async with self._command_lock:
                            await self._cleanup_stale_connection()
                        break

                    continue

                # Reset timeout counter on any received message
                consecutive_timeouts = 0

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.json()

                    # Check for screencast frame event
                    if data.get("method") == "Page.screencastFrame":
                        params = data.get("params", {})
                        session_id = params.get("sessionId")
                        frame_data = params.get("data")
                        metadata = params.get("metadata", {})

                        if frame_data and session_id is not None:
                            # Decode base64 image data
                            image_bytes = base64.b64decode(frame_data)

                            frame = ScreencastFrame(
                                data=image_bytes,
                                session_id=session_id,
                                timestamp=metadata.get("timestamp", 0),
                                metadata=metadata,
                            )

                            # Acknowledge immediately to receive next frame ASAP
                            await self.ack_frame(session_id)

                            yield frame

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"CDP WebSocket error during stream: {msg.data}")
                    break

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    logger.info("CDP WebSocket closed during stream")
                    break

                # Periodic health check (lightweight, doesn't block frame flow)
                now = time.monotonic()
                if now - last_health_check >= _STREAM_HEALTH_CHECK_INTERVAL:
                    last_health_check = now
                    if not await self.health_check():
                        logger.warning(
                            "Chrome health check failed during active stream. "
                            "Breaking stream to trigger recovery."
                        )
                        break

        except asyncio.CancelledError:
            logger.info("Screencast stream cancelled")
        except Exception as e:
            logger.error(f"Screencast stream error: {e}")
        finally:
            self._streaming = False

    # ------------------------------------------------------------------
    # Single-frame capture
    # ------------------------------------------------------------------

    async def capture_single_frame(
        self, quality: int | None = None, image_format: str | None = None
    ) -> bytes | None:
        """
        Capture a single frame from the browser.

        Uses persistent connection via ensure_connected() for low overhead.
        On page-detached errors, invalidates the cached URL and retries once
        with fresh page discovery so navigation/crashes recover automatically.

        Recovery escalation (tracked across calls):
        1. Cache invalidation + page rediscovery (default)
        2. Tab replacement via /json/new (same page fails 3+ times)
        3. Chrome restart via supervisord (total failures 6+)

        Args:
            quality: Override quality setting for this capture (default: use config)
            image_format: Override format for this capture (default: use config)
        """
        capture_quality = quality if quality is not None else self.config.quality
        capture_format = image_format if image_format is not None else self.config.format

        # Pre-check: escalate if thresholds were met by a previous call's failures.
        # This covers the case where previous bursts accumulated enough failures
        # that the NEXT burst's first call should immediately trigger recovery.
        if (
            self._same_page_failure_count >= _PAGE_RECOVERY_FAILURE_THRESHOLD
            or self._total_consecutive_failures >= _CHROME_RESTART_FAILURE_THRESHOLD
            or self._rediscovery_counter >= _SAME_URL_REDISCOVERY_THRESHOLD
        ):
            logger.warning(
                "Pre-check escalation: previous burst accumulated failures "
                "(same_page=%d, total=%d, rediscovery=%d)",
                self._same_page_failure_count,
                self._total_consecutive_failures,
                self._rediscovery_counter,
            )
            recovered = await self._escalate_recovery()
            if not recovered:
                return None

        # Try up to 2 times: initial attempt + 1 retry after page re-discovery
        for attempt in range(_MAX_RETRY_ATTEMPTS):
            if not await self.ensure_connected():
                if attempt == 0:
                    self.invalidate_cache()
                    continue
                return None

            # Ensure proper viewport on first attempt (handles new tabs with tiny viewports)
            if attempt == 0:
                await self._ensure_viewport()

            # Capture the current WS URL for failure tracking
            current_ws_url = self._cached_ws_url

            try:
                result = await self._send_command(
                    "Page.captureScreenshot",
                    {"format": capture_format, "quality": capture_quality},
                )

                # Detect timeout (result is None) and force reconnect
                if result is None:
                    logger.warning("CDP capture timed out, forcing reconnect")
                    self._record_page_failure(current_ws_url)
                    # Inline escalation — don't wait for next call's pre-check.
                    # This matters because concurrent callers all bypass the
                    # pre-check simultaneously (all see count=0 at call start).
                    if await self._maybe_escalate("timeout"):
                        if attempt == 0:
                            continue
                    elif attempt == 0:
                        await self._handle_page_detached("capture_screenshot_timeout")
                        continue
                    return None

                if "result" in result:
                    data = result["result"].get("data")
                    if data:
                        self._last_successful_capture = time.monotonic()
                        self._record_page_success()
                        return base64.b64decode(data)

                # Command returned error - check if page is detached
                if "error" in result:
                    logger.warning(
                        "CDP capture error response: %s", result["error"]
                    )
                    self._record_page_failure(current_ws_url)

                    # Inline escalation check — fires immediately when thresholds
                    # are met, without waiting for the next call's pre-check.
                    if await self._maybe_escalate("error"):
                        if attempt == 0:
                            continue
                        return None

                    if self._is_page_detached_error(result) and attempt == 0:
                        await self._handle_page_detached("capture_screenshot")
                        continue

                    # Non-retryable error — invalidate cache so the next call
                    # forces a fresh /json URL lookup instead of reusing the
                    # broken cached URL.  Without this, attempt 1 always
                    # reconnects to the same dead page target.
                    self.invalidate_cache()
                    async with self._command_lock:
                        await self._cleanup_stale_connection()

            except Exception as e:
                logger.warning("Failed to capture single frame: %s", e)
                self._record_page_failure(current_ws_url)
                if attempt == 0:
                    await self._handle_page_detached("capture_screenshot_exception")
                    continue
                async with self._command_lock:
                    await self._cleanup_stale_connection()

        return None


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_service_instance: CDPScreencastService | None = None
_service_lock = asyncio.Lock()


async def get_or_create_screencast_service(
    config: ScreencastConfig | None = None,
) -> CDPScreencastService:
    """Get or create the singleton CDP screencast service (async-safe)."""
    global _service_instance
    if _service_instance is None:
        async with _service_lock:
            # Double-check after acquiring lock
            if _service_instance is None:
                _service_instance = CDPScreencastService(config)
    return _service_instance


def get_screencast_service(
    config: ScreencastConfig | None = None,
) -> CDPScreencastService:
    """Get or create the singleton CDP screencast service (sync version)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CDPScreencastService(config)
    return _service_instance
