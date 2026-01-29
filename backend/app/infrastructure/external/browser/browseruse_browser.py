"""Browser-Use integration for autonomous browser control

This module provides autonomous browsing capabilities using the browser-use library.
It enables AI agents to perform complex multi-step browsing tasks with natural language
instructions, all visible in real-time via VNC.
"""

from typing import Optional, List, Dict, Any
import asyncio
import logging

try:
    from browser_use import Agent, BrowserSession
    from browser_use.agent.views import AgentHistory, ActionResult
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Agent = None
    BrowserSession = None
    AgentHistory = None
    ActionResult = None

from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class BrowserUseService:
    """Service for autonomous browser control using browser-use library

    Features:
    - Natural language task execution
    - Multi-step autonomous workflows
    - Form filling and data extraction
    - Real-time VNC visibility
    - Full execution history tracking
    """

    def __init__(self, cdp_url: str, llm_provider: Optional[Any] = None):
        """Initialize browser-use service

        Args:
            cdp_url: Chrome DevTools Protocol URL (e.g., "http://localhost:9222")
            llm_provider: Optional LLM provider instance (uses OpenAI by default)
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError(
                "browser-use library not installed. "
                "Install with: pip install browser-use>=0.11.0"
            )

        self.cdp_url = cdp_url
        self.llm_provider = llm_provider
        self.session: Optional[BrowserSession] = None
        self._initialized = False

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

    async def execute_autonomous_task(
        self,
        task: str,
        max_steps: int = 20,
        llm_model: str = "gpt-4o-mini",
    ) -> Dict[str, Any]:
        """Execute autonomous browsing task with natural language instruction

        Args:
            task: Natural language task description
                Examples:
                - "Search Google for Python tutorials and visit the top result"
                - "Go to Amazon, search for wireless keyboards, filter by 4+ stars"
                - "Fill out the contact form with my information"
            max_steps: Maximum autonomous actions before stopping (default: 20)
            llm_model: LLM model for decision-making (default: gpt-4o-mini)

        Returns:
            Dictionary containing:
                - success: Whether task completed successfully
                - actions: List of actions taken by the agent
                - final_result: Final output/result from the task
                - total_steps: Number of steps executed
                - error: Error message if failed
        """
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

            # Create autonomous agent with the task
            agent = Agent(
                task=task,
                llm=llm,
                browser_session=self.session,
                max_steps=max_steps,
            )

            logger.info(f"Starting autonomous task (max_steps={max_steps}): {task}")

            # Run the agent autonomously
            history: AgentHistory = await agent.run()

            # Extract and format results
            actions_taken = []
            for i, action in enumerate(history.history):
                # Extract action details
                action_info = {
                    "step": i + 1,
                    "action": str(action),
                    "timestamp": getattr(action, 'timestamp', None),
                }
                actions_taken.append(action_info)

            logger.info(f"Autonomous task completed in {len(actions_taken)} steps")

            return {
                "success": True,
                "actions": actions_taken,
                "final_result": history.final_result() if hasattr(history, 'final_result') else str(history),
                "total_steps": len(actions_taken),
                "model_used": llm_model,
            }

        except Exception as e:
            logger.error(f"Autonomous task execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "actions": [],
                "total_steps": 0,
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


def is_browser_use_available() -> bool:
    """Check if browser-use library is available

    Returns:
        True if browser-use is installed, False otherwise
    """
    return BROWSER_USE_AVAILABLE
