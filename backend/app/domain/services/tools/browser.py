import logging
import re

import aiohttp

from app.domain.external.browser import Browser
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool
from app.domain.services.tools.paywall_detector import PaywallDetector

logger = logging.getLogger(__name__)

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


async def get_http_session() -> aiohttp.ClientSession:
    """Get or create shared HTTP session for connection pooling.

    Uses reduced timeouts (15s total, 5s connect) for faster failure detection.
    """
    global _http_session
    if _http_session is None or _http_session.closed:
        # Reduced timeout: 15s total, 5s connect for faster failure detection
        # (was 30s total, 10s connect)
        timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
        _http_session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
    return _http_session


def html_to_text(html: str, max_length: int = 50000) -> str:
    """Convert HTML to clean text, stripping tags and extracting content.

    A lightweight alternative to BeautifulSoup for simple text extraction.
    """
    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Convert common block elements to newlines
    html = re.sub(r'<(p|div|br|h[1-6]|li|tr)[^>]*>', '\n', html, flags=re.IGNORECASE)

    # Remove all other HTML tags
    html = re.sub(r'<[^>]+>', '', html)

    # Decode common HTML entities
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&amp;', '&')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&quot;', '"')
    html = html.replace('&#39;', "'")

    # Clean up whitespace
    html = re.sub(r'\n\s*\n', '\n\n', html)
    html = re.sub(r' +', ' ', html)
    html = html.strip()

    return html[:max_length] if len(html) > max_length else html


