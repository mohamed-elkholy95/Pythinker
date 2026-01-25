"""
Playwright-based browser automation tool.

Provides advanced browser automation using Playwright with support for
multiple browsers (Chromium, Firefox, WebKit), sophisticated selectors,
wait conditions, and screenshot/PDF capture. Designed to coexist with
the existing CDP-based BrowserTool.
"""

import logging
import asyncio
import base64
import json
import uuid
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult

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

    def to_dict(self) -> Dict[str, Any]:
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
    expires: Optional[float] = None
    http_only: bool = False
    secure: bool = False
    same_site: str = "Lax"

    def to_dict(self) -> Dict[str, Any]:
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
        session_id: Optional[str] = None,
        max_observe: Optional[int] = None,
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
        browser_type: Optional[str] = None,
        headless: Optional[bool] = None,
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
        description="Navigate to a URL and wait for the page to load.",
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
            }
        },
        required=["url"]
    )
    async def playwright_navigate(
        self,
        url: str,
        wait_until: str = "load",
        timeout: int = 30000,
    ) -> ToolResult:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition
            timeout: Navigation timeout in ms

        Returns:
            ToolResult with page info
        """
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
        path: Optional[str] = None,
        selector: Optional[str] = None,
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
        path: Optional[str] = None,
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
        urls: Optional[List[str]] = None,
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
        cookies: List[Dict[str, Any]],
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
        url: Optional[str] = None,
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
        values: List[str],
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

    def _get_random_viewport(self) -> Dict[str, int]:
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
        block_patterns: Optional[List[str]] = None,
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
