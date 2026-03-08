import asyncio
import contextlib
import inspect
import logging
import random
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import get_settings
from app.core.prometheus_metrics import (
    browser_element_extraction_latency,
    browser_element_extraction_timeout_total,
    browser_element_extraction_total,
)
from app.domain.models.tool_result import ToolResult
from app.domain.utils.url_filters import is_ssrf_target, is_video_url
from app.infrastructure.external.llm import get_llm

# Set up logger for this module
logger = logging.getLogger(__name__)

# Default browser configuration for realistic browsing
# Viewport is the content area inside the browser window.
# With a 1280x1024 browser window and chrome (~90px for tabs/address bar),
# the actual visible content area is approximately 1280x934.
# We use the full width to avoid horizontal cutoff.
DEFAULT_VIEWPORT = {"width": 1280, "height": 900}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_TIMEZONE = "America/New_York"

# Professional browsing: User agent rotation pool for anti-detection
# Aligned with Chrome for Testing 128.0.6613.137 (Ubuntu 22.04 sandbox)
USER_AGENT_POOL = [
    # Chrome on Linux (matches sandbox Chrome 128.0.6613.137)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox on Windows (secondary)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/128.0.0.0",
]

# Fixed viewport — consistent 1280x900 for reliable rendering.
# Randomized viewports (especially 1024x768) trigger mobile/tablet layouts
# and cause inconsistent element positioning. Stability > anti-detection.
VIEWPORT_POOL = [
    {"width": 1280, "height": 900},
]

# Timezone variations
TIMEZONE_POOL = [
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "America/Denver",
    "Europe/London",
    "Europe/Berlin",
]

# Resource types to block for faster page loads (configurable).
# NOTE: font and stylesheet are NOT blocked by default — blocking them breaks
# page rendering (wrong fonts, no styling). Only block media for performance.
BLOCKABLE_RESOURCE_TYPES = {"media"}

# Ad/Tracker blocking disabled — was causing browsing issues
BLOCKED_URL_PATTERNS: list[str] = []

# Browser crash error signatures — when exceptions contain these strings,
# the browser/renderer has crashed and needs recovery, not retry.
BROWSER_CRASH_SIGNATURES: list[str] = [
    "Target closed",
    "Target crashed",
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Browser closed",
    "Session closed",
    "Execution context was destroyed",
    "Protocol error",
    "Connection closed",
    "Page crashed",
]

DEFAULT_BROWSER_CRASH_WINDOW_SECONDS = 300.0
DEFAULT_BROWSER_CRASH_THRESHOLD = 3
DEFAULT_BROWSER_CRASH_COOLDOWN_SECONDS = 60.0
DEFAULT_BROWSER_QUICK_HEALTH_CHECK_TIMEOUT = 3.0

# Video domains to skip - these waste agent time and resources
# Performance optimization constants (based on Browser-Use patterns from Context7)
# These limits prevent hangs on heavy documentation sites (e.g., claude.com/docs)
MAX_INTERACTIVE_ELEMENTS = 100  # Cap interactive elements to prevent 4+ minute extractions
MAX_CONTENT_ELEMENTS = 200  # Cap content elements for text extraction
JS_EVAL_TIMEOUT_MS = 5000  # 5 second timeout for JavaScript evaluation
EXTRACTION_CACHE_TTL_SECONDS = 10  # Cache extraction results for 10 seconds (overridden by config)
HEAVY_PAGE_THRESHOLD = 3000  # Pages with more elements use lightweight extraction

# Wikipedia and heavy page detection (Priority 1: crash prevention)
WIKIPEDIA_DOMAINS = ["wikipedia.org", "en.wikipedia.org", "*.wikipedia.org"]
QUICK_SIZE_CHECK_TIMEOUT_MS = 500  # Quick page size check timeout


