import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

# browser_use is an optional dependency
try:
    from browser_use import Agent, Browser, ChatOpenAI

    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Agent = None
    Browser = None
    ChatOpenAI = None

from app.domain.models.event import ToolProgressEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool
from app.domain.utils.browser_use_session import cdp_browser_session_extra_kwargs
from app.domain.utils.llm_compat import is_native_openai
from app.domain.utils.url_filters import is_ssrf_target, is_video_url

logger = logging.getLogger(__name__)

_PROGRESS_QUEUE_MAX_SIZE = 200


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
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Strip <think>...</think> blocks (e.g. MiniMax M2.7 reasoning traces)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
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

        if char == "\\" and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            if brace_count == 0 and bracket_count == 0:
                json_start = i
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and bracket_count == 0 and json_start != -1:
                json_end = i + 1
                break
        elif char == "[":
            if brace_count == 0 and bracket_count == 0 and json_start == -1:
                json_start = i
            bracket_count += 1
        elif char == "]":
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
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                json.loads(line)
                return line
            except json.JSONDecodeError:
                continue

    # Last resort: return original text and let downstream handle errors
    return text


# SanitizedChatOpenAI is only available when browser_use is installed
if BROWSER_USE_AVAILABLE and ChatOpenAI is not None:
    from dataclasses import dataclass as _dataclass
    from dataclasses import field as _dc_field

    # -- Thin wrapper around AsyncOpenAI to strip <think> tags from LLM
    #    responses *before* browser-use's structured-output parser runs.
    #    This is necessary because browser-use's ChatOpenAI.ainvoke() calls
    #    `output_format.model_validate_json(choice.message.content)` internally,
    #    so our post-hoc sanitisation via _sanitize_response never gets to run
    #    when a model (e.g. MiniMax-M2.7) wraps JSON in reasoning tags.

    _THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

    class _ThinkStrippingCompletions:
        """Proxies ``chat.completions`` and strips ``<think>`` blocks."""

        __slots__ = ("_inner",)

        def __init__(self, inner: object) -> None:
            self._inner = inner

        async def create(self, **kwargs: Any) -> Any:
            response = await self._inner.create(**kwargs)  # type: ignore[attr-defined]
            for choice in getattr(response, "choices", ()):
                msg = getattr(choice, "message", None)
                if msg and isinstance(getattr(msg, "content", None), str):
                    original = msg.content
                    stripped = _THINK_TAG_RE.sub("", original).strip()
                    if stripped != original:
                        with contextlib.suppress(AttributeError, TypeError):
                            msg.content = stripped
                        logger.debug(
                            "Stripped <think> block (%d chars) from LLM response",
                            len(original) - len(stripped),
                        )
            return response

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    class _ThinkStrippingChat:
        """Proxies ``client.chat`` with think-stripping completions."""

        __slots__ = ("_inner", "completions")

        def __init__(self, inner: object) -> None:
            self._inner = inner
            self.completions = _ThinkStrippingCompletions(inner.completions)  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    class _ThinkStrippingClient:
        """Thin proxy around ``AsyncOpenAI`` that strips ``<think>`` tags."""

        __slots__ = ("_inner", "chat")

        def __init__(self, inner: object) -> None:
            self._inner = inner
            self.chat = _ThinkStrippingChat(inner.chat)  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    @_dataclass
    class SanitizedChatOpenAI(ChatOpenAI):
        """ChatOpenAI wrapper with JSON sanitisation and provider compatibility.

        Extends browser-use's ``ChatOpenAI`` (a ``@dataclass``) with three
        concerns:

        1. **Think-tag stripping** (client-level) — wraps the ``AsyncOpenAI``
           client returned by ``get_client()`` so that ``<think>...</think>``
           reasoning blocks emitted by models like MiniMax-M2.7 are removed
           from ``choice.message.content`` *before* browser-use's internal
           ``model_validate_json`` call.  This fixes 100 % JSON-parse failure
           rates when such models are used.

        2. **JSON sanitisation** (response-level) — intercepts ``ainvoke`` /
           ``invoke`` results and extracts the first valid JSON object so that
           trailing characters or multiple objects don't break the caller.

        3. **Provider compatibility** (``compat_mode``) — when the LLM endpoint
           is *not* native OpenAI (GLM, Kimi, DeepSeek, OpenRouter, Ollama …),
           automatically configures browser-use's built-in flags to avoid
           sending OpenAI-specific parameters that those providers reject:

           * ``dont_force_structured_output = True``
           * ``add_schema_to_system_prompt = True``
           * ``frequency_penalty = None``
           * ``max_completion_tokens = None``

        Uses duck typing to avoid direct langchain_core imports.
        """

        # compat_mode is a dataclass field — participates in __init__
        compat_mode: bool = _dc_field(default=False)

        def __post_init__(self) -> None:
            """Apply provider-compatibility overrides after dataclass init."""
            # Delegate to parent first — ensures browser-use's own __post_init__
            # (if one is added in a future version) runs before our overrides.
            with contextlib.suppress(AttributeError):
                super().__post_init__()

            if self.compat_mode:
                # Use browser-use's own flags instead of monkey-patching
                object.__setattr__(self, "dont_force_structured_output", True)
                object.__setattr__(self, "add_schema_to_system_prompt", True)
                object.__setattr__(self, "frequency_penalty", None)
                object.__setattr__(self, "max_completion_tokens", None)
                logger.info(
                    "SanitizedChatOpenAI compat_mode enabled — "
                    "disabled response_format, frequency_penalty, max_completion_tokens"
                )

        # -- Client-level interception ------------------------------------

        def get_client(self) -> _ThinkStrippingClient:
            """Return a wrapped AsyncOpenAI client that strips <think> tags."""
            raw_client = super().get_client()
            return _ThinkStrippingClient(raw_client)

        # -- Response-level sanitisation ----------------------------------

        def _sanitize_response(self, response: Any) -> Any:
            """Sanitize a response object by cleaning its content.

            Works with any object that has a 'content' attribute (duck typing).

            Args:
                response: LLM response object with content attribute

            Returns:
                Response with sanitized content
            """
            if not hasattr(response, "content") or not isinstance(response.content, str):
                return response

            original_content = response.content
            sanitized_content = extract_first_json(original_content)

            if sanitized_content != original_content:
                logger.debug(
                    f"Sanitized LLM output: removed {len(original_content) - len(sanitized_content)} "
                    f"trailing characters"
                )
                # Modify content in place if possible, otherwise return as-is
                with contextlib.suppress(AttributeError):
                    response.content = sanitized_content

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

    name: str = "browsing"
    supports_progress: bool = True

    def __init__(self, cdp_url: str):
        """Initialize browser agent tool class

        Args:
            cdp_url: Chrome DevTools Protocol URL for connecting to existing browser

        Raises:
            ImportError: If browser_use package is not installed
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError("browser_use package is not installed. Install it with: pip install browser-use")
        super().__init__(
            defaults=ToolDefaults(category="browser"),
        )
        self._cdp_url = cdp_url
        self._browser: Browser | None = None
        self._progress_queue: asyncio.Queue[ToolProgressEvent] = asyncio.Queue(
            maxsize=_PROGRESS_QUEUE_MAX_SIZE,
        )
        self._active_tool_call_id: str = ""
        self._active_function_name: str = ""
        self._start_time: float = 0.0

        from app.core.config import get_settings

        self._settings = get_settings()

    @staticmethod
    def _normalize_action_name(action_name: str) -> str:
        """Normalize browser-use action names across versions."""
        if not action_name:
            return "wait"
        normalized = action_name.lower()
        aliases = {
            "go_to_url": "navigate",
            "click_element": "click",
            "click_element_by_index": "click",
            "input_text": "input",
            "scroll_down": "scroll",
            "scroll_up": "scroll",
            "scroll_to_text": "find_text",
            "extract_content": "extract",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        """Convert numeric-like values to int, else None."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None

    @staticmethod
    def _first_int(*values: Any) -> int | None:
        """Return the first value that can be coerced to int."""
        for value in values:
            coerced = BrowserAgentTool._coerce_int(value)
            if coerced is not None:
                return coerced
        return None

    @staticmethod
    def _extract_action_from_dump(action_dump: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Extract action name and args from a browser-use ActionModel dump."""
        for key, value in action_dump.items():
            if key == "interacted_element":
                continue
            if isinstance(value, dict):
                return key, value
            if value is not None:
                return key, {}
        return "wait", {}

    @staticmethod
    def _map_action_to_function(action_name: str, action_args: dict[str, Any]) -> tuple[str, str]:
        """Map browser-use action to frontend cursor action + function name."""
        normalized = BrowserAgentTool._normalize_action_name(action_name)

        if normalized == "click":
            return "click", "browser_click"
        if normalized in {"input", "select_dropdown"}:
            return "input", "browser_input"
        if normalized in {"navigate", "search", "go_back", "switch", "close"}:
            return "navigate", "browser_navigate"
        if normalized in {"scroll", "find_text"}:
            direction_down = bool(action_args.get("down", True))
            function_name = "browser_scroll_down" if direction_down else "browser_scroll_up"
            return "scroll", function_name
        if normalized in {"extract", "search_page", "find_elements", "read_long_content"}:
            return "extract", "browser_agent_extract"
        return "wait", "browser_agent_run"

    @staticmethod
    def _describe_action(action: str, action_args: dict[str, Any]) -> str:
        """Generate a concise human-readable step label."""
        if action == "click":
            index = action_args.get("index")
            return f"Click element {index}" if index is not None else "Click"
        if action == "input":
            index = action_args.get("index")
            return f"Type into element {index}" if index is not None else "Type text"
        if action == "navigate":
            url = action_args.get("url")
            return f"Navigate to {url}" if isinstance(url, str) and url else "Navigate"
        if action == "scroll":
            direction = "down" if bool(action_args.get("down", True)) else "up"
            return f"Scroll {direction}"
        if action == "find_text":
            text = action_args.get("text")
            return f"Find text: {text}" if isinstance(text, str) and text else "Find text on page"
        if action == "extract":
            return "Extract page content"
        return action.replace("_", " ").title()

    @staticmethod
    def _extract_coordinates(
        action_args: dict[str, Any], action_metadata: dict[str, Any] | None
    ) -> tuple[int | None, int | None]:
        """Extract best-available action coordinates from args or action metadata."""
        coordinate_x = BrowserAgentTool._coerce_int(action_args.get("coordinate_x"))
        coordinate_y = BrowserAgentTool._coerce_int(action_args.get("coordinate_y"))
        if coordinate_x is not None and coordinate_y is not None:
            return coordinate_x, coordinate_y

        if not isinstance(action_metadata, dict):
            return None, None

        coordinate_x = BrowserAgentTool._first_int(
            action_metadata.get("click_x"),
            action_metadata.get("input_x"),
            action_metadata.get("x"),
        )
        coordinate_y = BrowserAgentTool._first_int(
            action_metadata.get("click_y"),
            action_metadata.get("input_y"),
            action_metadata.get("y"),
        )
        return coordinate_x, coordinate_y

    def _enqueue_progress(
        self,
        *,
        current_step: str,
        steps_completed: int,
        steps_total: int | None,
        checkpoint_data: dict[str, Any] | None = None,
    ) -> None:
        """Enqueue a ToolProgressEvent without blocking execution."""
        percent = min(99, int(steps_completed / steps_total * 100)) if steps_total and steps_total > 0 else 0
        elapsed_ms = (time.monotonic() - self._start_time) * 1000 if self._start_time else 0
        event = ToolProgressEvent(
            tool_call_id=self._active_tool_call_id,
            tool_name=self.name,
            function_name=self._active_function_name,
            progress_percent=percent,
            current_step=current_step,
            steps_completed=steps_completed,
            steps_total=steps_total,
            elapsed_ms=elapsed_ms,
            checkpoint_data=checkpoint_data,
        )
        try:
            self._progress_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("Browser-agent progress queue full, dropping event: %s", current_step)

    def _reset_progress_queue(self) -> None:
        """Clear stale progress events from previous runs."""
        while not self._progress_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._progress_queue.get_nowait()

    def _emit_progress_from_agent_step(self, agent: Any, steps_total: int | None) -> None:
        """Extract latest browser-use step actions and emit tool_progress events."""
        history_obj = getattr(agent, "history", None)
        history_items = getattr(history_obj, "history", None)
        if not isinstance(history_items, list) or not history_items:
            return

        latest_step = history_items[-1]
        steps_completed = len(history_items)
        current_url = getattr(getattr(latest_step, "state", None), "url", None)

        model_output = getattr(latest_step, "model_output", None)
        actions = getattr(model_output, "action", None)
        results = getattr(latest_step, "result", None)
        action_results = results if isinstance(results, list) else []

        if not isinstance(actions, list) or not actions:
            self._enqueue_progress(
                current_step=f"Step {steps_completed}: Processing page",
                steps_completed=steps_completed,
                steps_total=steps_total,
                checkpoint_data={"action": "wait", "action_function": "browser_agent_run", "url": current_url},
            )
            return

        for idx, action in enumerate(actions):
            if not hasattr(action, "model_dump"):
                continue

            action_dump = action.model_dump(exclude_none=True, mode="json")
            if not isinstance(action_dump, dict):
                continue

            raw_action_name, action_args = self._extract_action_from_dump(action_dump)
            normalized_action, action_function = self._map_action_to_function(raw_action_name, action_args)

            action_metadata: dict[str, Any] | None = None
            if idx < len(action_results):
                metadata_candidate = getattr(action_results[idx], "metadata", None)
                if isinstance(metadata_candidate, dict):
                    action_metadata = metadata_candidate

            coordinate_x, coordinate_y = self._extract_coordinates(action_args, action_metadata)

            checkpoint_data: dict[str, Any] = {
                "action": normalized_action,
                "action_function": action_function,
                "step": steps_completed,
            }
            url_from_args = action_args.get("url")
            checkpoint_data["url"] = url_from_args if isinstance(url_from_args, str) and url_from_args else current_url
            index = action_args.get("index")
            if isinstance(index, int):
                checkpoint_data["index"] = index
            if coordinate_x is not None and coordinate_y is not None:
                checkpoint_data["coordinate_x"] = coordinate_x
                checkpoint_data["coordinate_y"] = coordinate_y

            self._enqueue_progress(
                current_step=f"Step {steps_completed}: {self._describe_action(normalized_action, action_args)}",
                steps_completed=steps_completed,
                steps_total=steps_total,
                checkpoint_data=checkpoint_data,
            )

    async def drain_progress_events(self) -> AsyncGenerator[ToolProgressEvent, None]:
        """Drain queued progress events for agent streaming."""
        while not self._progress_queue.empty():
            try:
                yield self._progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _get_browser(self) -> Browser:
        """Get or create browser instance connected via CDP"""
        if self._browser is None:
            s = self._settings
            self._browser = Browser(
                cdp_url=self._cdp_url,
                **cdp_browser_session_extra_kwargs(
                    min_page_load_wait=float(s.browser_agent_min_page_load_wait),
                    network_idle_wait=float(s.browser_agent_network_idle_wait),
                    max_iframes=int(s.browser_agent_max_iframes),
                    max_iframe_depth=int(s.browser_agent_max_iframe_depth),
                ),
            )
        return self._browser

    def _get_llm(self) -> SanitizedChatOpenAI:
        """Create LLM instance for browser agent using app config.

        Uses SanitizedChatOpenAI wrapper to handle malformed JSON responses
        from LLMs that return trailing characters or multiple JSON objects.

        Automatically enables ``compat_mode`` for non-native-OpenAI providers
        (GLM, Kimi, DeepSeek, OpenRouter, Ollama, …) which disables
        ``response_format`` and other OpenAI-specific parameters that those
        providers reject with HTTP 400.

        Applies an HTTP-level timeout via ``httpx.Timeout`` so that stalled
        LLM providers cannot block indefinitely — even when browser-use
        shields internal coroutines from ``asyncio.wait_for()``.

        Returns:
            SanitizedChatOpenAI instance configured with application settings
        """
        llm_timeout = float(self._settings.browser_agent_llm_timeout)  # 90s default
        compat = not is_native_openai(self._settings.api_base)
        return SanitizedChatOpenAI(
            model=self._settings.model_name,
            api_key=self._settings.api_key,
            base_url=self._settings.api_base,
            temperature=0.0,  # Zero temperature for deterministic JSON output
            timeout=httpx.Timeout(
                timeout=llm_timeout,
                connect=10.0,
            ),
            compat_mode=compat,
        )

    def _sanitize_task_prompt(self, task: str) -> str:
        """Sanitize and optimize task prompt for better LLM compliance

        Adds hardening instructions to:
        - Skip video sites
        - Close popups/dialogs
        - Handle cookie banners
        - Maintain efficiency

        Args:
            task: Original task description

        Returns:
            Optimized task prompt with safety instructions
        """
        suffix = """

CRITICAL INSTRUCTIONS:
1. SKIP video sites (YouTube, Vimeo, TikTok, Netflix, etc.) - navigate away immediately
2. CLOSE popups, modal dialogs, and cookie consent banners immediately when they appear
3. DENY notification requests - click "Block" or "No thanks"
4. DO NOT play videos or audio - skip media content entirely
5. If a page loads slowly or is stuck, press Escape and try an alternative
6. If you encounter a CAPTCHA, report it and move on
7. Keep responses concise and output valid JSON only."""
        return task + suffix

    async def _run_agent_task(
        self,
        task: str,
        start_url: str | None = None,
        max_steps: int | None = None,
        timeout_override: int | None = None,
    ) -> dict[str, Any]:
        """Execute browser agent task with comprehensive error handling and timeout protection

        Features:
        - Video URL filtering (auto-skip)
        - Popup/dialog handling instructions
        - Timeout protection at multiple levels
        - Graceful error recovery

        Args:
            task: Natural language task description
            start_url: Optional URL to start from
            max_steps: Maximum steps for the agent

        Returns:
            Task execution result dictionary
        """
        # SSRF protection — block internal/private URLs
        if start_url:
            ssrf_reason = is_ssrf_target(start_url)
            if ssrf_reason:
                logger.warning("SSRF blocked in browser_agent: %s → %s", start_url, ssrf_reason)
                return {
                    "success": False,
                    "error": f"Navigation blocked for security: {ssrf_reason}",
                    "result": None,
                    "skipped_reason": "ssrf_blocked",
                }

        # Check if start_url is a video URL - skip immediately
        if start_url and is_video_url(start_url):
            logger.info(f"Skipping video URL: {start_url}")
            return {
                "success": False,
                "error": f"Skipped video URL (not supported): {start_url}",
                "result": None,
                "skipped_reason": "video_url",
            }

        browser = await self._get_browser()
        llm = self._get_llm()

        effective_max_steps = max_steps or self._settings.browser_agent_max_steps
        timeout = timeout_override or self._settings.browser_agent_timeout
        self._start_time = time.monotonic()
        self._reset_progress_queue()

        # Build task with optional start URL
        if start_url:
            task = f"First navigate to {start_url}, then: {task}"

        # Sanitize task prompt (adds hardening instructions)
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

        # ── Two-layer timeout defence ───────────────────────────────────
        # Layer 1 (HTTP): httpx.Timeout on the LLM client — prevents any
        #   single LLM call from blocking indefinitely (set in _get_llm()).
        # Layer 2 (Task): asyncio.timeout() context manager (Python 3.11+) —
        #   hard-stops the entire agent run after (browser_agent_timeout + 30s)
        #   grace period.  asyncio.timeout() is preferred over the previous
        #   manual watchdog-task pattern because:
        #   • It uses the stdlib cancellation mechanism directly (no background task)
        #   • It transforms CancelledError → TimeoutError natively (per Python docs)
        #   • It is safely nestable with other timeout contexts
        #   browser-use shields its internal coroutines via asyncio.shield(), so the
        #   underlying browser steps continue briefly in the background after our task
        #   is cancelled — this is acceptable: we stop *waiting*, the browser cleans up
        #   on its own schedule.  The primary (httpx) layer should fire first anyway.
        watchdog_deadline = timeout + 30  # 30s grace beyond overall timeout

        try:

            async def _on_step_end(agent_instance: Any) -> None:
                self._emit_progress_from_agent_step(
                    agent_instance,
                    steps_total=effective_max_steps,
                )

            async with asyncio.timeout(watchdog_deadline):
                try:
                    history = await agent.run(
                        max_steps=effective_max_steps,
                        on_step_end=_on_step_end,
                    )
                except TypeError as type_error:
                    # Backward compatibility for older browser-use versions that
                    # do not accept hook callbacks in Agent.run().
                    if "on_step_end" not in str(type_error):
                        raise
                    logger.debug("browser-use Agent.run lacks on_step_end hook support, running without progress hooks")
                    history = await agent.run(max_steps=effective_max_steps)

            # Extract result information using AgentHistoryList methods
            final_result = history.final_result() if history else None
            steps_taken = history.number_of_steps() if history else 0
            is_successful = history.is_successful() if history else False
            has_errors = history.has_errors() if history else False

            # Get URLs visited and filter out video URLs
            all_urls = history.urls() if history else []
            urls_visited = []
            skipped_video_urls = []

            for url in all_urls or []:
                if is_video_url(url):
                    skipped_video_urls.append(url)
                    logger.debug(f"Filtered video URL from results: {url}")
                else:
                    urls_visited.append(url)

            # Clean up the final result if it contains markdown fences
            if final_result:
                final_result = self._clean_llm_response(final_result)

            # Simplified response - no granular action details
            result = {
                "success": is_successful if is_successful is not None else (not has_errors),
                "result": final_result,
                "steps_taken": steps_taken,
                "has_errors": has_errors,
                "urls_visited": urls_visited[:5] if urls_visited else [],
            }

            # Include skipped URLs if any were filtered
            if skipped_video_urls:
                result["skipped_video_urls"] = skipped_video_urls[:3]
                logger.info(f"Skipped {len(skipped_video_urls)} video URL(s) during task")

            return result

        except TimeoutError:
            # Raised by asyncio.timeout() (Layer 2) or propagated from httpx (Layer 1).
            # Both are caught here for uniform handling.
            logger.warning(
                "Browser agent timed out after %ds (deadline=%ds): %s...",
                timeout,
                watchdog_deadline,
                task[:50],
            )
            return {
                "success": False,
                "error": f"Task timed out after {watchdog_deadline}s",
                "result": None,
            }
        except httpx.TimeoutException as exc:
            # httpx-level timeout that escaped asyncio.timeout() (should be rare).
            logger.warning("Browser agent HTTP timeout: %s — task: %s...", exc, task[:50])
            return {
                "success": False,
                "error": f"LLM HTTP timeout: {exc}",
                "result": None,
            }
        except asyncio.CancelledError:
            # External cancellation (user cancelled session) — propagate cleanly.
            logger.info("Browser agent task was cancelled externally: %s...", task[:50])
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
        response = re.sub(r"^```(?:json)?\s*", "", response, flags=re.MULTILINE)
        response = re.sub(r"\s*```$", "", response, flags=re.MULTILINE)

        # Remove leading/trailing whitespace
        return response.strip()

    @tool(
        name="browser_agent_run",
        description="""Execute web tasks autonomously using AI-powered browser agent.

ALL ACTIONS VISIBLE IN REAL-TIME VIA LIVE PREVIEW.

Use this tool when you need to perform tasks that require:
- Multiple interactions across different pages
- Form filling with validation
- Navigation through multi-step workflows
- Tasks that require reading and responding to page content
- Complex web scraping that needs context awareness
- Search queries (will navigate to search engine visually)

Examples:
- "Search for 'best LLMs 2026' and extract top 5 results"
- "Fill out the contact form with name 'John Doe' and email 'john@example.com', then submit"
- "Search for 'laptop' on Amazon, filter by price under $500, and list the top 3 results"
- "Log into the dashboard with provided credentials and download the monthly report"

Note: For simple single-action tasks (click, navigate, input), use the regular browser_* tools instead.
For fast content extraction from known URLs, use browser_get_content instead.""",
        parameters={
            "task": {
                "type": "string",
                "description": "Natural language description of the web task to perform. Be specific about what needs to be done.",
            },
            "start_url": {
                "type": "string",
                "description": "(Optional) URL to navigate to before starting the task. If not provided, agent uses current page.",
            },
            "max_steps": {
                "type": "integer",
                "description": "(Optional) Maximum number of steps the agent can take. Default is 25.",
            },
        },
        required=["task"],
    )
    async def browsing(
        self,
        task: str,
        start_url: str | None = None,
        max_steps: int | None = None,
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
            steps_taken = result.get("steps_taken", 0)
            has_errors = result.get("has_errors", False)
            status_msg = "with some recoverable errors" if has_errors else "successfully"
            return ToolResult(success=True, message=f"Task completed {status_msg} in {steps_taken} steps", data=result)
        return ToolResult(success=False, message=result.get("error", "Task failed"), data=result)

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
                "description": "Description of what data to extract from the page. Be specific about the fields and format needed.",
            },
            "url": {
                "type": "string",
                "description": "(Optional) URL to extract data from. If not provided, extracts from current page.",
            },
        },
        required=["extraction_goal"],
    )
    async def browser_agent_extract(
        self,
        extraction_goal: str,
        url: str | None = None,
    ) -> ToolResult:
        """Extract structured data from web pages

        Args:
            extraction_goal: Description of what data to extract
            url: Optional URL to extract from

        Returns:
            Extracted data
        """
        # Frame the extraction as a task for the agent with clear JSON output instruction
        task = f"Extract the following information and return it in a structured JSON format: {extraction_goal}"

        logger.info(f"Browser agent starting extraction: {extraction_goal[:100]}...")

        # Use fewer steps and shorter timeout for extraction
        result = await self._run_agent_task(
            task,
            url,
            max_steps=15,
            timeout_override=self._settings.browser_agent_extract_timeout,
        )

        if result.get("success"):
            return ToolResult(success=True, message="Data extraction completed successfully", data=result)
        return ToolResult(success=False, message=result.get("error", "Extraction failed"), data=result)

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
