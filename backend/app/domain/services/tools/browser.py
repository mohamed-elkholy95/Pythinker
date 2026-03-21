import asyncio
import contextlib
import logging
import re
import time
from enum import Enum
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import aiohttp

from app.domain.external.browser import Browser
from app.domain.external.scraper import Scraper
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool
from app.domain.services.tools.paywall_detector import PaywallDetector

logger = logging.getLogger(__name__)


class BrowserIntent(str, Enum):
    """Browser interaction intent types inspired by Pythinker AI.

    Different intents optimize the browser's approach to page interaction:
    - NAVIGATIONAL: General browsing, exploring pages
    - INFORMATIONAL: Focused content extraction, research tasks
    - TRANSACTIONAL: Form filling, purchases, interactive operations
    """

    NAVIGATIONAL = "navigational"  # General browsing
    INFORMATIONAL = "informational"  # Content extraction focus
    TRANSACTIONAL = "transactional"  # Form filling, purchases


# Intent-specific configurations
BROWSER_INTENT_CONFIG = {
    BrowserIntent.NAVIGATIONAL: {
        "auto_scroll": True,
        "extract_interactive": True,
        "extract_content": True,
        "wait_for_network_idle": False,
        "max_content_length": 50000,
    },
    BrowserIntent.INFORMATIONAL: {
        "auto_scroll": True,
        "extract_interactive": False,  # Focus on content, not interactions
        "extract_content": True,
        "wait_for_network_idle": True,  # Wait for all content to load
        "max_content_length": 100000,  # Allow more content extraction
    },
    BrowserIntent.TRANSACTIONAL: {
        "auto_scroll": False,  # Don't scroll past form
        "extract_interactive": True,  # Need form elements
        "extract_content": False,  # Focus on interactions
        "wait_for_network_idle": True,  # Wait for form to load
        "max_content_length": 20000,
    },
}

# Domains known to be fully open-access — skip paywall detection
OPEN_ACCESS_DOMAINS: set[str] = {
    "docs.python.org",
    "docs.anthropic.com",
    "developer.mozilla.org",
    "github.com",
    "en.wikipedia.org",
    "stackoverflow.com",
    "docs.google.com",
    "react.dev",
    "vuejs.org",
    "nextjs.org",
    "fastapi.tiangolo.com",
    "docs.pydantic.dev",
    "platform.openai.com",
    "arxiv.org",
    "news.ycombinator.com",
    "pypi.org",
    "npmjs.com",
    "hub.docker.com",
    "docs.docker.com",
    "learn.microsoft.com",
    "dev.to",
    "medium.com",
}

# Singleton paywall detector
_paywall_detector: PaywallDetector | None = None


def get_paywall_detector() -> PaywallDetector:
    """Get or create shared paywall detector instance."""
    global _paywall_detector
    if _paywall_detector is None:
        _paywall_detector = PaywallDetector()
    return _paywall_detector


# Singleton HTTP client session for connection pooling
_http_session: aiohttp.ClientSession | None = None
_http_session_lock = asyncio.Lock()


