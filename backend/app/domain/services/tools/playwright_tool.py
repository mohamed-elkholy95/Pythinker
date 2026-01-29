"""
Playwright-based browser automation tool.

Provides advanced browser automation using Playwright with support for
multiple browsers (Chromium, Firefox, WebKit), sophisticated selectors,
wait conditions, and screenshot/PDF capture. Designed to coexist with
the existing CDP-based BrowserTool.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class BrowserType(str, Enum):
    """Supported browser types."""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class WaitState(str, Enum):
    """Page wait states."""
    LOAD = "load"  # Wait for load event
    DOMCONTENTLOADED = "domcontentloaded"  # Wait for DOMContentLoaded
    NETWORKIDLE = "networkidle"  # Wait until no network connections for 500ms


@dataclass
class PageState:
    """Current state of a browser page."""
    url: str
    title: str
    viewport_width: int
    viewport_height: int
    scroll_x: int
    scroll_y: int
    has_cookies: bool = False
    is_loading: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "scroll": {"x": self.scroll_x, "y": self.scroll_y},
            "has_cookies": self.has_cookies,
            "is_loading": self.is_loading,
        }


@dataclass
class Cookie:
    """Browser cookie representation."""
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: float | None = None
    http_only: bool = False
    secure: bool = False
    same_site: str = "Lax"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Playwright."""
        cookie_dict = {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "httpOnly": self.http_only,
            "secure": self.secure,
            "sameSite": self.same_site,
        }
        if self.expires:
            cookie_dict["expires"] = self.expires
        return cookie_dict


