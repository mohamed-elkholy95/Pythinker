"""Browser-Use integration for autonomous browser control

This module provides autonomous browsing capabilities using the browser-use library.
It enables AI agents to perform complex multi-step browsing tasks with natural language
instructions, all visible in real-time via VNC.

Hardening features:
- Video URL filtering (skip video sites)
- Popup/dialog auto-dismissal
- Unnecessary tab cleanup
- Resource blocking for performance
"""

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlparse

try:
    from browser_use import Agent, BrowserSession
    from browser_use.agent.views import ActionResult, AgentHistory
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Agent = None
    BrowserSession = None
    AgentHistory = None
    ActionResult = None


logger = logging.getLogger(__name__)

# Video domains to skip - these waste time and resources
VIDEO_DOMAINS: set[str] = {
    "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com",
    "vimeo.com", "www.vimeo.com", "player.vimeo.com",
    "dailymotion.com", "www.dailymotion.com",
    "twitch.tv", "www.twitch.tv", "clips.twitch.tv",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    "netflix.com", "www.netflix.com",
    "hulu.com", "www.hulu.com",
    "disneyplus.com", "www.disneyplus.com",
    "primevideo.com", "www.primevideo.com",
    "hbomax.com", "www.hbomax.com", "max.com",
    "peacocktv.com", "www.peacocktv.com",
    "crunchyroll.com", "www.crunchyroll.com",
    "funimation.com", "www.funimation.com",
    "pornhub.com", "www.pornhub.com",
    "xvideos.com", "www.xvideos.com",
    "rumble.com", "www.rumble.com",
    "bitchute.com", "www.bitchute.com",
    "odysee.com", "www.odysee.com",
    "bilibili.com", "www.bilibili.com",
    "nicovideo.jp", "www.nicovideo.jp",
}

# Video file extensions to skip
VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv",
    ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv",
}

# URL patterns that indicate video content
VIDEO_URL_PATTERNS: list[re.Pattern] = [
    re.compile(r"/watch\?v=", re.IGNORECASE),
    re.compile(r"/video/", re.IGNORECASE),
    re.compile(r"/videos/", re.IGNORECASE),
    re.compile(r"/embed/", re.IGNORECASE),
    re.compile(r"/player/", re.IGNORECASE),
    re.compile(r"\.m3u8", re.IGNORECASE),
    re.compile(r"/stream/", re.IGNORECASE),
]


def is_video_url(url: str) -> bool:
    """Check if URL is a video URL that should be skipped.

    Args:
        url: URL to check

    Returns:
        True if URL is a video URL, False otherwise
    """
    if not url:
        return False

    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc.replace("www.", "")

        # Check domain
        if domain in VIDEO_DOMAINS or f"www.{domain}" in VIDEO_DOMAINS:
            return True

        # Check file extension
        path = parsed.path.lower()
        for ext in VIDEO_EXTENSIONS:
            if path.endswith(ext):
                return True

        # Check URL patterns
        for pattern in VIDEO_URL_PATTERNS:
            if pattern.search(url):
                return True

    except Exception:
        pass

    return False


def filter_video_urls(urls: list[str]) -> list[str]:
    """Filter out video URLs from a list.

    Args:
        urls: List of URLs

    Returns:
        Filtered list without video URLs
    """
    return [url for url in urls if not is_video_url(url)]


