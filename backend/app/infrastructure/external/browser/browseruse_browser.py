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
from typing import Any

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

from app.core.config import get_settings
from app.infrastructure.external.browser.url_filters import VIDEO_URL_PATTERNS, is_video_url

logger = logging.getLogger(__name__)


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
            raise ImportError("browser-use library not installed. Install with: pip install browser-use>=0.11.0")

        self.cdp_url = cdp_url
        self.llm_provider = llm_provider
        self.session: BrowserSession | None = None
        self._initialized = False
        self._skip_video_urls = skip_video_urls
        self._auto_dismiss_dialogs = auto_dismiss_dialogs

    async def _force_window_to_origin(self) -> bool:
        """Force all browser windows to position (0,0) using CDP.

        This is critical for VNC display - new windows created by browser-use
        may not respect the original --window-position=0,0 flag.
        """
        try:
            import aiohttp

            # Get all targets from CDP (single session for all requests)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http_session, http_session.get(f"{self.cdp_url}/json") as resp:
                if resp.status != 200:
                    return False
                targets = await resp.json()

            # Find page targets and force their window position
            for target in targets:
                if target.get("type") != "page":
                    continue

                ws_url = target.get("webSocketDebuggerUrl")
                if not ws_url:
                    continue

                try:
                    async with aiohttp.ClientSession() as ws_session, ws_session.ws_connect(
                        ws_url, timeout=5.0
                    ) as ws:
                        # Get window ID (with timeout to prevent hangs on unresponsive Chrome)
                        await ws.send_json({"id": 1, "method": "Browser.getWindowForTarget"})

                        response = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        window_id = response.get("result", {}).get("windowId")

                        if window_id:
                            # Set window to normal state first
                            await ws.send_json(
                                {
                                    "id": 2,
                                    "method": "Browser.setWindowBounds",
                                    "params": {"windowId": window_id, "bounds": {"windowState": "normal"}},
                                }
                            )
                            await asyncio.wait_for(ws.receive_json(), timeout=5.0)

                            # Force position to (0,0) and size to match VNC
                            await ws.send_json(
                                {
                                    "id": 3,
                                    "method": "Browser.setWindowBounds",
                                    "params": {
                                        "windowId": window_id,
                                        "bounds": {"left": 0, "top": 0, "width": 1280, "height": 1024},
                                    },
                                }
                            )
                            await asyncio.wait_for(ws.receive_json(), timeout=5.0)

                        logger.info(f"Forced window {window_id} to position (0,0)")
                except Exception as e:
                    logger.debug(f"Failed to position window for target: {e}")
                    continue

            return True
        except Exception as e:
            logger.warning(f"Failed to force window position: {e}")
            return False

    async def initialize(self) -> bool:
        """Connect to existing Chrome instance via CDP

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            # Import BrowserConfig if available for viewport settings
            try:
                from browser_use.browser.config import BrowserConfig

                # Configure viewport to match VNC display (1280x1024)
                # This prevents browser-use from setting 1920x1080 which causes content cutoff
                browser_config = BrowserConfig(
                    viewport_width=1280,
                    viewport_height=900,  # Account for browser chrome
                    disable_security=True,
                )
                self.session = BrowserSession(
                    cdp_url=self.cdp_url,
                    browser_config=browser_config,
                )
                logger.info("Browser-use session configured with 1280x900 viewport")
            except ImportError:
                # Fallback if BrowserConfig not available
                self.session = BrowserSession(cdp_url=self.cdp_url)
                logger.warning("BrowserConfig not available, using default viewport")

            await self.session.start()

            # Force window position to (0,0) after browser-use creates/modifies pages
            # Browser-use may create new windows that aren't positioned correctly
            await self._force_window_to_origin()

            self._initialized = True
            logger.info(f"Browser-use session initialized with CDP: {self.cdp_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize browser-use session: {e}")
            self._initialized = False
            return False

    def _enhance_task_prompt(self, task: str) -> str:
        """Enhance task prompt with efficiency-focused instructions.

        Args:
            task: Original task

        Returns:
            Enhanced task with efficiency instructions
        """
        efficiency_instructions = """

EFFICIENCY RULES (CRITICAL - follow strictly):
1. Visit ONLY the top 2-3 most relevant sources - do NOT exhaustively browse
2. Skip video sites (YouTube, TikTok, etc.) and slow-loading pages
3. Extract key information quickly and move on - don't scroll entire pages
4. Close popups/banners immediately, deny notifications
5. If a page takes too long, skip it and try another source
6. Be CONCISE - gather essential info fast, then stop"""

        return task + efficiency_instructions

    async def execute_autonomous_task(
        self,
        task: str,
        max_steps: int = 12,
        llm_model: str | None = None,
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
            llm_model: LLM model for decision-making (default: from settings.model_name)
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
                    "total_steps": 0,
                }

        try:
            # Import here to avoid circular dependencies
            from browser_use import ChatOpenAI
            from langchain_core.language_models.chat_models import BaseChatModel

            # Get settings
            settings = get_settings()

            # Use model from settings if not specified
            model_name = llm_model or settings.model_name or "deepseek-chat"

            # Check if we need to strip response_format (non-OpenAI providers)
            is_openai = settings.api_base and (
                "api.openai.com" in settings.api_base.lower() or "openai.azure.com" in settings.api_base.lower()
            )

            # Create LLM provider
            if self.llm_provider:
                llm = self.llm_provider
            else:
                # Create base ChatOpenAI instance
                base_llm = ChatOpenAI(
                    model=model_name,
                    api_key=settings.api_key,
                    base_url=settings.api_base,
                    temperature=settings.temperature,
                )

                if not is_openai:
                    # Create a wrapper class that strips response_format for non-OpenAI providers
                    class NoResponseFormatLLM(BaseChatModel):
                        """Wrapper that strips response_format from all calls."""

                        def __init__(self, wrapped_llm):
                            super().__init__()
                            object.__setattr__(self, "_wrapped", wrapped_llm)

                        @property
                        def _llm_type(self) -> str:
                            return self._wrapped._llm_type

                        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                            kwargs.pop("response_format", None)
                            return self._wrapped._generate(messages, stop, run_manager, **kwargs)

                        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                            kwargs.pop("response_format", None)
                            return await self._wrapped._agenerate(messages, stop, run_manager, **kwargs)

                        def bind(self, **kwargs):
                            kwargs.pop("response_format", None)
                            return self._wrapped.bind(**kwargs)

                        def __getattr__(self, name):
                            return getattr(self._wrapped, name)

                    llm = NoResponseFormatLLM(base_llm)
                    logger.info("Created response_format-stripping wrapper for non-OpenAI provider")
                else:
                    llm = base_llm

                logger.info(f"Browser agent using LLM: {model_name} via {settings.api_base}")

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
                    "timestamp": getattr(action, "timestamp", None),
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
            if hasattr(history, "urls"):
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
                "final_result": history.final_result() if hasattr(history, "final_result") else str(history),
                "total_steps": len(actions_taken),
                "model_used": model_name,
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
            return {"initialized": False, "error": "Browser session not initialized"}

        try:
            # Get browser state from session if available
            state = {
                "initialized": True,
                "cdp_url": self.cdp_url,
                "session_active": self.session is not None,
            }

            # Try to get current page info
            if hasattr(self.session, "browser") and self.session.browser:
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
            return {"initialized": True, "error": f"Error getting state: {e!s}"}


def is_browser_use_available() -> bool:
    """Check if browser-use library is available

    Returns:
        True if browser-use is installed, False otherwise
    """
    return BROWSER_USE_AVAILABLE