class PlaywrightTool(BaseTool):
    """
    Playwright-based browser automation tool.

    Provides multi-browser support with advanced automation capabilities:
    - Multi-browser: Chromium, Firefox, WebKit
    - Navigation with configurable wait states
    - Element interaction: click, fill, type, select
    - Screenshots and PDF capture
    - Cookie management
    - Page wait conditions
    - Stealth mode (Phase 4): Bot detection bypass

    Note: This tool executes Playwright commands in the sandbox environment
    via shell execution, allowing it to work without direct Playwright dependency
    in the backend.
    """

    name: str = "playwright"

    # Stealth mode user agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]

    # Stealth viewport sizes for randomization
    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1366, "height": 768},
        {"width": 1280, "height": 720},
    ]

    # Stealth Chromium args to disable automation detection
    STEALTH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        "--disable-web-security",
        "--disable-features=BlockInsecurePrivateNetworkRequests",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--no-zygote",
        "--disable-gpu",
    ]

    def __init__(
        self,
        sandbox: Sandbox,
        session_id: str | None = None,
        max_observe: int | None = None,
        default_browser: BrowserType = BrowserType.CHROMIUM,
        headless: bool = True,
        stealth_mode: bool = False,
    ):
        """
        Initialize Playwright tool.

        Args:
            sandbox: Sandbox service for command execution
            session_id: Session identifier
            max_observe: Optional custom observation limit
            default_browser: Default browser type to use
            headless: Run browser in headless mode
            stealth_mode: Enable stealth mode for bot detection bypass
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox
        self.session_id = session_id or str(uuid.uuid4())
        self.default_browser = default_browser
        self.headless = headless
        self.stealth_mode = stealth_mode
        self._workspace = f"/workspace/{self.session_id}/playwright"
        self._initialized = False
        self._browser_launched = False
        self._current_user_agent = None
        self._current_viewport = None

    async def _ensure_workspace(self) -> None:
        """Ensure workspace directory exists."""
        if self._initialized:
            return

        result = await self.sandbox.exec_command(
            self.session_id,
            "/",
            f"mkdir -p {self._workspace}"
        )
        self._initialized = True

    async def _run_playwright_script(
        self,
        script: str,
        timeout: int = 30,
    ) -> ToolResult:
        """
        Run a Playwright script in the sandbox.

        Args:
            script: Python script using Playwright
            timeout: Execution timeout in seconds

        Returns:
            ToolResult with script output
        """
        await self._ensure_workspace()

        # Generate unique script file
        script_id = str(uuid.uuid4())[:8]
        script_path = f"{self._workspace}/script_{script_id}.py"

        # Wrap script with proper imports and async handling
        full_script = f'''
import asyncio
import json
import sys
from playwright.async_api import async_playwright

async def main():
    result = {{"success": False, "data": None, "error": None}}
    try:
{self._indent_code(script, 8)}
    except Exception as e:
        result["error"] = str(e)
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
'''

        # Write script to file
        write_result = await self.sandbox.file_write(script_path, full_script)
        if not write_result.success:
            return ToolResult(
                success=False,
                message=f"Failed to write script: {write_result.message}"
            )

        # Execute script
        exec_result = await self.sandbox.exec_command(
            self.session_id,
            self._workspace,
            f"timeout {timeout}s python3 {script_path} 2>&1"
        )

        # Clean up script file
        await self.sandbox.file_delete(script_path)

        # Parse result
        if exec_result.success and exec_result.message:
            try:
                # Find JSON output in the result
                lines = exec_result.message.strip().split('\n')
                for line in reversed(lines):
                    if line.strip().startswith('{'):
                        result_data = json.loads(line)
                        if result_data.get("error"):
                            return ToolResult(
                                success=False,
                                message=f"Playwright error: {result_data['error']}"
                            )
                        return ToolResult(
                            success=True,
                            message=str(result_data.get("data", "Success")),
                            data=result_data.get("data")
                        )
            except json.JSONDecodeError:
                pass

        return ToolResult(
            success=exec_result.success,
            message=exec_result.message or "Script execution completed"
        )

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by specified number of spaces."""
        indent = " " * spaces
        lines = code.split('\n')
        return '\n'.join(indent + line for line in lines)

    @tool(
        name="playwright_launch",
        description="Launch a Playwright browser instance. Must be called before other playwright operations.",
        parameters={
            "browser_type": {
                "type": "string",
                "description": "Browser to launch: chromium, firefox, or webkit",
                "enum": ["chromium", "firefox", "webkit"]
            },
            "headless": {
                "type": "boolean",
                "description": "Run browser in headless mode (default: true)"
            },
            "viewport_width": {
                "type": "integer",
                "description": "Viewport width in pixels (default: 1280)"
            },
            "viewport_height": {
                "type": "integer",
                "description": "Viewport height in pixels (default: 720)"
            }
        },
        required=[]
    )
    async def playwright_launch(
        self,
        browser_type: str | None = None,
        headless: bool | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> ToolResult:
        """
        Launch a Playwright browser.

        Args:
            browser_type: Browser type (chromium, firefox, webkit)
            headless: Run in headless mode
            viewport_width: Viewport width
            viewport_height: Viewport height

        Returns:
            ToolResult with launch status
        """
        browser = browser_type or self.default_browser.value
        is_headless = headless if headless is not None else self.headless

        script = f'''
async with async_playwright() as p:
    browser = await p.{browser}.launch(headless={is_headless})
    context = await browser.new_context(viewport={{"width": {viewport_width}, "height": {viewport_height}}})
    page = await context.new_page()
    result["success"] = True
    result["data"] = {{"browser": "{browser}", "headless": {is_headless}, "viewport": {{"width": {viewport_width}, "height": {viewport_height}}}}}
    await browser.close()
'''

        result = await self._run_playwright_script(script)
        if result.success:
            self._browser_launched = True
        return result

    @tool(
        name="playwright_navigate",
        description="Navigate to a URL and wait for the page to load. Supports optional stealth mode with user agent rotation and human-like delays.",
        parameters={
            "url": {
                "type": "string",
                "description": "URL to navigate to"
            },
            "wait_until": {
                "type": "string",
                "description": "Wait condition: load, domcontentloaded, or networkidle",
                "enum": ["load", "domcontentloaded", "networkidle"]
            },
            "timeout": {
                "type": "integer",
                "description": "Navigation timeout in milliseconds (default: 30000)"
            },
            "stealth": {
                "type": "boolean",
                "description": "Enable stealth mode with random user agent/viewport (default: false)"
            },
            "human_delay": {
                "type": "boolean",
                "description": "Add random human-like delays (default: true when stealth is enabled)"
            }
        },
        required=["url"]
    )
    async def playwright_navigate(
        self,
        url: str,
        wait_until: str = "load",
        timeout: int = 30000,
        stealth: bool = False,
        human_delay: bool | None = None,
    ) -> ToolResult:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition
            timeout: Navigation timeout in ms
            stealth: Enable stealth mode with random user agent and viewport
            human_delay: Add random human-like delays (defaults to stealth setting)

        Returns:
            ToolResult with page info
        """
        # Check config for stealth defaults
        try:
            from app.core.config import get_settings
            settings = get_settings()
            if not stealth and settings.browser_stealth_enabled:
                stealth = True
            if human_delay is None:
                human_delay = stealth and settings.browser_human_delays
        except Exception:
            if human_delay is None:
                human_delay = stealth

        if stealth:
            user_agent = self._get_random_user_agent()
            viewport = self._get_random_viewport()
            self._current_user_agent = user_agent
            self._current_viewport = viewport

            delay_code = ""
            if human_delay:
                delay_code = """
    import random
    await asyncio.sleep(random.uniform(0.1, 0.5))
"""

            script = f'''
import asyncio

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={viewport},
        user_agent="{user_agent}",
    )
    page = await context.new_page()

    # Disable webdriver detection
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
    """)
    {delay_code}
    response = await page.goto("{url}", wait_until="{wait_until}", timeout={timeout})

    title = await page.title()
    content = await page.content()

    result["success"] = True
    result["data"] = {{
        "url": page.url,
        "title": title,
        "status": response.status if response else None,
        "content_length": len(content),
        "stealth_mode": True,
        "user_agent": "{user_agent}",
    }}

    await browser.close()