async def get_http_session() -> aiohttp.ClientSession:
    """Get or create shared HTTP session for connection pooling.

    Uses reduced timeouts (15s total, 5s connect) for faster failure detection.
    Thread-safe via asyncio.Lock to prevent duplicate session creation.
    """
    global _http_session
    if _http_session is not None and not _http_session.closed:
        return _http_session
    async with _http_session_lock:
        # Double-check after acquiring lock
        if _http_session is None or _http_session.closed:
            timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
            _http_session = aiohttp.ClientSession(
                timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
    return _http_session


async def close_http_session() -> None:
    """Close the shared HTTP session on shutdown to prevent resource leaks."""
    global _http_session
    if _http_session is not None and not _http_session.closed:
        await _http_session.close()
        _http_session = None


def html_to_text(html: str, max_length: int = 50000) -> str:
    """Convert HTML to clean readable text, preserving key structure.

    Preserves headings, links, lists, and basic formatting
    without external dependencies.
    """
    # Remove scripts and styles
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

    # Preserve headings as markdown
    for i in range(1, 7):
        prefix = "#" * i
        html = re.sub(
            rf"<h{i}[^>]*>(.*?)</h{i}>",
            rf"\n\n{prefix} \1\n",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Preserve links as [text](url)
    html = re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        r"[\2](\1)",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Preserve list items
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", html, flags=re.IGNORECASE | re.DOTALL)

    # Convert table cells to pipe-separated (basic table support)
    html = re.sub(r"<th[^>]*>(.*?)</th>", r"| \1 ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<td[^>]*>(.*?)</td>", r"| \1 ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"</tr>", " |\n", html, flags=re.IGNORECASE)

    # Convert common block elements to newlines
    html = re.sub(r"<(p|div|br|tr|ul|ol|blockquote)[^>]*>", "\n", html, flags=re.IGNORECASE)

    # Remove all other HTML tags
    html = re.sub(r"<[^>]+>", "", html)

    # Decode common HTML entities
    html = html.replace("&nbsp;", " ")
    html = html.replace("&amp;", "&")
    html = html.replace("&lt;", "<")
    html = html.replace("&gt;", ">")
    html = html.replace("&quot;", '"')
    html = html.replace("&#39;", "'")

    # Clean up whitespace
    html = re.sub(r"\n\s*\n\s*\n", "\n\n", html)  # Max 2 consecutive newlines
    html = re.sub(r" +", " ", html)
    html = html.strip()

    return html[:max_length] if len(html) > max_length else html


class BrowserTool(BaseTool):
    """Browser tool class, providing browser interaction functions with text-first mode"""

    name: str = "browser"

    # URL content cache: url -> (timestamp, text_content)
    _url_cache: ClassVar[dict[str, tuple[float, str]]] = {}
    _url_cache_ttl: ClassVar[int] = 300  # 5 minutes
    _url_cache_max: ClassVar[int] = 50
    _tracking_query_params: ClassVar[set[str]] = {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "ref",
        "ref_src",
        "source",
        "sourceid",
    }

    def __init__(
        self,
        browser: Browser,
        max_observe: int | None = None,
        scraper: Scraper | None = None,
    ):
        """Initialize browser tool class

        Args:
            browser: Browser service
            max_observe: Optional custom observation limit (default: 10000)
            scraper: Optional scraper service injected from composition root
        """
        super().__init__(max_observe=max_observe)
        self.browser = browser
        self._scraper = scraper
        # Per-session URL visit counter to warn/reject repeated visits
        self._url_visit_counts: dict[str, int] = {}

    @classmethod
    def _normalize_url_for_visit_tracking(cls, url: str) -> str:
        """Normalize URL to detect repeat visits reliably across superficial variants."""
        stripped = url.strip()
        if not stripped:
            return stripped

        parsed = urlsplit(stripped)
        if not parsed.netloc:
            return stripped.split("#", 1)[0].rstrip("/").lower()

        scheme = (parsed.scheme or "https").lower()
        # Treat http/https as the same document for repeat-visit tracking.
        # Most real visits are redirected to https anyway; keeping them distinct
        # causes redundant revisits to slip past duplicate guards.
        if scheme in {"http", "https"}:
            scheme = "https"
        host = (parsed.hostname or "").lower()
        port = parsed.port
        netloc = (f"{host}:{port}" if port and port not in {80, 443} else host) if host else parsed.netloc.lower()
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")

        filtered_query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if not (k.lower().startswith("utm_") or k.lower() in cls._tracking_query_params)
        ]
        filtered_query.sort(key=lambda item: (item[0].lower(), item[1]))
        query = urlencode(filtered_query, doseq=True)
        return urlunsplit((scheme, netloc, path, query, ""))

    def _extract_focused_content(self, text: str, focus: str | None, max_length: int = 50000) -> str:
        """Extract content relevant to the focus area.

        Inspired by Pythinker's focus parameter for informational browsing.
        When a focus is specified, prioritize content matching that focus.

        Args:
            text: Full page text content
            focus: Focus area description (e.g., "pricing information", "technical specs")
            max_length: Maximum content length to return

        Returns:
            Focused or full content
        """
        if not focus or not text:
            return text[:max_length]

        # Split content into paragraphs
        paragraphs = text.split("\n\n")
        focus_lower = focus.lower()
        focus_words = set(focus_lower.split())

        # Score paragraphs by relevance to focus
        scored = []
        for para in paragraphs:
            para_lower = para.lower()
            # Count matching focus words
            score = sum(1 for word in focus_words if word in para_lower)
            # Boost if focus phrase appears
            if focus_lower in para_lower:
                score += 5
            scored.append((score, para))

        # Sort by score (highest first) but keep some context
        scored.sort(key=lambda x: x[0], reverse=True)

        # Build focused content: high-relevance paragraphs first
        focused_parts = []
        current_length = 0

        # First add high-scoring paragraphs
        for score, para in scored:
            if score > 0 and current_length + len(para) < max_length:
                focused_parts.append(para)
                current_length += len(para) + 2

        # If we have room, add some context from remaining paragraphs
        for score, para in scored:
            if score == 0 and current_length + len(para) < max_length * 0.3:  # 30% for context
                focused_parts.append(para)
                current_length += len(para) + 2

        if focused_parts:
            result = "\n\n".join(focused_parts)
            if len(result) < len(text) * 0.5:  # If we filtered significantly
                result = f"[FOCUSED CONTENT: {focus}]\n\n{result}"
            return result[:max_length]

        return text[:max_length]

    @tool(
        name="search",
        description="""Search and fetch content from a URL.

RENAMED FROM browser_get_content - This is the primary tool for visiting URLs and extracting content.

FEATURES:
- Fast HTTP-based content fetching (no browser overhead)
- Automatic paywall detection
- Optional focused content extraction
- Falls back to full browser rendering if needed
- Visible in live preview when fallback is triggered

WHEN TO USE:
- When you have a specific URL to visit
- For research and content extraction tasks
- To quickly fetch page text without JavaScript execution

EXAMPLE:
search(url="https://openrouter.ai/docs/pricing", focus="pricing tiers")
→ Fetches content and extracts pricing-related information

For complex interactions (clicking, scrolling, forms), use browser_navigate instead.""",
        parameters={
            "url": {
                "type": "string",
                "description": "Complete URL to fetch content from. Must include protocol prefix.",
            },
            "focus": {
                "type": "string",
                "description": "(Optional) Focus area for content extraction (e.g., 'pricing', 'features', 'reviews')",
            },
        },
        required=["url"],
    )
    async def search(self, url: str, focus: str | None = None) -> ToolResult:
        """Search and fetch content from a URL.

        Uses lightweight HTTP client for speed. Ideal for research tasks.
        Falls back to full browser navigation on failure.

        Args:
            url: Complete URL to fetch
            focus: Optional focus area for content extraction

        Returns:
            Page text content
        """
        logger.info(f"Searching URL: {url}" + (f" (focus: {focus})" if focus else ""))

        # Check per-session visit count and reject repeated visits.
        # Counter is only incremented after successful fetch (below), so
        # timed-out or failed fetches don't block retries.
        normalized_url = self._normalize_url_for_visit_tracking(url)
        visit_count = self._url_visit_counts.get(normalized_url, 0)

        if visit_count >= 3:
            logger.warning(f"URL visited {visit_count} times, returning short rejection: {url[:80]}")
            return ToolResult(
                success=True,
                message=(
                    f"This URL has already been visited {visit_count} times this session. "
                    "Content is identical to previous visits. "
                    "Please proceed with different URLs or complete the current step with the information you have."
                ),
                data={"url": url, "visit_count": visit_count, "access_status": "repeated"},
            )

        # Check URL content cache
        if url in self._url_cache:
            cached_ts, cached_text = self._url_cache[url]
            if time.time() - cached_ts < self._url_cache_ttl:
                logger.debug(f"URL cache hit: {url[:80]}")
                if focus:
                    cached_text = self._extract_focused_content(cached_text, focus, 100000)
                message = f"Content fetched (cached): {len(cached_text)} chars."
                if focus:
                    message = f"[FOCUSED: {focus}] {message}"
                # Count cache hit as a visit
                self._url_visit_counts[normalized_url] = visit_count + 1
                # Append warning on 2nd visit
                if visit_count >= 1:
                    message += (
                        "\n\nNOTE: You have already visited this URL. The content has not changed. "
                        "Consider visiting a different URL or extracting different information."
                    )
                return ToolResult(
                    success=True,
                    message=message,
                    data={"content": cached_text, "url": url, "access_status": "full", "focus": focus},
                )
            del self._url_cache[url]

        # Cancel any background browsing (from info_search_web) to avoid racing for the page
        _cancelled_bg = False
        if hasattr(self.browser, "cancel_background_browsing"):
            self.browser.cancel_background_browsing()
            _cancelled_bg = True

        # Start browser navigation concurrently so live preview shows activity immediately
        nav_task: asyncio.Task[None] | None = None
        if hasattr(self.browser, "navigate_for_display"):
            nav_task = asyncio.create_task(self.browser.navigate_for_display(url))

        try:
            # ── Fast fetch: Scrapling (enhanced) or legacy aiohttp ────────────
            text: str = ""
            html: str = ""
            fetched_url: str = url

            from app.core.config import get_settings as _get_settings

            _settings = _get_settings()
            if _settings.scraping_enhanced_fetch and self._scraper:
                # Scrapling path: TLS impersonation + three-tier escalation
                _result = await self._scraper.fetch_with_escalation(url)
                if _result.success and len(_result.text) > 500:
                    text = _result.text
                    html = _result.html or ""
                    fetched_url = _result.url
                    logger.debug(f"Scrapling resolved {url} via tier={_result.tier_used}")
                else:
                    return ToolResult(
                        success=False,
                        message=f"URL fetch failed: {_result.error or 'No usable content'}. "
                        "Try a different URL from your search results.",
                    )
            else:
                # Legacy aiohttp path (fallback when scraping_enhanced_fetch=false)
                session = await get_http_session()
                async with session.get(url, allow_redirects=True) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if "text/html" in content_type or "text/plain" in content_type:
                            html = await response.text()
                            text = html_to_text(html)
                            fetched_url = str(response.url)
                        else:
                            logger.debug(f"Content type {content_type} not suitable for fast fetch")
                    # Non-200 or wrong content type: fall through to browser fallback

            if len(text) > 500:  # Valid content threshold
                # Detect paywall (skip for known open-access domains)
                parsed_domain = urlparse(url).hostname or ""
                if any(parsed_domain.endswith(d) for d in OPEN_ACCESS_DOMAINS):
                    paywall_result = type(
                        "PaywallResult",
                        (),
                        {"detected": False, "access_type": "full", "confidence": 0, "indicators": []},
                    )()
                else:
                    detector = get_paywall_detector()
                    paywall_result = detector.detect(html, text, url)

                # Determine access status
                if paywall_result.detected:
                    access_status = "paywall" if paywall_result.access_type == "blocked" else "partial"
                    access_message = detector.get_access_status_message(paywall_result)
                else:
                    access_status = "full"
                    access_message = "Full content accessible"

                # Apply focus extraction if specified
                if focus:
                    text = self._extract_focused_content(text, focus, 100000)

                message = f"Content fetched ({access_status}): {len(text)} chars. {access_message}"
                if focus:
                    message = f"[FOCUSED: {focus}] {message}"

                # Increment visit counter and record in task state after successful fetch
                self._url_visit_counts[normalized_url] = visit_count + 1
                try:
                    from app.domain.services.agents.task_state_manager import get_task_state_manager

                    tsm = get_task_state_manager()
                    tsm.record_url(url)
                except Exception:
                    logger.debug("Failed to record URL visit in task state", exc_info=True)

                # Cache the fetched content
                if len(self._url_cache) >= self._url_cache_max:
                    oldest = min(self._url_cache, key=lambda k: self._url_cache[k][0])
                    del self._url_cache[oldest]
                self._url_cache[url] = (time.time(), text)

                # Wait for browser nav to complete (already running concurrently)
                nav_succeeded = False
                if nav_task:
                    try:
                        nav_succeeded = await nav_task
                    except Exception as nav_err:
                        logger.debug(f"navigate_for_display task failed: {nav_err}")
                    nav_task = None

                # Retry display navigation once if background task failed — ensures
                # the CDP screenshot matches what the agent reports it browsed
                if not nav_succeeded and hasattr(self.browser, "navigate_for_display"):
                    try:
                        await self.browser.navigate_for_display(url)
                    except Exception as retry_err:
                        logger.debug(f"navigate_for_display retry failed (non-critical): {retry_err}")

                return ToolResult(
                    success=True,
                    message=message,
                    data={
                        "content": text,
                        "url": fetched_url,
                        "access_status": access_status,
                        "focus": focus,
                        "paywall_confidence": paywall_result.confidence,
                        "paywall_indicators": paywall_result.indicators[:3] if paywall_result.indicators else [],
                    },
                )
        except Exception as e:
            logger.debug(f"Fast fetch failed for {url}: {e}, falling back to browser")
            if nav_task and not nav_task.done():
                nav_task.cancel()
                with contextlib.suppress(Exception):
                    await nav_task
        finally:
            # Re-enable background browsing so future search enrichment can work
            if _cancelled_bg and hasattr(self.browser, "allow_background_browsing"):
                self.browser.allow_background_browsing()

        # Fallback to full browser navigation with focus
        if focus:
            return await self.browser_navigate(url, intent="informational", focus=focus)
        return await self.browser_navigate(url)

    @tool(
        name="browser_view",
        description="""View current browser page content and interactive elements.

USE WHEN:
- Checking latest page state AFTER clicks, scrolls, or form interactions
- Re-extracting interactive elements after a dynamic page update
- Verifying content has loaded after an explicit wait

DO NOT USE:
- Immediately after browser_navigate — navigation already extracts full page content
  and returns interactive elements in the same call. Calling browser_view right after
  browser_navigate is redundant and wastes a tool call.

RETURNS: Page content, interactive elements list with indices, current URL, title.
Use element indices with browser_click, browser_input, etc.""",
        parameters={},
        required=[],
    )
    async def browser_view(self) -> ToolResult:
        """View current browser page content

        Returns:
            Browser page content
        """
        return await self.browser.view_page()

    @tool(
        name="browser_navigate",
        description="""Navigate browser to URL with automatic content loading (live preview visible).

AUTOMATIC BEHAVIOR (faster response, fewer tool calls):
- Scrolls page to load lazy content
- Extracts page content immediately
- Returns interactive elements + full content in single call

OPTIONAL INTENTS:
- navigational: General browsing, exploring pages (default)
- informational: Content extraction focus, research tasks
- transactional: Form filling, purchases, interactive operations

FOCUS (informational intent only):
For informational browsing, specify a focus area to extract relevant content.
Example: focus="pricing information" or focus="technical specifications"

Returns: Interactive elements, page content, title, URL - ready to use without additional calls.""",
        parameters={
            "url": {"type": "string", "description": "Complete URL to visit. Must include protocol prefix."},
            "intent": {
                "type": "string",
                "enum": ["navigational", "informational", "transactional"],
                "description": "(Optional) Browsing intent: navigational (general), informational (research), transactional (forms/purchase)",
            },
            "focus": {
                "type": "string",
                "description": "(Optional) For informational intent: specific content area to focus on (e.g., 'pricing', 'technical specs', 'reviews')",
            },
        },
        required=["url"],
    )
    async def browser_navigate(self, url: str, intent: str = "navigational", focus: str | None = None) -> ToolResult:
        """Navigate browser to specified URL with automatic content extraction

        Args:
            url: Complete URL address, must include protocol prefix
            intent: Browsing intent (navigational, informational, transactional)
            focus: Focus area for informational browsing

        Returns:
            Navigation result with interactive elements and page content
        """
        # Check per-session visit count and reject repeated visits.
        # Only count visits that actually succeeded — timed-out or failed navigations
        # must not block retries (the page was never loaded).
        nav_normalized_url = self._normalize_url_for_visit_tracking(url)
        nav_visit_count = self._url_visit_counts.get(nav_normalized_url, 0)

        if nav_visit_count >= 1:
            logger.warning(f"browser_navigate: URL visited {nav_visit_count} times, returning rejection: {url[:80]}")
            return ToolResult(
                success=True,
                message=(
                    "This URL was already visited this session. "
                    "The page content has not changed since the last visit. "
                    "Use the information already extracted. Do NOT navigate here again."
                ),
                data={"url": url, "visit_count": nav_visit_count},
            )

        # Navigate to URL
        result = await self.browser.navigate(url)

        # Only record URL visit and increment counter AFTER successful navigation.
        # Failed/timed-out navigations must not block future retries — neither
        # in the in-memory counter nor in the task-state prompt context.
        if result.success:
            self._url_visit_counts[nav_normalized_url] = nav_visit_count + 1
            try:
                from app.domain.services.agents.task_state_manager import get_task_state_manager

                tsm = get_task_state_manager()
                tsm.record_url(url)
            except Exception:
                logger.debug("Failed to record URL visit in task state", exc_info=True)

        if not result.success:
            return result

        status_code: int | None = None
        if result.data and isinstance(result.data, dict):
            raw_status = result.data.get("status")
            if isinstance(raw_status, int):
                status_code = raw_status

        if status_code is not None and status_code >= 400:
            return ToolResult(
                success=False,
                message=(
                    f"Navigation to {url} returned HTTP {status_code}. "
                    "Treat this source as unavailable and use an alternative URL."
                ),
                data=result.data,
            )

        # Parse intent
        try:
            browser_intent = BrowserIntent(intent.lower())
        except ValueError:
            browser_intent = BrowserIntent.NAVIGATIONAL
            logger.warning(f"Unknown browser intent '{intent}', defaulting to 'navigational'")

        # Get intent configuration
        config = BROWSER_INTENT_CONFIG.get(browser_intent, BROWSER_INTENT_CONFIG[BrowserIntent.NAVIGATIONAL])

        # Apply intent-specific post-processing
        if result.data and isinstance(result.data, dict):
            # For informational intent with focus, extract focused content
            if browser_intent == BrowserIntent.INFORMATIONAL and focus:
                content = result.data.get("content", "")
                focused_content = self._extract_focused_content(content, focus, config.get("max_content_length", 50000))
                result.data["content"] = focused_content
                result.data["focus"] = focus
                result.message = f"[INFORMATIONAL - Focus: {focus}] {result.message or ''}"

            # For transactional intent, emphasize interactive elements
            elif browser_intent == BrowserIntent.TRANSACTIONAL:
                if result.message:
                    result.message = f"[TRANSACTIONAL] {result.message}"
                else:
                    result.message = "[TRANSACTIONAL] Ready for form interaction"

            # Add intent metadata
            result.data["intent"] = browser_intent.value

        return result

    @tool(
        name="browser_restart",
        description="Restart browser and navigate to specified URL. Use when browser state needs to be reset.",
        parameters={
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix.",
            }
        },
        required=["url"],
    )
    async def browser_restart(self, url: str) -> ToolResult:
        """Restart browser and navigate to specified URL

        Args:
            url: Complete URL address to visit after restart, must include protocol prefix

        Returns:
            Restart result
        """
        # Reset URL visit counters — a restart means fresh browser state,
        # so previous visit failures should not block navigation to the target URL.
        self._url_visit_counts.clear()
        return await self.browser.restart(url)

    @tool(
        name="browser_click",
        description="""Click an interactive element on the page.

PREFERRED: Use element index from browser_navigate or browser_view results.
Alternative: Use coordinates for elements not in the interactive list.

AUTO-SCROLLS into view if element is off-screen.
AUTO-WAITS for potential navigation after click.

RETURNS: Click result. Use browser_view to see updated page state.""",
        parameters={
            "index": {
                "type": "integer",
                "description": "Element index from interactive elements list (preferred method)",
            },
            "coordinate_x": {"type": "number", "description": "X coordinate for coordinate-based click (fallback)"},
            "coordinate_y": {"type": "number", "description": "Y coordinate for coordinate-based click (fallback)"},
        },
        required=[],
    )
    async def browser_click(
        self, index: int | None = None, coordinate_x: float | None = None, coordinate_y: float | None = None
    ) -> ToolResult:
        """Click on elements in the current browser page

        Args:
            index: (Optional) Index number of the element to click
            coordinate_x: (Optional) X coordinate of click position
            coordinate_y: (Optional) Y coordinate of click position

        Returns:
            Click result
        """
        return await self.browser.click(index, coordinate_x, coordinate_y)

    @tool(
        name="browser_input",
        description="""Type text into an input field, textarea, or editable element.

AUTO-CLEARS existing content before typing (replaces, doesn't append).
Use element index from browser_navigate/browser_view for reliable targeting.

For search boxes: Set press_enter=true to submit.
For forms: Set press_enter=false and use browser_click on submit button.""",
        parameters={
            "index": {"type": "integer", "description": "Element index from interactive elements list (preferred)"},
            "coordinate_x": {"type": "number", "description": "X coordinate for coordinate-based input (fallback)"},
            "coordinate_y": {"type": "number", "description": "Y coordinate for coordinate-based input (fallback)"},
            "text": {"type": "string", "description": "Text to type (replaces existing content)"},
            "press_enter": {
                "type": "boolean",
                "description": "Press Enter after typing (true for search, false for multi-field forms)",
            },
        },
        required=["text", "press_enter"],
    )
    async def browser_input(
        self,
        text: str,
        press_enter: bool,
        index: int | None = None,
        coordinate_x: float | None = None,
        coordinate_y: float | None = None,
    ) -> ToolResult:
        """Overwrite text in editable elements on the current browser page

        Args:
            text: Complete text content to overwrite
            press_enter: Whether to press Enter key after input
            index: (Optional) Index number of the element to overwrite text
            coordinate_x: (Optional) X coordinate of the element to overwrite text
            coordinate_y: (Optional) Y coordinate of the element to overwrite text

        Returns:
            Input result
        """
        return await self.browser.input(text, press_enter, index, coordinate_x, coordinate_y)

    @tool(
        name="browser_move_mouse",
        description="Move cursor to specified position on the current browser page. Use when simulating user mouse movement.",
        parameters={
            "coordinate_x": {"type": "number", "description": "X coordinate of target cursor position"},
            "coordinate_y": {"type": "number", "description": "Y coordinate of target cursor position"},
        },
        required=["coordinate_x", "coordinate_y"],
    )
    async def browser_move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        """Move mouse cursor to specified position on the current browser page

        Args:
            coordinate_x: X coordinate of target cursor position
            coordinate_y: Y coordinate of target cursor position

        Returns:
            Move result
        """
        return await self.browser.move_mouse(coordinate_x, coordinate_y)

    @tool(
        name="browser_press_key",
        description="Simulate key press in the current browser page. Use when specific keyboard operations are needed.",
        parameters={
            "key": {
                "type": "string",
                "description": "Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter).",
            }
        },
        required=["key"],
    )
    async def browser_press_key(self, key: str) -> ToolResult:
        """Simulate key press in the current browser page

        Args:
            key: Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter)

        Returns:
            Key press result
        """
        return await self.browser.press_key(key)

    @tool(
        name="browser_select_option",
        description="Select specified option from dropdown list element in the current browser page. Use when selecting dropdown menu options.",
        parameters={
            "index": {"type": "integer", "description": "Index number of the dropdown list element"},
            "option": {"type": "integer", "description": "Option number to select, starting from 0."},
        },
        required=["index", "option"],
    )
    async def browser_select_option(self, index: int, option: int) -> ToolResult:
        """Select specified option from dropdown list element in the current browser page

        Args:
            index: Index number of the dropdown list element
            option: Option number to select, starting from 0

        Returns:
            Selection result
        """
        return await self.browser.select_option(index, option)

    @tool(
        name="browser_scroll_up",
        description="""Scroll up to view content above current position.

USE WHEN:
- Returning to content seen earlier
- Going back to page header/navigation
- Reaching top of page after scrolling down

RETURNS: Updated page state after scroll.""",
        parameters={
            "to_top": {
                "type": "boolean",
                "description": "(Optional) Jump directly to page top instead of one viewport up.",
            }
        },
        required=[],
    )
    async def browser_scroll_up(self, to_top: bool | None = None) -> ToolResult:
        """Scroll up the current browser page

        Args:
            to_top: (Optional) Whether to scroll directly to page top instead of one viewport up

        Returns:
            Scroll result
        """
        return await self.browser.scroll_up(to_top)

    @tool(
        name="browser_scroll_down",
        description="""Scroll down to view more content and trigger lazy loading.

LAZY CONTENT: Many sites load content as you scroll (infinite scroll, lazy images).
Scrolling reveals hidden content that wasn't in the initial view.

USE WHEN:
- Need to see content below the fold
- Loading more items in lists/feeds (infinite scroll)
- Triggering lazy-loaded images and content
- Navigating through long pages

RETURNS: Updated page state after scroll. Use browser_view to extract new content.""",
        parameters={
            "to_bottom": {
                "type": "boolean",
                "description": "(Optional) Scroll to page bottom. Use for short pages or when you need the footer.",
            }
        },
        required=[],
    )
    async def browser_scroll_down(self, to_bottom: bool | None = None) -> ToolResult:
        """Scroll down the current browser page

        Args:
            to_bottom: (Optional) Whether to scroll directly to page bottom instead of one viewport down

        Returns:
            Scroll result
        """
        return await self.browser.scroll_down(to_bottom)

    @tool(
        name="browser_console_exec",
        description="Execute JavaScript code in browser console. Use when custom scripts need to be executed.",
        parameters={
            "javascript": {
                "type": "string",
                "description": "JavaScript code to execute. Note that the runtime environment is browser console.",
            }
        },
        required=["javascript"],
    )
    async def browser_console_exec(self, javascript: str) -> ToolResult:
        """Execute JavaScript code in browser console

        Args:
            javascript: JavaScript code to execute, note that the runtime environment is browser console

        Returns:
            Execution result
        """
        return await self.browser.console_exec(javascript)

    @tool(
        name="browser_console_view",
        description="View browser console output. Use when checking JavaScript logs or debugging page errors.",
        parameters={
            "max_lines": {"type": "integer", "description": "(Optional) Maximum number of log lines to return."}
        },
        required=[],
    )
    async def browser_console_view(self, max_lines: int | None = None) -> ToolResult:
        """View browser console output

        Args:
            max_lines: (Optional) Maximum number of log lines to return

        Returns:
            Console output
        """
        return await self.browser.console_view(max_lines)