class BrowserTool(BaseTool):
    """Browser tool class, providing browser interaction functions with text-first mode"""

    name: str = "browser"

    def __init__(self, browser: Browser, max_observe: int | None = None):
        """Initialize browser tool class

        Args:
            browser: Browser service
            max_observe: Optional custom observation limit (default: 10000)
        """
        super().__init__(max_observe=max_observe)
        self.browser = browser

    @tool(
        name="browser_get_content",
        description="""Fast fetch page content as text (no browser rendering).
Use for research tasks when you only need to read text content without interactions.
Much faster than browser_navigate for read-only pages. Falls back to browser_navigate on failure.""",
        parameters={
            "url": {
                "type": "string",
                "description": "Complete URL to fetch content from. Must include protocol prefix."
            }
        },
        required=["url"]
    )
    async def browser_get_content(self, url: str) -> ToolResult:
        """Fast fetch page content as text without browser rendering.

        Uses lightweight HTTP client for speed. Ideal for research tasks.
        Falls back to full browser navigation on failure.

        Args:
            url: Complete URL to fetch

        Returns:
            Page text content
        """
        try:
            session = await get_http_session()
            async with session.get(url, allow_redirects=True) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' in content_type or 'text/plain' in content_type:
                        html = await response.text()
                        text = html_to_text(html)
                        if len(text) > 500:  # Valid content threshold
                            # Detect paywall
                            detector = get_paywall_detector()
                            paywall_result = detector.detect(html, text, url)

                            # Determine access status
                            if paywall_result.detected:
                                access_status = "paywall" if paywall_result.access_type == "blocked" else "partial"
                                access_message = detector.get_access_status_message(paywall_result)
                            else:
                                access_status = "full"
                                access_message = "Full content accessible"

                            return ToolResult(
                                success=True,
                                message=f"Content fetched ({access_status}): {len(text)} chars. {access_message}",
                                data={
                                    "content": text,
                                    "url": str(response.url),
                                    "access_status": access_status,
                                    "paywall_confidence": paywall_result.confidence,
                                    "paywall_indicators": paywall_result.indicators[:3] if paywall_result.indicators else []
                                }
                            )
                    logger.debug(f"Content type {content_type} not suitable for fast fetch")
        except Exception as e:
            logger.debug(f"Fast fetch failed for {url}: {e}, falling back to browser")

        # Fallback to full browser navigation
        return await self.browser_navigate(url)

    @tool(
        name="browser_view",
        description="""View current browser page content and interactive elements.

USE WHEN:
- Checking latest page state after clicks, scrolls, or other interactions
- Verifying page content has loaded after waiting
- Re-extracting interactive elements after page updates

RETURNS: Page content, interactive elements list with indices, current URL, title.
Use element indices with browser_click, browser_input, etc.""",
        parameters={},
        required=[]
    )
    async def browser_view(self) -> ToolResult:
        """View current browser page content

        Returns:
            Browser page content
        """
        return await self.browser.view_page()

    @tool(
        name="browser_navigate",
        description="""Navigate browser to URL with automatic content loading.

AUTOMATIC BEHAVIOR (faster response, fewer tool calls):
- Scrolls page to load lazy content
- Extracts page content immediately
- Returns interactive elements + full content in single call

Returns: Interactive elements, page content, title, URL - ready to use without additional calls.""",
        parameters={
            "url": {
                "type": "string",
                "description": "Complete URL to visit. Must include protocol prefix."
            }
        },
        required=["url"]
    )
    async def browser_navigate(self, url: str) -> ToolResult:
        """Navigate browser to specified URL with automatic content extraction

        Args:
            url: Complete URL address, must include protocol prefix

        Returns:
            Navigation result with interactive elements and page content
        """
        return await self.browser.navigate(url)

    @tool(
        name="browser_restart",
        description="Restart browser and navigate to specified URL. Use when browser state needs to be reset.",
        parameters={
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix."
            }
        },
        required=["url"]
    )
    async def browser_restart(self, url: str) -> ToolResult:
        """Restart browser and navigate to specified URL
        
        Args:
            url: Complete URL address to visit after restart, must include protocol prefix
            
        Returns:
            Restart result
        """
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
                "description": "Element index from interactive elements list (preferred method)"
            },
            "coordinate_x": {
                "type": "number",
                "description": "X coordinate for coordinate-based click (fallback)"
            },
            "coordinate_y": {
                "type": "number",
                "description": "Y coordinate for coordinate-based click (fallback)"
            }
        },
        required=[]
    )
    async def browser_click(
        self,
        index: int | None = None,
        coordinate_x: float | None = None,
        coordinate_y: float | None = None
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
            "index": {
                "type": "integer",
                "description": "Element index from interactive elements list (preferred)"
            },
            "coordinate_x": {
                "type": "number",
                "description": "X coordinate for coordinate-based input (fallback)"
            },
            "coordinate_y": {
                "type": "number",
                "description": "Y coordinate for coordinate-based input (fallback)"
            },
            "text": {
                "type": "string",
                "description": "Text to type (replaces existing content)"
            },
            "press_enter": {
                "type": "boolean",
                "description": "Press Enter after typing (true for search, false for multi-field forms)"
            }
        },
        required=["text", "press_enter"]
    )
    async def browser_input(
        self,
        text: str,
        press_enter: bool,
        index: int | None = None,
        coordinate_x: float | None = None,
        coordinate_y: float | None = None
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
            "coordinate_x": {
                "type": "number",
                "description": "X coordinate of target cursor position"
            },
            "coordinate_y": {
                "type": "number",
                "description": "Y coordinate of target cursor position"
            }
        },
        required=["coordinate_x", "coordinate_y"]
    )
    async def browser_move_mouse(
        self,
        coordinate_x: float,
        coordinate_y: float
    ) -> ToolResult:
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
                "description": "Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter)."
            }
        },
        required=["key"]
    )
    async def browser_press_key(
        self,
        key: str
    ) -> ToolResult:
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
            "index": {
                "type": "integer",
                "description": "Index number of the dropdown list element"
            },
            "option": {
                "type": "integer",
                "description": "Option number to select, starting from 0."
            }
        },
        required=["index", "option"]
    )
    async def browser_select_option(
        self,
        index: int,
        option: int
    ) -> ToolResult:
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
                "description": "(Optional) Jump directly to page top instead of one viewport up."
            }
        },
        required=[]
    )
    async def browser_scroll_up(
        self,
        to_top: bool | None = None
    ) -> ToolResult:
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
                "description": "(Optional) Scroll to page bottom. Use for short pages or when you need the footer."
            }
        },
        required=[]
    )
    async def browser_scroll_down(
        self,
        to_bottom: bool | None = None
    ) -> ToolResult:
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
                "description": "JavaScript code to execute. Note that the runtime environment is browser console."
            }
        },
        required=["javascript"]
    )
    async def browser_console_exec(
        self,
        javascript: str
    ) -> ToolResult:
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
            "max_lines": {
                "type": "integer",
                "description": "(Optional) Maximum number of log lines to return."
            }
        },
        required=[]
    )
    async def browser_console_view(
        self,
        max_lines: int | None = None
    ) -> ToolResult:
        """View browser console output

        Args:
            max_lines: (Optional) Maximum number of log lines to return

        Returns:
            Console output
        """
        return await self.browser.console_view(max_lines)

    @tool(
        name="browsing",
        description="""Execute complex multi-step browsing task autonomously using AI.

WHEN TO USE:
- Complex workflows: research, comparison shopping, multi-page navigation
- Form filling with contextual understanding
- Data extraction across multiple pages
- When user wants to "watch" autonomous browsing in VNC

AUTOMATIC CAPABILITIES:
- Navigates pages intelligently
- Scrolls to find elements
- Clicks buttons and links
- Fills forms with context awareness
- Extracts and processes data
- Handles pagination and multi-step flows

ALL ACTIONS VISIBLE IN REAL-TIME VIA VNC

Examples:
- "Search Amazon for wireless keyboards, filter by 4+ stars, extract top 3 products"
- "Go to httpbin.org/forms/post and fill the form with test data"
- "Research Python async tutorials, visit top 3 sites, summarize key concepts"
""",
        parameters={
            "task": {
                "type": "string",
                "description": "Natural language description of the browsing task. Be specific about what to search, filter, extract, or do."
            },
            "max_steps": {
                "type": "integer",
                "description": "Maximum autonomous actions before stopping. Default: 20. Range: 5-50. Use higher for complex multi-page tasks."
            }
        },
        required=["task"]
    )
    async def browsing(
        self,
        task: str,
        max_steps: int | None = 20
    ) -> ToolResult:
        """Execute autonomous browsing task with natural language instruction

        Args:
            task: Natural language task description
            max_steps: Maximum autonomous actions (default: 20, range: 5-50)

        Returns:
            Execution results with actions taken and final output
        """
        try:
            # Lazy import to avoid circular dependencies
            from app.infrastructure.external.browser.browseruse_browser import (
                BrowserUseService,
                is_browser_use_available,
            )

            # Check if browser-use is available
            if not is_browser_use_available():
                return ToolResult(
                    success=False,
                    message="Browser-use library not installed. Install with: pip install browser-use>=0.11.0"
                )

            # Validate max_steps range
            if max_steps is not None:
                max_steps = max(5, min(50, max_steps))
            else:
                max_steps = 20

            # Get or create browser-use service
            if not hasattr(self.browser, 'browseruse_service'):
                # Get CDP URL from existing browser
                cdp_url = getattr(self.browser, 'cdp_url', 'http://localhost:9222')

                # Create browser-use service
                self.browser.browseruse_service = BrowserUseService(cdp_url=cdp_url)
                await self.browser.browseruse_service.initialize()

                logger.info("Initialized browser-use service for autonomous browsing")

            # Execute autonomous task
            logger.info(f"Executing autonomous task (max_steps={max_steps}): {task}")

            result = await self.browser.browseruse_service.execute_autonomous_task(
                task=task,
                max_steps=max_steps
            )

            if result["success"]:
                # Format successful result
                actions_summary = "\n".join([
                    f"Step {action['step']}: {action['action']}"
                    for action in result["actions"][:10]  # Show first 10 steps
                ])

                if len(result["actions"]) > 10:
                    actions_summary += f"\n... and {len(result['actions']) - 10} more steps"

                return ToolResult(
                    success=True,
                    message=f"Autonomous task completed in {result['total_steps']} steps",
                    data={
                        "final_result": result["final_result"],
                        "total_steps": result["total_steps"],
                        "actions_summary": actions_summary,
                        "model_used": result.get("model_used", "gpt-4o-mini"),
                        "all_actions": result["actions"]  # Full action history
                    }
                )
            # Task failed
            return ToolResult(
                success=False,
                message=f"Autonomous task failed: {result.get('error', 'Unknown error')}"
            )

        except Exception as e:
            logger.error(f"browsing failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                message=f"Failed to execute autonomous task: {e!s}"
            )