'''
        else:
            script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    response = await page.goto("{url}", wait_until="{wait_until}", timeout={timeout})

    title = await page.title()
    content = await page.content()

    result["success"] = True
    result["data"] = {{
        "url": page.url,
        "title": title,
        "status": response.status if response else None,
        "content_length": len(content)
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script, timeout=timeout // 1000 + 10)

    @tool(
        name="playwright_click",
        description="Click on an element using a CSS selector.",
        parameters={
            "selector": {
                "type": "string",
                "description": "CSS selector for the element to click"
            },
            "button": {
                "type": "string",
                "description": "Mouse button: left, right, or middle",
                "enum": ["left", "right", "middle"]
            },
            "click_count": {
                "type": "integer",
                "description": "Number of clicks (default: 1)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (default: 30000)"
            }
        },
        required=["selector"]
    )
    async def playwright_click(
        self,
        selector: str,
        button: str = "left",
        click_count: int = 1,
        timeout: int = 30000,
    ) -> ToolResult:
        """
        Click on an element.

        Args:
            selector: CSS selector
            button: Mouse button
            click_count: Number of clicks
            timeout: Timeout in ms

        Returns:
            ToolResult with click status
        """
        # Escape selector for Python string
        safe_selector = selector.replace('"', '\\"')

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Assuming page is already navigated
    await page.click("{safe_selector}", button="{button}", click_count={click_count}, timeout={timeout})

    result["success"] = True
    result["data"] = {{"selector": "{safe_selector}", "clicked": True}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_fill",
        description="Fill an input field with text. Clears existing content first.",
        parameters={
            "selector": {
                "type": "string",
                "description": "CSS selector for the input element"
            },
            "text": {
                "type": "string",
                "description": "Text to fill in the input"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (default: 30000)"
            }
        },
        required=["selector", "text"]
    )
    async def playwright_fill(
        self,
        selector: str,
        text: str,
        timeout: int = 30000,
    ) -> ToolResult:
        """
        Fill an input field.

        Args:
            selector: CSS selector
            text: Text to fill
            timeout: Timeout in ms

        Returns:
            ToolResult with fill status
        """
        safe_selector = selector.replace('"', '\\"')
        safe_text = text.replace('"', '\\"').replace('\n', '\\n')

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    await page.fill("{safe_selector}", "{safe_text}", timeout={timeout})

    result["success"] = True
    result["data"] = {{"selector": "{safe_selector}", "filled": True}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_type",
        description="Type text character by character (useful for inputs that react to each keystroke).",
        parameters={
            "selector": {
                "type": "string",
                "description": "CSS selector for the input element"
            },
            "text": {
                "type": "string",
                "description": "Text to type"
            },
            "delay": {
                "type": "integer",
                "description": "Delay between keystrokes in milliseconds (default: 50)"
            }
        },
        required=["selector", "text"]
    )
    async def playwright_type(
        self,
        selector: str,
        text: str,
        delay: int = 50,
    ) -> ToolResult:
        """
        Type text character by character.

        Args:
            selector: CSS selector
            text: Text to type
            delay: Delay between keystrokes in ms

        Returns:
            ToolResult with type status
        """
        safe_selector = selector.replace('"', '\\"')
        safe_text = text.replace('"', '\\"').replace('\n', '\\n')

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    await page.type("{safe_selector}", "{safe_text}", delay={delay})

    result["success"] = True
    result["data"] = {{"selector": "{safe_selector}", "typed": True, "length": {len(text)}}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_screenshot",
        description="Take a screenshot of the current page or a specific element.",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to save the screenshot (default: auto-generated)"
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element screenshot (optional)"
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full scrollable page (default: false)"
            },
            "type": {
                "type": "string",
                "description": "Image type: png or jpeg",
                "enum": ["png", "jpeg"]
            }
        },
        required=[]
    )
    async def playwright_screenshot(
        self,
        path: str | None = None,
        selector: str | None = None,
        full_page: bool = False,
        type: str = "png",
    ) -> ToolResult:
        """
        Take a screenshot.

        Args:
            path: Save path
            selector: Element selector for element screenshot
            full_page: Capture full page
            type: Image type

        Returns:
            ToolResult with screenshot info
        """
        screenshot_id = str(uuid.uuid4())[:8]
        save_path = path or f"{self._workspace}/screenshot_{screenshot_id}.{type}"

        if selector:
            safe_selector = selector.replace('"', '\\"')
            script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    element = await page.query_selector("{safe_selector}")
    if element:
        await element.screenshot(path="{save_path}", type="{type}")
        result["success"] = True
        result["data"] = {{"path": "{save_path}", "selector": "{safe_selector}"}}
    else:
        result["error"] = "Element not found"

    await browser.close()
'''
        else:
            script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    await page.screenshot(path="{save_path}", full_page={full_page}, type="{type}")

    result["success"] = True
    result["data"] = {{"path": "{save_path}", "full_page": {full_page}}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_pdf",
        description="Generate a PDF of the current page (Chromium only).",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to save the PDF (default: auto-generated)"
            },
            "format": {
                "type": "string",
                "description": "Paper format: Letter, Legal, A4, etc.",
                "enum": ["Letter", "Legal", "A4", "A3", "Tabloid"]
            },
            "print_background": {
                "type": "boolean",
                "description": "Print background graphics (default: true)"
            }
        },
        required=[]
    )
    async def playwright_pdf(
        self,
        path: str | None = None,
        format: str = "Letter",
        print_background: bool = True,
    ) -> ToolResult:
        """
        Generate a PDF of the page.

        Args:
            path: Save path
            format: Paper format
            print_background: Include background

        Returns:
            ToolResult with PDF info
        """
        pdf_id = str(uuid.uuid4())[:8]
        save_path = path or f"{self._workspace}/page_{pdf_id}.pdf"

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    await page.pdf(path="{save_path}", format="{format}", print_background={print_background})

    result["success"] = True
    result["data"] = {{"path": "{save_path}", "format": "{format}"}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_wait_for_selector",
        description="Wait for an element matching the selector to appear.",
        parameters={
            "selector": {
                "type": "string",
                "description": "CSS selector to wait for"
            },
            "state": {
                "type": "string",
                "description": "Wait for element state: attached, detached, visible, or hidden",
                "enum": ["attached", "detached", "visible", "hidden"]
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (default: 30000)"
            }
        },
        required=["selector"]
    )
    async def playwright_wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout: int = 30000,
    ) -> ToolResult:
        """
        Wait for an element to reach a state.

        Args:
            selector: CSS selector
            state: Element state to wait for
            timeout: Timeout in ms

        Returns:
            ToolResult with wait status
        """
        safe_selector = selector.replace('"', '\\"')

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    element = await page.wait_for_selector("{safe_selector}", state="{state}", timeout={timeout})

    result["success"] = True
    result["data"] = {{"selector": "{safe_selector}", "state": "{state}", "found": element is not None}}

    await browser.close()
