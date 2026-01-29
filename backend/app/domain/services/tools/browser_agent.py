import asyncio
import json
import logging
import re
from typing import Optional, Dict, Any

# browser_use is an optional dependency
try:
    from browser_use import Agent, Browser, ChatOpenAI
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Agent = None
    Browser = None
    ChatOpenAI = None

from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def extract_first_json(text: str) -> str:
    """Extract the first valid JSON object from text with trailing characters.

    Handles common LLM output issues:
    - Multiple JSON objects on separate lines
    - Trailing characters after valid JSON
    - Markdown code fences
    - Extra whitespace and newlines

    Args:
        text: Raw LLM output that may contain malformed JSON

    Returns:
        Cleaned string containing only the first valid JSON object
    """
    if not text:
        return text

    # Remove markdown code fences first
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Try to find and extract the first complete JSON object
    # Use a bracket-counting approach for robustness
    brace_count = 0
    bracket_count = 0
    in_string = False
    escape_next = False
    json_start = -1
    json_end = -1

    for i, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue

        if char == '\\' and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == '{':
            if brace_count == 0 and bracket_count == 0:
                json_start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and bracket_count == 0 and json_start != -1:
                json_end = i + 1
                break
        elif char == '[':
            if brace_count == 0 and bracket_count == 0 and json_start == -1:
                json_start = i
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0 and brace_count == 0 and json_start != -1:
                json_end = i + 1
                break

    # Extract the JSON portion
    if json_start != -1 and json_end != -1:
        extracted = text[json_start:json_end]
        # Validate it's actually valid JSON
        try:
            json.loads(extracted)
            return extracted
        except json.JSONDecodeError:
            pass

    # Fallback: try line-by-line to find valid JSON
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('{') or line.startswith('['):
            try:
                json.loads(line)
                return line
            except json.JSONDecodeError:
                continue

    # Last resort: return original text and let downstream handle errors
    return text


# SanitizedChatOpenAI is only available when browser_use is installed
if BROWSER_USE_AVAILABLE and ChatOpenAI is not None:
    class SanitizedChatOpenAI(ChatOpenAI):
        """Custom ChatOpenAI wrapper that sanitizes LLM output to fix JSON parsing issues.

        The browser-use library expects clean JSON from the LLM, but some models return
        malformed JSON with trailing characters, multiple JSON objects, or extra content.
        This wrapper intercepts responses and extracts the first valid JSON object.

        Uses duck typing to avoid direct langchain_core imports which may not be available.
        """

        def _sanitize_response(self, response: Any) -> Any:
            """Sanitize a response object by cleaning its content.

            Works with any object that has a 'content' attribute (duck typing).

            Args:
                response: LLM response object with content attribute

            Returns:
                Response with sanitized content
            """
            if not hasattr(response, 'content') or not isinstance(response.content, str):
                return response

            original_content = response.content
            sanitized_content = extract_first_json(original_content)

            if sanitized_content != original_content:
                logger.debug(
                    f"Sanitized LLM output: removed {len(original_content) - len(sanitized_content)} "
                    f"trailing characters"
                )
                # Modify content in place if possible, otherwise return as-is
                try:
                    response.content = sanitized_content
                except AttributeError:
                    pass  # Read-only, return as-is

            return response

        async def ainvoke(self, *args, **kwargs) -> Any:
            """Override ainvoke to sanitize LLM output before returning."""
            result = await super().ainvoke(*args, **kwargs)
            return self._sanitize_response(result)

        def invoke(self, *args, **kwargs) -> Any:
            """Override invoke to sanitize LLM output before returning."""
            result = super().invoke(*args, **kwargs)
            return self._sanitize_response(result)
else:
    SanitizedChatOpenAI = None


