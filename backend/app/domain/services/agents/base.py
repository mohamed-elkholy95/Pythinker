import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, ClassVar

from app.domain.exceptions.base import AgentConfigurationException, ToolNotFoundException
from app.domain.external.llm import LLM
from app.domain.external.logging import get_agent_logger
from app.domain.models.agent import Agent
from app.domain.models.event import (
    BaseEvent,
    CouponItem,
    DealItem,
    DealToolContent,
    ErrorEvent,
    MessageEvent,
    SearchToolContent,
    StreamEvent,
    ToolEvent,
    ToolStatus,
    ToolStreamEvent,
    WaitEvent,
)
from app.domain.models.message import Message
from app.domain.models.search import SearchResultItem
from app.domain.models.state_manifest import StateEntry, StateManifest
from app.domain.models.tool_call import ToolCallEnvelope
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.error_handler import ErrorHandler, ErrorType, TokenLimitExceededError
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.security_assessor import ActionSecurityRisk, SecurityAssessor
from app.domain.services.agents.stuck_detector import StuckDetector
from app.domain.services.agents.tool_stream_parser import (
    content_type_for_function,
    extract_partial_content,
    is_streamable_function,
)

if TYPE_CHECKING:
    from app.domain.external.circuit_breaker import CircuitBreakerPort
    from app.domain.services.agents.scratchpad import Scratchpad
    from app.domain.services.agents.tool_result_store import ToolResultStore
    from app.domain.services.agents.url_failure_guard import UrlFailureGuard
    from app.domain.utils.cancellation import CancellationToken
from app.domain.models.tool_name import ToolName
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.context_manager import SandboxContextManager
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.command_formatter import CommandFormatter
from app.domain.services.tools.dynamic_toolset import get_toolset_manager
from app.domain.services.tools.tool_profiler import get_tool_profiler
from app.domain.services.tools.tool_tracing import get_tool_tracer
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

# Tools that are safe to execute in parallel (read-only, no side effects)
# Canonical source: ToolName.safe_parallel_tools()
SAFE_PARALLEL_TOOLS = ToolName.safe_parallel_tools()

# MCP tool prefixes that are safe for parallel execution (read-only patterns)
SAFE_MCP_PREFIXES = ToolName._SAFE_MCP_PREFIXES

# Maximum number of concurrent tool executions (increased for better throughput)
MAX_CONCURRENT_TOOLS = 5


def _extract_url_from_args(arguments: dict) -> str | None:
    """Extract URL from tool call arguments.

    Checks common URL parameter names used across tools.
    """
    for key in ("url", "target_url", "page_url", "query"):
        val = arguments.get(key)
        if val and isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    return None


def _extract_search_result_urls(result: ToolResult | None) -> list[str]:
    """Extract URL candidates from common search tool payload shapes."""
    if result is None or result.data is None:
        return []

    data = result.data
    if hasattr(data, "model_dump"):
        with contextlib.suppress(Exception):
            data = data.model_dump()

    raw_results: Any = None
    if isinstance(data, dict):
        raw_results = data.get("results")
    else:
        with contextlib.suppress(AttributeError):
            raw_results = data.results

    if not isinstance(raw_results, list):
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for item in raw_results:
        candidate: str | None = None
        if isinstance(item, dict):
            value = item.get("link") or item.get("url")
            if isinstance(value, str):
                candidate = value
        else:
            value = getattr(item, "link", None) or getattr(item, "url", None)
            if isinstance(value, str):
                candidate = value

        if candidate and candidate.startswith(("http://", "https://")) and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)

    return urls


# ── Graduated wall-clock pressure (design 2A) ─────────────────────────

_WRITE_TOOLS = frozenset({"file_write", "file_str_replace", "code_save_artifact"})


def _get_wall_clock_pressure_level(elapsed: float, budget: float) -> str | None:
    """Return pressure level based on elapsed/budget ratio."""
    if budget <= 0:
        return None
    ratio = elapsed / budget
    if ratio >= 0.90:
        return "CRITICAL"
    if ratio >= 0.75:
        return "URGENT"
    if ratio >= 0.50:
        return "ADVISORY"
    return None


def _should_block_tool_at_pressure(tool_name: str, level: str) -> bool:
    """Check if a tool should be blocked at the given pressure level."""
    if level == "CRITICAL":
        return tool_name not in _WRITE_TOOLS
    if level == "URGENT":
        read_tools = frozenset(t.value for t in ToolName.read_only_tools())
        return tool_name in read_tools
    return False


_LONG_TIMEOUT_TOOLS: frozenset[str] = frozenset(
    {
        "wide_research",
        "info_search_web",
        "deal_scraper_search",
        "deal_scraper_compare",
        "deal_scraper_recommend",
    }
)
_DEFAULT_TOOL_TIMEOUT: float = 120.0
_LONG_TOOL_TIMEOUT: float = 300.0


def _resolve_tool_timeout(function_name: str) -> float:
    """Return timeout in seconds based on tool type."""
    if function_name.startswith("browser_"):
        return _LONG_TOOL_TIMEOUT
    if function_name in _LONG_TIMEOUT_TOOLS:
        return _LONG_TOOL_TIMEOUT
    return _DEFAULT_TOOL_TIMEOUT