'''

        return await self._run_playwright_script(script, timeout=timeout // 1000 + 10)

    @tool(
        name="playwright_get_cookies",
        description="Get all cookies from the current browser context.",
        parameters={
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter cookies by URLs (optional)"
            }
        },
        required=[]
    )
    async def playwright_get_cookies(
        self,
        urls: list[str] | None = None,
    ) -> ToolResult:
        """
        Get browser cookies.

        Args:
            urls: Optional URL filter

        Returns:
            ToolResult with cookies
        """
        urls_param = json.dumps(urls) if urls else "None"

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    urls = {urls_param}
    cookies = await context.cookies(urls) if urls else await context.cookies()

    result["success"] = True
    result["data"] = {{"cookies": cookies, "count": len(cookies)}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_set_cookies",
        description="Set cookies in the browser context.",
        parameters={
            "cookies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "domain": {"type": "string"},
                        "path": {"type": "string"},
                        "secure": {"type": "boolean"},
                        "httpOnly": {"type": "boolean"}
                    }
                },
                "description": "Array of cookie objects to set"
            }
        },
        required=["cookies"]
    )
    async def playwright_set_cookies(
        self,
        cookies: list[dict[str, Any]],
    ) -> ToolResult:
        """
        Set browser cookies.

        Args:
            cookies: List of cookie objects

        Returns:
            ToolResult with set status
        """
        cookies_json = json.dumps(cookies)

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()

    cookies = {cookies_json}
    await context.add_cookies(cookies)

    result["success"] = True
    result["data"] = {{"cookies_set": len(cookies)}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_get_content",
        description="Get the full HTML content of the current page.",
        parameters={
            "url": {
                "type": "string",
                "description": "URL to navigate to first (optional)"
            }
        },
        required=[]
    )
    async def playwright_get_content(
        self,
        url: str | None = None,
    ) -> ToolResult:
        """
        Get page HTML content.

        Args:
            url: Optional URL to navigate to first

        Returns:
            ToolResult with HTML content
        """
        navigate_line = f'await page.goto("{url}")' if url else "pass"

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    {navigate_line}

    content = await page.content()
    title = await page.title()

    result["success"] = True
    result["data"] = {{"content": content[:50000], "title": title, "url": page.url, "length": len(content)}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_evaluate",
        description="Execute JavaScript in the page context and return the result.",
        parameters={
            "expression": {
                "type": "string",
                "description": "JavaScript expression to evaluate"
            }
        },
        required=["expression"]
    )
    async def playwright_evaluate(
        self,
        expression: str,
    ) -> ToolResult:
        """
        Evaluate JavaScript in the page.

        Args:
            expression: JavaScript expression

        Returns:
            ToolResult with evaluation result
        """
        # Escape the expression for Python string
        safe_expr = expression.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    eval_result = await page.evaluate("{safe_expr}")

    result["success"] = True
    result["data"] = {{"result": eval_result}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_select_option",
        description="Select option(s) from a select element.",
        parameters={
            "selector": {
                "type": "string",
                "description": "CSS selector for the select element"
            },
            "values": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Option values to select"
            }
        },
        required=["selector", "values"]
    )
    async def playwright_select_option(
        self,
        selector: str,
        values: list[str],
    ) -> ToolResult:
        """
        Select options from a dropdown.

        Args:
            selector: CSS selector
            values: Values to select

        Returns:
            ToolResult with selection status
        """
        safe_selector = selector.replace('"', '\\"')
        values_json = json.dumps(values)

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    selected = await page.select_option("{safe_selector}", {values_json})

    result["success"] = True
    result["data"] = {{"selector": "{safe_selector}", "selected": selected}}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    # ==================== Phase 4: Stealth Mode Features ====================

    def _get_random_user_agent(self) -> str:
        """Get a random user agent for stealth mode."""
        import random
        return random.choice(self.USER_AGENTS)

    def _get_random_viewport(self) -> dict[str, int]:
        """Get a random viewport for stealth mode."""
        import random
        return random.choice(self.VIEWPORTS)

    def _get_stealth_args(self) -> str:
        """Get stealth args as a Python list string."""
        return str(self.STEALTH_ARGS)

    @tool(
        name="playwright_stealth_navigate",
        description="Navigate to a URL with stealth mode enabled to bypass bot detection. Uses random user agents, viewports, and anti-detection techniques.",
        parameters={
            "url": {
                "type": "string",
                "description": "URL to navigate to"
            },
            "wait_until": {
                "type": "string",
                "description": "Wait condition: load, domcontentloaded, or networkidle",
                "enum": ["load", "domcontentloaded", "networkidle"]
            },
            "timeout": {
                "type": "integer",
                "description": "Navigation timeout in milliseconds (default: 60000)"
            },
            "human_delay": {
                "type": "boolean",
                "description": "Add random human-like delays (default: true)"
            }
        },
        required=["url"]
    )
    async def playwright_stealth_navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: int = 60000,
        human_delay: bool = True,
    ) -> ToolResult:
        """
        Navigate with stealth mode enabled.

        Uses playwright-stealth and various evasion techniques to
        bypass bot detection systems.
        """
        user_agent = self._get_random_user_agent()
        viewport = self._get_random_viewport()
        stealth_args = self._get_stealth_args()

        self._current_user_agent = user_agent
        self._current_viewport = viewport

        delay_code = ""
        if human_delay:
            delay_code = """
    import random
    await asyncio.sleep(random.uniform(0.5, 2.0))
"""

        script = f'''