class BrowserAgentTool(BaseTool):
    """Browser Agent tool class for autonomous multi-step web task execution.

    Uses the browser-use library to execute complex web automation tasks
    that require multiple steps and decision-making capabilities.

    Features:
    - Robust error handling with configurable retry logic
    - Timeout protection at multiple levels (step, LLM, overall)
    - Vision-based browser automation support
    - Structured output validation
    """

    name: str = "browser_agent"

    def __init__(self, cdp_url: str):
        """Initialize browser agent tool class

        Args:
            cdp_url: Chrome DevTools Protocol URL for connecting to existing browser

        Raises:
            ImportError: If browser_use package is not installed
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError(
                "browser_use package is not installed. "
                "Install it with: pip install browser-use"
            )
        super().__init__()
        self._cdp_url = cdp_url
        self._browser: Optional[Browser] = None
        self._settings = get_settings()

    async def _get_browser(self) -> Browser:
        """Get or create browser instance connected via CDP"""
        if self._browser is None:
            self._browser = Browser(
                cdp_url=self._cdp_url,
                headless=False,
            )
        return self._browser

    def _get_llm(self) -> SanitizedChatOpenAI:
        """Create LLM instance for browser agent using app config

        Uses SanitizedChatOpenAI wrapper to handle malformed JSON responses
        from LLMs that return trailing characters or multiple JSON objects.

        Returns:
            SanitizedChatOpenAI instance configured with application settings
        """
        return SanitizedChatOpenAI(
            model=self._settings.model_name,
            api_key=self._settings.api_key,
            base_url=self._settings.api_base,
            temperature=0.0,  # Zero temperature for deterministic JSON output
        )

    def _sanitize_task_prompt(self, task: str) -> str:
        """Sanitize and optimize task prompt for better LLM compliance

        Args:
            task: Original task description

        Returns:
            Optimized task prompt
        """
        # Add instruction for clean JSON output
        suffix = "\n\nIMPORTANT: Keep responses concise and output valid JSON only."
        return task + suffix

    async def _run_agent_task(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute browser agent task with comprehensive error handling and timeout protection

        Args:
            task: Natural language task description
            start_url: Optional URL to start from
            max_steps: Maximum steps for the agent

        Returns:
            Task execution result dictionary
        """
        browser = await self._get_browser()
        llm = self._get_llm()

        effective_max_steps = max_steps or self._settings.browser_agent_max_steps
        timeout = self._settings.browser_agent_timeout

        # Build task with optional start URL
        if start_url:
            task = f"First navigate to {start_url}, then: {task}"

        # Sanitize task prompt
        task = self._sanitize_task_prompt(task)

        # Create agent with robust configuration
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            use_vision=self._settings.browser_agent_use_vision,
            max_failures=self._settings.browser_agent_max_failures,
            llm_timeout=self._settings.browser_agent_llm_timeout,
            step_timeout=self._settings.browser_agent_step_timeout,
            flash_mode=self._settings.browser_agent_flash_mode,
            final_response_after_failure=True,  # Attempt final response even after failures
        )

        try:
            # Run with overall timeout protection
            history = await asyncio.wait_for(
                agent.run(max_steps=effective_max_steps),
                timeout=timeout
            )

            # Extract result information using AgentHistoryList methods
            final_result = history.final_result() if history else None
            steps_taken = history.number_of_steps() if history else 0
            is_successful = history.is_successful() if history else False
            has_errors = history.has_errors() if history else False

            # Get URLs visited (simplified - no granular actions)
            urls_visited = history.urls() if history else []

            # Clean up the final result if it contains markdown fences
            if final_result:
                final_result = self._clean_llm_response(final_result)

            # Simplified response - no granular action details
            return {
                "success": is_successful if is_successful is not None else (not has_errors),
                "result": final_result,
                "steps_taken": steps_taken,
                "has_errors": has_errors,
                "urls_visited": urls_visited[:5] if urls_visited else [],  # Only show URLs visited
            }

        except asyncio.TimeoutError:
            logger.warning(f"Browser agent task timed out after {timeout}s: {task[:50]}...")
            return {
                "success": False,
                "error": f"Task timed out after {timeout} seconds",
                "result": None,
            }
        except asyncio.CancelledError:
            logger.info(f"Browser agent task was cancelled: {task[:50]}...")
            return {
                "success": False,
                "error": "Task was cancelled",
                "result": None,
            }
        except Exception as e:
            error_msg = str(e)
            # Log with appropriate level based on error type
            if "validation error" in error_msg.lower() or "json" in error_msg.lower():
                logger.warning(f"Browser agent JSON/validation error (may retry): {error_msg}")
            else:
                logger.exception(f"Browser agent task failed: {error_msg}")

            return {
                "success": False,
                "error": error_msg,
                "result": None,
            }

    def _clean_llm_response(self, response: str) -> str:
        """Clean LLM response by removing markdown fences and extra whitespace

        Args:
            response: Raw LLM response string

        Returns:
            Cleaned response string
        """
        if not response:
            return response

        # Remove markdown code fences
        response = re.sub(r'^```(?:json)?\s*', '', response, flags=re.MULTILINE)
        response = re.sub(r'\s*```$', '', response, flags=re.MULTILINE)

        # Remove leading/trailing whitespace
        response = response.strip()

        return response

    @tool(
        name="browsing",
        description="""Execute web tasks autonomously using AI-powered browser agent.

Use this tool when you need to perform tasks that require:
- Multiple interactions across different pages
- Form filling with validation
- Navigation through multi-step workflows
- Tasks that require reading and responding to page content
- Complex web scraping that needs context awareness

Examples:
- "Fill out the contact form with name 'John Doe' and email 'john@example.com', then submit"
- "Search for 'laptop' on Amazon, filter by price under $500, and list the top 3 results"
- "Log into the dashboard with provided credentials and download the monthly report"

Note: For simple single-action tasks (click, navigate, input), use the regular browser_* tools instead.""",
        parameters={
            "task": {
                "type": "string",
                "description": "Natural language description of the web task to perform. Be specific about what needs to be done."
            },
            "start_url": {
                "type": "string",
                "description": "(Optional) URL to navigate to before starting the task. If not provided, agent uses current page."
            },
            "max_steps": {
                "type": "integer",
                "description": "(Optional) Maximum number of steps the agent can take. Default is 25."
            }
        },
        required=["task"]
    )
    async def browsing(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> ToolResult:
        """Execute complex multi-step web tasks autonomously

        Args:
            task: Natural language description of the web task
            start_url: Optional URL to start from
            max_steps: Maximum steps the agent can take

        Returns:
            Task execution result
        """
        logger.info(f"Browsing: {task[:100]}...")

        result = await self._run_agent_task(task, start_url, max_steps)

        if result.get("success"):
            steps_taken = result.get('steps_taken', 0)
            has_errors = result.get('has_errors', False)
            status_msg = "with some recoverable errors" if has_errors else "successfully"
            return ToolResult(
                success=True,
                message=f"Task completed {status_msg} in {steps_taken} steps",
                data=result
            )
        else:
            return ToolResult(
                success=False,
                message=result.get("error", "Task failed"),
                data=result
            )

    @tool(
        name="browser_agent_extract",
        description="""Extract structured data from web pages using an AI-powered browser agent.

Use this tool when you need to:
- Extract specific information from complex web pages
- Gather data that requires understanding page context
- Scrape information from dynamic content
- Extract data from pages that require interaction first

Examples:
- "Extract all product names, prices, and ratings from this search results page"
- "Get the contact information (name, email, phone) from this company's about page"
- "Extract the main article text and publication date from this news page"

The agent will navigate and interact with the page as needed to extract the requested information.""",
        parameters={
            "extraction_goal": {
                "type": "string",
                "description": "Description of what data to extract from the page. Be specific about the fields and format needed."
            },
            "url": {
                "type": "string",
                "description": "(Optional) URL to extract data from. If not provided, extracts from current page."
            }
        },
        required=["extraction_goal"]
    )
    async def browser_agent_extract(
        self,
        extraction_goal: str,
        url: Optional[str] = None,
    ) -> ToolResult:
        """Extract structured data from web pages

        Args:
            extraction_goal: Description of what data to extract
            url: Optional URL to extract from

        Returns:
            Extracted data
        """
        # Frame the extraction as a task for the agent with clear JSON output instruction
        task = (
            f"Extract the following information and return it in a structured JSON format: "
            f"{extraction_goal}"
        )

        logger.info(f"Browser agent starting extraction: {extraction_goal[:100]}...")

        # Use fewer steps for extraction (typically doesn't need many interactions)
        result = await self._run_agent_task(task, url, max_steps=15)

        if result.get("success"):
            return ToolResult(
                success=True,
                message="Data extraction completed successfully",
                data=result
            )
        else:
            return ToolResult(
                success=False,
                message=result.get("error", "Extraction failed"),
                data=result
            )

    async def cleanup(self) -> None:
        """Cleanup browser resources"""
        if self._browser is not None:
            try:
                await self._browser.close()
                logger.info("Browser agent browser closed successfully")
            except Exception as e:
                logger.warning(f"Error closing browser agent browser: {e}")
            finally:
                self._browser = None