class BaseAgent:
    """
    Base agent class, defining the basic behavior of the agent
    """

    name: str = ""
    system_prompt: str = ""
    format: str | None = None
    max_iterations: int = 400  # Doubled for complex tasks
    max_retries: int = 3
    retry_interval: float = 0.3  # Faster retry with exponential backoff
    retry_backoff: float = 1.5  # Backoff multiplier (0.3s -> 0.45s -> 0.67s)
    max_consecutive_truncations: int = 3  # Force text-only response after this many
    tool_choice: str | None = None

    # Iteration budget management
    iteration_warning_threshold: float = 0.8  # Warn at 80% of limit
    read_only_iteration_weight: float = 0.3  # Read-only ops count as 30% (reduced from 50%)
    max_step_iterations: int = 50  # Max iterations for a single step before auto-failing

    # Per-step hallucination injection cap: if correction prompts are injected
    # this many times in one step, the model is fundamentally confused — force-advance.
    max_hallucinations_per_step: int = 3

    # Per-step compression cycle cap: prevents oscillation where compression
    # reduces context, execution adds tokens, triggering compression again.
    max_compression_cycles_per_step: int = 5

    # Phase-based tool filtering: keeps active tool count <20 per phase
    # to reduce hallucination (OpenAI guidance: accuracy drops above ~20 tools)
    # Canonical source: ToolName.for_phase()
    PHASE_TOOL_GROUPS: ClassVar[dict[str, frozenset[ToolName] | None]] = {
        "planning": ToolName.for_phase("planning"),
        "executing": None,  # None = all tools available
        "verifying": ToolName.for_phase("verifying"),
    }

    _TOKEN_BUDGET_FORCE_CONCLUDE_MESSAGE: ClassVar[str] = (
        "TOKEN BUDGET CRITICAL (95%+). You MUST conclude your current step and summarize results now. "
        "Do not start any new exploratory tool calls."
    )
    _TOKEN_BUDGET_HARD_STOP_MESSAGE: ClassVar[str] = (
        "TOKEN BUDGET EMERGENCY (99%+). Tool calls are now disabled. "
        "Provide the best possible final summary from gathered evidence."
    )

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        json_parser: JsonParser,
        tools: list[BaseTool] | None = None,
        state_manifest: StateManifest | None = None,
        circuit_breaker: "CircuitBreakerPort | None" = None,
        feature_flags: dict[str, bool] | None = None,
        cancel_token: "CancellationToken | None" = None,
        tool_result_store: "ToolResultStore | None" = None,
    ):
        if tools is None:
            tools = []
        self._agent_id = agent_id
        self._repository = agent_repository
        self.llm = llm
        self.json_parser = json_parser
        self.tools = tools
        self.memory = None
        self._background_tasks: set[asyncio.Task] = set()
        self._active_phase: str | None = None  # Phase-based tool filtering (set by orchestrator)
        self._step_model_override: str | None = None  # DeepCode Phase 1: Adaptive model selection
        self._user_thinking_mode: str | None = None  # User-selected thinking mode override
        self._circuit_breaker = circuit_breaker
        self._feature_flags = feature_flags
        self._tool_result_store = tool_result_store
        self._scratchpad: Scratchpad | None = None

        # Structured agent logger
        self._log = get_agent_logger(agent_id)

        # Initialize cancellation token for graceful shutdown
        from app.domain.utils.cancellation import CancellationToken

        self._cancel_token = cancel_token or CancellationToken.null()

        # Initialize metrics port for Prometheus integration
        from app.domain.external.observability import get_null_metrics

        self._metrics = get_null_metrics()

        # Initialize reliability components
        self._stuck_detector = StuckDetector(window_size=5, threshold=3)
        self._recent_truncation_count = 0  # Tracks consecutive truncated tool calls
        self._truncation_retry_max_tokens: int | None = None
        self._token_manager = TokenManager(model_name=getattr(llm, "model_name", "gpt-4"))
        self._error_handler = ErrorHandler()

        # Initialize hallucination detector with available tool names and schemas
        available_tools = self.get_available_tools() or []
        tool_names = [t.get("function", {}).get("name", "") for t in available_tools]
        self._hallucination_detector = ToolHallucinationDetector(tool_names)

        # Initialize tool schemas for parameter validation
        self._hallucination_detector.update_tool_schemas(self._extract_tool_schemas(available_tools))

        # Initialize security assessor for action risk evaluation
        self._security_assessor = SecurityAssessor(
            autonomy_level="autonomous",  # Default to autonomous mode
            allow_credential_access=False,
            allow_destructive_operations=False,
        )

        # Per-agent efficiency monitor (NOT a global singleton — prevents cross-session bleed)
        from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor

        self._efficiency_monitor = ToolEfficiencyMonitor(window_size=10, read_threshold=5, strong_threshold=6)
        self._efficiency_nudges: list[dict] = []

        # URL Failure Guard — session-scoped, set externally by PlanActFlow
        # When None, guard checks are skipped (backward compatible)
        self._url_failure_guard: UrlFailureGuard | None = None

        # Context manager for Pythinker-style attention manipulation (optional)
        self.context_manager: SandboxContextManager | None = None

        # State manifest for blackboard architecture (optional)
        self.state_manifest: StateManifest | None = state_manifest

        # Flag set when stuck recovery is exhausted — signals callers to force-advance
        self._stuck_recovery_exhausted: bool = False

        # Per-step counters for stability guards (reset at top of execute())
        self._hallucination_count_this_step: int = 0
        self._compression_cycles_this_step: int = 0
        self._compression_guard_active: bool = False
        self._step_start_time: float | None = None

        # Per-session hallucination rate tracking (for model escalation)
        self._total_hallucinations: int = 0
        self._total_tool_calls: int = 0
        self._hallucination_escalated: bool = False

        # Phase 2: Proactive token budget manager (feature-flagged)
        self._token_budget: Any = None  # TokenBudget — set by orchestrator via set_token_budget()
        self._token_budget_manager: Any = None  # TokenBudgetManager
        self._sliding_window: Any = None  # SlidingWindowContextManager

    def _resolve_feature_flags(self) -> dict[str, bool]:
        """Return injected feature flags, falling back to core config."""
        if self._feature_flags is not None:
            return self._feature_flags
        from app.core.config import get_feature_flags

        return get_feature_flags()

    async def _ask_structured_tiered(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[Any],
        tier: str,
        **kwargs: Any,
    ) -> Any:
        """Prefer tier-aware structured policy path when available and enabled."""
        flags = self._resolve_feature_flags()
        structured_enabled = flags.get("structured_outputs", False)

        policy_method = getattr(self.llm, "ask_structured_with_policy", None)

        # Guard against MagicMock/AsyncMock attribute autovivification in tests.
        llm_module = getattr(type(self.llm), "__module__", "")
        is_mock_llm = llm_module.startswith("unittest.mock")
        if structured_enabled and callable(policy_method) and not is_mock_llm:
            return await policy_method(
                messages=messages,
                response_model=response_model,
                tier=tier,
            )

        return await self.llm.ask_structured(
            messages=messages,
            response_model=response_model,
            tools=kwargs.get("tools"),
            tool_choice=kwargs.get("tool_choice"),
            enable_caching=kwargs.get("enable_caching", True),
            model=kwargs.get("model"),
            temperature=kwargs.get("temperature"),
            max_tokens=kwargs.get("max_tokens"),
        )

    # Tool result compaction limits for memory writes
    _TOOL_RESULT_MEMORY_MAX_CHARS: ClassVar[int] = 12000
    _TOOL_RESULT_MESSAGE_PREVIEW_CHARS: ClassVar[int] = 2000
    _TOOL_RESULT_DATA_PREVIEW_CHARS: ClassVar[int] = 7000

    def set_token_budget(self, budget: Any) -> None:
        """Inject a TokenBudget for proactive phase-level token management.

        Called by the orchestrator (PlanActFlow) at flow start. When set,
        _ensure_within_token_limit() will use budget-aware compression
        instead of the reactive two-stage strategy.
        """
        self._token_budget = budget
        # Lazily create budget manager + sliding window on first budget injection
        if budget is not None and self._token_budget_manager is None:
            from app.domain.services.agents.sliding_window_context import SlidingWindowContextManager
            from app.domain.services.agents.token_budget_manager import TokenBudgetManager

            self._token_budget_manager = TokenBudgetManager(self._token_manager)
            self._sliding_window = SlidingWindowContextManager(self._token_manager)

    def set_thinking_mode(self, thinking_mode: str | None) -> None:
        """Set user-requested thinking mode for model selection override.

        Args:
            thinking_mode: 'fast' -> FAST tier, 'deep_think' -> POWERFUL tier,
                           'auto'/None -> automatic complexity-based routing.
        """
        self._user_thinking_mode = thinking_mode

    def get_available_tools(self) -> list[dict[str, Any]] | None:
        """Get all available tools list, filtered by active phase if set."""
        available_tools = []
        for tool in self.tools:
            available_tools.extend(tool.get_tools())

        # Apply phase-based filtering when a phase is active
        if self._active_phase:
            allowed = self.PHASE_TOOL_GROUPS.get(self._active_phase)
            if allowed is not None:  # None means all tools
                available_tools = [t for t in available_tools if t.get("function", {}).get("name", "") in allowed]

        # Block tools when efficiency monitor signals hard stop
        # Guard with hasattr: get_available_tools() is called during __init__ before _efficiency_monitor is set
        if hasattr(self, "_efficiency_monitor"):
            signal = self._efficiency_monitor.check_efficiency()
            usage_ratio = self._current_token_usage_ratio()

            # At critical budget pressure, enforce loop breaks even when a tool
            # would normally be exempt from repetitive-tool checks.
            if usage_ratio >= 0.98:
                repeated_tool = getattr(self._efficiency_monitor, "_last_tool_name", None)
                repeated_count = getattr(self._efficiency_monitor, "_consecutive_same_tool", 0)
                threshold = getattr(self._efficiency_monitor, "same_tool_threshold", 0)
                if repeated_tool and repeated_count >= threshold:
                    available_tools = [
                        t for t in available_tools if t.get("function", {}).get("name", "") != repeated_tool
                    ]

            if signal.hard_stop:
                if signal.signal_type == "repetitive_tool":
                    # Only apply if feature flag is enabled
                    from app.core.config import get_settings as _get_settings

                    _s = _get_settings()
                    if getattr(_s, "feature_repetitive_tool_detection_enabled", False):
                        # Block only the specific repeated tool
                        blocked_tool = self._efficiency_monitor._last_tool_name
                        available_tools = [
                            t for t in available_tools if t.get("function", {}).get("name", "") != blocked_tool
                        ]
                else:
                    # Original behavior: block all read tools
                    available_tools = [
                        t
                        for t in available_tools
                        if not self._efficiency_monitor._is_read_tool(t.get("function", {}).get("name", ""))
                    ]

        return available_tools

    def _extract_tool_schemas(self, available_tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Extract parameter schemas from tool definitions for hallucination detection."""
        schemas: dict[str, dict[str, Any]] = {}
        for tool_def in available_tools:
            func_def = tool_def.get("function", {})
            tool_name = func_def.get("name", "")
            params = func_def.get("parameters", {})
            if tool_name and params:
                schemas[tool_name] = {
                    "required": params.get("required", []),
                    "properties": params.get("properties", {}),
                }
        return schemas

    def get_filtered_tools(self, task_description: str, include_mcp: bool = True) -> list[dict[str, Any]]:
        """Get tools filtered by task context for reduced token usage.

        Uses semantic matching to provide only relevant tools based on
        the task description, achieving up to 96% token reduction.

        Args:
            task_description: Natural language description of the task
            include_mcp: Whether to include MCP tools

        Returns:
            Filtered list of tool schemas
        """
        all_tools = self.get_available_tools() or []

        # Get or initialize the toolset manager
        manager = get_toolset_manager()

        # Register tools if not already done
        if not manager._tools:
            manager.register_tools(all_tools)

        # Get filtered tools for this task
        filtered = manager.get_tools_for_task(task_description, include_mcp=include_mcp)

        # Update hallucination detector with filtered tools
        tool_names = [t.get("function", {}).get("name", "") for t in filtered]
        self._hallucination_detector.update_available_tools(tool_names)

        return filtered

    def get_tool(self, function_name: str) -> BaseTool:
        """Get specified tool.

        Raises:
            ValueError: If tool is not found (includes hallucination detection)
        """
        for tool in self.tools:
            if tool.has_function(function_name):
                return tool

        # Tool not found - check if this is a hallucination
        # NOTE: This early detection provides defense-in-depth. The primary validation
        # happens in invoke_tool() via validate_tool_call(), but this catches issues
        # earlier in the execution flow when tools are looked up by name.
        correction = self._hallucination_detector.detect(function_name)
        if correction:
            raise ToolNotFoundException(function_name, correction=correction)

        raise ToolNotFoundException(function_name)

    def refresh_hallucination_detector(self) -> None:
        """Refresh the hallucination detector with current available tools.

        Call this after dynamically loading MCP tools. Updates both the
        list of available tool names and their parameter schemas for
        comprehensive validation.
        """
        available_tools = self.get_available_tools() or []

        # Update available tool names
        tool_names = [t.get("function", {}).get("name", "") for t in available_tools]
        self._hallucination_detector.update_available_tools(tool_names)

        # Update tool schemas for parameter validation
        self._hallucination_detector.update_tool_schemas(self._extract_tool_schemas(available_tools))

    async def _get_attention_context(self) -> str:
        """Get attention context for prompt injection.

        Implements Pythinker-style attention manipulation to prevent
        goal drift in long conversations. The context manager
        provides goal/todo context that should be periodically
        recited to keep the agent focused.

        Returns:
            Formatted context string with goal, todos, and state,
            or empty string if no context manager is configured.
        """
        if self.context_manager:
            return await self.context_manager.get_attention_context()
        return ""

    async def post_state(
        self,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Post state to the shared blackboard.

        Implements the blackboard architecture pattern where agents post findings
        to a shared state manifest for other agents to discover and build upon.

        Args:
            key: Unique identifier for this piece of state (e.g., "research_findings")
            value: The state value to post (any JSON-serializable type)
            metadata: Optional metadata about the entry (e.g., confidence, model used)

        Raises:
            ValueError: If no state manifest is configured
        """
        if self.state_manifest is None:
            raise AgentConfigurationException("No state manifest configured for this agent")

        entry = StateEntry(
            key=key,
            value=value,
            posted_by=self._agent_id,
            metadata=metadata or {},
        )
        self.state_manifest.post(entry)
        logger.debug(
            f"Agent {self._agent_id} posted state",
            extra={"key": key, "value_type": type(value).__name__},
        )

    async def read_state(self, key: str) -> Any | None:
        """Read state from the shared blackboard.

        Enables discovery of findings posted by other agents without
        direct communication between agents.

        Args:
            key: The key to look up

        Returns:
            The value of the most recent entry for this key, or None if not found
            or no state manifest is configured.
        """
        if self.state_manifest is None:
            return None

        entry = self.state_manifest.get(key)
        if entry is None:
            return None
        return entry.value

    def _get_blackboard_context(self, max_entries: int = 10) -> str:
        """Get blackboard state for LLM context injection.

        Formats recent blackboard entries as a string suitable for including
        in an LLM prompt to provide context about shared state from other agents.

        Args:
            max_entries: Maximum number of entries to include (default: 10)

        Returns:
            Formatted string representation of recent blackboard state,
            or empty string if no state manifest is configured.
        """
        if self.state_manifest is None:
            return ""
        return self.state_manifest.to_context_string(max_entries=max_entries)

    def _record_tool_usage(self, tool_name: str, success: bool, duration_ms: float) -> None:
        """Record tool usage for dynamic toolset prioritization.

        Args:
            tool_name: Name of the executed tool
            success: Whether execution was successful
            duration_ms: Execution duration in milliseconds
        """
        try:
            manager = get_toolset_manager()
            manager.record_tool_usage(tool_name, success, duration_ms)
        except Exception as e:
            logger.debug(f"Failed to record tool usage for {tool_name}: {e}")

    def _create_tool_event(
        self,
        tool_call_id: str,
        tool_name: str,
        function_name: str,
        function_args: dict[str, Any],
        status: ToolStatus,
        **kwargs,
    ) -> ToolEvent:
        """Create ToolEvent with command formatting applied.

        Args:
            tool_call_id: Unique ID for this tool call
            tool_name: Name of the tool
            function_name: Function being called
            function_args: Function arguments
            status: Tool execution status
            **kwargs: Additional fields for ToolEvent

        Returns:
            ToolEvent with display_command, command_category, and command_summary populated
        """
        # Format command for human-readable display
        try:
            display_command, command_category, command_summary = CommandFormatter.format_tool_call(
                tool_name=tool_name,
                function_name=function_name,
                function_args=function_args,
            )
        except Exception as e:
            logger.debug(f"Failed to format command: {e}")
            display_command = f"{function_name}(...)"
            command_category = "other"
            command_summary = function_name

        # Populate tool_content for search tools (Pythinker-style search results display)
        tool_content = kwargs.pop("tool_content", None)
        search_functions = ToolName.search_tools()
        # Max results shown in the search results panel per tool invocation.
        # wide_research collects up to 20 results across 16 queries; cap display at 20
        # so the panel is informative without being overwhelming.
        search_panel_max = 20
        if tool_content is None and status == ToolStatus.CALLED and function_name in search_functions:
            function_result = kwargs.get("function_result")
            # Extract search results from ToolResult.data if valid result with data
            if (
                function_result
                and hasattr(function_result, "success")
                and function_result.success
                and hasattr(function_result, "data")
                and function_result.data
            ):
                data = function_result.data
                results_list: list[SearchResultItem] = []

                # Handle SearchResults object (API search path)
                if hasattr(data, "results") and data.results:
                    results_list = [
                        SearchResultItem(
                            title=r.title or "No title",
                            link=r.link or "",
                            snippet=r.snippet or "",
                        )
                        for r in data.results[:search_panel_max]
                    ]
                # Handle wide_research dict with "sources" key
                elif isinstance(data, dict) and data.get("sources"):
                    results_list = [
                        SearchResultItem(
                            title=s.get("title", "No title"),
                            link=s.get("url", s.get("link", "")),
                            snippet=s.get("snippet", ""),
                        )
                        for s in data["sources"][:search_panel_max]
                    ]

                if results_list:
                    tool_content = SearchToolContent(results=results_list)
                    logger.info(f"SearchToolContent created with {len(results_list)} results for {function_name}")

        # Handle deal scraper tools — emit structured DealToolContent
        deal_functions = {"deal_search", "deal_compare_prices", "deal_find_coupons"}
        if tool_content is None and status == ToolStatus.CALLED and function_name in deal_functions:
            function_result = kwargs.get("function_result")
            if (
                function_result
                and hasattr(function_result, "success")
                and function_result.success
                and hasattr(function_result, "data")
                and function_result.data is not None
            ):
                data = function_result.data
                raw_deals = data.get("deals", []) if isinstance(data, dict) else []
                deal_items = [
                    DealItem(
                        store=d.get("store", d.get("store_name", "")),
                        price=d.get("price"),
                        original_price=d.get("original_price"),
                        discount_percent=d.get("discount_percent", d.get("discount", None)),
                        product_name=d.get("title", d.get("product_name", "")),
                        url=d.get("url", d.get("product_url", "")),
                        score=d.get("score"),
                        in_stock=d.get("in_stock"),
                        coupon_code=d.get("coupon_code"),
                        image_url=d.get("image_url"),
                    )
                    for d in raw_deals[:10]
                ]
                raw_coupons = data.get("coupons", []) if isinstance(data, dict) else []
                coupon_items = [
                    CouponItem(
                        code=c.get("code", ""),
                        description=c.get("description", ""),
                        store=c.get("store_name", c.get("store", "")),
                        expiry=c.get("expiry_date", c.get("expiry")),
                        verified=bool(c.get("verified", False)),
                        source=c.get("source", ""),
                    )
                    for c in raw_coupons[:10]
                ]
                # Determine best deal by score
                best_idx: int | None = None
                if deal_items:
                    scored = [(i, d.score or 0) for i, d in enumerate(deal_items)]
                    best_idx = max(scored, key=lambda x: x[1])[0] if any(s > 0 for _, s in scored) else 0
                query_str = function_args.get("query", function_args.get("product", ""))
                # Extract store metadata (always present even when deals are empty)
                searched_stores: list[str] = data.get("searched_stores", []) if isinstance(data, dict) else []
                store_errors: list[dict[str, str]] = data.get("store_errors", []) if isinstance(data, dict) else []
                empty_reason = data.get("empty_reason") if isinstance(data, dict) else None
                stores_attempted = data.get("stores_attempted") if isinstance(data, dict) else None
                stores_with_results = data.get("stores_with_results") if isinstance(data, dict) else None
                tool_content = DealToolContent(
                    deals=deal_items,
                    coupons=coupon_items,
                    query=query_str,
                    best_deal_index=best_idx,
                    searched_stores=searched_stores,
                    store_errors=store_errors,
                    empty_reason=empty_reason if isinstance(empty_reason, str) else None,
                    stores_attempted=stores_attempted if isinstance(stores_attempted, int) else None,
                    stores_with_results=stores_with_results if isinstance(stores_with_results, int) else None,
                )
                logger.info(
                    f"DealToolContent created with {len(deal_items)} deals, "
                    f"{len(coupon_items)} coupons, {len(searched_stores)} stores for {function_name}"
                )

        # For CALLED events, merge resolved coordinates from browser click/input
        # into function_args so the frontend cursor overlay can track index-based actions.
        # Creates a new dict to avoid mutating the original args reference.
        final_args = function_args
        if status == ToolStatus.CALLED:
            function_result = kwargs.get("function_result")
            if (
                function_result
                and hasattr(function_result, "data")
                and isinstance(function_result.data, dict)
                and {"resolved_x", "resolved_y"}.issubset(function_result.data)
            ):
                final_args = {
                    **function_args,
                    "coordinate_x": function_result.data["resolved_x"],
                    "coordinate_y": function_result.data["resolved_y"],
                }

        return ToolEvent(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=final_args,
            status=status,
            display_command=display_command,
            command_category=command_category,
            command_summary=command_summary,
            tool_content=tool_content,
            **kwargs,
        )

    async def invoke_tool(
        self,
        tool: BaseTool,
        function_name: str,
        arguments: dict[str, Any],
        skip_security: bool = False,
    ) -> ToolResult:
        """Invoke specified tool, with retry mechanism and exponential backoff.

        Integrates with:
        - ToolHallucinationDetector for pre-execution validation
        - ToolExecutionProfiler for timing and reliability tracking
        - SecurityAssessor for risk evaluation
        - StuckDetector for action pattern detection
        """
        import time

        profiler = get_tool_profiler()
        tool_tracer = None
        flags = self._resolve_feature_flags()
        if flags.get("tool_tracing"):
            tool_tracer = get_tool_tracer()
        start_time = time.perf_counter()

        # Create standardized envelope for this tool call
        tool_call_id = str(uuid.uuid4())
        envelope = ToolCallEnvelope(
            tool_call_id=tool_call_id,
            tool_name=tool.name,
            function_name=function_name,
            arguments=arguments,
        )

        # Log tool invocation via structured logger
        log_start = self._log.tool_started(function_name, tool_call_id, arguments)

        # Pre-execution hallucination check (validates tool name and parameters)
        validation_result = self._hallucination_detector.validate_tool_call(
            tool_name=function_name,
            parameters=arguments,
        )

        self._total_tool_calls += 1

        if not validation_result.is_valid:
            logger.warning(
                f"Tool hallucination detected: {validation_result.error_message}",
                extra={
                    "function_name": function_name,
                    "error_type": validation_result.error_type,
                    "suggestions": validation_result.suggestions,
                    "session_id": getattr(self, "_session_id", None),
                    "agent_id": getattr(self, "_agent_id", None),
                },
            )
            # Build correction message with suggestions if available
            correction_message = validation_result.error_message or "Tool validation failed"
            if validation_result.suggestions:
                correction_message += f" Suggestions: {', '.join(validation_result.suggestions)}"

            self._total_hallucinations += 1

            # Check if hallucination rate warrants escalation
            try:
                from app.core.config import get_settings

                _settings = get_settings()
                if (
                    getattr(_settings, "feature_hallucination_escalation_enabled", False)
                    and not self._hallucination_escalated
                    and self._total_tool_calls >= getattr(_settings, "hallucination_escalation_min_samples", 10)
                ):
                    rate = self._total_hallucinations / max(1, self._total_tool_calls)
                    threshold = getattr(_settings, "hallucination_escalation_threshold", 0.15)
                    if rate >= threshold:
                        self._hallucination_escalated = True
                        logger.warning(
                            "Hallucination rate escalation triggered: rate=%.2f "
                            "(threshold=%.2f, calls=%d, hallucinations=%d)",
                            rate,
                            threshold,
                            self._total_tool_calls,
                            self._total_hallucinations,
                        )
            except Exception:
                logger.debug(
                    "Hallucination escalation check failed (non-critical)",
                    exc_info=True,
                )

            return ToolResult(success=False, message=correction_message)

        # Security assessment before execution (skip for user-confirmed actions)
        if not skip_security:
            security_assessment = self._security_assessor.assess_action(function_name, arguments)
            if security_assessment.blocked:
                self._log.security_event("blocked", function_name, security_assessment.reason)
                envelope.mark_blocked(security_assessment.reason)
                return ToolResult(success=False, message=f"Action blocked for security: {security_assessment.reason}")

            if security_assessment.risk_level == ActionSecurityRisk.HIGH:
                self._log.security_event("high_risk", function_name, security_assessment.reason)

        # Circuit breaker: reject calls to tools that are failing repeatedly
        if self._circuit_breaker and not self._circuit_breaker.can_execute(function_name):
            msg = f"Tool '{function_name}' circuit is open — skipping to avoid cascading failures"
            logger.warning(msg)
            envelope.mark_failed(msg)
            return ToolResult(success=False, message=msg)

        retries = 0
        current_interval = self.retry_interval
        last_error = ""
        result: ToolResult | None = None
        envelope.mark_started()

        # WP-5: Capture trace context for per-tool distributed tracing spans.
        # _trace_ctx is injected by PlanActFlow after agent construction when
        # feature_tool_tracing is enabled.
        _trace_ctx_for_tool = getattr(self, "_trace_ctx", None)

        # Phase 4: HITL interrupt — block high-risk tool calls before execution
        if flags.get("hitl_enabled"):
            try:
                from app.domain.services.flows.hitl_policy import get_hitl_policy

                _hitl_assessment = get_hitl_policy().assess(function_name, arguments)
                if _hitl_assessment.requires_approval:
                    logger.warning(
                        "HITL interrupt: tool=%s risk=%s level=%s — returning requires_approval",
                        function_name,
                        _hitl_assessment.reason,
                        _hitl_assessment.risk_level,
                    )
                    return ToolResult(
                        success=False,
                        message=(
                            f"[HITL] This action requires human approval before execution. "
                            f"Risk: {_hitl_assessment.reason} (level={_hitl_assessment.risk_level}). "
                            "Please confirm or cancel the action."
                        ),
                    )
            except Exception as _hitl_err:
                logger.debug("HITL policy check failed (non-critical): %s", _hitl_err)

        # ── URL Failure Guard: pre-check ─────────────────────────────────────
        _guard_url: str | None = None
        if self._url_failure_guard is not None:
            _guard_url = _extract_url_from_args(arguments)
            if _guard_url:
                _guard_decision = self._url_failure_guard.check_url(_guard_url)
                try:
                    from app.core.prometheus_metrics import url_guard_actions_total, url_guard_escalations_total

                    url_guard_actions_total.inc({"tier": str(_guard_decision.tier), "action": _guard_decision.action})
                    if _guard_decision.action in ("warn", "block"):
                        url_guard_escalations_total.inc({"tier": str(_guard_decision.tier)})
                except Exception:
                    logger.debug("URL guard metrics emission failed (non-critical)", exc_info=True)
                if _guard_decision.action == "block":
                    # Tier 3: Hard-block — skip execution entirely
                    logger.warning(
                        "URL guard BLOCKED %s (tier=%d): %s",
                        _guard_url,
                        _guard_decision.tier,
                        _guard_decision.message,
                    )
                    return ToolResult(success=False, message=_guard_decision.message)
                if _guard_decision.action == "warn" and _guard_decision.message:
                    # Tier 2: Inject warning — execution still proceeds
                    logger.info(
                        "URL guard WARNING for %s (tier=%d)",
                        _guard_url,
                        _guard_decision.tier,
                    )
                    self._efficiency_nudges.append(
                        {
                            "message": _guard_decision.message,
                            "read_count": 0,
                            "action_count": 0,
                            "confidence": 0.90,
                            "hard_stop": False,
                        }
                    )

        while retries <= self.max_retries:
            try:
                # ORPHANED TASK FIX: Check cancellation BEFORE invoking function
                # Prevents tool execution if cancelled during retry loop
                await self._cancel_token.check_cancelled()

                # WP-5: Wrap actual execution in a distributed-tracing span when enabled
                if flags.get("tool_tracing") and _trace_ctx_for_tool:
                    with _trace_ctx_for_tool.span(
                        f"tool:{function_name}",
                        "tool_execution",
                        {
                            "tool.name": function_name,
                            "agent.id": getattr(self, "_agent_id", ""),
                            "attempt": retries,
                        },
                    ) as _tool_span:
                        result = await asyncio.wait_for(
                            tool.invoke_function(function_name, **arguments),
                            timeout=_resolve_tool_timeout(function_name),
                        )
                        try:
                            _tool_span.set_attribute("tool.success", result.success)
                            _tool_span.set_attribute("tool.result_size", len(str(result.message or "")))
                        except Exception as _span_err:
                            logger.debug("Tool span attribute set failed (non-critical): %s", _span_err)
                else:
                    result = await asyncio.wait_for(
                        tool.invoke_function(function_name, **arguments),
                        timeout=_resolve_tool_timeout(function_name),
                    )
            except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                raise
            except TimeoutError:
                _timeout_used = _resolve_tool_timeout(function_name)
                last_error = f"Tool execution timed out after {_timeout_used:.0f}s"
                self._log.tool_failed(function_name, tool_call_id, last_error, log_start)
                # Classify timeout: network-related tools are recoverable, others are fatal
                network_tools = {"info_search_web", "browser_get_content", "browser_navigate", "mcp_call_tool"}
                if function_name in network_tools and retries < self.max_retries:
                    retries += 1
                    logger.info(f"Recoverable timeout for {function_name}, retrying ({retries}/{self.max_retries})")
                    await asyncio.sleep(current_interval)
                    current_interval *= self.retry_backoff
                    continue
                envelope.mark_failed(last_error)
                break
            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(current_interval)
                    current_interval *= self.retry_backoff
                    continue
                self._log.tool_failed(function_name, tool_call_id, last_error, log_start)
                envelope.mark_failed(last_error)
                break

            # Post-execution tracking (non-critical — must not prevent result return)
            try:
                duration_ms = (time.perf_counter() - start_time) * 1000
                profiler.record_execution(
                    tool_name=function_name,
                    duration_ms=duration_ms,
                    success=result.success if result else False,
                    error=result.message if result and not result.success else None,
                )

                if tool_tracer:
                    tool_tracer.trace_execution(
                        tool_name=function_name,
                        arguments=arguments,
                        result=result,
                        duration_ms=duration_ms,
                    )

                self._record_tool_usage(
                    function_name, success=result.success if result else False, duration_ms=duration_ms
                )

                result_preview = str(result.message)[:500] if result else ""
                self._stuck_detector.track_tool_action(
                    tool_name=function_name,
                    tool_args=arguments,
                    success=result.success if result else False,
                    result=result_preview,
                    error=result.message if result and not result.success else None,
                )

                # Tool efficiency monitoring (analysis paralysis detection)
                try:
                    self._efficiency_monitor.record(function_name)
                    signal = self._efficiency_monitor.check_efficiency()

                    if not signal.is_balanced and signal.nudge_message:
                        logger.info(
                            f"Tool efficiency nudge (hard_stop={signal.hard_stop}): {signal.nudge_message[:80]}... "
                            f"(reads={signal.read_count}, actions={signal.action_count}, "
                            f"confidence={signal.confidence})"
                        )

                        self._metrics.increment(
                            "pythinker_tool_efficiency_nudges_total",
                            labels={
                                "threshold": "hard_stop" if signal.hard_stop else "soft",
                                "read_count": str(signal.read_count),
                                "action_count": str(signal.action_count),
                            },
                        )

                        self._efficiency_nudges.append(
                            {
                                "message": signal.nudge_message,
                                "read_count": signal.read_count,
                                "action_count": signal.action_count,
                                "confidence": signal.confidence,
                                "hard_stop": signal.hard_stop,
                            }
                        )
                except Exception as e:
                    logger.debug(f"Tool efficiency monitoring failed for {function_name}: {e}")

                # URL Failure Guard: ingest search results and record URL failures.
                if self._url_failure_guard and result:
                    try:
                        if result.success and "search" in function_name:
                            discovered_urls = _extract_search_result_urls(result)
                            if discovered_urls:
                                self._url_failure_guard.record_search_results(discovered_urls)
                        if _guard_url and not result.success:
                            self._url_failure_guard.record_failure(
                                _guard_url,
                                result.message[:200] if result.message else "Unknown error",
                                function_name,
                            )
                        from app.core.prometheus_metrics import url_guard_tracked_urls

                        metrics = self._url_failure_guard.get_metrics()
                        url_guard_tracked_urls.set(value=float(metrics.get("tracked_urls", 0)))
                    except Exception as _guard_err:
                        logger.debug("URL failure guard post-execution handling failed: %s", _guard_err)

                try:
                    from app.domain.services.agents.task_state_manager import get_task_state_manager

                    task_state_manager = getattr(self, "_task_state_manager", None) or get_task_state_manager()
                    await task_state_manager.record_action(
                        function_name=function_name,
                        success=result.success if result else False,
                        result=result.data
                        if result and result.data is not None
                        else result.message
                        if result
                        else None,
                        error=result.message if result and not result.success else None,
                    )
                except Exception as e:
                    logger.debug(f"Task state recording failed for {function_name}: {e}")

                envelope.mark_completed(
                    success=result.success if result else False,
                    message=result.message if result else None,
                )
                self._log.tool_completed(
                    function_name,
                    tool_call_id,
                    log_start,
                    success=result.success if result else False,
                    message=result.message if result else None,
                )
            except Exception as e:
                logger.warning(f"Post-execution tracking failed for {function_name}: {e}")

            # Circuit breaker: record success
            if self._circuit_breaker and result and result.success:
                self._circuit_breaker.record_success(function_name)

            return result

        # Retry loop exhausted — record failure metrics
        if self._circuit_breaker:
            self._circuit_breaker.record_failure(function_name)
        duration_ms = (time.perf_counter() - start_time) * 1000
        profiler.record_execution(
            tool_name=function_name, duration_ms=duration_ms, success=False, error=last_error[:200]
        )

        if tool_tracer:
            tool_tracer.trace_execution(
                tool_name=function_name,
                arguments=arguments,
                result=None,
                duration_ms=duration_ms,
                error=last_error[:200],
            )

        self._stuck_detector.track_tool_action(
            tool_name=function_name,
            tool_args=arguments,
            success=False,
            error=last_error[:200],
        )

        # Tool efficiency monitoring (even on failure, track the attempt)
        try:
            self._efficiency_monitor.record(function_name)
            signal = self._efficiency_monitor.check_efficiency()

            if not signal.is_balanced and signal.nudge_message:
                logger.info(
                    f"Tool efficiency nudge after failure (hard_stop={signal.hard_stop}): "
                    f"(reads={signal.read_count}, actions={signal.action_count})"
                )
                self._metrics.increment(
                    "pythinker_tool_efficiency_nudges_total",
                    labels={
                        "threshold": "hard_stop" if signal.hard_stop else "soft",
                        "read_count": str(signal.read_count),
                        "action_count": str(signal.action_count),
                    },
                )
                self._efficiency_nudges.append(
                    {
                        "message": signal.nudge_message,
                        "read_count": signal.read_count,
                        "action_count": signal.action_count,
                        "confidence": signal.confidence,
                        "hard_stop": signal.hard_stop,
                    }
                )
        except Exception as e:
            logger.debug(f"Tool efficiency monitoring failed for {function_name}: {e}")

        # URL Failure Guard: record failure when retries exhausted
        if self._url_failure_guard and _guard_url:
            try:
                self._url_failure_guard.record_failure(_guard_url, last_error[:200], function_name)
                from app.core.prometheus_metrics import url_guard_tracked_urls

                metrics = self._url_failure_guard.get_metrics()
                url_guard_tracked_urls.set(value=float(metrics.get("tracked_urls", 0)))
            except Exception as _guard_err:
                logger.debug("URL failure guard recording failed (retry exhausted): %s", _guard_err)

        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            task_state_manager = getattr(self, "_task_state_manager", None) or get_task_state_manager()
            await task_state_manager.record_action(
                function_name=function_name,
                success=False,
                result=None,
                error=last_error[:200],
            )
        except Exception as e:
            logger.debug(f"Task state recording failed for {function_name} error path: {e}")

        return ToolResult(success=False, message=last_error)

    @staticmethod
    def _truncate_text(content: str, max_chars: int) -> str:
        """Truncate text with a compact marker."""
        if len(content) <= max_chars:
            return content
        truncated_chars = len(content) - max_chars
        return f"{content[:max_chars]}\n\n... [truncated {truncated_chars:,} chars]"

    def _tool_data_preview(self, data: Any, max_chars: int) -> str:
        """Create a bounded preview string for tool result data."""
        if hasattr(data, "model_dump"):
            data = data.model_dump()

        if isinstance(data, str):
            return self._truncate_text(data, max_chars)

        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            serialized = str(data)

        return self._truncate_text(serialized, max_chars)

    def _serialize_tool_result_for_memory(self, result: ToolResult, function_name: str = "") -> str:
        """Serialize tool results with size guardrails to avoid memory bloat."""
        raw = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
        if len(raw) <= self._TOOL_RESULT_MEMORY_MAX_CHARS:
            return raw

        # ── ToolResultStore offload (Component 1) ─────────────────────
        # Store full content externally, keep only preview + ref in conversation.
        if self._tool_result_store and self._tool_result_store.should_offload(raw):
            result_id, preview = self._tool_result_store.store(raw, function_name)
            return ToolResult(
                success=result.success,
                message="Tool output stored externally.",
                data={
                    "_stored_externally": True,
                    "_result_ref": result_id,
                    "_original_size_chars": len(raw),
                    "_preview": preview,
                },
            ).model_dump_json()

        compacted_data: dict[str, Any] = {
            "_compacted": True,
            "_original_size_chars": len(raw),
        }
        if result.data is not None:
            compacted_data["_preview"] = self._tool_data_preview(result.data, self._TOOL_RESULT_DATA_PREVIEW_CHARS)

        compacted = ToolResult(
            success=result.success,
            message=self._truncate_text(
                result.message or "Tool output compacted for memory.",
                self._TOOL_RESULT_MESSAGE_PREVIEW_CHARS,
            ),
            data=compacted_data,
        ).model_dump_json()

        if len(compacted) <= self._TOOL_RESULT_MEMORY_MAX_CHARS:
            return compacted

        # Final fallback for extreme payloads
        return ToolResult(
            success=result.success,
            message=self._truncate_text(
                result.message or "Tool output omitted from memory to control context size.",
                1000,
            ),
            data={
                "_compacted": True,
                "_original_size_chars": len(raw),
            },
        ).model_dump_json()

    def _truncate_args_for_logging(self, arguments: dict[str, Any], max_len: int = 100) -> dict[str, str]:
        """Truncate large argument values for logging to prevent log bloat."""
        truncated = {}
        for key, value in arguments.items():
            str_value = str(value)
            if len(str_value) > max_len:
                truncated[key] = f"{str_value[:max_len]}... (truncated, {len(str_value)} chars total)"
            else:
                truncated[key] = str_value
        return truncated

    def _parse_tool_arguments(self, raw_arguments: Any, *, function_name: str) -> dict[str, Any]:
        """Parse tool-call arguments using strict JSON object semantics.

        Tool-call arguments are execution-critical. They must be a JSON object
        so we can safely pass them as ``**kwargs``. Unlike generic LLM output
        parsing, do not run permissive "repair" heuristics here because those
        can silently transform prose/truncated text into incorrect keys.
        """
        if raw_arguments is None:
            return {}

        if isinstance(raw_arguments, dict):
            return raw_arguments

        if not isinstance(raw_arguments, str):
            raise ValueError(f"expected JSON object string, got {type(raw_arguments).__name__}")

        stripped = raw_arguments.strip()
        if not stripped or stripped.lower() == "null":
            return {}

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc

        if parsed is None:
            return {}
        if parsed == []:
            return {}
        if not isinstance(parsed, dict):
            raise ValueError(f"expected JSON object for tool '{function_name}', got {type(parsed).__name__}")
        return parsed

    def _tool_requires_arguments(self, function_name: str) -> bool:
        """Return True when the tool schema declares required parameters."""
        for tool_def in self.get_available_tools() or []:
            func = tool_def.get("function", {})
            if func.get("name") != function_name:
                continue
            params = func.get("parameters", {}) or {}
            required = params.get("required", []) or []
            return len(required) > 0
        return False

    def _invalid_tool_args_result(self, *, function_name: str, raw_arguments: Any, error: ValueError) -> ToolResult:
        """Create a deterministic error result for malformed tool-call arguments."""
        raw_preview = self._truncate_text(str(raw_arguments), 240)
        logger.warning(
            "Skipping malformed tool call '%s': %s (raw_args=%s)",
            function_name,
            error,
            raw_preview,
        )
        return ToolResult.error(
            f"Invalid JSON arguments for tool '{function_name}'. Please resend this tool call with a valid JSON object."
        )

    def _to_tool_call(self, tc: dict) -> Any:
        """Convert an LLM tool_call dict to a ParallelToolExecutor ToolCall.

        Args:
            tc: Raw tool_call dict from LLM response (has 'id' and 'function' keys)

        Returns:
            ToolCall dataclass for ParallelToolExecutor
        """
        from app.domain.services.agents.parallel_executor import ToolCall as ToolCallParallel

        return ToolCallParallel(
            id=tc.get("id", ""),
            tool_name=tc.get("function", {}).get("name", ""),
            arguments=tc.get("function", {}).get("arguments", {}),
        )

    def _can_parallelize_tools(self, tool_calls: list[dict]) -> bool:
        """Check if tool calls can be executed in parallel using dependency detection.

        Uses ParallelToolExecutor.detect_dependencies() to catch data-flow
        dependencies (e.g. write-then-read same file) that pure whitelist
        checking would miss.

        Supports both explicit tool whitelist and MCP read-only patterns.
        Also checks SEQUENTIAL_ONLY_TOOLS blacklist from parallel_executor.
        """
        from app.domain.services.agents.parallel_executor import ParallelToolExecutor

        if len(tool_calls) <= 1:
            return False

        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")

            # Check blacklist first — these must never run in parallel
            if tool_name in ParallelToolExecutor.SEQUENTIAL_ONLY_TOOLS:
                return False

            # Check explicit whitelist
            if tool_name in SAFE_PARALLEL_TOOLS:
                continue

            # Check MCP read-only prefixes (dynamic tools from MCP servers).
            # Use strict prefix matching only; substring matching is unsafe and
            # can accidentally classify unrelated tools (e.g. any name with "_")
            # as MCP read tools.
            if tool_name.startswith(SAFE_MCP_PREFIXES):
                continue

            # Tool not in safe list
            return False

        # WP-2: Dependency detection — if any data-flow dependency exists between
        # these calls, they cannot safely run in parallel.
        try:
            executor = ParallelToolExecutor()
            tool_call_objs = [self._to_tool_call(tc) for tc in tool_calls]
            executor.add_calls(tool_call_objs)
            executor.detect_dependencies()
            # If any call has unresolvable dependencies, we must go sequential
            for call in executor._pending_calls:
                if call.depends_on:
                    return False
        except Exception as _dep_err:
            logger.debug("Dependency detection failed (non-critical): %s", _dep_err)

        return True

    def _is_read_only_tool(self, function_name: str) -> bool:
        """Check if a tool is read-only (doesn't modify state)."""
        read_only_patterns = {
            # File operations
            "file_read",
            "file_search",
            "file_list",
            "file_info",
            # Shell read operations
            "shell_exec",  # Will check command content separately
            # Browser read operations
            "browser_view",
            "browser_screenshot",
            "search",
            # Search
            "info_search",
            # Code read operations
            "code_list",
            "code_read",
            # Git read operations
            "git_status",
            "git_diff",
            "git_log",
            "git_branches",
            # Workspace info
            "workspace_info",
            "workspace_tree",
            # Test list
            "test_list",
            # Export list
            "export_list",
        }
        name_lower = function_name.lower()
        return any(name_lower == pattern or name_lower.startswith(pattern + "_") for pattern in read_only_patterns)

    def _calculate_iteration_cost(self, tool_calls: list[dict]) -> float:
        """Calculate weighted iteration cost based on tool types."""
        cost = 0.0
        for tc in tool_calls:
            function_name = tc.get("function", {}).get("name", "")
            if self._is_read_only_tool(function_name):
                cost += self.read_only_iteration_weight
            else:
                cost += 1.0
        return max(1.0, cost)  # Minimum 1 iteration per cycle

    async def execute(self, request: str, format: str | None = None) -> AsyncGenerator[BaseEvent, None]:
        format = format or self.format
        # Don't use json_object format when tools are available - causes empty responses
        # Only enforce JSON format after tool calling is complete
        has_tools = bool(self.get_available_tools())
        initial_format = None if has_tools else format
        message = await self.ask(request, initial_format)

        # Use weighted iteration tracking for better handling of large tasks
        iteration_budget = float(self.max_iterations)
        iteration_spent = 0.0
        step_iteration_count = 0  # Per-step iteration counter
        warning_emitted = False
        graceful_completion_requested = False
        wall_clock_advisory_sent = False
        wall_clock_urgent_sent = False
        wall_clock_critical_sent = False
        wall_clock_exceeded = False

        # Reset per-step stability counters
        self._hallucination_count_this_step = 0
        self._compression_cycles_this_step = 0
        self._compression_guard_active = False
        self._step_start_time = time.monotonic()
        self._recent_truncation_count = 0  # Prevent stale count from prior step
        self._stuck_recovery_exhausted = False

        while iteration_spent < iteration_budget:
            if not message.get("tool_calls"):
                break

            tool_calls = message["tool_calls"]
            tool_responses = []
            wall_clock_pressure_active: str | None = None

            # Check for hallucination loop escalation
            if self._hallucination_detector.should_inject_correction_prompt():
                self._hallucination_count_this_step += 1
                if self._hallucination_count_this_step >= self.max_hallucinations_per_step:
                    logger.warning(
                        "Hallucination cap reached (%d/%d injections this step), force-advancing",
                        self._hallucination_count_this_step,
                        self.max_hallucinations_per_step,
                    )
                    self._stuck_recovery_exhausted = True
                    break
                correction = self._hallucination_detector.get_correction_prompt()
                logger.warning(
                    f"Hallucination loop detected ({self._hallucination_detector.hallucination_count} consecutive), "
                    f"injecting correction prompt ({self._hallucination_count_this_step}/{self.max_hallucinations_per_step})"
                )
                correction_messages = [{"role": "user", "content": correction}]
                message = await self.ask_with_messages(correction_messages)
                self._hallucination_detector.reset()
                continue

            # Calculate iteration cost for this cycle
            iteration_cost = self._calculate_iteration_cost(tool_calls)
            iteration_spent += iteration_cost
            step_iteration_count += 1

            # Check per-step iteration budget
            if step_iteration_count >= self.max_step_iterations:
                logger.warning(
                    f"Step iteration budget exhausted ({step_iteration_count}/{self.max_step_iterations}). "
                    "Setting stuck_recovery_exhausted flag."
                )
                self._stuck_recovery_exhausted = True
                break

            # Check per-step wall-clock limit
            if self._step_start_time is not None:
                from app.core.config import get_settings

                _settings = get_settings()
                # Per-depth budgets override the global limit when research depth is known
                _depth = getattr(self, "_research_depth", None)
                if _depth == "QUICK":
                    wall_limit = getattr(_settings, "step_budget_quick_seconds", 300.0)
                elif _depth == "DEEP":
                    wall_limit = getattr(_settings, "step_budget_deep_seconds", 900.0)
                elif _depth == "STANDARD":
                    wall_limit = getattr(_settings, "step_budget_standard_seconds", 600.0)
                else:
                    wall_limit = getattr(_settings, "max_step_wall_clock_seconds", 600.0)
                if wall_limit > 0:
                    elapsed = time.monotonic() - self._step_start_time
                    if elapsed > wall_limit:
                        logger.warning(
                            "Step wall-clock limit exceeded (%.0fs > %.0fs). Force-advancing.",
                            elapsed,
                            wall_limit,
                        )
                        wall_clock_exceeded = True
                        self._stuck_recovery_exhausted = True
                        break
                    # ── Graduated wall-clock pressure ──────────────────
                    pressure = _get_wall_clock_pressure_level(elapsed, wall_limit)

                    if pressure == "ADVISORY" and not wall_clock_advisory_sent:
                        wall_clock_advisory_sent = True
                        logger.info(
                            "Step wall-clock at 50%% (%.0fs/%.0fs); advisory injected.",
                            elapsed,
                            wall_limit,
                        )
                        await self._add_to_memory(
                            [
                                {
                                    "role": "user",
                                    "content": (
                                        f"STEP TIME ADVISORY: You have used 50% of the step time budget "
                                        f"({elapsed:.0f}s of {wall_limit:.0f}s). "
                                        f"Begin wrapping up research and focus on writing output."
                                    ),
                                }
                            ]
                        )

                    elif pressure == "URGENT" and not wall_clock_urgent_sent:
                        wall_clock_urgent_sent = True
                        logger.warning(
                            "Step wall-clock at 75%% (%.0fs/%.0fs); blocking read-only tools.",
                            elapsed,
                            wall_limit,
                        )
                        await self._add_to_memory(
                            [
                                {
                                    "role": "user",
                                    "content": (
                                        f"STEP TIME URGENT: 75% of budget used ({elapsed:.0f}s of {wall_limit:.0f}s). "
                                        f"Read-only tools are now BLOCKED. You MUST finalize your output immediately. "
                                        f"Use file_write or file_str_replace to save findings NOW."
                                    ),
                                }
                            ]
                        )
                        graceful_completion_requested = True
                        wall_clock_pressure_active = "URGENT"

                    elif pressure == "CRITICAL" and not wall_clock_critical_sent:
                        wall_clock_critical_sent = True
                        logger.warning(
                            "Step wall-clock at 90%% (%.0fs/%.0fs); blocking ALL non-write tools.",
                            elapsed,
                            wall_limit,
                        )
                        await self._add_to_memory(
                            [
                                {
                                    "role": "user",
                                    "content": (
                                        f"STEP TIME CRITICAL: 90% of budget used ({elapsed:.0f}s of {wall_limit:.0f}s). "
                                        f"ALL tools except file_write and code_save_artifact are BLOCKED. "
                                        f"Write your output NOW or it will be lost."
                                    ),
                                }
                            ]
                        )
                        graceful_completion_requested = True
                        wall_clock_pressure_active = "CRITICAL"

            # Check if we're approaching the limit
            remaining_budget = iteration_budget - iteration_spent
            budget_ratio = iteration_spent / iteration_budget

            # Emit warning at threshold
            if budget_ratio >= self.iteration_warning_threshold and not warning_emitted:
                logger.warning(
                    f"Approaching iteration limit: {iteration_spent:.1f}/{iteration_budget} "
                    f"({budget_ratio * 100:.0f}% used)"
                )
                warning_emitted = True

            # Request graceful completion when near limit
            if remaining_budget < 10 and not graceful_completion_requested:
                logger.warning(
                    f"Low iteration budget ({remaining_budget:.1f} remaining), requesting completion on next cycle"
                )
                graceful_completion_requested = True

            if wall_clock_pressure_active:
                tool_calls = [
                    tc
                    for tc in tool_calls
                    if not _should_block_tool_at_pressure(
                        tc.get("function", {}).get("name", ""),
                        wall_clock_pressure_active,
                    )
                ]

            # Check if we can execute tools in parallel
            if self._can_parallelize_tools(tool_calls):
                # Parse all arguments first
                parsed_calls = []
                for tool_call in tool_calls[:MAX_CONCURRENT_TOOLS]:  # Limit parallel calls
                    if not tool_call.get("function"):
                        continue
                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call.get("id") or str(uuid.uuid4())
                    raw_function_args = tool_call["function"].get("arguments", "{}")
                    try:
                        function_args = self._parse_tool_arguments(raw_function_args, function_name=function_name)
                    except ValueError as parse_error:
                        self._recent_truncation_count += 1
                        parse_result = self._invalid_tool_args_result(
                            function_name=function_name,
                            raw_arguments=raw_function_args,
                            error=parse_error,
                        )
                        tool_name = function_name or "unknown_tool"
                        with contextlib.suppress(Exception):
                            tool_name = self.get_tool(function_name).name
                        yield self._create_tool_event(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            function_name=function_name,
                            function_args={},
                            status=ToolStatus.CALLED,
                            function_result=parse_result,
                        )
                        tool_responses.append(
                            {
                                "role": "tool",
                                "function_name": function_name,
                                "tool_call_id": tool_call_id,
                                "content": self._serialize_tool_result_for_memory(
                                    parse_result, function_name=function_name
                                ),
                            }
                        )
                        continue

                    tool = self.get_tool(function_name)
                    security_assessment = self._security_assessor.assess_action(function_name, function_args)
                    confirmation_state = "awaiting_confirmation" if security_assessment.requires_confirmation else None

                    if security_assessment.requires_confirmation:
                        yield self._create_tool_event(
                            tool_call_id=tool_call_id,
                            tool_name=tool.name,
                            function_name=function_name,
                            function_args=function_args,
                            status=ToolStatus.CALLING,
                            security_risk=security_assessment.risk_level.value,
                            security_reason=security_assessment.reason,
                            security_suggestions=security_assessment.suggestions,
                            confirmation_state=confirmation_state,
                        )
                        yield WaitEvent(wait_reason="user_input", suggest_user_takeover="none")
                        return

                    # ORPHANED TASK FIX: Check cancellation BEFORE emitting tool event
                    # Prevents tools from starting if SSE disconnect happened
                    await self._cancel_token.check_cancelled()

                    # Emit tool_stream preview so the frontend can show content
                    # in the editor/terminal BEFORE the tool starts executing.
                    raw_args = tool_call["function"].get("arguments", "{}")
                    if is_streamable_function(function_name):
                        partial = extract_partial_content(function_name, raw_args)
                        if partial:
                            yield ToolStreamEvent(
                                tool_call_id=tool_call_id,
                                tool_name=tool.name,
                                function_name=function_name,
                                partial_content=partial,
                                content_type=content_type_for_function(function_name),
                                is_final=True,
                            )

                    # Emit CALLING events for all parallel tools
                    yield self._create_tool_event(
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args,
                        status=ToolStatus.CALLING,
                        security_risk=security_assessment.risk_level.value,
                        security_reason=security_assessment.reason,
                        security_suggestions=security_assessment.suggestions,
                        confirmation_state=confirmation_state,
                    )
                    parsed_calls.append(
                        (
                            tool_call,
                            tool_call_id,
                            function_args,
                            tool,
                            security_assessment,
                        )
                    )

                # Execute all tools concurrently with semaphore
                semaphore = asyncio.Semaphore(MAX_CONCURRENT_TOOLS)
                tasks = []
                for tool_call, tool_call_id, function_args, tool, _ in parsed_calls:
                    function_name = tool_call["function"]["name"]
                    tasks.append(
                        self._execute_parallel_tool(semaphore, tool, function_name, function_args, tool_call_id)
                    )

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Re-raise cancellation signals before processing results
                for result in results:
                    if isinstance(result, (asyncio.CancelledError, KeyboardInterrupt)):
                        raise result

                # Process results and emit CALLED events
                if len(parsed_calls) != len(results):
                    logger.error(
                        f"Parallel execution result count mismatch: {len(parsed_calls)} calls vs {len(results)} results"
                    )
                for (tool_call, tool_call_id, function_args, tool, security_assessment), result in zip(
                    parsed_calls, results, strict=True
                ):
                    function_name = tool_call["function"]["name"]
                    if isinstance(result, Exception):
                        result = ToolResult(success=False, message=str(result))

                    yield self._create_tool_event(
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args,
                        status=ToolStatus.CALLED,
                        function_result=result,
                        security_risk=security_assessment.risk_level.value,
                        security_reason=security_assessment.reason,
                        security_suggestions=security_assessment.suggestions,
                        confirmation_state=(
                            "awaiting_confirmation" if security_assessment.requires_confirmation else None
                        ),
                    )

                    tool_responses.append(
                        {
                            "role": "tool",
                            "function_name": function_name,
                            "tool_call_id": tool_call_id,
                            "content": self._serialize_tool_result_for_memory(result, function_name=function_name),
                        }
                    )
            else:
                # Sequential execution for non-parallelizable tools (original behavior)
                for tool_call in tool_calls:
                    if not tool_call.get("function"):
                        continue

                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call.get("id") or str(uuid.uuid4())
                    raw_function_args = tool_call["function"].get("arguments", "{}")
                    try:
                        function_args = self._parse_tool_arguments(raw_function_args, function_name=function_name)
                    except ValueError as parse_error:
                        self._recent_truncation_count += 1
                        parse_result = self._invalid_tool_args_result(
                            function_name=function_name,
                            raw_arguments=raw_function_args,
                            error=parse_error,
                        )
                        tool_name = function_name or "unknown_tool"
                        with contextlib.suppress(Exception):
                            tool_name = self.get_tool(function_name).name
                        yield self._create_tool_event(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            function_name=function_name,
                            function_args={},
                            status=ToolStatus.CALLED,
                            function_result=parse_result,
                        )
                        tool_responses.append(
                            {
                                "role": "tool",
                                "function_name": function_name,
                                "tool_call_id": tool_call_id,
                                "content": self._serialize_tool_result_for_memory(
                                    parse_result, function_name=function_name
                                ),
                            }
                        )
                        continue

                    tool = self.get_tool(function_name)

                    # Generate event before tool call
                    security_assessment = self._security_assessor.assess_action(function_name, function_args)
                    confirmation_state = "awaiting_confirmation" if security_assessment.requires_confirmation else None
                    if security_assessment.requires_confirmation:
                        yield self._create_tool_event(
                            tool_call_id=tool_call_id,
                            tool_name=tool.name,
                            function_name=function_name,
                            function_args=function_args,
                            status=ToolStatus.CALLING,
                            security_risk=security_assessment.risk_level.value,
                            security_reason=security_assessment.reason,
                            security_suggestions=security_assessment.suggestions,
                            confirmation_state=confirmation_state,
                        )
                        yield WaitEvent(wait_reason="user_input", suggest_user_takeover="none")
                        return
                    # ORPHANED TASK FIX: Check cancellation BEFORE emitting tool event
                    # Prevents tools from starting if SSE disconnect happened
                    await self._cancel_token.check_cancelled()

                    # Emit tool_stream preview so the frontend can show content
                    # in the editor/terminal BEFORE the tool starts executing.
                    raw_args_seq = tool_call["function"].get("arguments", "{}")
                    if is_streamable_function(function_name):
                        partial = extract_partial_content(function_name, raw_args_seq)
                        if partial:
                            yield ToolStreamEvent(
                                tool_call_id=tool_call_id,
                                tool_name=tool.name,
                                function_name=function_name,
                                partial_content=partial,
                                content_type=content_type_for_function(function_name),
                                is_final=True,
                            )

                    yield self._create_tool_event(
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args,
                        status=ToolStatus.CALLING,
                        security_risk=security_assessment.risk_level.value,
                        security_reason=security_assessment.reason,
                        security_suggestions=security_assessment.suggestions,
                        confirmation_state=confirmation_state,
                    )

                    # ORPHANED TASK FIX: Check cancellation BEFORE invoking tool
                    # Prevents execution if cancelled between emit and invoke
                    await self._cancel_token.check_cancelled()

                    # Live shell streaming: poll sandbox for real-time output
                    flags = self._resolve_feature_flags()
                    if flags.get("live_shell_streaming") and function_name == "shell_exec" and hasattr(tool, "sandbox"):
                        from app.domain.services.tools.shell_output_poller import (
                            ShellOutputPoller,
                        )

                        session_id = function_args.get("id", "")
                        poll_interval = flags.get("live_shell_poll_interval_ms", 500)
                        max_polls = flags.get("live_shell_max_polls", 600)
                        poller = ShellOutputPoller(
                            sandbox=tool.sandbox,
                            session_id=session_id,
                            tool_call_id=tool_call_id,
                            tool_name=tool.name,
                            function_name=function_name,
                            poll_interval_ms=int(poll_interval) if poll_interval else 500,
                            max_polls=int(max_polls) if max_polls else 600,
                        )
                        poll_task = asyncio.create_task(poller.start_polling())
                        exec_task = asyncio.create_task(self.invoke_tool(tool, function_name, function_args))
                        try:
                            while not exec_task.done():
                                await asyncio.sleep(0.3)
                                async for ev in poller.drain_events():
                                    yield ev
                            result = exec_task.result()
                        finally:
                            poller.stop()
                            if not poll_task.done():
                                await poll_task
                            # Drain any remaining events
                            async for ev in poller.drain_events():
                                yield ev
                    elif getattr(tool, "supports_progress", False) and hasattr(tool, "drain_progress_events"):
                        # Tools with built-in progress queue (e.g. DealScraperTool)
                        tool._active_tool_call_id = tool_call_id
                        tool._active_function_name = function_name
                        exec_task = asyncio.create_task(self.invoke_tool(tool, function_name, function_args))
                        try:
                            while not exec_task.done():
                                await asyncio.sleep(0.3)
                                async for ev in tool.drain_progress_events():
                                    yield ev
                            result = exec_task.result()
                        finally:
                            # Drain any remaining events after completion
                            async for ev in tool.drain_progress_events():
                                yield ev
                    else:
                        result = await self.invoke_tool(tool, function_name, function_args)

                    # Generate event after tool call (reuse pre-execution security_assessment)
                    yield self._create_tool_event(
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args,
                        status=ToolStatus.CALLED,
                        function_result=result,
                        security_risk=security_assessment.risk_level.value,
                        security_reason=security_assessment.reason,
                        security_suggestions=security_assessment.suggestions,
                        confirmation_state=confirmation_state,
                    )

                    tool_responses.append(
                        {
                            "role": "tool",
                            "function_name": function_name,
                            "tool_call_id": tool_call_id,
                            "content": self._serialize_tool_result_for_memory(result, function_name=function_name),
                        }
                    )

            # Annotate tool results with step time after 50% mark (design 2A)
            if wall_clock_advisory_sent and self._step_start_time is not None:
                _now = time.monotonic()
                _el = _now - self._step_start_time
                _tag = f"\n[Step time: {_el:.0f}s/{wall_limit:.0f}s]"
                for tr in tool_responses:
                    if tr.get("role") == "tool" and isinstance(tr.get("content"), str):
                        tr["content"] += _tag

            # If graceful completion was requested, add a hint to wrap up
            if graceful_completion_requested:
                tool_responses.append(
                    {
                        "role": "system",
                        "content": (
                            "[SYSTEM: Approaching execution limit. Please complete the current task "
                            "and provide a summary of your findings. If the task is not complete, "
                            "summarize what was accomplished and what remains to be done.]"
                        ),
                    }
                )
                graceful_completion_requested = False  # Only inject once

            message = await self.ask_with_messages(tool_responses)
        else:
            # Budget exhausted - provide informative error with context
            logger.error(
                f"Iteration budget exhausted: {iteration_spent:.1f}/{iteration_budget} after processing tool calls"
            )
            yield ErrorEvent(
                error=(
                    f"Task execution limit reached ({int(iteration_spent)} iterations). "
                    "The task was too complex to complete in a single run. "
                    "Consider breaking it into smaller sub-tasks or increasing the iteration limit."
                ),
                error_type="iteration_limit",
                recoverable=True,
                retry_hint="Try breaking your request into smaller, focused tasks.",
            )

        # Re-enforce JSON format after tool-calling loop completes.
        # The while-loop ran without format enforcement (initial_format=None) to
        # avoid empty-response bugs with some LLM providers.  Now that the loop
        # has exited we must verify the response is valid JSON and, if not, make
        # one extra ask_with_messages() call with format="json_object".
        # _final_text captures pre-enforcement content for salvage if re-enforcement fails.
        _final_text = (message.get("content") or "").strip()
        if has_tools and format == "json_object":
            _needs_format_fix = False
            if _final_text:
                try:
                    json.loads(_final_text)
                except (ValueError, TypeError):
                    _needs_format_fix = True
            else:
                _needs_format_fix = True

            if _needs_format_fix:
                logger.info("Re-enforcing JSON format on post-tool-loop response")
                message = await self.ask_with_messages(
                    [
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was not in the required JSON format. "
                                "Restate your response as ONLY a valid JSON object matching the "
                                "expected schema. No prose, no markdown fencing."
                            ),
                        }
                    ],
                    format="json_object",
                )

        final_content = message.get("content")
        if not final_content:
            # Salvage: If the pre-enforcement response was substantial prose
            # (e.g. a report the LLM wrote as raw markdown instead of JSON),
            # wrap it in a success JSON rather than discarding it.
            _stripped = _final_text.lstrip()
            if (
                _final_text
                and len(_final_text) > 200
                and not _stripped.startswith("{")
                and not _stripped.startswith("[")
            ):
                logger.info(
                    "Salvaging %d-char prose response as step result (LLM wrote content instead of JSON)",
                    len(_final_text),
                )
                # Truncate to a summary for the result field; the full text will
                # reach the user via the summarization phase which reads context.
                _salvage_summary = _final_text[:300].split("\n")[0].strip()
                final_content = json.dumps(
                    {
                        "success": True,
                        "result": _salvage_summary,
                        "attachments": [],
                    }
                )
            else:
                logger.warning("Agent produced empty final message — yielding fallback")
                fallback_error = (
                    "Step time limit exceeded. No result produced."
                    if wall_clock_exceeded
                    else "I was unable to produce a complete response. Please try again or rephrase your request."
                )
                final_content = json.dumps(
                    {
                        "success": False,
                        "result": None,
                        "attachments": [],
                        "error": fallback_error,
                    }
                )
        yield MessageEvent(message=final_content)

        # Cleanup background tasks on normal exit (e.g. background memory saves)
        await self.cleanup_background_tasks()

    async def _execute_parallel_tool(
        self,
        semaphore: asyncio.Semaphore,
        tool: BaseTool,
        function_name: str,
        function_args: dict[str, Any],
        tool_call_id: str,
    ) -> ToolResult:
        """Execute a single tool with semaphore limiting concurrent executions"""
        async with semaphore:
            return await self.invoke_tool(tool, function_name, function_args)

    async def _ensure_memory(self):
        """Ensure the agent has initialized memory.

        Retrieves memory from the repository, creating the agent document
        if it doesn't exist (defensive fallback).
        """
        if not self.memory:
            try:
                self.memory = await self._repository.get_memory(self._agent_id, self.name)
            except ValueError as e:
                # Agent document doesn't exist - create it as fallback
                # This should not normally happen as the factory creates the document,
                # but we handle it defensively for robustness
                if "not found" in str(e).lower():
                    logger.warning(f"Agent {self._agent_id} not found in database, creating document defensively")
                    agent_model = Agent(id=self._agent_id)
                    await self._repository.save(agent_model)
                    self.memory = await self._repository.get_memory(self._agent_id, self.name)
                else:
                    raise
            # Apply graduated compaction setting from feature flags
            flags = self._resolve_feature_flags()
            if flags.get("graduated_compaction"):
                self.memory.config.use_graduated_compaction = True

    async def _add_to_memory(self, messages: list[dict[str, Any]]) -> None:
        """Update memory and save to repository"""
        await self._ensure_memory()
        if self.memory.empty:
            self.memory.add_message(
                {
                    "role": "system",
                    "content": self.system_prompt,
                }
            )
        self.memory.add_messages(messages)
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    async def _roll_back_memory(self) -> None:
        await self._ensure_memory()
        self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    def _current_token_usage_ratio(self) -> float:
        """Return current memory token usage ratio against effective limit."""
        if not self.memory:
            return 0.0
        token_count = self._token_manager.count_messages_tokens(self.memory.get_messages())
        effective_limit = max(1, self._token_manager._effective_limit)
        return token_count / effective_limit

    def _resolve_budget_action(self, usage_ratio: float):
        """Resolve token budget action with manager-aware fallback."""
        from app.domain.services.agents.token_budget_manager import BudgetAction

        manager = getattr(self, "_token_budget_manager", None)
        if manager and hasattr(manager, "enforce_budget_policy"):
            return manager.enforce_budget_policy(usage_ratio)

        if usage_ratio >= 0.99:
            return BudgetAction.HARD_STOP_TOOLS
        if usage_ratio >= 0.98:
            return BudgetAction.FORCE_HARD_STOP_NUDGE
        if usage_ratio >= 0.95:
            return BudgetAction.FORCE_CONCLUDE
        if usage_ratio >= 0.90:
            return BudgetAction.REDUCE_VERBOSITY
        return BudgetAction.NORMAL

    async def _inject_budget_notice_if_needed(self, notice: str) -> None:
        """Append a budget notice once to avoid repeated duplicate injections."""
        if not self.memory:
            return
        current_messages = self.memory.get_messages()
        if current_messages:
            last = current_messages[-1]
            if last.get("role") == "user" and last.get("content") == notice:
                return
        await self._add_to_memory([{"role": "user", "content": notice}])

    def _filter_read_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Drop read-only tools, keeping only action-capable tools."""
        if tools is None:
            return None
        filtered = [
            tool
            for tool in tools
            if not self._efficiency_monitor._is_read_tool(tool.get("function", {}).get("name", ""))
        ]
        return filtered or None

    async def ask_with_messages(self, messages: list[dict[str, Any]], format: str | None = None) -> dict[str, Any]:
        await self._add_to_memory(messages)

        # Check and handle token limits before making LLM call
        await self._ensure_within_token_limit()

        # Inject efficiency nudges if any are pending (DeepCode Phase 2: Tool Efficiency Monitor)
        if self._efficiency_nudges:
            # Take the most severe nudge (hard_stop takes priority)
            nudge = max(self._efficiency_nudges, key=lambda n: (n.get("hard_stop", False), n["confidence"]))
            # Always use "user" role — many LLM APIs (e.g. GLM-5) reject mid-conversation system messages
            nudge_message = {
                "role": "user",
                "content": nudge["message"],
            }
            await self._add_to_memory([nudge_message])
            self._efficiency_nudges.clear()

        response_format = None
        if format:
            response_format = {"type": format}

        from app.domain.services.agents.token_budget_manager import BudgetAction

        empty_response_count = 0
        max_empty_responses = 5

        for _retry in range(self.max_retries + max_empty_responses):
            usage_ratio = self._current_token_usage_ratio()
            budget_action = self._resolve_budget_action(usage_ratio)
            available_tools = self.get_available_tools()
            max_tokens_override: int | None = None

            if self._truncation_retry_max_tokens is not None:
                max_tokens_override = self._truncation_retry_max_tokens

            # Force text-only response after repeated truncations to escape
            # the empty-args loop (e.g. GLM-5 hitting output limits).
            if self._recent_truncation_count >= max(1, self.max_consecutive_truncations - 1):
                available_tools = []
                logger.warning(
                    "Forcing text-only response after %d consecutive truncations",
                    self._recent_truncation_count,
                )

            if budget_action == BudgetAction.REDUCE_VERBOSITY:
                llm_default_max = int(getattr(self.llm, "max_tokens", 2048) or 2048)
                reduced_limit = max(512, llm_default_max // 2)
                max_tokens_override = (
                    reduced_limit if max_tokens_override is None else min(max_tokens_override, reduced_limit)
                )
            elif budget_action == BudgetAction.FORCE_CONCLUDE:
                await self._inject_budget_notice_if_needed(self._TOKEN_BUDGET_FORCE_CONCLUDE_MESSAGE)
            elif budget_action == BudgetAction.FORCE_HARD_STOP_NUDGE:
                await self._inject_budget_notice_if_needed(self._TOKEN_BUDGET_FORCE_CONCLUDE_MESSAGE)
                available_tools = self._filter_read_tools(available_tools)
            elif budget_action == BudgetAction.HARD_STOP_TOOLS:
                await self._inject_budget_notice_if_needed(self._TOKEN_BUDGET_HARD_STOP_MESSAGE)
                available_tools = None
                self._active_phase = "summarizing"

            try:
                # Build message list for LLM — inject scratchpad transiently
                llm_messages = self.memory.get_messages()
                if self._scratchpad and not self._scratchpad.is_empty:
                    scratchpad_content = self._scratchpad.get_content()
                    if scratchpad_content:
                        # Insert scratchpad after system messages, before conversation.
                        # Uses "user" role for GLM-5 compatibility.
                        insert_idx = 0
                        for idx, m in enumerate(llm_messages):
                            if m.get("role") == "system":
                                insert_idx = idx + 1
                            else:
                                break
                        llm_messages = list(llm_messages)  # shallow copy to avoid mutating memory
                        llm_messages.insert(
                            insert_idx,
                            {"role": "user", "content": scratchpad_content},
                        )

                message = await self.llm.ask(
                    llm_messages,
                    tools=available_tools,
                    response_format=response_format,
                    tool_choice=self.tool_choice,
                    model=self._step_model_override,  # DeepCode Phase 1: Adaptive model selection
                    max_tokens=max_tokens_override,
                )
            except TokenLimitExceededError as e:
                logger.warning(f"Token limit exceeded, trimming context: {e}")
                await self._handle_token_limit_exceeded()
                continue
            except Exception as e:
                error_context = self._error_handler.classify_error(e)
                if error_context.error_type == ErrorType.TOKEN_LIMIT:
                    await self._handle_token_limit_exceeded()
                    continue
                raise

            # Detect truncated responses via _finish_reason from LLM adapters
            is_truncated = message.get("_finish_reason") == "length" or message.get("_tool_args_truncated", False)

            # Also detect malformed/truncated tool-call arguments heuristically.
            # Some providers return finish_reason="stop" even when tool args are
            # cut off or malformed. Validate args strictly before execution.
            if not is_truncated and message.get("tool_calls"):
                for tc in message.get("tool_calls", []):
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    tool_name = func.get("name", "unknown")
                    raw_args = func.get("arguments", "")

                    try:
                        parsed_args = self._parse_tool_arguments(raw_args, function_name=tool_name)
                    except ValueError as parse_err:
                        logger.warning(
                            "Tool call '%s' has malformed args (%s) — treating as truncation",
                            tool_name,
                            parse_err,
                        )
                        is_truncated = True
                        break

                    if not parsed_args and self._tool_requires_arguments(tool_name):
                        logger.warning(
                            "Tool call '%s' has empty args despite required parameters — treating as truncation",
                            tool_name,
                        )
                        is_truncated = True
                        break

            if is_truncated and message.get("tool_calls"):
                # Truncated tool calls have malformed/empty JSON — drop and retry.
                # Tell the LLM to break content into smaller pieces to avoid
                # hitting the output limit again.
                self._recent_truncation_count += 1
                llm_default_max = int(getattr(self.llm, "max_tokens", 2048) or 2048)
                if self._truncation_retry_max_tokens is None:
                    self._truncation_retry_max_tokens = max(512, llm_default_max // 2)
                else:
                    self._truncation_retry_max_tokens = max(512, self._truncation_retry_max_tokens // 2)
                logger.warning(
                    "LLM response truncated with partial tool_calls (consecutive: %d) — requesting smaller output",
                    self._recent_truncation_count,
                )
                await self._add_to_memory(
                    [
                        {"role": "assistant", "content": message.get("content") or ""},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was cut off due to output length limits, "
                                "so the tool call arguments were lost. "
                                "Please break your work into SMALLER pieces:\n"
                                "- If writing a file, write it in sections using multiple smaller writes\n"
                                "- If the content is long, summarize first then write details separately\n"
                                "- Do NOT try to write the entire content in a single tool call\n"
                                "Continue with a smaller action now."
                            ),
                        },
                    ]
                )
                continue

            if is_truncated and message.get("content"):
                # Text-only truncation: return partial answer with note
                logger.warning("Final answer may be truncated (finish_reason=length)")
                message["content"] = message["content"] + "\n\n[Note: Response may be incomplete due to length limits]"

            filtered_message = {}
            if message.get("role") == "assistant":
                if not message.get("content") and not message.get("tool_calls"):
                    empty_response_count += 1
                    if empty_response_count >= max_empty_responses:
                        logger.error(
                            f"Empty response from LLM after {empty_response_count} attempts, returning fallback"
                        )
                        return {
                            "role": "assistant",
                            "content": (
                                "I encountered difficulties completing this step. "
                                "The information gathered so far has been preserved. "
                                "Please try again or rephrase your request."
                            ),
                        }
                    logger.warning(
                        f"Assistant message has no content ({empty_response_count}/{max_empty_responses}), retry"
                    )
                    await self._add_to_memory(
                        [
                            {"role": "assistant", "content": ""},
                            {"role": "user", "content": "no thinking, please continue"},
                        ]
                    )
                    continue
                filtered_message = {
                    "role": "assistant",
                    "content": message.get("content"),
                }
                if message.get("tool_calls"):
                    tool_calls = message.get("tool_calls", [])
                    # Allow multiple tool calls for safe parallel tools
                    if self._can_parallelize_tools(tool_calls):
                        filtered_message["tool_calls"] = tool_calls[:MAX_CONCURRENT_TOOLS]
                    else:
                        filtered_message["tool_calls"] = tool_calls[:1]
            else:
                logger.warning(f"Unknown message role: {message.get('role')}")
                filtered_message = message

            # Track response for stuck detection (response-level) (Phase 4 P1: with confidence)
            is_response_stuck, confidence = self._stuck_detector.track_response(filtered_message)

            # Also check for action-level stuck patterns
            action_analysis = self._stuck_detector.get_analysis()
            is_action_stuck = action_analysis is not None

            is_stuck = is_response_stuck or is_action_stuck

            # Log stuck detection with confidence
            if is_stuck:
                logger.info(
                    "Stuck detection triggered",
                    extra={
                        "response_stuck": is_response_stuck,
                        "action_stuck": is_action_stuck,
                        "confidence": confidence,
                        "session_id": getattr(self, "_session_id", None),
                    },
                )

            if is_stuck and self._stuck_detector.can_attempt_recovery():
                self._stuck_detector.record_recovery_attempt()

                # Use truncation-specific recovery if the stuck loop was
                # caused by repeated output truncation (e.g., LLM keeps
                # trying to write a large file in one tool call).
                if self._recent_truncation_count >= 2:
                    recovery_prompt = self._stuck_detector.get_truncation_recovery_prompt()
                    logger.warning(
                        "Agent stuck due to output truncation (%d consecutive), injecting split-output prompt",
                        self._recent_truncation_count,
                    )
                elif action_analysis:
                    # Use enhanced guidance if we have action-level analysis
                    recovery_prompt = self._stuck_detector.get_recovery_guidance()
                    logger.warning(
                        f"Agent stuck detected ({action_analysis.loop_type.value}), "
                        f"recovery strategy: {action_analysis.recovery_strategy.value}"
                    )
                else:
                    recovery_prompt = self._stuck_detector.get_recovery_prompt()
                    logger.warning("Agent stuck detected (response-level), injecting recovery prompt")

                await self._add_to_memory([filtered_message, {"role": "user", "content": recovery_prompt}])
                continue

            # If stuck but recovery exhausted, set flag for caller (e.g., plan_act step execution)
            if is_stuck and not self._stuck_detector.can_attempt_recovery():
                self._stuck_recovery_exhausted = True
                logger.warning("Stuck recovery exhausted — signaling caller to force-advance step")

            await self._add_to_memory([filtered_message])
            empty_response_count = 0  # Reset on successful non-empty response
            self._recent_truncation_count = 0  # Reset truncation counter on success
            self._truncation_retry_max_tokens = None
            return filtered_message

        # Retry loop exhausted — return graceful fallback instead of crashing
        logger.error("LLM retry loop exhausted, returning fallback response")
        return {
            "role": "assistant",
            "content": (
                "I encountered difficulties completing this step. "
                "The information gathered so far has been preserved. "
                "Please try again or rephrase your request."
            ),
        }

    async def _ensure_within_token_limit(self) -> None:
        """Ensure memory is within token limits, trim if necessary.

        When feature_token_budget_manager is enabled and a TokenBudget is set,
        uses budget-aware sliding window compression. Otherwise falls back to
        the legacy two-stage strategy (proactive compaction + hard trim).
        """
        await self._ensure_memory()
        if self._compression_guard_active:
            # Guard already tripped for this step; avoid repeated compression loops.
            return
        current_messages = self.memory.get_messages()

        # ── Budget-aware path (Phase 2) ──────────────────────────────
        flags = self._resolve_feature_flags()
        if (
            flags.get("token_budget_manager")
            and self._token_budget is not None
            and self._token_budget_manager is not None
        ):
            from app.domain.services.agents.token_budget_manager import BudgetPhase

            phase = self._active_phase or "execution"
            budget_phase_map = {
                "planning": BudgetPhase.PLANNING,
                "executing": BudgetPhase.EXECUTION,
                "verifying": BudgetPhase.EXECUTION,
                "summarizing": BudgetPhase.SUMMARIZATION,
            }
            budget_phase = budget_phase_map.get(phase, BudgetPhase.EXECUTION)

            ok, reason = self._token_budget_manager.check_before_call(
                self._token_budget,
                budget_phase,
                current_messages,
            )
            if not ok:
                self._compression_cycles_this_step += 1
                if self._compression_cycles_this_step > self.max_compression_cycles_per_step:
                    self._trip_compression_guard(
                        stage_label="budget-aware",
                        current_messages=current_messages,
                    )
                    return
                logger.info("Token budget exceeded (%s), compressing to fit", reason)
                compressed = self._token_budget_manager.compress_to_fit(
                    self._token_budget,
                    budget_phase,
                    current_messages,
                )
                self.memory.messages = compressed
            return

        # ── Legacy path (reactive two-stage) ─────────────────────────
        # Stage 1: Proactive compaction before hitting the hard limit.
        # Uses configurable context_compression_trigger_pct (default 0.80) for
        # earlier triggering. Falls back to TokenManager early_warning (0.60).
        token_count = self._token_manager.count_messages_tokens(current_messages)
        try:
            from app.core.config import get_settings

            trigger_threshold = getattr(get_settings(), "context_compression_trigger_pct", 0.80)
        except Exception:
            trigger_threshold = self._token_manager.PRESSURE_THRESHOLDS["early_warning"]
        if token_count > self._token_manager._effective_limit * trigger_threshold:
            self._compression_cycles_this_step += 1
            if self._compression_cycles_this_step > self.max_compression_cycles_per_step:
                self._trip_compression_guard(
                    stage_label="legacy-stage-1",
                    current_messages=current_messages,
                )
                return
            # Use graduated compaction when enabled (preserves more info)
            flags = self._resolve_feature_flags()
            if flags.get("graduated_compaction") and self.memory.config.use_graduated_compaction:
                self.memory.graduated_compact()
            else:
                self.memory.smart_compact()
            current_messages = self.memory.get_messages()
            logger.debug(
                f"Proactive context compaction at {token_count} tokens "
                f"({token_count / self._token_manager._effective_limit:.0%} utilization)"
            )

        # Stage 2: Hard-limit trim if still over after compaction.
        if not self._token_manager.is_within_limit(current_messages):
            self._compression_cycles_this_step += 1
            if self._compression_cycles_this_step > self.max_compression_cycles_per_step:
                self._trip_compression_guard(
                    stage_label="legacy-stage-2",
                    current_messages=current_messages,
                )
                return
            logger.warning("Memory exceeds token limit, trimming...")
            # Capture the first user message before trimming — it contains the original
            # request and must survive trimming to prevent topic drift / hallucination.
            first_user_msg = next((m for m in current_messages if m.get("role") == "user"), None)
            trimmed_messages, tokens_removed = self._token_manager.trim_messages(
                current_messages, preserve_system=True, preserve_recent=6
            )
            # Re-inject first user message if it was lost during trimming
            if first_user_msg and not any(m is first_user_msg for m in trimmed_messages):
                # Insert after system messages, before the remaining conversation
                insert_idx = 0
                for i, m in enumerate(trimmed_messages):
                    if m.get("role") == "system":
                        insert_idx = i + 1
                    else:
                        break
                trimmed_messages.insert(insert_idx, first_user_msg)
                logger.info("Re-injected first user message after trimming to preserve topic anchor")
            self.memory.messages = trimmed_messages
            await self._repository.save_memory(self._agent_id, self.name, self.memory)
            logger.info(f"Trimmed memory, removed {tokens_removed} tokens")

        # Stage 3: Structured compaction (emergency LLM summary) when still over limit.
        current_messages = self.memory.get_messages()
        if not self._token_manager.is_within_limit(current_messages):
            flags_s3 = self._resolve_feature_flags()
            if flags_s3.get("structured_compaction"):
                self._compression_cycles_this_step += 1
                if self._compression_cycles_this_step <= self.max_compression_cycles_per_step:
                    from app.domain.services.agents.memory_manager import get_memory_manager

                    mm = get_memory_manager()
                    compacted_msgs, tokens_saved = await mm.structured_compact(
                        current_messages, self.llm, preserve_recent=6
                    )
                    if tokens_saved > 0:
                        self.memory.messages = compacted_msgs
                        await self._repository.save_memory(self._agent_id, self.name, self.memory)
                        logger.info("Structured compaction saved ~%d tokens", tokens_saved)

    async def _handle_token_limit_exceeded(self) -> None:
        """Handle token limit exceeded error by aggressively trimming context.

        Memory compaction and trimming are done synchronously (fast, in-memory),
        but the MongoDB save is done in the background to avoid blocking the retry loop.
        """
        await self._ensure_memory()

        # First compact verbose tool results (fast, in-memory)
        self.memory.smart_compact()

        # Then trim messages (fast, in-memory)
        all_messages = self.memory.get_messages()
        # Capture the first user message before trimming for topic preservation
        first_user_msg = next((m for m in all_messages if m.get("role") == "user"), None)
        trimmed_messages, tokens_removed = self._token_manager.trim_messages(
            all_messages,
            preserve_system=True,
            preserve_recent=4,  # More aggressive trim
        )
        # Re-inject first user message if lost during aggressive trimming
        if first_user_msg and not any(m is first_user_msg for m in trimmed_messages):
            insert_idx = 0
            for i, m in enumerate(trimmed_messages):
                if m.get("role") == "system":
                    insert_idx = i + 1
                else:
                    break
            trimmed_messages.insert(insert_idx, first_user_msg)
            logger.info("Re-injected first user message after aggressive trim to preserve topic anchor")
        self.memory.messages = trimmed_messages

        # Save to MongoDB in background (non-blocking) to avoid delaying retry
        # Snapshot messages to avoid race with main loop mutating self.memory
        from app.domain.models.memory import Memory

        memory_snapshot = Memory(messages=list(self.memory.messages))

        async def _save_background():
            try:
                await self._repository.save_memory(self._agent_id, self.name, memory_snapshot)
                logger.debug("Background memory save completed after token limit handling")
            except Exception as e:
                logger.warning(f"Background memory save failed after token limit handling: {e}")

        task = asyncio.create_task(_save_background())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        logger.info(f"Handled token limit by trimming {tokens_removed} tokens (save in background)")

    async def cleanup_background_tasks(self, timeout: float = 5.0) -> None:  # noqa: ASYNC109
        """Await pending background tasks with timeout, cancel remaining, and clear the set."""
        if not self._background_tasks:
            return

        pending = list(self._background_tasks)
        logger.debug(f"Cleaning up {len(pending)} background tasks")

        _done, not_done = await asyncio.wait(pending, timeout=timeout)
        for task in not_done:
            task.cancel()
        if not_done:
            logger.warning(f"Cancelled {len(not_done)} background tasks that did not complete within {timeout}s")

        self._background_tasks.clear()

    async def ask(self, request: str, format: str | None = None) -> dict[str, Any]:
        return await self.ask_with_messages([{"role": "user", "content": request}], format)

    async def roll_back(self, message: Message):
        await self._ensure_memory()
        last_message = self.memory.get_last_message()
        if not last_message or not last_message.get("tool_calls") or len(last_message.get("tool_calls")) == 0:
            return
        tool_call = last_message.get("tool_calls")[0]
        function_name = tool_call.get("function", {}).get("name")
        tool_call_id = tool_call.get("id")
        if function_name == "message_ask_user":
            self.memory.add_message(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "function_name": function_name,
                    "content": message.model_dump_json(),
                }
            )
        else:
            self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    async def compact_memory(self) -> None:
        await self._ensure_memory()
        self.memory.compact()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    def configure_security(
        self,
        autonomy_level: str = "autonomous",
        allow_credential_access: bool = False,
        allow_destructive_operations: bool = False,
        blocked_patterns: list[str] | None = None,
    ) -> None:
        """Configure the security assessor for this agent.

        Args:
            autonomy_level: One of "supervised", "guided", "autonomous", "unrestricted"
            allow_credential_access: Whether to allow credential-related operations
            allow_destructive_operations: Whether to allow destructive operations
            blocked_patterns: Additional regex patterns to block
        """
        self._security_assessor = SecurityAssessor(
            autonomy_level=autonomy_level,
            allow_credential_access=allow_credential_access,
            allow_destructive_operations=allow_destructive_operations,
            custom_blocked_patterns=blocked_patterns or [],
        )
        logger.info(
            f"Security configured: level={autonomy_level}, "
            f"credentials={allow_credential_access}, destructive={allow_destructive_operations}"
        )

    def get_reliability_stats(self) -> dict[str, Any]:
        """Get comprehensive reliability statistics.

        Returns:
            Dictionary with stuck detection, security, and tool stats
        """
        return {
            "stuck_detector": self._stuck_detector.get_stats(),
            "security": self._security_assessor.get_risk_summary(),
            "hallucination_detector": {
                "available_tools": len(self._hallucination_detector.available_tools),
            },
        }

    def is_stuck_recovery_exhausted(self) -> bool:
        """Check if stuck recovery was exhausted during the last execution.

        Returns True once and resets the flag, allowing callers to take
        remedial action (e.g., force-fail the current step and advance).
        """
        if self._stuck_recovery_exhausted:
            self._stuck_recovery_exhausted = False
            return True
        return False

    def reset_reliability_state(self) -> None:
        """Reset all reliability tracking state.

        Call this when starting a new task or session.
        """
        self._stuck_detector.reset()
        self._stuck_recovery_exhausted = False
        self._recent_truncation_count = 0
        self._truncation_retry_max_tokens = None

        # Reset per-step stability counters
        self._hallucination_count_this_step = 0
        self._compression_cycles_this_step = 0
        self._compression_guard_active = False
        self._step_start_time = None

        # Reset per-agent efficiency monitor
        self._efficiency_monitor.reset()
        self._efficiency_nudges.clear()

        logger.debug("Reliability state reset")

    def _trip_compression_guard(self, stage_label: str, current_messages: list[dict[str, Any]]) -> None:
        """Latch compression guard and apply one-shot emergency trim.

        This prevents repeated compaction churn within the same step while still
        preserving a minimal anchored context for graceful completion.
        """
        if self._compression_guard_active:
            return
        self._compression_guard_active = True
        self._stuck_recovery_exhausted = True
        logger.warning(
            "Compression oscillation guard triggered (%d/%d cycles this step, %s). "
            "Applying emergency context trim and skipping further compression this step.",
            self._compression_cycles_this_step,
            self.max_compression_cycles_per_step,
            stage_label,
        )

        first_user_msg = next((m for m in current_messages if m.get("role") == "user"), None)
        trimmed_messages, _tokens_removed = self._token_manager.trim_messages(
            current_messages,
            preserve_system=True,
            preserve_recent=2,
        )
        if first_user_msg and not any(m is first_user_msg for m in trimmed_messages):
            insert_idx = 0
            for i, msg in enumerate(trimmed_messages):
                if msg.get("role") == "system":
                    insert_idx = i + 1
                else:
                    break
            trimmed_messages.insert(insert_idx, first_user_msg)
        self.memory.messages = trimmed_messages

    async def ask_streaming(self, request: str, format: str | None = None) -> AsyncGenerator[BaseEvent, None]:
        """Execute a request with streaming LLM response.

        Yields StreamEvents as content chunks arrive, then MessageEvent for full response.
        Falls back to non-streaming if LLM doesn't support streaming.

        Args:
            request: The user request
            format: Optional response format

        Yields:
            StreamEvent for each content chunk, then MessageEvent with full content
        """
        # Add request to memory
        await self._add_to_memory([{"role": "user", "content": request}])
        await self._ensure_within_token_limit()

        # Inject efficiency nudges if any are pending (DeepCode Phase 2: Tool Efficiency Monitor)
        if self._efficiency_nudges:
            nudge = max(self._efficiency_nudges, key=lambda n: (n.get("hard_stop", False), n["confidence"]))
            # Always use "user" role — many LLM APIs (e.g. GLM-5) reject mid-conversation system messages
            nudge_message = {
                "role": "user",
                "content": nudge["message"],
            }
            await self._add_to_memory([nudge_message])
            self._efficiency_nudges.clear()

        # Check if LLM supports streaming
        if not hasattr(self.llm, "ask_stream"):
            # Fall back to non-streaming — use ask_with_messages([]) since
            # user message was already added to memory above
            response = await self.ask_with_messages([], format)
            yield MessageEvent(message=response.get("content", ""))
            return

        response_format = {"type": format} if format else None
        full_content = ""

        try:
            async for chunk in self.llm.ask_stream(
                self.memory.get_messages(),
                tools=None,  # Streaming typically used without tools
                response_format=response_format,
            ):
                full_content += chunk
                yield StreamEvent(content=chunk, is_final=False)

            # Yield final stream event and message
            yield StreamEvent(content="", is_final=True)

            # Save response to memory
            await self._add_to_memory([{"role": "assistant", "content": full_content}])

            yield MessageEvent(message=full_content)

        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            # Fall back to non-streaming on error
            response = await self.ask_with_messages([], format)
            yield MessageEvent(message=response.get("content", ""))