import asyncio
from playwright_stealth import stealth_async

async with async_playwright() as p:
    browser = await p.chromium.launch(
        headless=True,
        args={stealth_args}
    )
    context = await browser.new_context(
        viewport={viewport},
        user_agent="{user_agent}",
        locale="en-US",
        timezone_id="America/New_York",
    )
    page = await context.new_page()
    await stealth_async(page)

    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
    """)
    {delay_code}
    response = await page.goto("{url}", wait_until="{wait_until}", timeout={timeout})
    title = await page.title()
    content = await page.content()

    bot_detected = "captcha" in content.lower() or "cloudflare" in content.lower()

    result["success"] = True
    result["data"] = {{
        "url": page.url,
        "title": title,
        "status": response.status if response else None,
        "stealth_mode": True,
        "bot_detected": bot_detected,
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script, timeout=timeout // 1000 + 30)

    @tool(
        name="playwright_detect_protection",
        description="Detect what type of bot protection is present on a page.",
        parameters={
            "url": {
                "type": "string",
                "description": "URL to check for protection"
            }
        },
        required=["url"]
    )
    async def playwright_detect_protection(
        self,
        url: str,
    ) -> ToolResult:
        """Detect bot protection systems on a page."""
        user_agent = self._get_random_user_agent()
        viewport = self._get_random_viewport()

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={viewport},
        user_agent="{user_agent}"
    )
    page = await context.new_page()
    response = await page.goto("{url}", wait_until="domcontentloaded", timeout=30000)
    content = await page.content()
    content_lower = content.lower()

    protections = []
    if "cloudflare" in content_lower:
        protections.append({{"type": "cloudflare", "confidence": "high"}})
    if "recaptcha" in content_lower:
        protections.append({{"type": "recaptcha", "confidence": "high"}})
    if "hcaptcha" in content_lower:
        protections.append({{"type": "hcaptcha", "confidence": "high"}})

    result["success"] = True
    result["data"] = {{
        "url": "{url}",
        "status": response.status if response else None,
        "protections_detected": protections,
        "is_protected": len(protections) > 0,
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_intercept_requests",
        description="Intercept and optionally block network requests.",
        parameters={
            "url": {
                "type": "string",
                "description": "URL to navigate to"
            },
            "block_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URL patterns to block"
            }
        },
        required=["url"]
    )
    async def playwright_intercept_requests(
        self,
        url: str,
        block_patterns: list[str] | None = None,
    ) -> ToolResult:
        """Intercept and block network requests."""
        patterns = json.dumps(block_patterns or [])

        script = f'''
import re

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    blocked_count = 0
    block_patterns = {patterns}

    async def handle_route(route):
        nonlocal blocked_count
        url = route.request.url
        for pattern in block_patterns:
            if re.search(pattern.replace("*", ".*"), url):
                blocked_count += 1
                await route.abort()
                return
        await route.continue_()

    await page.route("**/*", handle_route)
    await page.goto("{url}", wait_until="networkidle", timeout=60000)
    title = await page.title()

    result["success"] = True
    result["data"] = {{
        "url": page.url,
        "title": title,
        "blocked_requests": blocked_count,
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script, timeout=90)

    # ==================== Phase 2.4: Anti-Bot Features ====================

    @tool(
        name="playwright_solve_recaptcha",
        description="Solve a reCAPTCHA challenge using an external solving service (requires API key configuration).",
        parameters={
            "site_key": {
                "type": "string",
                "description": "The reCAPTCHA site key (data-sitekey attribute)"
            },
            "page_url": {
                "type": "string",
                "description": "The URL of the page containing the CAPTCHA"
            },
            "captcha_type": {
                "type": "string",
                "description": "Type of reCAPTCHA: v2, v3, or enterprise",
                "enum": ["v2", "v3", "enterprise"]
            },
            "action": {
                "type": "string",
                "description": "Action name for v3/enterprise (e.g., 'login', 'submit')"
            }
        },
        required=["site_key", "page_url"]
    )
    async def playwright_solve_recaptcha(
        self,
        site_key: str,
        page_url: str,
        captcha_type: str = "v2",
        action: str = "verify",
    ) -> ToolResult:
        """
        Solve a reCAPTCHA challenge using an external service.

        Requires browser_recaptcha_solver and browser_recaptcha_api_key
        to be configured in settings.

        Args:
            site_key: reCAPTCHA site key
            page_url: URL of the page with CAPTCHA
            captcha_type: Type of reCAPTCHA (v2, v3, enterprise)
            action: Action name for v3/enterprise

        Returns:
            ToolResult with solution token
        """
        try:
            from app.core.config import get_settings
            settings = get_settings()

            solver = settings.browser_recaptcha_solver
            api_key = settings.browser_recaptcha_api_key

            if not solver or not api_key:
                return ToolResult(
                    success=False,
                    message="CAPTCHA solver not configured. Set browser_recaptcha_solver and browser_recaptcha_api_key in settings."
                )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to get settings: {e}"
            )

        # Generate script based on solver type
        if solver == "anticaptcha":
            script = f'''
from anticaptchaofficial.recaptchav2proxyless import recaptchaV2Proxyless
from anticaptchaofficial.recaptchav3proxyless import recaptchaV3Proxyless

api_key = "{api_key}"
site_key = "{site_key}"
page_url = "{page_url}"
captcha_type = "{captcha_type}"
action = "{action}"

try:
    if captcha_type == "v2":
        solver = recaptchaV2Proxyless()
        solver.set_key(api_key)
        solver.set_website_url(page_url)
        solver.set_website_key(site_key)
        token = solver.solve_and_return_solution()
    elif captcha_type in ("v3", "enterprise"):
        solver = recaptchaV3Proxyless()
        solver.set_key(api_key)
        solver.set_website_url(page_url)
        solver.set_website_key(site_key)
        solver.set_page_action(action)
        solver.set_min_score(0.7)
        if captcha_type == "enterprise":
            solver.set_is_enterprise(True)
        token = solver.solve_and_return_solution()
    else:
        result["error"] = f"Unsupported captcha type: {{captcha_type}}"
        token = None

    if token:
        result["success"] = True
        result["data"] = {{
            "token": token,
            "captcha_type": captcha_type,
            "site_key": site_key,
        }}
    else:
        result["error"] = solver.error_code if hasattr(solver, 'error_code') else "Failed to solve CAPTCHA"
except Exception as e:
    result["error"] = str(e)
'''
        elif solver == "2captcha":
            script = f'''
import requests
import time

api_key = "{api_key}"
site_key = "{site_key}"
page_url = "{page_url}"
captcha_type = "{captcha_type}"

try:
    # Submit CAPTCHA
    if captcha_type == "v2":
        submit_url = f"http://2captcha.com/in.php?key={{api_key}}&method=userrecaptcha&googlekey={{site_key}}&pageurl={{page_url}}&json=1"
    elif captcha_type in ("v3", "enterprise"):
        action = "{action}"
        submit_url = f"http://2captcha.com/in.php?key={{api_key}}&method=userrecaptcha&googlekey={{site_key}}&pageurl={{page_url}}&version=v3&action={{action}}&min_score=0.7&json=1"
        if captcha_type == "enterprise":
            submit_url += "&enterprise=1"
    else:
        result["error"] = f"Unsupported captcha type: {{captcha_type}}"
        raise ValueError("Unsupported type")

    response = requests.get(submit_url)
    submit_result = response.json()

    if submit_result.get("status") != 1:
        result["error"] = submit_result.get("request", "Submit failed")
        raise ValueError("Submit failed")

    captcha_id = submit_result["request"]

    # Poll for result
    for _ in range(60):
        time.sleep(3)
        check_url = f"http://2captcha.com/res.php?key={{api_key}}&action=get&id={{captcha_id}}&json=1"
        response = requests.get(check_url)
        check_result = response.json()

        if check_result.get("status") == 1:
            result["success"] = True
            result["data"] = {{
                "token": check_result["request"],
                "captcha_type": captcha_type,
                "site_key": site_key,
            }}
            break
        elif check_result.get("request") != "CAPCHA_NOT_READY":
            result["error"] = check_result.get("request", "Unknown error")
            break
    else:
        result["error"] = "Timeout waiting for CAPTCHA solution"

except Exception as e:
    if not result.get("error"):
        result["error"] = str(e)
'''
        else:
            return ToolResult(
                success=False,
                message=f"Unknown CAPTCHA solver: {solver}. Supported: anticaptcha, 2captcha"
            )

        return await self._run_playwright_script(script, timeout=180)

    @tool(
        name="playwright_cloudflare_bypass",
        description="Navigate through a Cloudflare challenge page with extended wait times and stealth mode.",
        parameters={
            "url": {
                "type": "string",
                "description": "URL to navigate to (may be behind Cloudflare)"
            },
            "max_wait_seconds": {
                "type": "integer",
                "description": "Maximum seconds to wait for challenge to complete (default: 30)"
            }
        },
        required=["url"]
    )
    async def playwright_cloudflare_bypass(
        self,
        url: str,
        max_wait_seconds: int = 30,
    ) -> ToolResult:
        """
        Navigate through a Cloudflare challenge page.

        Uses stealth mode with extended wait times to handle Cloudflare's
        "checking your browser" and similar challenge pages.

        Args:
            url: URL to navigate to
            max_wait_seconds: Maximum time to wait for challenge

        Returns:
            ToolResult with page info after bypass
        """
        user_agent = self._get_random_user_agent()
        viewport = self._get_random_viewport()
        stealth_args = self._get_stealth_args()

        self._current_user_agent = user_agent
        self._current_viewport = viewport

        script = f'''
import asyncio

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

async with async_playwright() as p:
    browser = await p.chromium.launch(
        headless=True,
        args={stealth_args}
    )
    context = await browser.new_context(
        viewport={viewport},
        user_agent="{user_agent}",
        locale="en-US",
        timezone_id="America/New_York",
    )
    page = await context.new_page()

    if HAS_STEALTH:
        await stealth_async(page)

    # Disable webdriver detection
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
        Object.defineProperty(navigator, 'plugins', {{get: () => [1, 2, 3]}});
        Object.defineProperty(navigator, 'languages', {{get: () => ['en-US', 'en']}});
    """)

    # Initial navigation
    response = await page.goto("{url}", wait_until="domcontentloaded", timeout=60000)

    # Wait for Cloudflare challenge to complete
    cloudflare_detected = False
    challenge_passed = False
    max_wait = {max_wait_seconds}

    for _ in range(max_wait):
        content = await page.content()
        content_lower = content.lower()

        # Check for Cloudflare challenge indicators
        if any(indicator in content_lower for indicator in [
            "checking your browser",
            "please wait",
            "ddos-guard",
            "cf-challenge",
            "cf_chl_opt",
            "ray id",
        ]):
            cloudflare_detected = True
            await asyncio.sleep(1)
        else:
            if cloudflare_detected:
                challenge_passed = True
            break

    title = await page.title()
    final_url = page.url
    final_content = await page.content()
    status = response.status if response else None

    result["success"] = True
    result["data"] = {{
        "url": final_url,
        "title": title,
        "status": status,
        "cloudflare_detected": cloudflare_detected,
        "challenge_passed": challenge_passed,
        "content_length": len(final_content),
        "stealth_mode": True,
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script, timeout=max_wait_seconds + 90)

    @tool(
        name="playwright_fill_2fa_code",
        description="Auto-fill a 2FA/TOTP code from a stored credential into a form field.",
        parameters={
            "credential_id": {
                "type": "string",
                "description": "ID of the credential containing the TOTP secret"
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for the 2FA input field"
            },
            "url": {
                "type": "string",
                "description": "URL of the page (for context in logs)"
            }
        },
        required=["credential_id", "selector"]
    )
    async def playwright_fill_2fa_code(
        self,
        credential_id: str,
        selector: str,
        url: str | None = None,
    ) -> ToolResult:
        """
        Auto-fill a 2FA/TOTP code from a stored credential.

        Retrieves the current TOTP code from the credential manager
        and fills it into the specified form field.

        Args:
            credential_id: Credential ID with TOTP secret
            selector: CSS selector for the 2FA input field
            url: URL context for logging

        Returns:
            ToolResult with fill status
        """
        try:
            from app.domain.services.security.credential_manager import get_credential_manager

            credential_manager = get_credential_manager()
            totp_code = await credential_manager.get_totp_code(
                credential_id,
                session_id=self.session_id,
            )

            if not totp_code:
                return ToolResult(
                    success=False,
                    message=f"Failed to get TOTP code for credential {credential_id}. "
                           "Ensure the credential has a totp_secret field."
                )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to get TOTP code: {e}"
            )

        safe_selector = selector.replace('"', '\\"')
        safe_code = totp_code

        script = f'''
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Fill the 2FA code
    await page.fill("{safe_selector}", "{safe_code}", timeout=10000)

    result["success"] = True
    result["data"] = {{
        "selector": "{safe_selector}",
        "code_filled": True,
        "code_length": len("{safe_code}"),
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script)

    @tool(
        name="playwright_login_with_2fa",
        description="Complete a full login flow including username, password, and 2FA code from stored credentials.",
        parameters={
            "credential_id": {
                "type": "string",
                "description": "ID of the credential containing login data and optional TOTP secret"
            },
            "url": {
                "type": "string",
                "description": "Login page URL"
            },
            "username_selector": {
                "type": "string",
                "description": "CSS selector for username/email field"
            },
            "password_selector": {
                "type": "string",
                "description": "CSS selector for password field"
            },
            "submit_selector": {
                "type": "string",
                "description": "CSS selector for submit/login button"
            },
            "totp_selector": {
                "type": "string",
                "description": "CSS selector for 2FA input field (optional)"
            }
        },
        required=["credential_id", "url", "username_selector", "password_selector", "submit_selector"]
    )
    async def playwright_login_with_2fa(
        self,
        credential_id: str,
        url: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        totp_selector: str | None = None,
    ) -> ToolResult:
        """
        Complete a full login flow with optional 2FA.

        Args:
            credential_id: Credential ID with login data
            url: Login page URL
            username_selector: Username field selector
            password_selector: Password field selector
            submit_selector: Submit button selector
            totp_selector: 2FA input selector (optional)

        Returns:
            ToolResult with login status
        """
        try:
            from app.domain.services.security.credential_manager import get_credential_manager

            credential_manager = get_credential_manager()
            credential = await credential_manager.get(
                credential_id,
                session_id=self.session_id,
            )

            if not credential:
                return ToolResult(
                    success=False,
                    message=f"Credential {credential_id} not found"
                )

            username = credential.data.get("username") or credential.data.get("email")
            password = credential.data.get("password")

            if not username or not password:
                return ToolResult(
                    success=False,
                    message="Credential must have username/email and password fields"
                )

            # Get TOTP code if needed
            totp_code = None
            if totp_selector and credential.data.get("totp_secret"):
                totp_code = await credential_manager.get_totp_code(
                    credential_id,
                    session_id=self.session_id,
                )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to get credentials: {e}"
            )

        safe_username = username.replace('"', '\\"')
        safe_password = password.replace('"', '\\"')
        safe_username_sel = username_selector.replace('"', '\\"')
        safe_password_sel = password_selector.replace('"', '\\"')
        safe_submit_sel = submit_selector.replace('"', '\\"')

        totp_fill_code = ""
        if totp_code and totp_selector:
            safe_totp_sel = totp_selector.replace('"', '\\"')
            totp_fill_code = f'''
    # Wait for 2FA page
    await asyncio.sleep(1)
    try:
        await page.wait_for_selector("{safe_totp_sel}", state="visible", timeout=10000)
        await page.fill("{safe_totp_sel}", "{totp_code}")
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception as totp_error:
        pass  # 2FA might not be required
'''

        user_agent = self._get_random_user_agent()
        viewport = self._get_random_viewport()

        script = f'''
import asyncio

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={viewport},
        user_agent="{user_agent}",
    )
    page = await context.new_page()

    # Navigate to login page
    await page.goto("{url}", wait_until="networkidle", timeout=30000)

    # Fill login form
    await page.fill("{safe_username_sel}", "{safe_username}")
    await asyncio.sleep(0.3)
    await page.fill("{safe_password_sel}", "{safe_password}")
    await asyncio.sleep(0.2)

    # Submit form
    await page.click("{safe_submit_sel}")
    await page.wait_for_load_state("networkidle", timeout=30000)

    {totp_fill_code}

    title = await page.title()
    final_url = page.url

    result["success"] = True
    result["data"] = {{
        "url": final_url,
        "title": title,
        "login_attempted": True,
        "totp_used": {str(bool(totp_code)).lower()},
    }}

    await browser.close()
'''

        return await self._run_playwright_script(script, timeout=90)