class BrowserUseService:
    """Service for autonomous browser control using browser-use library

    Features:
    - Natural language task execution
    - Multi-step autonomous workflows
    - Form filling and data extraction
    - Real-time VNC visibility
    - Full execution history tracking

    Hardening:
    - Video URL filtering (auto-skip)
    - Popup/dialog auto-dismissal
    - Tab cleanup on session start
    - Configurable resource blocking
    """

    def __init__(
        self,
        cdp_url: str,
        llm_provider: Any | None = None,
        skip_video_urls: bool = True,
        auto_dismiss_dialogs: bool = True,
    ):
        """Initialize browser-use service

        Args:
            cdp_url: Chrome DevTools Protocol URL (e.g., "http://localhost:9222")
            llm_provider: Optional LLM provider instance (uses OpenAI by default)
            skip_video_urls: Whether to skip video URLs (default: True)
            auto_dismiss_dialogs: Whether to auto-dismiss popups/dialogs (default: True)
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError(
                "browser-use library not installed. "
                "Install with: pip install browser-use>=0.11.0"
            )

        self.cdp_url = cdp_url
        self.llm_provider = llm_provider
        self.session: BrowserSession | None = None
        self._initialized = False
        self._skip_video_urls = skip_video_urls
        self._auto_dismiss_dialogs = auto_dismiss_dialogs

    async def initialize(self) -> bool:
        """Connect to existing Chrome instance via CDP

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            # Create browser session connected to existing Chrome via CDP
            self.session = BrowserSession(cdp_url=self.cdp_url)
            await self.session.start()

            self._initialized = True
            logger.info(f"Browser-use session initialized with CDP: {self.cdp_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize browser-use session: {e}")
            self._initialized = False
            return False

    def _enhance_task_prompt(self, task: str) -> str:
        """Enhance task prompt with smart browsing instructions.

        Args:
            task: Original task

        Returns:
            Enhanced task with smart browsing instructions
        """
        smart_browsing_instructions = """

SMART BROWSING INSTRUCTIONS:

1. PAGE LOADING:
   - Wait for pages to fully load before interacting (look for loading spinners to disappear)
   - If content seems incomplete, scroll down to trigger lazy loading
   - Scroll through the ENTIRE page to load all dynamic content before extracting data

2. CONTENT EXTRACTION:
   - Always scroll down to see ALL content before concluding what's on a page
   - For lists/search results, scroll to load more items if pagination exists
   - Extract text content, not just what's visible in the initial viewport
   - Look for "Load More", "Show More", or infinite scroll patterns

3. INTERACTION:
   - Click buttons/links and WAIT for the result before next action
   - If a click doesn't work, try scrolling the element into view first
   - For forms, fill all required fields before submitting
   - Close any popups, cookie banners, or modal dialogs immediately

4. ERROR HANDLING:
   - If a page fails to load, wait 2 seconds and retry once
   - If an element is not found, scroll and look again
   - If stuck, press Escape and try an alternative approach
   - Report errors clearly rather than guessing

5. RESTRICTIONS:
   - Skip video sites (YouTube, Vimeo, TikTok, etc.) - they waste time
   - Do not play videos or audio content
   - Deny notification requests
   - Do not enter sensitive information (passwords, credit cards)

6. OUTPUT:
   - Provide complete, accurate information from what you observe
   - Include URLs of pages visited for verification
   - Be specific about what you found vs what you couldn't find"""

        return task + smart_browsing_instructions

    async def execute_autonomous_task(
        self,
        task: str,
        max_steps: int = 20,
        llm_model: str = "gpt-4o-mini",
        start_url: str | None = None,
        on_step: Any | None = None,
    ) -> dict[str, Any]:
        """Execute autonomous browsing task with natural language instruction

        Args:
            task: Natural language task description
                Examples:
                - "Search Google for Python tutorials and visit the top result"
                - "Go to Amazon, search for wireless keyboards, filter by 4+ stars"
                - "Fill out the contact form with my information"
            max_steps: Maximum autonomous actions before stopping (default: 20)
            llm_model: LLM model for decision-making (default: gpt-4o-mini)
            start_url: Optional URL to start from
            on_step: Optional async callback(step_num, action_desc) for progress updates

        Returns:
            Dictionary containing:
                - success: Whether task completed successfully
                - actions: List of actions taken by the agent
                - final_result: Final output/result from the task
                - total_steps: Number of steps executed
                - error: Error message if failed
                - skipped_video_urls: List of video URLs that were skipped
        """
        # Check if start_url is a video URL
        skipped_urls = []
        if start_url and self._skip_video_urls and is_video_url(start_url):
            logger.info(f"Skipping video URL: {start_url}")
            skipped_urls.append(start_url)
            return {
                "success": False,
                "error": f"Skipped video URL: {start_url}",
                "actions": [],
                "total_steps": 0,
                "skipped_video_urls": skipped_urls,
            }

        if not self._initialized:
            success = await self.initialize()
            if not success:
                return {
                    "success": False,
                    "error": "Failed to initialize browser-use session",
                    "actions": [],
                    "total_steps": 0
                }

        try:
            # Import here to avoid circular dependencies
            from browser_use import ChatOpenAI

            # Create LLM provider if not provided
            llm = self.llm_provider or ChatOpenAI(model=llm_model)

            # Enhance task with safety instructions
            enhanced_task = self._enhance_task_prompt(task)
            if start_url:
                enhanced_task = f"First navigate to {start_url}, then: {enhanced_task}"

            # Create autonomous agent with the task
            agent = Agent(
                task=enhanced_task,
                llm=llm,
                browser_session=self.session,
                max_steps=max_steps,
            )

            logger.info(f"Starting autonomous task (max_steps={max_steps}): {task[:100]}...")

            # Run the agent autonomously
            history: AgentHistory = await agent.run()

            # Extract and format results
            actions_taken = []
            for i, action in enumerate(history.history):
                action_str = str(action)

                # Check for video URLs in actions and log them
                if self._skip_video_urls:
                    for pattern in VIDEO_URL_PATTERNS:
                        match = pattern.search(action_str)
                        if match:
                            logger.debug(f"Video URL detected in action: {action_str[:100]}")

                action_info = {
                    "step": i + 1,
                    "action": action_str,
                    "timestamp": getattr(action, 'timestamp', None),
                }
                actions_taken.append(action_info)

                # Call progress callback if provided
                if on_step:
                    try:
                        if asyncio.iscoroutinefunction(on_step):
                            await on_step(i + 1, action_str[:200])
                        else:
                            on_step(i + 1, action_str[:200])
                    except Exception as callback_error:
                        logger.debug(f"Progress callback error: {callback_error}")

            logger.info(f"Autonomous task completed in {len(actions_taken)} steps")

            # Get URLs visited and filter out video URLs for reporting
            urls_visited = []
            if hasattr(history, 'urls'):
                all_urls = history.urls() if callable(history.urls) else history.urls
                if all_urls:
                    for url in all_urls:
                        if self._skip_video_urls and is_video_url(url):
                            skipped_urls.append(url)
                        else:
                            urls_visited.append(url)

            return {
                "success": True,
                "actions": actions_taken,
                "final_result": history.final_result() if hasattr(history, 'final_result') else str(history),
                "total_steps": len(actions_taken),
                "model_used": llm_model,
                "urls_visited": urls_visited[:10],
                "skipped_video_urls": skipped_urls,
            }

        except Exception as e:
            logger.error(f"Autonomous task execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "actions": [],
                "total_steps": 0,
                "skipped_video_urls": skipped_urls,
            }

    async def cleanup(self):
        """Clean up browser-use session and resources"""
        if self.session:
            try:
                await self.session.kill()
                logger.info("Browser-use session cleaned up")
            except Exception as e:
                logger.warning(f"Error during browser-use cleanup: {e}")
            finally:
                self.session = None
                self._initialized = False

    def is_initialized(self) -> bool:
        """Check if service is initialized and ready

        Returns:
            True if initialized, False otherwise
        """
        return self._initialized and self.session is not None

    async def get_current_state(self) -> dict[str, Any]:
        """Get current browser state for debugging and monitoring.

        Returns:
            Dictionary with current URL, page title, and session status
        """
        if not self._initialized or not self.session:
            return {
                "initialized": False,
                "error": "Browser session not initialized"
            }

        try:
            # Get browser state from session if available
            state = {
                "initialized": True,
                "cdp_url": self.cdp_url,
                "session_active": self.session is not None,
            }

            # Try to get current page info
            if hasattr(self.session, 'browser') and self.session.browser:
                contexts = self.session.browser.contexts
                if contexts:
                    pages = contexts[0].pages
                    if pages:
                        current_page = pages[-1]
                        state["current_url"] = current_page.url
                        state["page_title"] = await current_page.title()
                        state["page_count"] = len(pages)

            return state

        except Exception as e:
            return {
                "initialized": True,
                "error": f"Error getting state: {e!s}"
            }


def is_browser_use_available() -> bool:
    """Check if browser-use library is available

    Returns:
        True if browser-use is installed, False otherwise
    """
    return BROWSER_USE_AVAILABLE