class PlaywrightBrowser:
    """Playwright client that provides specific implementation of browser operations

    Features:
    - Proper browser context configuration for realistic browsing
    - Network request interception for performance optimization
    - Robust error handling with automatic recovery
    - Efficient page load waiting using Playwright's native methods
    """

    def __init__(
        self,
        cdp_url: str | None = None,
        block_resources: bool = False,
        blocked_types: set[str] | None = None,
        randomize_fingerprint: bool = True,
    ):
        """Initialize PlaywrightBrowser

        Args:
            cdp_url: Chrome DevTools Protocol URL for connection. If omitted,
                falls back to configured default or localhost CDP.
            block_resources: Whether to block unnecessary resources (images, ads, etc.)
            blocked_types: Set of resource types to block (e.g., {"image", "font"})
            randomize_fingerprint: Whether to randomize browser fingerprint (default: True)
        """
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None
        self.llm = get_llm()
        self.settings = get_settings()
        configured_cdp_url = getattr(self.settings, "browser_cdp_url", None)
        self.cdp_url = cdp_url or configured_cdp_url or "ws://localhost:9222"
        self.block_resources = block_resources
        # Use settings-configured blocked types, fallback to BLOCKABLE_RESOURCE_TYPES
        default_blocked_types = self.settings.browser_blocked_types_set or BLOCKABLE_RESOURCE_TYPES
        self.blocked_types = blocked_types or default_blocked_types if block_resources else set()
        self._interactive_elements_cache: list[dict] = []
        self._connection_healthy = False
        self._randomize_fingerprint = randomize_fingerprint
        # Serialize navigation to prevent concurrent page.goto() race conditions.
        # Note: only protects navigate(); other page methods (click, type) rely on
        # SEQUENTIAL_ONLY_TOOLS enforcement in parallel_executor.py as primary safeguard.
        self._navigation_lock = asyncio.Lock()
        # Track URLs that already triggered heavy-page warnings to reduce log noise.
        # Each URL is warned once per browser instance lifetime.
        self._heavy_page_warned_urls: set[str] = set()
        # Keeps strong references to fire-and-forget background tasks (satisfies RUF006).
        self._background_tasks: set[asyncio.Task] = set()
        # Cache the feature flag once at init — avoids repeated get_settings() in hot paths.
        self._dom_cursor_enabled: bool = getattr(self.settings, "feature_dom_cursor_injection", False)

        # Extraction cache for performance (prevents duplicate extractions)
        self._extraction_cache: dict[str, Any] = {
            "url": None,
            "timestamp": 0.0,
            "elements": None,
            "content": None,
        }

        # Circuit breaker for navigate_for_display (live preview display)
        # Stops attempting live preview navigations after repeated failures (e.g., browser crash)
        self._display_failure_count: int = 0
        self._display_failure_threshold: int = 2

        # Cancellation signal for background browsing (prevents race with foreground ops)
        self._background_browse_cancelled: bool = False

        # Circuit breaker for browser crashes (Phase 1: hardening)
        # Tracks crash timestamps to detect repeated failures and fail-fast
        self._crash_history: list[float] = []  # Timestamps of recent crashes
        self._crash_window_seconds: float = self._safe_float(
            getattr(self.settings, "browser_crash_window_seconds", DEFAULT_BROWSER_CRASH_WINDOW_SECONDS),
            DEFAULT_BROWSER_CRASH_WINDOW_SECONDS,
            minimum=1.0,
        )
        self._crash_threshold: int = self._safe_int(
            getattr(self.settings, "browser_crash_threshold", DEFAULT_BROWSER_CRASH_THRESHOLD),
            DEFAULT_BROWSER_CRASH_THRESHOLD,
            minimum=1,
        )
        self._crash_cooldown_seconds: float = self._safe_float(
            getattr(self.settings, "browser_crash_cooldown_seconds", DEFAULT_BROWSER_CRASH_COOLDOWN_SECONDS),
            DEFAULT_BROWSER_CRASH_COOLDOWN_SECONDS,
            minimum=0.0,
        )
        self._circuit_open_until: float = 0.0  # Timestamp when circuit can close
        self._circuit_breaker_enabled: bool = self._safe_bool(
            getattr(self.settings, "browser_crash_circuit_breaker_enabled", True),
            True,
        )
        self._quick_health_check_enabled: bool = self._safe_bool(
            getattr(self.settings, "browser_quick_health_check_enabled", True),
            True,
        )
        self._quick_health_check_timeout: float = self._safe_float(
            getattr(self.settings, "browser_quick_health_check_timeout", DEFAULT_BROWSER_QUICK_HEALTH_CHECK_TIMEOUT),
            DEFAULT_BROWSER_QUICK_HEALTH_CHECK_TIMEOUT,
            minimum=0.1,
        )

        # Current fingerprint values (randomized on each session)
        self._current_user_agent: str = DEFAULT_USER_AGENT
        self._current_viewport: dict[str, int] = DEFAULT_VIEWPORT
        self._current_timezone: str = DEFAULT_TIMEZONE

        # Shutdown guard — prevents spurious reconnect on intentional cleanup
        self._shutting_down: bool = False
        # CDP keepalive task — periodic JS eval to prevent idle WebSocket disconnects
        self._keepalive_task: asyncio.Task | None = None
        self._keepalive_enabled: bool = self._safe_bool(
            getattr(self.settings, "browser_cdp_keepalive_enabled", True), True
        )
        self._keepalive_interval: float = self._safe_float(
            getattr(self.settings, "browser_cdp_keepalive_interval", 45.0), 45.0, minimum=5.0
        )

        # Recovery callback — set by BrowserTool to emit progress events on reconnect
        self._recovery_callback: Callable[[], Awaitable[None]] | None = None

    @staticmethod
    def _safe_bool(value: Any, default: bool) -> bool:
        """Return a strict bool value or fallback to default."""
        return value if isinstance(value, bool) else default

    @staticmethod
    def _safe_int(value: Any, default: int, minimum: int = 1) -> int:
        """Return a validated int value or fallback to default."""
        if isinstance(value, int) and not isinstance(value, bool) and value >= minimum:
            return value
        return default

    @staticmethod
    def _safe_float(value: Any, default: float, minimum: float = 0.0) -> float:
        """Return a validated float value or fallback to default."""
        if isinstance(value, int | float) and not isinstance(value, bool):
            coerced = float(value)
            if coerced >= minimum:
                return coerced
        return default

    @staticmethod
    def _is_page_closed(page: Any | None) -> bool:
        """Return True only when page is missing or explicitly reports closed."""
        if page is None:
            return True

        is_closed = getattr(page, "is_closed", None)
        if not callable(is_closed):
            return False

        try:
            return is_closed() is True
        except Exception:
            return True

    @staticmethod
    def _is_crash_error(error: BaseException) -> bool:
        """Check if an exception indicates a browser/renderer crash.

        Args:
            error: The exception to check

        Returns:
            True if the error matches a known crash signature
        """
        msg = str(error).lower()
        return any(sig.lower() in msg for sig in BROWSER_CRASH_SIGNATURES)

    def _randomize_browser_fingerprint(self) -> tuple[str, dict[str, int], str]:
        """Randomize browser fingerprint for anti-detection.

        Returns:
            Tuple of (user_agent, viewport, timezone)
        """
        user_agent = random.choice(USER_AGENT_POOL)  # noqa: S311 - Random fingerprint for stealth, not cryptographic
        viewport = random.choice(VIEWPORT_POOL)  # noqa: S311 - Random fingerprint for stealth, not cryptographic
        timezone = random.choice(TIMEZONE_POOL)  # noqa: S311 - Random fingerprint for stealth, not cryptographic

        logger.debug(
            f"Randomized fingerprint: UA={user_agent[:50]}..., "
            f"Viewport={viewport['width']}x{viewport['height']}, "
            f"TZ={timezone}"
        )

        return user_agent, viewport, timezone

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations (not too many crashes).

        Returns:
            True if circuit is closed (allow operations), False if open (reject operations)
        """
        if not self._circuit_breaker_enabled:
            return True

        current_time = time.time()

        # Circuit explicitly open with cooldown?
        if current_time < self._circuit_open_until:
            remaining = self._circuit_open_until - current_time
            logger.warning(f"Circuit breaker OPEN: too many crashes. Cooldown: {remaining:.1f}s remaining")
            return False

        # Clean old crashes outside tracking window
        cutoff = current_time - self._crash_window_seconds
        self._crash_history = [ts for ts in self._crash_history if ts > cutoff]

        # Check if threshold exceeded
        if len(self._crash_history) >= self._crash_threshold:
            # Open circuit for cooldown period
            self._circuit_open_until = current_time + self._crash_cooldown_seconds
            logger.error(
                f"Circuit breaker OPEN: {len(self._crash_history)} crashes in "
                f"{self._crash_window_seconds}s window. Cooldown: "
                f"{self._crash_cooldown_seconds}s"
            )
            return False

        return True  # Circuit closed, allow operations

    def _record_crash(self) -> None:
        """Record a browser crash for circuit breaker tracking."""
        if not self._circuit_breaker_enabled:
            return

        current_time = time.time()
        self._crash_history.append(current_time)

        # Clean old crashes
        cutoff = current_time - self._crash_window_seconds
        self._crash_history = [ts for ts in self._crash_history if ts > cutoff]

        logger.warning(
            f"Browser crash recorded: {len(self._crash_history)} crashes in last "
            f"{self._crash_window_seconds}s (threshold: {self._crash_threshold})"
        )

    async def _ensure_page_visible(self) -> None:
        """Bring page to front for live preview visibility.

        Uses both Playwright API and CDP commands to ensure the page is visible
        in the live preview viewer. This is critical for user visibility of browser actions.

        Handles errors gracefully - live preview visibility is best-effort and should not
        block browser operations.
        """
        # Guard against uninitialized state
        if not self.page or not self.context:
            logger.debug("Cannot ensure page visibility: page or context is None")
            return

        try:
            await self.page.bring_to_front()
            # Also try CDP-level activation for live preview visibility
            cdp_session = None
            try:
                cdp_session = await self.context.new_cdp_session(self.page)
                await cdp_session.send("Page.bringToFront")
                logger.info("Brought page to front via CDP for live preview visibility")
            except (PlaywrightError, OSError) as cdp_error:
                logger.debug(f"CDP bring_to_front: {cdp_error}")
            finally:
                if cdp_session:
                    try:
                        await cdp_session.detach()
                    except Exception as detach_error:
                        logger.debug(f"CDP session detach failed: {detach_error}")
        except (PlaywrightError, OSError) as e:
            logger.debug(f"Could not bring page to front: {e}")

    async def _quick_health_check(self) -> bool:
        """Quick health check before operations to detect crashes fast (<5s).

        P1.1: Enhanced to check page complexity and proactively clear heavy pages.

        Returns:
            True if healthy, False if crashed/unhealthy
        """
        if not self._quick_health_check_enabled:
            # Fast path: skip health check if disabled
            return self._connection_healthy

        try:
            if self._is_page_closed(self.page):
                logger.debug("Quick health check: page is None or closed")
                return False

            # Fast evaluation with short timeout
            evaluate_result = self.page.evaluate("() => true")
            if not inspect.isawaitable(evaluate_result):
                logger.debug("Quick health check skipped: page.evaluate is not awaitable")
                return self._connection_healthy
            await asyncio.wait_for(
                evaluate_result,
                timeout=self._quick_health_check_timeout,
            )

            # P1.1: Check page complexity and clear if too heavy
            complexity = await self._get_page_complexity()
            if isinstance(complexity, dict) and complexity.get("isHeavy"):
                iframe_count = complexity.get("iframeCount", 0)
                element_count = complexity.get("elementCount", 0)
                current_url = self.page.url if self.page else ""
                if current_url not in self._heavy_page_warned_urls:
                    self._heavy_page_warned_urls.add(current_url)
                    logger.warning(
                        f"Heavy page detected ({iframe_count} iframes, {element_count} elements), clearing to about:blank"
                    )
                try:
                    await self.page.goto("about:blank", timeout=5000)
                except Exception as clear_error:
                    logger.debug(f"Failed to clear heavy page: {clear_error}")
                    # Continue anyway - we tried

            return True

        except TimeoutError:
            logger.warning(f"Quick health check timed out after {self._quick_health_check_timeout}s")
            self._connection_healthy = False
            return False

        except Exception as e:
            if self._is_crash_error(e):
                err_str = str(e)
                # Navigation destroys execution context — this is expected, not a crash
                if "Execution context was destroyed" in err_str:
                    logger.debug("Health check during navigation (context destroyed) — treating as healthy")
                    return True
                logger.error(f"Browser crash detected in quick health check: {e}")
                self._connection_healthy = False
                self._record_crash()
            else:
                logger.warning(f"Quick health check failed: {e}")
                self._connection_healthy = False
            return False

    async def _evaluate_with_timeout(self, script: str, timeout_ms: int = JS_EVAL_TIMEOUT_MS) -> Any:
        """Execute JavaScript with timeout protection.

        Prevents hangs on heavy pages (e.g., documentation sites with 5000+ elements).
        Pattern from Playwright best practices (Context7 research).

        Args:
            script: JavaScript code to execute (should be an expression that returns a value)
            timeout_ms: Maximum execution time in milliseconds (default: 5000)

        Returns:
            Result of JavaScript execution, or None if timeout/error
        """
        if not self.page:
            return None

        # Wrap script in Promise.race with timeout
        timeout_script = f"""
        Promise.race([
            (async () => {{ return {script} }})(),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('JS evaluation timeout after {timeout_ms}ms')), {timeout_ms})
            )
        ])
        """
        try:
            return await self.page.evaluate(timeout_script)
        except PlaywrightTimeoutError:
            logger.warning(f"JS evaluation timed out after {timeout_ms}ms")
            return None
        except Exception as e:
            # Log but don't fail - return None to allow graceful degradation
            logger.warning(f"JS evaluation error: {e}")
            return None

    async def _get_page_complexity(self) -> dict[str, Any] | None:
        """Quick page complexity check before full extraction.

        Used to detect heavy pages and switch to lightweight extraction mode.

        Returns:
            Dict with elementCount, interactiveCount, scriptCount, isHeavy
            or None if check fails
        """
        return await self._evaluate_with_timeout(
            """(() => ({
                elementCount: document.querySelectorAll('*').length,
                interactiveCount: document.querySelectorAll('button, a, input, textarea, select').length,
                scriptCount: document.scripts.length,
                iframeCount: document.querySelectorAll('iframe').length,
                isHeavy: document.querySelectorAll('*').length > """
            + str(HEAVY_PAGE_THRESHOLD)
            + """
            }))()""",
            timeout_ms=1000,  # Very quick check
        )

    async def _quick_page_size_check(self) -> dict[str, Any] | None:
        """Quick page size check BEFORE expensive DOM operations.

        This runs before smart scroll and element extraction to detect heavy pages proactively.
        Priority 1: Crash prevention - check HTML size and DOM count with minimal overhead.

        Returns:
            Dict with htmlSize, domCount, isHeavy or None if check fails
        """
        if not self.page:
            return None

        return await self._evaluate_with_timeout(
            f"""(() => {{
                const htmlSize = document.documentElement.innerHTML.length;
                const domCount = document.querySelectorAll('*').length;
                return {{
                    htmlSize: htmlSize,
                    domCount: domCount,
                    isHeavy: htmlSize > {get_settings().browser_heavy_page_html_size_threshold} ||
                             domCount > {get_settings().browser_heavy_page_dom_threshold}
                }};
            }})()""",
            timeout_ms=QUICK_SIZE_CHECK_TIMEOUT_MS,
        )

    def _is_wikipedia_url(self, url: str) -> bool:
        """Check if URL is a Wikipedia page.

        Args:
            url: URL to check

        Returns:
            True if URL is Wikipedia, False otherwise
        """
        if not url:
            return False
        return any(domain in url.lower() for domain in WIKIPEDIA_DOMAINS)

    async def _extract_wikipedia_summary(self) -> dict[str, Any]:
        """Extract lightweight summary from Wikipedia page.

        Priority 1: Memory optimization - extract only lead section to prevent crashes.
        Skips tables, references, navigation, and sidebars.

        Returns:
            Dict with title, summary, url
        """
        if not self.page:
            return {"title": "", "summary": "", "content": "", "text": "", "url": ""}

        try:
            summary_data = await self._evaluate_with_timeout(
                """(() => {
                    const title = document.querySelector('#firstHeading')?.textContent || document.title;
                    const content = document.querySelector('#mw-content-text .mw-parser-output');

                    if (!content) {
                        return {title: title, summary: '', paragraphs: 0};
                    }

                    // Extract only first 3 paragraphs (lead section)
                    const paragraphs = Array.from(content.querySelectorAll('p'))
                        .slice(0, 3)
                        .map(p => p.textContent.trim())
                        .filter(text => text.length > 0);

                    return {
                        title: title,
                        summary: paragraphs.join('\\n\\n'),
                        paragraphs: paragraphs.length
                    };
                })()""",
                timeout_ms=2000,
            )

            if summary_data:
                logger.info(
                    f"Extracted Wikipedia summary: {summary_data.get('paragraphs', 0)} paragraphs, "
                    f"{len(summary_data.get('summary', ''))} chars"
                )
                return {
                    "title": summary_data.get("title", ""),
                    "summary": summary_data.get("summary", ""),
                    "content": summary_data.get("summary", ""),
                    "text": summary_data.get("summary", ""),
                    "url": self.page.url,
                    "mode": "wikipedia_summary",
                }
        except Exception as e:
            logger.warning(f"Wikipedia summary extraction failed: {e}")

        return {"title": "", "summary": "", "content": "", "text": "", "url": self.page.url if self.page else ""}

    async def _check_memory_pressure(self) -> dict[str, Any] | None:
        """Check browser memory usage via CDP Performance.getMetrics().

        Priority 1: Proactive crash prevention - detect memory pressure before browser crashes.

        Returns:
            Dict with used_mb, total_mb, pressure_level (low/medium/high/critical) or None
        """
        if not self.page:
            return None

        cdp_session = None
        try:
            # Get CDP session
            cdp_session = await self.page.context.new_cdp_session(self.page)

            # Get performance metrics
            metrics = await cdp_session.send("Performance.getMetrics")

            # Extract memory metrics
            metrics_dict = {m["name"]: m["value"] for m in metrics.get("metrics", [])}

            js_heap_used = metrics_dict.get("JSHeapUsedSize", 0) / (1024 * 1024)  # Convert to MB
            js_heap_total = metrics_dict.get("JSHeapTotalSize", 0) / (1024 * 1024)
            nodes = metrics_dict.get("Nodes", 0)

            # Determine pressure level
            settings = get_settings()
            if js_heap_used > settings.browser_memory_critical_threshold_mb or nodes > 10000:
                pressure_level = "critical"
            elif js_heap_used > settings.browser_memory_high_threshold_mb:
                pressure_level = "high"
            elif js_heap_used > 300:  # 300MB
                pressure_level = "medium"
            else:
                pressure_level = "low"

            return {
                "used_mb": round(js_heap_used, 2),
                "total_mb": round(js_heap_total, 2),
                "nodes": int(nodes),
                "pressure_level": pressure_level,
            }

        except Exception as e:
            logger.debug(f"Memory pressure check failed: {e}")
            return None
        finally:
            # Always detach CDP session to prevent leaks
            if cdp_session is not None:
                try:
                    await cdp_session.detach()
                except Exception as e:
                    logger.debug(f"Failed to detach CDP session: {e}")

    async def _force_window_position(
        self, page: Page, x: int = 0, y: int = 0, width: int = 1280, height: int = 1024
    ) -> bool:
        """Force browser window to specific position using CDP.

        This is critical for live preview display - Chrome's --window-position flag only affects
        the FIRST window. Subsequent windows created by new_page() will be offset.
        Using CDP Browser.setWindowBounds forces the window to the correct position.

        Args:
            page: The page whose window to position
            x: Left position (default 0)
            y: Top position (default 0)
            width: Window width (default 1280 for stable live preview rendering)
            height: Window height (default 1024 for stable live preview rendering)

        Returns:
            bool: True if positioning succeeded, False otherwise
        """
        if not self.context or not page:
            return False

        cdp_session = None
        try:
            cdp_session = await self.context.new_cdp_session(page)

            # Get the window ID for this page's target
            result = await cdp_session.send("Browser.getWindowForTarget")
            window_id = result.get("windowId")

            if not window_id:
                logger.warning("Could not get windowId for page")
                return False

            # First ensure window is in normal state (not maximized) so bounds can be set
            await cdp_session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {"windowState": "normal"},
                },
            )

            # Set window bounds to force position at 0,0 with exact expected size
            expected_bounds = {"left": x, "top": y, "width": width, "height": height}
            await cdp_session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": expected_bounds,
                },
            )

            # Readback bounds to verify they were applied correctly
            readback = await cdp_session.send("Browser.getWindowBounds", {"windowId": window_id})
            actual_bounds = readback.get("bounds", {})
            actual_left = actual_bounds.get("left", -1)
            actual_top = actual_bounds.get("top", -1)

            # Check if bounds match (allow small tolerance for WM adjustments)
            if actual_left != x or actual_top != y:
                logger.warning(
                    f"Window bounds mismatch after first attempt: expected ({x}, {y}), "
                    f"got ({actual_left}, {actual_top}). Retrying..."
                )
                # Retry once - sometimes WM needs a moment
                await asyncio.sleep(0.1)
                await cdp_session.send(
                    "Browser.setWindowBounds",
                    {
                        "windowId": window_id,
                        "bounds": expected_bounds,
                    },
                )
                # Final readback
                readback = await cdp_session.send("Browser.getWindowBounds", {"windowId": window_id})
                actual_bounds = readback.get("bounds", {})
                actual_left = actual_bounds.get("left", -1)
                actual_top = actual_bounds.get("top", -1)

                if actual_left != x or actual_top != y:
                    logger.error(
                        f"Window bounds still incorrect after retry: expected ({x}, {y}), "
                        f"got ({actual_left}, {actual_top})"
                    )
                    return False

            logger.info(
                f"Forced window position via CDP: ({actual_left}, {actual_top}) "
                f"size {actual_bounds.get('width', 0)}x{actual_bounds.get('height', 0)}"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to force window position via CDP: {e}")
            return False
        finally:
            if cdp_session:
                with contextlib.suppress(Exception):
                    await cdp_session.detach()

    async def _new_page_with_bounds(self, context: BrowserContext | None = None) -> Page:
        """Create a new page with proper window positioning for live preview display.

        This is the ONLY correct way to create a new page in this class.
        It ensures the browser window is positioned at (0,0) to avoid live preview offset issues.

        Args:
            context: Browser context to create page in. Uses self.context if not provided.

        Returns:
            Page: The newly created and positioned page

        Raises:
            Exception: If no context available or page creation fails
        """
        ctx = context or self.context
        if not ctx:
            from app.domain.exceptions.browser import BrowserError, BrowserErrorCode

            raise BrowserError(
                message="No browser context available for creating new page",
                code=BrowserErrorCode.BROWSER_CRASHED,
                recoverable=True,
            )

        page = await ctx.new_page()
        logger.info(f"Created new page (total pages in context: {len(ctx.pages)})")

        # CRITICAL: Always force window position after creating new page
        # New windows may be offset by the WM without this
        success = await self._force_window_position(page)
        if not success:
            logger.warning("Failed to force window position on new page - live preview display may be offset")

        # Small delay to let WM settle after positioning
        await asyncio.sleep(0.05)

        return page

    async def _setup_route_interception(self, context: BrowserContext) -> None:
        """Set up network route interception for optional resource blocking.

        Only blocks resource types (images, fonts, etc.) when block_resources=True.
        No ad blocking — removed to avoid breaking legitimate browsing.

        Args:
            context: Browser context to configure routes on
        """
        if not self.block_resources:
            logger.debug("Network route interception skipped (no blocking enabled)")
            return

        async def route_handler(route):
            request = route.request
            resource_type = request.resource_type

            if resource_type in self.blocked_types:
                await route.abort()
                return

            # SSRF protection: block subrequests/redirects to internal addresses
            ssrf_reason = is_ssrf_target(request.url)
            if ssrf_reason:
                # Chrome internal URLs (chrome://, chrome-extension://) are expected noise
                # from the browser engine — log at debug to avoid spamming warnings
                if request.url.startswith(("chrome://", "chrome-extension://")):
                    logger.debug("SSRF blocked (chrome internal): %s → %s", request.url, ssrf_reason)
                else:
                    logger.warning("SSRF blocked (subrequest): %s → %s", request.url, ssrf_reason)
                await route.abort()
                return

            await route.continue_()

        await context.route("**/*", route_handler)
        logger.debug(f"Network route interception configured (resource blocking: {self.blocked_types})")

    async def _show_cursor_click(self, x: float, y: float) -> None:
        """Show cursor animation at the specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        if not self.page or not self._dom_cursor_enabled:
            return

        try:
            await self.page.evaluate(f"window.__animateAgentClick && window.__animateAgentClick({x}, {y})")
            # Brief pause to let animation be visible
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.debug(f"Could not show cursor animation: {e}")

    async def _setup_dialog_handlers(self, page: Page) -> None:
        """Set up automatic dialog/popup handlers for the page.

        Automatically dismisses:
        - Alert dialogs
        - Confirm dialogs (accepts or dismisses based on context)
        - Prompt dialogs
        - beforeunload dialogs

        Args:
            page: Page to configure handlers on
        """

        async def handle_dialog(dialog):
            dialog_type = dialog.type
            message = dialog.message[:100] if dialog.message else ""
            logger.info(f"Auto-dismissing {dialog_type} dialog: {message}")

            try:
                if dialog_type == "beforeunload":
                    # Accept beforeunload to allow navigation
                    await dialog.accept()
                elif dialog_type == "confirm":
                    # Dismiss confirms (usually "Leave page?" or "Are you sure?")
                    await dialog.dismiss()
                elif dialog_type == "prompt":
                    # Dismiss prompts
                    await dialog.dismiss()
                else:
                    # Dismiss alerts
                    await dialog.dismiss()
            except Exception as e:
                logger.debug(f"Error handling dialog: {e}")

        page.on("dialog", handle_dialog)
        logger.debug("Dialog handlers configured")

    async def _inject_overlay_scrollbar_css(self) -> None:
        """Inject CSS to make scrollbars overlay content instead of taking width.

        This ensures the full viewport width is available for content rendering,
        preventing content cutoff on the right side when scrollbars appear.
        """
        if not self.page:
            return

        try:
            await self.page.add_init_script("""
                (function() {
                    // Create style element for overlay scrollbars
                    const style = document.createElement('style');
                    style.id = 'agent-overlay-scrollbar';
                    style.textContent = `
                        /* Make scrollbars overlay content instead of taking width */
                        * {
                            scrollbar-width: thin;
                        }
                        *::-webkit-scrollbar {
                            width: 8px;
                            height: 8px;
                        }
                        *::-webkit-scrollbar-track {
                            background: transparent;
                        }
                        *::-webkit-scrollbar-thumb {
                            background-color: rgba(155, 155, 155, 0.5);
                            border-radius: 4px;
                        }
                        *::-webkit-scrollbar-thumb:hover {
                            background-color: rgba(155, 155, 155, 0.7);
                        }
                        /* Ensure html and body use overlay scrollbar behavior */
                        html, body {
                            overflow: overlay !important;
                            scrollbar-gutter: auto !important;
                        }
                    `;

                    // Inject as soon as possible
                    if (document.head) {
                        document.head.appendChild(style);
                    } else {
                        document.addEventListener('DOMContentLoaded', () => {
                            document.head.appendChild(style);
                        });
                    }
                })();
            """)
            logger.debug("Overlay scrollbar CSS injected")
        except Exception as e:
            logger.debug(f"Failed to inject overlay scrollbar CSS: {e}")

    async def _inject_cursor_indicator(self) -> None:
        """Inject visual cursor indicator for agent actions.

        Shows a visible cursor/pointer that follows agent clicks,
        giving users visual feedback that the agent is working.
        """
        if not self.page or not self._dom_cursor_enabled:
            return

        try:
            await self.page.add_init_script("""
                (function() {
                    // Create cursor element
                    const cursor = document.createElement('div');
                    cursor.id = 'agent-cursor';
                    cursor.style.cssText = `
                        position: fixed;
                        width: 20px;
                        height: 20px;
                        border: 3px solid #7c3aed;
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999999;
                        transition: all 0.15s ease-out;
                        display: none;
                        box-shadow: 0 0 10px rgba(124, 58, 237, 0.5);
                    `;

                    // Create click ripple effect
                    const ripple = document.createElement('div');
                    ripple.id = 'agent-cursor-ripple';
                    ripple.style.cssText = `
                        position: fixed;
                        width: 40px;
                        height: 40px;
                        border: 2px solid #7c3aed;
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999998;
                        opacity: 0;
                        transform: scale(0);
                    `;

                    document.addEventListener('DOMContentLoaded', () => {
                        document.body.appendChild(cursor);
                        document.body.appendChild(ripple);
                    });

                    // Also append immediately if DOM is ready
                    if (document.body) {
                        document.body.appendChild(cursor);
                        document.body.appendChild(ripple);
                    }

                    // Global function to show cursor at position
                    window.__showAgentCursor = function(x, y) {
                        const c = document.getElementById('agent-cursor');
                        if (c) {
                            c.style.left = (x - 10) + 'px';
                            c.style.top = (y - 10) + 'px';
                            c.style.display = 'block';
                        }
                    };

                    // Global function to animate click
                    window.__animateAgentClick = function(x, y) {
                        const c = document.getElementById('agent-cursor');
                        const r = document.getElementById('agent-cursor-ripple');

                        if (c) {
                            c.style.left = (x - 10) + 'px';
                            c.style.top = (y - 10) + 'px';
                            c.style.display = 'block';
                            c.style.transform = 'scale(0.8)';
                            setTimeout(() => { c.style.transform = 'scale(1)'; }, 100);
                        }

                        if (r) {
                            r.style.left = (x - 20) + 'px';
                            r.style.top = (y - 20) + 'px';
                            r.style.opacity = '1';
                            r.style.transform = 'scale(1)';
                            r.style.transition = 'none';

                            setTimeout(() => {
                                r.style.transition = 'all 0.4s ease-out';
                                r.style.opacity = '0';
                                r.style.transform = 'scale(2)';
                            }, 10);
                        }
                    };

                    // Global function to hide cursor
                    window.__hideAgentCursor = function() {
                        const c = document.getElementById('agent-cursor');
                        if (c) c.style.display = 'none';
                    };
                })();
            """)
            logger.debug("Cursor indicator script injected")
        except Exception as e:
            logger.debug(f"Failed to inject cursor indicator: {e}")

    async def _inject_anti_detection_scripts(self) -> None:
        """Inject scripts to evade bot detection.

        These scripts modify browser properties that are commonly checked
        by anti-bot systems to detect automation.
        """
        if not self.page:
            return

        # First inject cursor indicator
        await self._inject_cursor_indicator()

        # Inject overlay scrollbar CSS to prevent width cutoff
        await self._inject_overlay_scrollbar_css()

        try:
            # Inject scripts before any page loads
            await self.page.add_init_script("""
                // Override webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // Override automation indicators
                delete navigator.__proto__.webdriver;

                // Mock plugins array (empty indicates headless)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        return [
                            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                            { name: 'Native Client', filename: 'internal-nacl-plugin' }
                        ];
                    },
                });

                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });

                // Mock platform if needed
                if (navigator.platform === '') {
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32',
                    });
                }

                // Override permissions query for notifications
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Remove Chromium automation flags from window.chrome
                if (window.chrome) {
                    window.chrome.runtime = {
                        PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
                        PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
                        PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
                        RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
                        OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
                        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }
                    };
                }

                // Console logging cleanup (some bots are detected by console logs)
                const originalConsoleDebug = console.debug;
                console.debug = function(...args) {
                    if (args[0] && typeof args[0] === 'string' && args[0].includes('puppeteer')) {
                        return;
                    }
                    return originalConsoleDebug.apply(console, args);
                };
            """)
            logger.debug("Anti-detection scripts injected")
        except Exception as e:
            logger.warning(f"Failed to inject anti-detection scripts: {e}")

    def _on_page_crash(self) -> None:
        """Handle page crash event (Playwright best practice).

        Called when the page crashes, typically due to excessive memory allocation.
        Sets connection as unhealthy so the next operation triggers re-initialization.
        Guard prevents duplicate log emissions when Playwright fires the event
        multiple times (e.g. across pooled connection listeners).
        """
        if self._connection_healthy:
            logger.error(f"Page crash detected (CDP: {self.cdp_url}) - marking connection unhealthy")
            self._connection_healthy = False

    def _on_browser_disconnected(self) -> None:
        """Handle browser disconnection event (Playwright best practice).

        Fires when browser application closes, crashes, or CDP connection drops.
        Different from page.on('crash') which only fires for renderer crashes.
        This catches browser process death (kill -9, OOM killer, supervisord restart).

        Skips reconnect during intentional shutdown (cleanup/close) to prevent
        task leaks and false reconnect noise.
        """
        if self._shutting_down:
            logger.debug("Browser disconnected during intentional shutdown; skipping reconnect")
            return

        logger.error(f"Browser disconnected (CDP: {self.cdp_url}) - marking connection unhealthy")
        self._connection_healthy = False
        with contextlib.suppress(RuntimeError):
            self._track_background_task(self._proactive_reconnect())

    async def _proactive_reconnect(self, delay: float = 3.0) -> None:
        """Reconnect after browser disconnect with a short delay.

        Waits briefly for supervisord to restart the Chrome process, then
        re-initializes the Playwright connection so the browser is ready
        before the next user operation arrives.

        Args:
            delay: Seconds to wait before attempting reconnect (allows Chrome to restart).
        """
        await asyncio.sleep(delay)
        if self._connection_healthy:
            return  # Already recovered via a concurrent operation
        logger.info(f"Proactive reconnect attempt after browser disconnect (CDP: {self.cdp_url})")
        try:
            await self._ensure_browser()
            if self._connection_healthy:
                logger.info(f"Proactive reconnect succeeded (CDP: {self.cdp_url})")
                # Reset viewport and verify window position to prevent
                # "zoomed in" screencast after recovery
                await self._verify_and_reset_viewport()
                # Notify recovery callback if registered
                if self._recovery_callback:
                    try:
                        await self._recovery_callback()
                    except Exception as cb_err:
                        logger.debug(f"Recovery callback failed: {cb_err}")
        except Exception as e:
            logger.warning(f"Proactive reconnect failed (CDP: {self.cdp_url}): {e} — will retry on next operation")

    # ── Background task lifecycle ──────────────────────────────────────

    def _track_background_task(self, coro) -> asyncio.Task:
        """Create a background task with automatic cleanup on completion."""
        task = asyncio.get_running_loop().create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _cancel_background_tasks(self) -> None:
        """Cancel all outstanding background tasks (keepalive, reconnects, etc.)."""
        tasks = [t for t in self._background_tasks if not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        self._keepalive_task = None

    # ── CDP keepalive ───────────────────────────────────────────────────

    def _start_keepalive(self) -> None:
        """Start the CDP keepalive loop if enabled and not already running."""
        if not self._keepalive_enabled:
            return
        if self._keepalive_task and not self._keepalive_task.done():
            return  # Already running
        try:
            self._keepalive_task = self._track_background_task(self._keepalive_loop())
            logger.debug("CDP keepalive started (interval=%.1fs)", self._keepalive_interval)
        except RuntimeError:
            pass  # No running event loop

    async def _stop_keepalive(self) -> None:
        """Stop the CDP keepalive loop."""
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._keepalive_task
        self._keepalive_task = None

    async def _keepalive_loop(self) -> None:
        """Periodic keepalive loop — runs until cancelled."""
        while True:
            await asyncio.sleep(self._keepalive_interval)
            if self._shutting_down:
                return
            await self._keepalive_ping()

    async def _keepalive_ping(self) -> None:
        """Send a single keepalive probe to the browser.

        Skips when shutting down, already unhealthy, or navigation is in progress.
        Treats 'Execution context was destroyed' as a navigation race (non-fatal).
        """
        if self._shutting_down:
            return
        if not self._connection_healthy:
            return
        if self._navigation_lock.locked():
            logger.debug("Keepalive skipped: navigation in progress")
            return
        if self._is_page_closed(self.page):
            return

        try:
            await asyncio.wait_for(
                self.page.evaluate("() => true"),
                timeout=self._quick_health_check_timeout,
            )
        except Exception as exc:
            if "Execution context was destroyed" in str(exc):
                logger.debug("Keepalive: execution context destroyed (navigation race) — non-fatal")
                return
            logger.warning("CDP keepalive probe failed: %s", exc)
            self._connection_healthy = False
            # Schedule proactive reconnect
            with contextlib.suppress(RuntimeError):
                self._track_background_task(self._proactive_reconnect())

    def is_healthy(self) -> bool:
        """Synchronous health check for fast-path routing.

        Returns:
            bool: True if browser components are initialized and page is open.
        """
        return bool(
            self.playwright
            and self.browser
            and self.context
            and self.page
            and not self.page.is_closed()
            and self._connection_healthy
        )

    async def _verify_connection_health(self) -> bool:
        """Verify the browser connection is healthy.

        Checks:
        1. Page is open and responsive (JS evaluation)
        2. Viewport dimensions match expected values (logs drift, best-effort)

        Returns:
            bool: True if connection is healthy, False otherwise
        """
        try:
            if not self.page or self.page.is_closed():
                return False
            # Simple evaluation to verify connection (uses page's default timeout)
            await self.page.evaluate("() => true")

            # Lightweight viewport sanity check — log drift but don't fail health check
            try:
                vp = self.page.viewport_size
                if vp:
                    expected_w = self._current_viewport.get("width", DEFAULT_VIEWPORT["width"])
                    expected_h = self._current_viewport.get("height", DEFAULT_VIEWPORT["height"])
                    if vp["width"] != expected_w or vp["height"] != expected_h:
                        logger.warning(
                            f"Viewport drift detected: {vp['width']}x{vp['height']} "
                            f"(expected {expected_w}x{expected_h})"
                        )
            except Exception:
                logger.debug("Viewport size check skipped (best-effort)")

            return True
        except Exception as e:
            if self._is_crash_error(e):
                logger.error(f"Browser crash detected during health check: {e}")
                self._connection_healthy = False
            else:
                logger.warning(f"Connection health check failed: {e}")
            return False

    async def _verify_and_reset_viewport(self) -> None:
        """Verify and reset viewport + window position after crash recovery.

        After a browser crash, the recovered page may have wrong viewport
        dimensions or window position, causing the CDP screencast to appear
        "zoomed in" on the frontend. This method:
        1. Resets viewport to DEFAULT_VIEWPORT (1280x900)
        2. Verifies window position is at (0,0) via CDP
        3. Corrects position if displaced

        Called after successful recovery in _ensure_browser() and
        _proactive_reconnect(). Safe to call multiple times (idempotent).

        Validated against:
        - Playwright docs: set_viewport_size before navigation (Context7)
        - CDP Browser.getWindowBounds / setWindowBounds (Ref AI)
        """
        if not self.page or not self.context:
            return

        # Step 1: Reset viewport to known dimensions
        try:
            await self.page.set_viewport_size(DEFAULT_VIEWPORT)
            self._current_viewport = DEFAULT_VIEWPORT
            logger.info(f"Viewport reset to {DEFAULT_VIEWPORT['width']}x{DEFAULT_VIEWPORT['height']} after recovery")
        except Exception as e:
            logger.warning(f"Failed to reset viewport after recovery: {e}")

        # Step 2: Verify window position via CDP (lightweight check)
        cdp_session = None
        try:
            cdp_session = await self.context.new_cdp_session(self.page)
            result = await cdp_session.send("Browser.getWindowForTarget")
            window_id = result.get("windowId")
            if window_id:
                readback = await cdp_session.send("Browser.getWindowBounds", {"windowId": window_id})
                actual = readback.get("bounds", {})
                actual_left = actual.get("left", 0)
                actual_top = actual.get("top", 0)

                if actual_left != 0 or actual_top != 0:
                    logger.warning(
                        f"Window displaced after recovery: ({actual_left}, {actual_top}). Forcing to (0, 0)."
                    )
                    await self._force_window_position(self.page)
                else:
                    logger.debug("Window position verified at (0, 0) after recovery")
        except Exception as e:
            logger.debug(f"Window position check after recovery failed: {e}")
        finally:
            if cdp_session:
                with contextlib.suppress(Exception):
                    await cdp_session.detach()

    async def clear_session(self) -> None:
        """Clear browser state while preserving the original window position.

        This method clears browser state for a fresh session, but PRESERVES the first
        window to avoid live preview positioning issues. When context.new_page() is called,
        Chrome creates a NEW WINDOW (not a tab), which may appear shifted right
        since only the first window respects --window-position=0,0.

        Strategy:
        1. Keep the first page (original window at position 0,0)
        2. Navigate it to about:blank to clear state
        3. Close all additional pages/windows
        """
        if not self.browser:
            return

        try:
            for context in self.browser.contexts:
                pages = context.pages
                if not pages:
                    continue

                logger.info(f"Clearing browser session: {len(pages)} pages found")

                # Keep the first page (original window) - just clear its content
                first_page = pages[0]
                try:
                    if not first_page.is_closed():
                        try:
                            await first_page.goto("about:blank", timeout=5000)
                            logger.debug("Cleared first page (preserved original window)")
                        except Exception as e:
                            logger.debug(f"Error navigating first page to blank: {e}")
                except Exception as e:
                    logger.debug(f"Error clearing first page: {e}")

                # Close all additional pages (they create new windows which shift right)
                for page in pages[1:]:
                    try:
                        if not page.is_closed():
                            with contextlib.suppress(Exception):
                                await page.goto("about:blank", timeout=5000)
                            await page.close()
                            logger.debug("Closed additional page/window")
                    except Exception as e:
                        logger.debug(f"Error closing page during session clear: {e}")

                # Update our page reference to the preserved first page
                if not first_page.is_closed():
                    self.page = first_page
        except Exception as e:
            logger.warning(f"Error during session clear: {e}")

    async def export_storage_state(self) -> dict[str, Any] | None:
        """Export current Playwright storage state (cookies + origin localStorage)."""
        try:
            await self._ensure_browser()
            if not self.context:
                return None
            return await self.context.storage_state()
        except Exception as e:
            logger.warning("Failed to export browser storage state: %s", e)
            return None

    async def import_storage_state(self, storage_state: dict[str, Any]) -> bool:
        """Restore cookies and origin localStorage from a Playwright storageState payload."""
        if not storage_state:
            return False

        try:
            await self._ensure_browser()
            if not self.context:
                return False

            cookies = storage_state.get("cookies")
            if isinstance(cookies, list):
                with contextlib.suppress(Exception):
                    await self.context.clear_cookies()
                if cookies:
                    await self.context.add_cookies(cookies)

            origins = storage_state.get("origins")
            if not isinstance(origins, list):
                return True

            page = self.page
            if page is None or page.is_closed():
                existing_pages = [p for p in self.context.pages if not p.is_closed()]
                page = existing_pages[0] if existing_pages else None

            if page is None:
                # Cookies were restored, but no page exists to replay localStorage entries.
                return True

            for origin_state in origins:
                if not isinstance(origin_state, dict):
                    continue
                origin_url = origin_state.get("origin")
                raw_local_storage = origin_state.get("localStorage")
                if not isinstance(origin_url, str) or not origin_url:
                    continue
                if not isinstance(raw_local_storage, list) or not raw_local_storage:
                    continue

                local_storage_entries = []
                for item in raw_local_storage:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("name")
                    if not isinstance(key, str) or not key:
                        continue
                    value = item.get("value")
                    local_storage_entries.append({"name": key, "value": "" if value is None else str(value)})

                if not local_storage_entries:
                    continue

                try:
                    await page.goto(origin_url, wait_until="domcontentloaded", timeout=10000)
                    await page.evaluate(
                        """(entries) => {
                            for (const entry of entries) {
                                if (!entry || typeof entry.name !== 'string') continue;
                                localStorage.setItem(entry.name, String(entry.value ?? ''));
                            }
                        }""",
                        local_storage_entries,
                    )
                except Exception as e:
                    logger.debug("Skipping localStorage restore for %s: %s", origin_url, e)

            return True
        except Exception as e:
            logger.warning("Failed to import browser storage state: %s", e)
            return False

    async def initialize(self, clear_existing: bool = False) -> bool:
        """Initialize browser connection with proper configuration

        Features:
        - Exponential backoff retry logic
        - Proper browser context configuration (viewport, user agent, timezone)
        - Optional network interception for performance
        - Connection health verification

        Args:
            clear_existing: Whether to close all existing pages/tabs (default: False)

        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        max_retries = 3
        retry_delay = 1.0  # Initial wait 1s
        cdp_connect_timeout_ms = 15000

        for attempt in range(max_retries):
            try:
                # Stop any existing Playwright instance to prevent subprocess leaks
                if self.playwright is not None:
                    with contextlib.suppress(Exception):
                        await self.playwright.stop()
                    self.playwright = None

                self.playwright = await async_playwright().start()

                # Connect to existing Chrome instance via CDP
                self.browser = await self.playwright.chromium.connect_over_cdp(
                    self.cdp_url,
                    timeout=cdp_connect_timeout_ms,
                )

                # Clear existing pages for fresh session
                if clear_existing:
                    await asyncio.wait_for(self.clear_session(), timeout=5.0)

                # Get existing contexts or prepare to create new one
                contexts = self.browser.contexts

                if contexts:
                    # ALWAYS use the default (first) context - this is the visible one in live preview
                    self.context = contexts[0]
                    pages = self.context.pages

                    logger.info(
                        f"Using existing default context with {len(pages)} page(s) - will be visible in live preview"
                    )

                    # CRITICAL: Reuse ANY existing page to avoid creating new windows
                    # New windows can desync from the active live-preview capture surface.
                    reuse_page = None
                    if len(pages) > 0:
                        # Prefer to reuse the FIRST page (original Chrome window at position 0,0)
                        try:
                            candidate_page = pages[0]
                            # Check if page is usable
                            if not candidate_page.is_closed():
                                reuse_page = candidate_page
                                page_url = await candidate_page.evaluate("window.location.href")
                                logger.info(
                                    f"Reusing existing page (URL: {page_url[:100]}) to avoid creating new window"
                                )
                        except Exception as e:
                            logger.debug(f"Could not reuse page[0]: {e}")
                            # Try other pages if first one failed
                            for page in pages[1:]:
                                try:
                                    if not page.is_closed():
                                        reuse_page = page
                                        logger.info("Reusing alternate existing page")
                                        break
                                except (PlaywrightError, OSError):
                                    logger.debug("Failed to check if page is closed", exc_info=True)
                                    continue

                    if reuse_page:
                        # Clear heavy content from previous session before reusing
                        # (P0.2: Navigate to about:blank to prevent ad network thread saturation)
                        try:
                            await reuse_page.goto("about:blank", timeout=5000)
                            logger.info("Cleared existing page to about:blank before reuse")
                        except Exception as clear_error:
                            # If we can't even navigate to blank, close and create fresh
                            logger.warning(f"Failed to clear page, will create new: {clear_error}")
                            try:
                                await reuse_page.close()
                            except Exception as close_error:
                                logger.debug(f"Failed to close page: {close_error}")
                            reuse_page = None
                            # Create new page with proper window positioning
                            self.page = await self._new_page_with_bounds(self.context)
                        else:
                            self.page = reuse_page
                            if attempt > 0:
                                # Recovery path: verify viewport + window position
                                # to prevent "zoomed in" screencast appearance
                                await self._verify_and_reset_viewport()
                                logger.info("Reusing existing page after recovery - viewport verified")
                            else:
                                # Normal path: window is positioned by Chrome's launch flags
                                logger.info("Reusing existing page - keeping current window position")
                    else:
                        # Last resort: Create new page with proper window positioning
                        logger.warning("No existing pages available, creating new page with bounds")
                        self.page = await self._new_page_with_bounds(self.context)

                    # Ensure the page is brought to front and visible in live preview
                    await self._ensure_page_visible()
                else:
                    # No contexts exist yet - wait for Chrome to create default context
                    # IMPORTANT: Do NOT use browser.new_context() as it creates an isolated
                    # context that is NOT visible in live preview. live preview only shows the default Chrome window.
                    logger.warning("No browser contexts found, waiting for Chrome default context...")

                    # Wait up to 5 seconds for Chrome to create its default context
                    for i in range(10):
                        await asyncio.sleep(0.5)
                        contexts = self.browser.contexts
                        if contexts:
                            logger.info(f"Default context appeared after {(i + 1) * 0.5}s")
                            break

                    if contexts:
                        # Use the default context that appeared
                        self.context = contexts[0]
                        pages = self.context.pages
                        if pages:
                            self.page = pages[0]
                            logger.info("Using default context's existing page - keeping current window position")
                        else:
                            # Create new page with proper window positioning
                            self.page = await self._new_page_with_bounds(self.context)
                    else:
                        # Last resort: Still no contexts, this shouldn't happen with a running Chrome
                        # Create page via CDP's default mechanism instead of isolated context
                        logger.error("No contexts after waiting - Chrome may not be properly initialized")
                        # Try to create a page directly, which will use default context
                        self.context = await self.browser.new_context()
                        self.page = await self._new_page_with_bounds(self.context)
                        logger.warning("Created new context as fallback - live preview may show different content")

                    # Set fingerprint values for consistency
                    if self._randomize_fingerprint:
                        self._current_user_agent, self._current_viewport, self._current_timezone = (
                            self._randomize_browser_fingerprint()
                        )
                    else:
                        self._current_user_agent = DEFAULT_USER_AGENT
                        self._current_viewport = DEFAULT_VIEWPORT
                        self._current_timezone = DEFAULT_TIMEZONE

                # Set up network interception if enabled
                await self._setup_route_interception(self.context)

                # Set up automatic dialog/popup handlers
                await self._setup_dialog_handlers(self.page)

                # Register crash handlers (Playwright best practice)
                self.page.on("crash", lambda: self._on_page_crash())
                self.browser.on("disconnected", lambda: self._on_browser_disconnected())

                # Configure default timeouts
                self.page.set_default_timeout(30000)  # 30 seconds for operations
                self.page.set_default_navigation_timeout(60000)  # 60 seconds for navigation

                # Verify connection is healthy
                self._connection_healthy = await self._verify_connection_health()
                if not self._connection_healthy:
                    from app.domain.exceptions.browser import BrowserError, BrowserErrorCode

                    raise BrowserError(
                        message="Connection health verification failed",
                        code=BrowserErrorCode.CONNECTION_REFUSED,
                        recoverable=True,
                    )

                logger.info(f"Browser initialized successfully (attempt {attempt + 1})")

                # After recovery (attempt > 0), reset viewport and window
                # position to prevent "zoomed in" screencast on frontend
                if attempt > 0:
                    await self._verify_and_reset_viewport()

                # Reset shutdown flag and start keepalive
                self._shutting_down = False
                self._start_keepalive()

                return True

            except Exception as e:
                # Phase 1: Record crash if it's a crash error
                if self._is_crash_error(e):
                    self._record_crash()

                # Clean up failed resources
                await self.cleanup()

                if attempt == max_retries - 1:
                    logger.error(f"Browser initialization failed after {max_retries} attempts: {e}")
                    return False

                # Exponential backoff with cap
                retry_delay = min(retry_delay * 2, 4)

                # Phase 1: Emit progress during recovery
                # NOTE: Direct event emission not available in browser class
                # Progress logged here can be picked up by monitoring/logs
                logger.warning(
                    f"Browser crashed, recovering... (attempt {attempt + 2}/{max_retries}, "
                    f"retrying in {retry_delay}s): {e}"
                )

                await asyncio.sleep(retry_delay)

        return False

    async def start(self, clear_existing: bool = False) -> bool:
        """Backward-compatible alias for initialize()."""
        return await self.initialize(clear_existing=clear_existing)

    async def _release_playwright_resources(self) -> None:
        """Release Playwright subprocess without closing Chrome pages.

        Used by restart() — Chrome stays running (managed by supervisord),
        we only disconnect Playwright's Node.js subprocess to avoid leaks.
        """
        # Stop Playwright subprocess (prevents Node.js zombie processes)
        if self.playwright is not None:
            with contextlib.suppress(Exception):
                await self.playwright.stop()

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

    async def cleanup(self):
        """Clean up Playwright resources safely

        Closes pages, contexts, browser connection, and Playwright instance
        in the correct order to avoid resource leaks.
        """
        self._shutting_down = True
        self._connection_healthy = False
        self._interactive_elements_cache = []

        # Cancel keepalive and any other background tasks before closing browser
        await self._cancel_background_tasks()

        try:
            # Close pages in all contexts
            if self.browser:
                for context in self.browser.contexts:
                    for page in context.pages:
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception as e:
                            logger.debug(f"Error closing page: {e}")

            # Close the current page if it still exists
            if self.page and not self.page.is_closed():
                try:
                    await self.page.close()
                except Exception as e:
                    logger.debug(f"Error closing current page: {e}")

            # Close context
            if self.context:
                try:
                    await self.context.close()
                except Exception as e:
                    logger.debug(f"Error closing context: {e}")

            # Close browser connection
            if self.browser:
                try:
                    await self.browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")

            # Stop Playwright instance
            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception as e:
                    logger.debug(f"Error stopping playwright: {e}")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

    async def close(self) -> None:
        """Backward-compatible alias for cleanup()."""
        await self.cleanup()

    async def _ensure_browser(self) -> None:
        """Ensure browser connection is active and healthy

        Raises:
            Exception: If browser cannot be initialized
        """
        # Check if we need to reinitialize
        needs_init = not self.browser or not self.page or not self._connection_healthy

        if needs_init:
            # Verify existing connection if we have one
            if self.browser and self.page:
                self._connection_healthy = await self._verify_connection_health()
                if self._connection_healthy:
                    return

            if not await self.initialize():
                from app.domain.exceptions.browser import BrowserError, BrowserErrorCode

                raise BrowserError(
                    message="Unable to initialize browser resources",
                    code=BrowserErrorCode.CONNECTION_REFUSED,
                    recoverable=False,
                )

    async def _ensure_page(self) -> None:
        """Ensure page is available and switch to most recent tab if needed

        This method ensures we're working with an active page, preferring
        the most recently opened tab in multi-tab scenarios.

        IMPORTANT: Avoids creating new pages when possible to prevent live preview positioning issues.
        """
        await self._ensure_browser()

        if self._is_page_closed(self.page):
            if not self.context:
                from app.domain.exceptions.browser import BrowserError, BrowserErrorCode

                raise BrowserError(
                    message="No browser context available",
                    code=BrowserErrorCode.BROWSER_CRASHED,
                    recoverable=True,
                )

            # CRITICAL: Try to reuse any existing page before creating a new one
            # New pages create new windows which may shift in live preview display
            pages = self.context.pages
            if pages:
                # Reuse the first available page
                for page in pages:
                    if not self._is_page_closed(page):
                        self.page = page
                        logger.info("Reused existing page in _ensure_page to avoid creating new window")
                        return

            # Last resort: Create new page with proper positioning
            logger.warning("No existing pages in _ensure_page, creating new page with bounds")
            self.page = await self._new_page_with_bounds(self.context)
            return

        # Switch to the most recent (rightmost) tab if there are multiple
        if self.context:
            pages = self.context.pages
            if pages and len(pages) > 1:
                rightmost_page = pages[-1]
                if self.page != rightmost_page and not self._is_page_closed(rightmost_page):
                    self.page = rightmost_page

    async def _smart_scroll_for_lazy_content(self, max_scrolls: int = 3, scroll_delay: float = 0.4) -> None:
        """Smart scroll through page to trigger lazy-loaded content.

        This method scrolls incrementally through the page to trigger
        lazy loading of images, infinite scroll content, and other
        dynamically loaded elements.

        Args:
            max_scrolls: Maximum number of scroll iterations (default: 3)
            scroll_delay: Delay in seconds between scrolls for content to load (default: 0.4)
        """
        await self._ensure_page()

        try:
            # Get initial page height
            initial_height = await self.page.evaluate("document.body.scrollHeight")
            viewport_height = await self.page.evaluate("window.innerHeight")

            # Calculate scroll increments (scroll by 80% of viewport each time)
            scroll_increment = int(viewport_height * 0.8)
            current_position = 0

            for i in range(max_scrolls):
                # Calculate target scroll position
                target_position = current_position + scroll_increment

                # Scroll to target position
                await self.page.evaluate(f"window.scrollTo({{top: {target_position}, behavior: 'smooth'}})")
                await asyncio.sleep(scroll_delay)

                # Check if we've reached the bottom
                current_scroll = await self.page.evaluate("window.scrollY")
                page_height = await self.page.evaluate("document.body.scrollHeight")

                # If page height increased (infinite scroll), continue
                if page_height > initial_height:
                    logger.debug(f"Page height increased from {initial_height} to {page_height} (lazy content loaded)")
                    initial_height = page_height

                # Check if we've reached the bottom
                if current_scroll + viewport_height >= page_height - 50:
                    logger.debug(f"Reached page bottom after {i + 1} scrolls")
                    break

                current_position = target_position

            # Scroll back to top for initial view
            await self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            await asyncio.sleep(0.2)

        except Exception as e:
            logger.debug(f"Smart scroll error (non-critical): {e}")
            # Fallback to simple scroll
            try:
                await self.page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
                await asyncio.sleep(0.3)
                await self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            except (PlaywrightError, PlaywrightTimeoutError, OSError):
                logger.debug("Failed to perform fallback scroll", exc_info=True)

    async def wait_for_page_load(self, timeout: int = 15000, wait_until: str = "domcontentloaded") -> bool:  # noqa: ASYNC109
        """Wait for page to reach specified load state using Playwright's native methods

        Args:
            timeout: Maximum wait time in milliseconds (default: 15000)
            wait_until: Load state to wait for. Options:
                - "load": Wait for the load event
                - "domcontentloaded": Wait for DOMContentLoaded event (faster, default)
                - "networkidle": Wait until no network connections for 500ms (slowest but most complete)

        Returns:
            bool: True if page loaded successfully, False on timeout
        """
        await self._ensure_page()

        try:
            await self.page.wait_for_load_state(wait_until, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            logger.warning(f"Page load timeout after {timeout}ms (wait_until={wait_until})")
            return False
        except Exception as e:
            logger.warning(f"Error waiting for page load: {e}")
            return False

    async def wait_for_navigation(self, timeout: int = 30000, wait_until: str = "domcontentloaded") -> bool:  # noqa: ASYNC109
        """Wait for navigation to complete after an action

        Args:
            timeout: Maximum wait time in milliseconds
            wait_until: Load state to wait for

        Returns:
            bool: True if navigation completed, False on timeout
        """
        await self._ensure_page()

        try:
            await self.page.wait_for_load_state(wait_until, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            logger.debug(f"Navigation wait timeout after {timeout}ms")
            return False
        except Exception as e:
            logger.debug(f"Navigation wait error: {e}")
            return False

    async def _extract_content(self) -> str:
        """Extract page content without LLM call (fast path).

        Optimized extraction that:
        - Uses timeout protection to prevent hangs on heavy pages
        - Prioritizes semantic HTML elements (main, article) for efficiency
        - Falls back to TreeWalker for text extraction
        - Removes LLM call (moved to agent layer per Browser-Use patterns)

        Returns:
            Extracted text content or error message
        """
        # Use optimized extraction with timeout protection
        content = await self._evaluate_with_timeout(
            f"""(() => {{
                const MAX_CHARS = 30000;
                const MAX_ELEMENTS = {MAX_CONTENT_ELEMENTS};

                // Priority 1: Semantic HTML main content areas
                const mainSelectors = ['main', 'article', '[role="main"]', '.content', '#content', '.post', '.entry'];
                for (const selector of mainSelectors) {{
                    const mainContent = document.querySelector(selector);
                    if (mainContent) {{
                        const text = mainContent.innerText?.trim();
                        if (text && text.length > 500) {{
                            return text.slice(0, MAX_CHARS);
                        }}
                    }}
                }}

                // Priority 2: Visible text in viewport using TreeWalker (more efficient than querySelectorAll)
                const viewportHeight = window.innerHeight * 2; // Include some below-fold content
                const texts = [];
                let charCount = 0;
                let elementCount = 0;

                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    {{
                        acceptNode: function(node) {{
                            // Skip script, style, and hidden elements
                            const parent = node.parentElement;
                            if (!parent) return NodeFilter.FILTER_REJECT;
                            const tag = parent.tagName;
                            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') {{
                                return NodeFilter.FILTER_REJECT;
                            }}
                            return NodeFilter.FILTER_ACCEPT;
                        }}
                    }}
                );

                let textNode;
                while ((textNode = walker.nextNode()) && charCount < MAX_CHARS && elementCount < MAX_ELEMENTS) {{
                    const text = textNode.textContent?.trim();
                    if (!text || text.length < 3) continue;

                    // Check if parent is reasonably visible
                    const parent = textNode.parentElement;
                    if (parent) {{
                        const rect = parent.getBoundingClientRect();
                        // Skip elements way below viewport
                        if (rect.top > viewportHeight) continue;
                        // Skip hidden elements (quick check without getComputedStyle)
                        if (parent.offsetParent === null && parent.tagName !== 'BODY') continue;
                    }}

                    texts.push(text);
                    charCount += text.length;
                    elementCount++;
                }}

                return texts.join('\\n') || 'No content extracted';
            }})()""",
            timeout_ms=3000,  # 3 second timeout for content extraction
        )

        if not content:
            logger.warning("Content extraction timed out or failed, returning fallback message")
            return (
                "Content extraction timed out - page may be too complex. Try browser_get_content for text-only fetch."
            )

        return content

    async def _extract_page_content(self) -> str:
        """Backward-compatible alias for page content extraction."""
        return await self._extract_content()

    async def view_page(self, wait_for_load: bool = True) -> ToolResult:
        """View visible elements within the current page's viewport.

        Optimized with:
        - Extraction caching (10s TTL) to skip duplicate extractions
        - Parallel extraction of elements and content
        - Page complexity detection for heavy pages
        - Timeout protection on all JavaScript evaluation

        Based on LangChain parallel execution patterns (Context7 research).

        Args:
            wait_for_load: Whether to wait for page load before extracting (default: True)

        Returns:
            ToolResult with page content and interactive elements
        """
        await self._ensure_page()

        # Ensure page is visible in live preview when viewing
        await self._ensure_page_visible()

        try:
            current_url = self.page.url
            now = time.time()

            # Check extraction cache (prevents duplicate extractions after navigate)
            # Priority 5: Use config value for cache TTL (increased from 10s to 15s)
            cache_ttl = get_settings().browser_element_extraction_cache_ttl
            if (
                self._extraction_cache["url"] == current_url
                and now - self._extraction_cache["timestamp"] < cache_ttl
                and self._extraction_cache["elements"] is not None
            ):
                logger.debug(f"Returning cached extraction for {current_url}")
                from app.core.prometheus_metrics import (
                    element_extraction_cache_hits_total,
                )

                element_extraction_cache_hits_total.inc()
                return ToolResult(
                    success=True,
                    data={
                        "interactive_elements": self._extraction_cache["elements"],
                        "content": self._extraction_cache["content"],
                        "url": current_url,
                        "title": await self.page.title(),
                        "cached": True,
                    },
                )

            # Cache miss
            from app.core.prometheus_metrics import (
                element_extraction_cache_misses_total,
            )

            element_extraction_cache_misses_total.inc()

            # Wait for page to be ready
            if wait_for_load:
                await self.wait_for_page_load(timeout=15000)

            # Check page complexity before full extraction
            complexity = await self._get_page_complexity()
            if isinstance(complexity, dict) and complexity.get("isHeavy"):
                current_url = self.page.url if self.page else ""
                if current_url not in self._heavy_page_warned_urls:
                    self._heavy_page_warned_urls.add(current_url)
                    logger.warning(
                        f"Heavy page detected: {complexity.get('elementCount', 'unknown')} elements, "
                        f"{complexity.get('interactiveCount', 'unknown')} interactive"
                    )

            # Parallel extraction of elements and content (LangChain pattern)
            elements_task = asyncio.create_task(self._extract_interactive_elements())
            content_task = asyncio.create_task(self._extract_content())

            interactive_elements, content = await asyncio.gather(elements_task, content_task, return_exceptions=True)

            # Handle extraction errors gracefully
            if isinstance(interactive_elements, Exception):
                logger.error(f"Element extraction failed: {interactive_elements}")
                interactive_elements = ["0:<span>Element extraction failed - use coordinates</span>"]

            if isinstance(content, Exception):
                logger.error(f"Content extraction failed: {content}")
                content = "Content extraction failed"

            # Update extraction cache
            self._extraction_cache = {
                "url": current_url,
                "timestamp": now,
                "elements": interactive_elements,
                "content": content,
            }

            return ToolResult(
                success=True,
                data={
                    "interactive_elements": interactive_elements,
                    "content": content,
                    "url": current_url,
                    "title": await self.page.title(),
                },
            )
        except Exception as e:
            logger.error(f"Error viewing page: {e}")
            return ToolResult(success=False, message=f"Failed to view page: {e!s}")

    async def _extract_interactive_elements(self) -> list[str]:
        """Extract visible interactive elements with performance limits.

        Optimized extraction that:
        - Limits elements to MAX_INTERACTIVE_ELEMENTS (100) to prevent hangs
        - Uses timeout protection to avoid blocking on heavy pages
        - Retries with exponential backoff for slow-loading pages
        - Skips expensive getComputedStyle for most elements
        - Preserves label/placeholder extraction for form elements

        Based on Browser-Use DomService patterns (Context7 research).

        Returns:
            List of formatted elements: "index:<tag>text</tag>"
        """
        await self._ensure_page()

        # Clear the cache to ensure we get fresh elements
        self._interactive_elements_cache = []

        # Get configuration values
        settings = get_settings()
        timeout_ms = int(settings.browser_element_extraction_timeout * 1000)
        max_retries = settings.browser_element_extraction_retries
        retry_delay = settings.browser_element_extraction_retry_delay

        # Extraction JavaScript code
        extraction_script = f"""(() => {{
                const MAX_ELEMENTS = {MAX_INTERACTIVE_ELEMENTS};
                const interactiveElements = [];
                const viewportHeight = window.innerHeight;
                const viewportWidth = window.innerWidth;

                // Single combined selector for all interactive elements (Browser-Use pattern)
                const elements = document.querySelectorAll(
                    'button, a[href], input:not([type="hidden"]), textarea, select, ' +
                    '[role="button"], [role="link"], [onclick], [tabindex]:not([tabindex="-1"])'
                );

                let validElementIndex = 0;

                for (let i = 0; i < elements.length && validElementIndex < MAX_ELEMENTS; i++) {{
                    const element = elements[i];
                    const rect = element.getBoundingClientRect();

                    // Quick dimension check
                    if (rect.width < 1 || rect.height < 1) continue;

                    // Viewport bounds check
                    if (rect.bottom < 0 || rect.top > viewportHeight) continue;
                    if (rect.right < 0 || rect.left > viewportWidth) continue;

                    // Quick visibility check using offsetParent (faster than getComputedStyle)
                    // offsetParent is null for hidden elements, but also for <body> and fixed/sticky elements
                    if (element.offsetParent === null && element.tagName !== 'BODY') {{
                        // Only do expensive style check for elements that might be fixed/sticky
                        const style = window.getComputedStyle(element);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                    }}

                    const tagName = element.tagName.toLowerCase();
                    let text = '';

                    // Extract text with label/placeholder context for form elements
                    if (element.value && ['input', 'textarea', 'select'].includes(tagName)) {{
                        text = element.value;

                        // Add label context for inputs
                        if (tagName === 'input' || tagName === 'textarea') {{
                            let labelText = '';
                            if (element.id) {{
                                const label = document.querySelector('label[for="' + element.id + '"]');
                                if (label) labelText = label.innerText?.trim()?.slice(0, 30);
                            }}
                            if (!labelText) {{
                                const parentLabel = element.closest('label');
                                if (parentLabel) labelText = parentLabel.innerText?.trim()?.slice(0, 30);
                            }}
                            if (labelText) text = '[' + labelText + '] ' + text;
                            if (element.placeholder) text += ' [' + element.placeholder + ']';
                        }}
                    }} else if (element.innerText) {{
                        text = element.innerText.trim().replace(/\\s+/g, ' ');
                    }} else if (element.alt) {{
                        text = element.alt;
                    }} else if (element.title) {{
                        text = element.title;
                    }} else if (element.placeholder) {{
                        text = '[' + element.placeholder + ']';
                    }} else if (element.type) {{
                        text = '[' + element.type + ']';
                    }} else {{
                        text = '[no text]';
                    }}

                    // Truncate long text
                    if (text.length > 80) {{
                        text = text.substring(0, 77) + '...';
                    }}

                    // Set data attribute for later selection
                    element.setAttribute('data-pythinker-id', 'pythinker-element-' + validElementIndex);

                    interactiveElements.push({{
                        index: validElementIndex,
                        tag: tagName,
                        text: text,
                        selector: '[data-pythinker-id="pythinker-element-' + validElementIndex + '"]'
                    }});

                    validElementIndex++;
                }}

                return interactiveElements;
            }})()"""

        # Retry loop with exponential backoff
        interactive_elements = None
        start_time = time.time()
        extraction_status = "error"  # Default to error, update on success

        for attempt in range(max_retries + 1):
            try:
                # Execute JavaScript with timeout protection and element limit
                interactive_elements = await self._evaluate_with_timeout(
                    extraction_script,
                    timeout_ms=timeout_ms,
                )

                # Success - break out of retry loop
                if interactive_elements:
                    extraction_status = "success"
                    break

                # Empty result but no exception - might need to wait for page load
                if attempt < max_retries:
                    # Don't record as "timeout" - this is just an empty result
                    # Only actual timeout exceptions should be recorded in timeout metrics
                    logger.debug(
                        "Element extraction returned empty result (attempt %d/%d), retrying after %.1fs",
                        attempt + 1,
                        max_retries + 1,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)

            except (PlaywrightTimeoutError, TimeoutError) as e:
                # Record timeout metric
                attempt_label = "final" if attempt == max_retries else ("retry" if attempt > 0 else "first")
                browser_element_extraction_timeout_total.inc({"attempt": attempt_label})

                if attempt < max_retries:
                    logger.debug(
                        "Element extraction timed out (attempt %d/%d), retrying after %.1fs",
                        attempt + 1,
                        max_retries + 1,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    extraction_status = "timeout"
                    logger.warning(
                        "Element extraction timed out after %d attempts: %s",
                        max_retries + 1,
                        str(e),
                    )

        # Record metrics
        elapsed = time.time() - start_time
        browser_element_extraction_total.inc({"status": extraction_status})
        browser_element_extraction_latency.observe({"status": extraction_status}, elapsed)

        # Handle final timeout or error after all retries
        if not interactive_elements:
            logger.warning(
                "Interactive element extraction timed out or returned empty after %d attempts", max_retries + 1
            )
            return ["0:<span>Page too complex or extraction timed out - use browser_click with coordinates</span>"]

        # Update cache
        self._interactive_elements_cache = interactive_elements

        # Format element information
        return [f"{el['index']}:<{el['tag']}>{el['text']}</{el['tag']}>" for el in interactive_elements]

    async def navigate(
        self,
        url: str,
        timeout: int | None = 30000,  # noqa: ASYNC109
        wait_until: str = "domcontentloaded",
        auto_extract: bool = True,
    ) -> ToolResult:
        """Navigate to the specified URL with automatic content loading and extraction

        Args:
            url: URL to navigate to
            timeout: Navigation timeout in milliseconds (default: 30000)
            wait_until: Load state to wait for ("load", "domcontentloaded", "networkidle")
            auto_extract: Whether to automatically scroll and extract content (default: True)

        Returns:
            ToolResult with navigation status, interactive elements, and optionally page content
        """
        # SSRF protection — block navigation to internal/private addresses
        ssrf_reason = is_ssrf_target(url)
        if ssrf_reason:
            logger.warning("SSRF blocked: %s → %s", url, ssrf_reason)
            return ToolResult(
                success=False,
                message=f"Navigation blocked for security: {ssrf_reason}",
                data={"blocked_url": url, "reason": ssrf_reason},
            )

        # Check if URL is a video URL before acquiring the lock
        if is_video_url(url):
            logger.info(f"Skipping video URL: {url}")
            return ToolResult(
                success=False,
                message=f"Skipped video URL (YouTube, TikTok, etc. are blocked to save time): {url}",
                data={"skipped_video_url": url, "reason": "Video sites are blocked for efficiency"},
            )

        # Serialize navigation — concurrent page.goto() causes ERR_ABORTED race conditions
        async with self._navigation_lock:
            return await self._navigate_impl(url, timeout, wait_until, auto_extract)

    async def _navigate_impl(
        self,
        url: str,
        timeout: int | None = 30000,  # noqa: ASYNC109
        wait_until: str = "domcontentloaded",
        auto_extract: bool = True,
    ) -> ToolResult:
        """Internal navigate implementation (caller must hold _navigation_lock)."""
        # Phase 1: Circuit breaker check - fail fast if too many crashes
        if not self._check_circuit_breaker():
            from app.domain.exceptions.browser import BrowserCrashedError, BrowserErrorContext

            context = BrowserErrorContext(
                cdp_url=self.cdp_url,
                operation="navigate",
                additional_info={"url": url, "reason": "circuit_breaker_open"},
            )
            raise BrowserCrashedError(
                cdp_url=self.cdp_url,
                context=context,
            )

        await self._ensure_page()

        # Phase 1: Quick health check before navigation - detect crashes early (<5s vs 120s)
        is_healthy = await self._quick_health_check()
        if not is_healthy:
            logger.warning(f"Browser unhealthy before navigation to {url}, reinitializing...")
            # Mark for reinitialization
            self._connection_healthy = False
            await self._ensure_page()  # Will reinitialize if needed

        # Clear cache only if URL changed (Priority 5: improve cache effectiveness)
        current_url = self.page.url if self.page else None
        if current_url != url:
            self._interactive_elements_cache = []

        # Priority 1: Wikipedia-specific optimization
        settings = get_settings()
        is_wikipedia = self._is_wikipedia_url(url) and settings.browser_wikipedia_lightweight_mode
        if is_wikipedia:
            logger.info(f"Wikipedia URL detected: {url} - using lightweight mode")
            # Force domcontentloaded instead of full load for Wikipedia
            wait_until = "domcontentloaded"

        try:
            # Navigate with proper wait_until parameter
            response = await self.page.goto(url, timeout=timeout, wait_until=wait_until)

            # Check if navigation was successful
            if response and response.status >= 400:
                logger.warning(f"Navigation to {url} returned status {response.status}")

            # Priority 1: Quick page size check BEFORE expensive operations
            is_heavy_page = False
            if auto_extract and not is_wikipedia:
                page_size = await self._quick_page_size_check()
                if isinstance(page_size, dict) and page_size.get("isHeavy"):
                    is_heavy_page = True
                    # Rate-limit: warn once per URL per browser instance
                    if url not in self._heavy_page_warned_urls:
                        self._heavy_page_warned_urls.add(url)
                        logger.warning(
                            f"Heavy page detected early: {page_size.get('htmlSize', 0) // 1024}KB HTML, "
                            f"{page_size.get('domCount', 0)} DOM elements - switching to lightweight mode"
                        )
                    else:
                        logger.debug(
                            f"Heavy page (repeat visit, suppressing warning): {page_size.get('domCount', 0)} DOM elements"
                        )
                    from app.core.prometheus_metrics import (
                        browser_heavy_page_detections_total,
                    )

                    browser_heavy_page_detections_total.inc(labels={"detection_method": "quick_check"})

            # AUTOMATIC BEHAVIOR: Smart scroll to load lazy content comprehensively
            # Priority 1: Skip smart scroll for Wikipedia and heavy pages to prevent crashes
            if auto_extract and not is_wikipedia and not is_heavy_page:
                try:
                    await self._smart_scroll_for_lazy_content()
                    logger.debug("Smart-scrolled page to load lazy content")
                except Exception as e:
                    logger.debug(f"Smart scroll failed (non-critical): {e}")
            elif auto_extract and (is_wikipedia or is_heavy_page):
                skip_reason = "Wikipedia" if is_wikipedia else "heavy page"
                logger.debug(f"Skipped smart scroll for {skip_reason}")

            # Extract interactive elements after page loads
            interactive_elements = await self._extract_interactive_elements()

            # Ensure page is visible in live preview after navigation
            await self._ensure_page_visible()

            # AUTOMATIC BEHAVIOR: Extract page content automatically for faster response
            result_data = {
                "interactive_elements": interactive_elements,
                "url": self.page.url,
                "status": response.status if response else None,
            }

            if auto_extract:
                try:
                    # Priority 1: Use Wikipedia summary for Wikipedia pages
                    if is_wikipedia:
                        wiki_summary = await self._extract_wikipedia_summary()
                        result_data["content"] = wiki_summary.get("summary", "")
                        result_data["title"] = wiki_summary.get("title", await self.page.title())
                        result_data["extraction_mode"] = "wikipedia_summary"
                        from app.core.prometheus_metrics import (
                            browser_wikipedia_summary_mode_total,
                        )

                        browser_wikipedia_summary_mode_total.inc()
                        logger.info(f"Wikipedia summary extracted ({len(result_data['content'])} chars) from {url}")
                    else:
                        # Extract content automatically
                        content = await self._extract_page_content()
                        title = await self.page.title()

                        result_data["content"] = content
                        result_data["title"] = title

                        logger.info(f"Auto-extracted content ({len(content)} chars) from {url}")
                except Exception as e:
                    logger.warning(f"Auto-extract content failed: {e}")
                    # Continue without content - non-critical

            # Priority 1: Check memory pressure after navigation (if heavy page)
            if settings.browser_memory_auto_restart and auto_extract:
                memory_pressure = await self._check_memory_pressure()
                if memory_pressure:
                    pressure_level = memory_pressure.get("pressure_level")
                    if pressure_level in ("high", "critical"):
                        logger.warning(
                            f"Memory pressure {pressure_level}: {memory_pressure.get('used_mb')}MB used, "
                            f"{memory_pressure.get('nodes')} DOM nodes"
                        )
                        from app.core.prometheus_metrics import (
                            browser_memory_pressure_total,
                        )

                        browser_memory_pressure_total.inc(labels={"level": pressure_level})

                        if pressure_level == "critical":
                            logger.warning("CRITICAL memory pressure - browser restart recommended on next navigation")
                            # Note: Don't restart immediately - wait for next navigation
                            # This prevents disrupting current successful navigation

            # Successful navigation — reset display circuit breaker
            self._display_failure_count = 0
            return ToolResult(success=True, data=result_data)
        except PlaywrightTimeoutError:
            # Page might still be usable even after timeout
            logger.warning(f"Navigation to {url} timed out, attempting to extract elements anyway")
            try:
                # Smart scroll even after timeout to load lazy content
                if auto_extract:
                    with contextlib.suppress(Exception):
                        await self._smart_scroll_for_lazy_content(max_scrolls=2, scroll_delay=0.3)

                interactive_elements = await self._extract_interactive_elements()

                # Ensure page is visible in live preview even after timeout
                await self._ensure_page_visible()

                result_data = {
                    "interactive_elements": interactive_elements,
                    "url": self.page.url,
                }

                # Try to extract content even after timeout
                if auto_extract:
                    try:
                        content = await self._extract_page_content()
                        title = await self.page.title()
                        result_data["content"] = content
                        result_data["title"] = title
                    except (PlaywrightError, PlaywrightTimeoutError, OSError):
                        logger.debug("Failed to extract content after partial page load", exc_info=True)

                return ToolResult(
                    success=True, message="Navigation timed out but page partially loaded", data=result_data
                )
            except (PlaywrightError, OSError):
                return ToolResult(success=False, message=f"Navigation to {url} timed out")
        except Exception as e:
            if self._is_crash_error(e):
                logger.error(f"Browser crash detected during navigation to {url}: {e}")
                self._connection_healthy = False
                self._record_crash()  # Phase 1: Track crash for circuit breaker

                # Priority 1: Graceful degradation - return partial result instead of failing
                if settings.browser_graceful_degradation and auto_extract:
                    logger.info("Graceful degradation enabled - returning partial result instead of failure")
                    try:
                        # Try to get whatever info we can before crash
                        partial_data = {
                            "url": url,
                            "partial": True,
                            "crash_reason": "browser_crash",
                            "interactive_elements": [],
                        }

                        # Try to get title and URL if page still exists
                        if self.page:
                            try:
                                partial_data["title"] = await self.page.title()
                                partial_data["url"] = self.page.url
                            except (PlaywrightError, OSError):
                                logger.debug("Failed to get title/URL from page after crash", exc_info=True)

                        return ToolResult(
                            success=False,
                            message=(
                                "Browser crashed during extraction after partial navigation. "
                                "Partial data is attached for recovery handling."
                            ),
                            data=partial_data,
                        )
                    except Exception as partial_err:
                        logger.warning(f"Could not extract partial data: {partial_err}")

                # Attempt auto-recovery via restart (if graceful degradation disabled or failed)
                try:
                    recovery_result = await self.restart(url)
                    if recovery_result.success:
                        logger.info(f"Browser auto-recovered after crash, navigated to {url}")
                        self._display_failure_count = 0
                        return recovery_result
                except Exception as recovery_err:
                    logger.error(f"Browser crash recovery failed: {recovery_err}")

                return ToolResult(
                    success=False,
                    message=f"Browser crashed navigating to {url}. Recovery failed — try again.",
                )
            return ToolResult(success=False, message=f"Failed to navigate to {url}: {e!s}")

    async def navigate_fast(self, url: str, timeout: int = 15000) -> ToolResult:  # noqa: ASYNC109
        """Fast navigation optimized for quick page loads without heavy extraction.

        This method is designed for fast-path queries where we want to get to
        a page quickly without the overhead of:
        - Smart scrolling for lazy content
        - Full interactive element extraction
        - Extended content analysis

        Args:
            url: URL to navigate to
            timeout: Navigation timeout in milliseconds (default: 15000, shorter than regular)

        Returns:
            ToolResult with basic page info (title, URL, truncated content)
        """
        await self._ensure_page()

        # SSRF protection
        ssrf_reason = is_ssrf_target(url)
        if ssrf_reason:
            logger.warning("SSRF blocked (fast): %s → %s", url, ssrf_reason)
            return ToolResult(
                success=False,
                message=f"Navigation blocked for security: {ssrf_reason}",
                data={"blocked_url": url, "reason": ssrf_reason},
            )

        # Check if URL is a video URL - skip to save agent time
        if is_video_url(url):
            logger.info(f"Skipping video URL in fast mode: {url}")
            return ToolResult(
                success=False,
                message=f"Skipped video URL: {url}",
                data={"skipped_video_url": url, "reason": "Video sites are blocked"},
            )

        try:
            # Navigate with shorter timeout and domcontentloaded (faster than load/networkidle)
            response = await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            status_code = response.status if response else None

            # Log warning for error status codes but continue
            if response and response.status >= 400:
                logger.warning(f"Fast navigation to {url} returned status {response.status}")

            # Bring page to front for live preview visibility
            await self._ensure_page_visible()

            # Extract basic content quickly (no scrolling, no full element extraction)
            try:
                title = await self.page.title()

                # Get text content directly - faster than full extraction
                content = await self.page.evaluate("""() => {
                    // Get main content areas first
                    const mainSelectors = ['main', 'article', '[role="main"]', '.content', '#content'];
                    for (const selector of mainSelectors) {
                        const el = document.querySelector(selector);
                        if (el && el.innerText && el.innerText.length > 100) {
                            return el.innerText.slice(0, 8000);
                        }
                    }
                    // Fallback to body text
                    return document.body ? document.body.innerText.slice(0, 8000) : '';
                }""")

                # Truncate for response
                if len(content) > 5000:
                    content = content[:5000] + "\n\n... (content truncated)"

                return ToolResult(
                    success=True,
                    data={
                        "url": self.page.url,
                        "title": title,
                        "content": content,
                        "status": status_code,
                        "fast_mode": True,
                    },
                )

            except Exception as e:
                logger.warning(f"Fast content extraction failed: {e}")
                # Return success with minimal info
                return ToolResult(
                    success=True,
                    data={
                        "url": self.page.url,
                        "title": await self.page.title() if self.page else "",
                        "status": status_code,
                        "fast_mode": True,
                    },
                )

        except PlaywrightTimeoutError:
            logger.warning(f"Fast navigation to {url} timed out after {timeout}ms")
            # Try to get whatever loaded
            try:
                return ToolResult(
                    success=True,
                    message="Page timed out but partially loaded",
                    data={
                        "url": self.page.url if self.page else url,
                        "title": await self.page.title() if self.page else "",
                        "fast_mode": True,
                        "timed_out": True,
                    },
                )
            except (PlaywrightError, OSError):
                return ToolResult(success=False, message=f"Fast navigation to {url} timed out")

        except Exception as e:
            logger.error(f"Fast navigation failed: {e}")
            return ToolResult(success=False, message=f"Failed to navigate to {url}: {e!s}")

    async def navigate_for_display(self, url: str, timeout: int = 10000) -> bool:  # noqa: ASYNC109
        """Navigate to URL purely for live preview display (best-effort, non-blocking).

        This is a lightweight navigation used after HTTP-based content fetching
        so the user can see the fetched page in the live preview viewer. It does NOT
        extract content, scroll, or interact with the page.

        Uses a trylock pattern: if the browser is already busy navigating,
        this returns False immediately without blocking.

        Args:
            url: URL to display in the browser
            timeout: Navigation timeout in milliseconds (default: 10000)

        Returns:
            True if navigation succeeded, False if skipped or failed
        """
        if is_video_url(url) or is_ssrf_target(url):
            return False

        # Circuit breaker: stop attempting live preview display after repeated failures
        if self._display_failure_count >= self._display_failure_threshold:
            logger.debug("navigate_for_display: circuit breaker open, skipping live preview display")
            return False

        # Trylock: if browser is already navigating, skip live preview display
        if self._navigation_lock.locked():
            logger.debug("navigate_for_display: browser busy, skipping live preview display")
            return False

        try:
            async with self._navigation_lock:
                await self._ensure_page()
                await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                # Bring page to front for live preview visibility
                await self._ensure_page_visible()
                logger.debug(f"navigate_for_display: showed {url} on live preview")
                self._display_failure_count = 0
                return True
        except Exception as e:
            self._display_failure_count += 1
            if self._is_crash_error(e):
                logger.error(f"navigate_for_display: browser crash detected for {url}: {e}")
                self._connection_healthy = False
            else:
                logger.debug(f"navigate_for_display failed for {url}: {e}")
            return False

    def cancel_background_browsing(self) -> None:
        """Signal background browsing loops to stop.

        Called by foreground browser operations (e.g. search, navigate) to prevent
        the fire-and-forget _browse_top_results task from competing for the page.
        """
        self._background_browse_cancelled = True

    def allow_background_browsing(self) -> None:
        """Reset cancellation for a new background browsing session."""
        self._background_browse_cancelled = False

    async def restart(self, url: str) -> ToolResult:
        """Restart the browser and navigate to the specified URL

        IMPORTANT: This does NOT restart Chrome itself (which runs continuously).
        It only refreshes Playwright's connection and navigates to a new URL.
        Reuses existing browser windows to avoid live preview positioning issues.

        Args:
            url: URL to navigate to after restart

        Returns:
            ToolResult with navigation result
        """
        # Don't call cleanup() - it closes pages which creates new windows when reinitializing
        # Instead, just reinitialize the connection if needed and navigate
        # This reuses the existing browser window and avoids live preview positioning issues

        # Verify connection is healthy, reinitialize only if necessary
        try:
            self._connection_healthy = await self._verify_connection_health()
            if not self._connection_healthy:
                logger.info("Browser connection unhealthy, reinitializing without closing pages")
                await self._release_playwright_resources()

                if not await self.initialize():
                    return ToolResult(success=False, message="Failed to reinitialize browser after restart")
        except Exception as e:
            logger.warning(f"Health check failed: {e}, reinitializing")
            await self._release_playwright_resources()

            if not await self.initialize():
                return ToolResult(success=False, message="Failed to reinitialize browser after restart")

        # Navigate to the target URL (reuses existing page/window)
        return await self.navigate(url)

    async def set_resource_blocking(self, enabled: bool, resource_types: set[str] | None = None) -> None:
        """Enable or disable resource blocking for performance optimization

        Args:
            enabled: Whether to enable resource blocking
            resource_types: Set of resource types to block (e.g., {"image", "font", "media"})
                           If None, uses default blockable types
        """
        self.block_resources = enabled
        if enabled:
            self.blocked_types = resource_types or BLOCKABLE_RESOURCE_TYPES
        else:
            self.blocked_types = set()

        # Re-setup routes if context exists
        if self.context:
            # Clear existing routes
            await self.context.unroute_all()
            # Setup new routes if blocking enabled
            await self._setup_route_interception(self.context)

    def is_connected(self) -> bool:
        """Check if browser connection appears healthy

        Returns:
            bool: True if connection looks healthy
        """
        return self._connection_healthy and self.browser is not None and self.page is not None

    async def _get_element_by_index(self, index: int, retry_with_refresh: bool = True) -> Any | None:
        """Get element by index using multiple fallback strategies.

        Phase 5: Enhanced element targeting with fallbacks:
        1. Primary: data-pythinker-id selector
        2. Fallback 1: Original selector from cache
        3. Fallback 2: Text-based matching from cache
        4. Fallback 3: Refresh element list and retry

        Args:
            index: Element index
            retry_with_refresh: Whether to retry with refreshed element list (default: True)

        Returns:
            The found element, or None if not found
        """
        # Check if there are cached elements
        if not self._interactive_elements_cache or index >= len(self._interactive_elements_cache):
            # If cache is empty/invalid and retry is enabled, refresh and try again
            if retry_with_refresh:
                logger.debug(f"Element cache miss for index {index}, refreshing...")
                await self._extract_interactive_elements()
                return await self._get_element_by_index(index, retry_with_refresh=False)
            return None

        cached_element = self._interactive_elements_cache[index]

        # Strategy 1: Use data-pythinker-id selector (most reliable)
        selector = f'[data-pythinker-id="pythinker-element-{index}"]'
        try:
            element = await self.page.query_selector(selector)
            if element:
                return element
        except Exception as e:
            logger.debug(f"Strategy 1 (data-pythinker-id) failed for index {index}: {e}")

        # Strategy 2: Try original selector from cache
        if "selector" in cached_element:
            try:
                element = await self.page.query_selector(cached_element["selector"])
                if element:
                    logger.debug(f"Found element via fallback selector: {cached_element['selector']}")
                    return element
            except Exception as e:
                logger.debug(f"Strategy 2 (cached selector) failed: {e}")

        # Strategy 3: Text-based matching (for elements with unique text)
        if "text" in cached_element and cached_element["text"] and "tag" in cached_element:
            text = cached_element["text"]
            tag = cached_element["tag"]
            # Clean up text for matching (remove prefixes like [Label:...])
            clean_text = text.strip()
            if clean_text and len(clean_text) > 3:
                try:
                    # Try exact text match first
                    text_selector = f"{tag}:has-text('{clean_text[:50]}')"
                    element = await self.page.query_selector(text_selector)
                    if element:
                        logger.debug(f"Found element via text match: {clean_text[:30]}...")
                        return element
                except Exception as e:
                    logger.debug(f"Strategy 3 (text matching) failed: {e}")

        # Strategy 4: Refresh element list and retry once
        if retry_with_refresh:
            logger.debug(f"All strategies failed for index {index}, refreshing element list...")
            await self._extract_interactive_elements()
            return await self._get_element_by_index(index, retry_with_refresh=False)

        logger.warning(f"Could not find element with index {index} after all fallback strategies")
        return None

    async def click(
        self,
        index: int | None = None,
        coordinate_x: float | None = None,
        coordinate_y: float | None = None,
        wait_for_navigation: bool = True,
    ) -> ToolResult:
        """Click an element with proper visibility checking and navigation waiting

        Args:
            index: Element index to click
            coordinate_x: X coordinate for coordinate-based click
            coordinate_y: Y coordinate for coordinate-based click
            wait_for_navigation: Whether to wait for potential navigation after click

        Returns:
            ToolResult indicating success or failure
        """
        await self._ensure_page()

        # Ensure page is visible in live preview before clicking
        await self._ensure_page_visible()

        try:
            resolved_coords: dict[str, float] | None = None
            if coordinate_x is not None and coordinate_y is not None:
                # Show cursor animation at coordinates
                await self._show_cursor_click(coordinate_x, coordinate_y)
                await self.page.mouse.click(coordinate_x, coordinate_y)
                resolved_coords = {"resolved_x": coordinate_x, "resolved_y": coordinate_y}
            elif index is not None:
                element = await self._get_element_by_index(index)
                if not element:
                    # Phase 5: Enhanced error message with suggestions
                    cache_info = ""
                    if self._interactive_elements_cache and index < len(self._interactive_elements_cache):
                        cached = self._interactive_elements_cache[index]
                        cache_info = f" (was: {cached.get('tag', '?')} '{cached.get('text', '')[:30]}')"
                    return ToolResult(
                        success=False,
                        message=f"Cannot find element index {index}{cache_info}. "
                        f"Use browser_view to get fresh element indices - page content may have changed.",
                    )

                # Check if element is visible and scroll if needed
                is_visible = await self.page.evaluate(
                    """(element) => {
                    if (!element) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return !(
                        rect.width === 0 ||
                        rect.height === 0 ||
                        style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        style.opacity === '0'
                    );
                }""",
                    element,
                )

                if not is_visible:
                    # Scroll element into view
                    await element.scroll_into_view_if_needed()
                    # Brief wait for scroll animation
                    await asyncio.sleep(0.3)

                # Get element center coordinates for cursor animation
                try:
                    box = await element.bounding_box()
                    if box:
                        center_x = box["x"] + box["width"] / 2
                        center_y = box["y"] + box["height"] / 2
                        resolved_coords = {"resolved_x": center_x, "resolved_y": center_y}
                        await self._show_cursor_click(center_x, center_y)
                except (PlaywrightError, PlaywrightTimeoutError, OSError):
                    logger.debug("Failed to show cursor click animation", exc_info=True)

                # Click with force option as fallback for tricky elements
                try:
                    await element.click(timeout=10000)
                except PlaywrightTimeoutError:
                    # Try force click if normal click times out
                    await element.click(force=True, timeout=5000)
            else:
                return ToolResult(success=False, message="Either index or coordinates must be provided")

            # Wait briefly for any navigation that might occur
            if wait_for_navigation:
                await self.wait_for_navigation(timeout=5000)

            return ToolResult(success=True, data=resolved_coords)

        except PlaywrightError as e:
            return ToolResult(success=False, message=f"Click failed: {e!s}")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to click element: {e!s}")

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: int | None = None,
        coordinate_x: float | None = None,
        coordinate_y: float | None = None,
        clear_first: bool = True,
    ) -> ToolResult:
        """Input text into an element with proper clearing and error handling

        Args:
            text: Text to input
            press_enter: Whether to press Enter after input
            index: Element index for input
            coordinate_x: X coordinate for coordinate-based input
            coordinate_y: Y coordinate for coordinate-based input
            clear_first: Whether to clear existing content before typing (default: True)

        Returns:
            ToolResult indicating success or failure
        """
        await self._ensure_page()

        # Ensure page is visible in live preview before input
        await self._ensure_page_visible()

        try:
            resolved_coords: dict[str, float] | None = None
            if coordinate_x is not None and coordinate_y is not None:
                # Show cursor animation at coordinates
                await self._show_cursor_click(coordinate_x, coordinate_y)
                await self.page.mouse.click(coordinate_x, coordinate_y)
                resolved_coords = {"resolved_x": coordinate_x, "resolved_y": coordinate_y}
                if clear_first:
                    # Select all and clear
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.press("Backspace")
                await self.page.keyboard.type(text, delay=10)  # Small delay for reliability
            elif index is not None:
                element = await self._get_element_by_index(index)
                if not element:
                    # Phase 5: Enhanced error message with suggestions
                    cache_info = ""
                    if self._interactive_elements_cache and index < len(self._interactive_elements_cache):
                        cached = self._interactive_elements_cache[index]
                        cache_info = f" (was: {cached.get('tag', '?')} '{cached.get('text', '')[:30]}')"
                    return ToolResult(
                        success=False,
                        message=f"Cannot find input element index {index}{cache_info}. "
                        f"Use browser_view to get fresh element indices - page content may have changed.",
                    )

                # Scroll into view if needed
                await element.scroll_into_view_if_needed()

                # Get element center coordinates for cursor animation
                try:
                    box = await element.bounding_box()
                    if box:
                        center_x = box["x"] + box["width"] / 2
                        center_y = box["y"] + box["height"] / 2
                        resolved_coords = {"resolved_x": center_x, "resolved_y": center_y}
                        await self._show_cursor_click(center_x, center_y)
                except (PlaywrightError, PlaywrightTimeoutError, OSError):
                    logger.debug("Failed to show cursor click animation for input", exc_info=True)

                # Try fill() first (fastest and most reliable for input fields)
                try:
                    if clear_first:
                        await element.fill("")
                    await element.fill(text)
                except (PlaywrightError, PlaywrightTimeoutError):
                    # Fallback: click and type character by character
                    try:
                        await element.click()
                        if clear_first:
                            await self.page.keyboard.press("Control+a")
                            await self.page.keyboard.press("Backspace")
                        await self.page.keyboard.type(text, delay=10)
                    except Exception as e:
                        return ToolResult(
                            success=False, message=f"Failed to input text using both fill and type methods: {e!s}"
                        )
            else:
                return ToolResult(success=False, message="Either index or coordinates must be provided")

            if press_enter:
                await self.page.keyboard.press("Enter")
                # Wait for potential form submission
                await self.wait_for_navigation(timeout=5000)

            return ToolResult(success=True, data=resolved_coords)

        except Exception as e:
            return ToolResult(success=False, message=f"Failed to input text: {e!s}")

    async def move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        """Move the mouse"""
        await self._ensure_page()
        await self.page.mouse.move(coordinate_x, coordinate_y)
        return ToolResult(success=True)

    async def press_key(self, key: str) -> ToolResult:
        """Simulate key press"""
        await self._ensure_page()
        await self.page.keyboard.press(key)
        return ToolResult(success=True)

    async def select_option(self, index: int, option: int) -> ToolResult:
        """Select dropdown option"""
        await self._ensure_page()
        try:
            element = await self._get_element_by_index(index)
            if not element:
                return ToolResult(success=False, message=f"Cannot find selector element with index {index}")

            # Try to select the option
            await element.select_option(index=option)
            return ToolResult(success=True)
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to select option: {e!s}")

    async def scroll_up(self, to_top: bool | None = None) -> ToolResult:
        """Scroll up on the current page

        Args:
            to_top: If True, scroll to page top; otherwise scroll one viewport up

        Returns:
            ToolResult indicating success with scroll metrics
        """
        await self._ensure_page()
        try:
            # Ensure page is visible in live preview before scrolling
            await self._ensure_page_visible()

            if to_top:
                await self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            else:
                await self.page.evaluate("window.scrollBy({top: -window.innerHeight, behavior: 'smooth'})")

            # Wait for smooth scroll animation
            await asyncio.sleep(0.3)

            # Get scroll position info
            new_scroll = await self.page.evaluate("window.scrollY")
            page_height = await self.page.evaluate("document.body.scrollHeight")
            viewport_height = await self.page.evaluate("window.innerHeight")
            at_top = new_scroll <= 10
            scroll_percentage = int((new_scroll + viewport_height) / page_height * 100) if page_height > 0 else 0

            return ToolResult(
                success=True,
                message=f"Scrolled {'to top' if to_top else 'up'}. Position: {scroll_percentage}% of page",
                data={
                    "scroll_position": new_scroll,
                    "page_height": page_height,
                    "at_top": at_top,
                    "scroll_percentage": scroll_percentage,
                },
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll up failed: {e!s}")

    async def scroll_down(self, to_bottom: bool | None = None) -> ToolResult:
        """Scroll down on the current page with smart lazy content detection

        Args:
            to_bottom: If True, scroll to page bottom; otherwise scroll one viewport down

        Returns:
            ToolResult indicating success with scroll metrics
        """
        await self._ensure_page()
        try:
            # Ensure page is visible in live preview before scrolling
            await self._ensure_page_visible()

            # Get initial metrics for lazy loading detection
            initial_height = await self.page.evaluate("document.body.scrollHeight")
            await self.page.evaluate("window.scrollY")
            viewport_height = await self.page.evaluate("window.innerHeight")

            if to_bottom:
                await self.page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
            else:
                await self.page.evaluate("window.scrollBy({top: window.innerHeight, behavior: 'smooth'})")

            # Wait for smooth scroll animation
            await asyncio.sleep(0.35)

            # Check if lazy content loaded (page got taller)
            new_height = await self.page.evaluate("document.body.scrollHeight")
            new_scroll = await self.page.evaluate("window.scrollY")
            lazy_content_loaded = new_height > initial_height

            if lazy_content_loaded:
                # Wait a bit more for lazy content to fully render
                await asyncio.sleep(0.2)
                logger.debug(f"Lazy content detected: page grew from {initial_height} to {new_height}px")

            # Calculate scroll position info
            at_bottom = (new_scroll + viewport_height) >= (new_height - 50)
            scroll_percentage = int((new_scroll + viewport_height) / new_height * 100) if new_height > 0 else 0

            return ToolResult(
                success=True,
                message=f"Scrolled {'to bottom' if to_bottom else 'down'}. Position: {scroll_percentage}% of page{' (more content loaded)' if lazy_content_loaded else ''}",
                data={
                    "scroll_position": new_scroll,
                    "page_height": new_height,
                    "viewport_height": viewport_height,
                    "at_bottom": at_bottom,
                    "lazy_content_loaded": lazy_content_loaded,
                    "scroll_percentage": scroll_percentage,
                },
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll down failed: {e!s}")

    async def screenshot(self, full_page: bool | None = False) -> bytes:
        """Take a screenshot of the current page

        Args:
            full_page: Whether to capture the full page or just the viewport

        Returns:
            bytes: PNG screenshot data
        """
        await self._ensure_page()

        # Configure screenshot options
        screenshot_options = {"full_page": full_page, "type": "png"}

        # Return bytes data directly
        return await self.page.screenshot(**screenshot_options)

    # SECURITY: Dangerous JavaScript patterns that should be blocked
    # unless browser_allow_dangerous_js is explicitly enabled
    _DANGEROUS_JS_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        # Network exfiltration
        (r'\bfetch\s*\(\s*["\']https?://(?!localhost|127\.0\.0\.1)', "External fetch requests"),
        (r"\bnew\s+XMLHttpRequest\b", "XMLHttpRequest usage"),
        (r"\bnew\s+WebSocket\b", "WebSocket connections"),
        (r"\bnavigator\.sendBeacon\b", "Data beaconing"),
        # Cookie/credential theft
        (r"\bdocument\.cookie\b", "Cookie access"),
        (r"\blocalStorage\b", "localStorage access"),
        (r"\bsessionStorage\b", "sessionStorage access"),
        (r"\bindexedDB\b", "IndexedDB access"),
        # Code injection vectors
        (r"\beval\s*\(", "eval() usage"),
        (r"\bnew\s+Function\s*\(", "Function constructor"),
        (r'\bsetTimeout\s*\(\s*["\']', "setTimeout with string"),
        (r'\bsetInterval\s*\(\s*["\']', "setInterval with string"),
        # DOM manipulation that could enable XSS
        (r"\.innerHTML\s*=", "innerHTML assignment"),
        (r"\.outerHTML\s*=", "outerHTML assignment"),
        (r"\bdocument\.write\b", "document.write"),
        (r"\bdocument\.writeln\b", "document.writeln"),
        # Window manipulation
        (r"\bwindow\.open\s*\(", "window.open"),
        (r"\bwindow\.location\s*=", "window.location assignment"),
        (r"\blocation\.href\s*=", "location.href assignment"),
        (r"\blocation\.replace\s*\(", "location.replace"),
        # Script injection
        (r'createElement\s*\(\s*["\']script', "Script element creation"),
        (r'\.src\s*=\s*["\']https?://', "External script source"),
    ]

    def _validate_javascript(self, javascript: str) -> tuple[bool, str]:
        """Validate JavaScript code for potentially dangerous patterns.

        SECURITY: This is a defense-in-depth measure. It blocks common
        patterns that could be used for data exfiltration or XSS attacks.

        Returns:
            tuple: (is_safe, error_message)
        """
        if self.settings.browser_allow_dangerous_js:
            logger.warning("Dangerous JavaScript validation bypassed via settings")
            return True, ""

        for pattern, description in self._DANGEROUS_JS_PATTERNS:
            if re.search(pattern, javascript, re.IGNORECASE):
                return False, f"Blocked: {description} - Pattern matched: {pattern}"

        return True, ""

    async def console_exec(self, javascript: str) -> ToolResult:
        """Execute JavaScript code with security validation.

        SECURITY: Validates JavaScript before execution to prevent:
        - Data exfiltration (fetch, XHR, WebSocket to external URLs)
        - Cookie/credential theft (document.cookie, localStorage)
        - Code injection (eval, innerHTML, document.write)
        - Window manipulation (window.open, location changes)

        Set browser_allow_dangerous_js=True in settings to bypass validation.
        """
        await self._ensure_page()

        # SECURITY: Validate JavaScript before execution
        is_safe, error_msg = self._validate_javascript(javascript)
        if not is_safe:
            logger.warning(f"Blocked dangerous JavaScript execution: {error_msg}")
            return ToolResult(
                success=False,
                error=f"JavaScript blocked for security reasons: {error_msg}",
                data={"blocked": True, "reason": error_msg},
            )

        try:
            result = await self.page.evaluate(javascript)
            return ToolResult(success=True, data={"result": result})
        except Exception as e:
            logger.error(f"JavaScript execution error: {e}")
            return ToolResult(success=False, error=str(e))

    async def console_view(self, max_lines: int | None = None) -> ToolResult:
        """View console output"""
        await self._ensure_page()
        logs = await self.page.evaluate("""() => {
            return window.console.logs || [];
        }""")
        if max_lines is not None:
            logs = logs[-max_lines:]
        return ToolResult(success=True, data={"logs": logs})
