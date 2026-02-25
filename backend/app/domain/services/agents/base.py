import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, ClassVar

from app.domain.exceptions.base import AgentConfigurationException, ToolNotFoundException
from app.domain.external.llm import LLM
from app.domain.external.logging import get_agent_logger
from app.domain.models.agent import Agent
from app.domain.models.event import (
    BaseEvent,
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
    from app.domain.utils.cancellation import CancellationToken
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
SAFE_PARALLEL_TOOLS = {
    # Search operations - excluded to run sequentially for better context
    # "info_search_web",  # Run searches one-by-one so agent can react to each result
    # File read operations
    "file_read",
    "file_search",
    "file_list_directory",
    # Browser read operations
    # "search" removed — now navigates browser for live preview, must be sequential
    "browser_view",
    # Code executor read-only operations
    "code_list_artifacts",
    "code_read_artifact",
    # MCP read-only tools (pattern matching)
    "mcp_list_resources",
    "mcp_read_resource",
    "mcp_server_status",
}

# MCP tool prefixes that are safe for parallel execution (read-only patterns)
SAFE_MCP_PREFIXES = {"mcp_get_", "mcp_list_", "mcp_search_", "mcp_read_", "mcp_fetch_"}

# Maximum number of concurrent tool executions (increased for better throughput)
MAX_CONCURRENT_TOOLS = 5


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
    tool_choice: str | None = None

    # Iteration budget management
    iteration_warning_threshold: float = 0.8  # Warn at 80% of limit
    read_only_iteration_weight: float = 0.3  # Read-only ops count as 30% (reduced from 50%)
    max_step_iterations: int = 50  # Max iterations for a single step before auto-failing

    # Phase-based tool filtering: keeps active tool count <20 per phase
    # to reduce hallucination (OpenAI guidance: accuracy drops above ~20 tools)
    PHASE_TOOL_GROUPS: ClassVar[dict[str, set[str] | None]] = {
        "planning": {
            "file_read",
            "file_list",
            "file_list_directory",
            "file_search",
            "file_find",
            "info_search_web",
            "wide_research",
            "browser_navigate",
            "browser_view",
            "browser_get_content",
            "workspace_info",
            "workspace_tree",
            "shell_exec",
            "shell_view",
            "message_ask_user",
            "message_notify_user",
            "code_list_artifacts",
            "code_read_artifact",
        },
        "executing": None,  # None = all tools available
        "verifying": {
            "file_read",
            "file_list",
            "file_list_directory",
            "file_search",
            "shell_exec",
            "shell_view",
            "browser_navigate",
            "browser_view",
            "browser_get_content",
            "test_run",
            "test_list",
            "code_execute",
            "code_list_artifacts",
            "code_read_artifact",
            "message_ask_user",
        },
    }

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

        # Context manager for Pythinker-style attention manipulation (optional)
        self.context_manager: SandboxContextManager | None = None

        # State manifest for blackboard architecture (optional)
        self.state_manifest: StateManifest | None = state_manifest

        # Flag set when stuck recovery is exhausted — signals callers to force-advance
        self._stuck_recovery_exhausted: bool = False

    def _resolve_feature_flags(self) -> dict[str, bool]:
        """Return injected feature flags, falling back to core config."""
        if self._feature_flags is not None:
            return self._feature_flags
        from app.core.config import get_feature_flags

        return get_feature_flags()

    # Tool result compaction limits for memory writes
    _TOOL_RESULT_MEMORY_MAX_CHARS: ClassVar[int] = 12000
    _TOOL_RESULT_MESSAGE_PREVIEW_CHARS: ClassVar[int] = 2000
    _TOOL_RESULT_DATA_PREVIEW_CHARS: ClassVar[int] = 7000

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

        # Block search tools when efficiency monitor signals hard stop (analysis paralysis)
        # Guard with hasattr: get_available_tools() is called during __init__ before _efficiency_monitor is set
        if (
            hasattr(self, "_efficiency_monitor")
            and self._efficiency_monitor._consecutive_reads >= self._efficiency_monitor.strong_threshold
        ):
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
        search_functions = {"info_search_web", "web_search", "wide_research", "search"}
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
                        for r in data.results[:5]
                    ]
                # Handle wide_research dict with "sources" key
                elif isinstance(data, dict) and data.get("sources"):
                    results_list = [
                        SearchResultItem(
                            title=s.get("title", "No title"),
                            link=s.get("url", s.get("link", "")),
                            snippet=s.get("snippet", ""),
                        )
                        for s in data["sources"][:5]
                    ]

                if results_list:
                    tool_content = SearchToolContent(results=results_list)
                    logger.info(f"SearchToolContent created with {len(results_list)} results for {function_name}")

        return ToolEvent(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
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
                            timeout=120.0,
                        )
                        try:
                            _tool_span.set_attribute("tool.success", result.success)
                            _tool_span.set_attribute(
                                "tool.result_size", len(str(result.message or ""))
                            )
                        except Exception as _span_err:
                            logger.debug("Tool span attribute set failed (non-critical): %s", _span_err)
                else:
                    result = await asyncio.wait_for(
                        tool.invoke_function(function_name, **arguments),
                        timeout=120.0,
                    )
            except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                raise
            except TimeoutError:
                last_error = "Tool execution timed out after 120s"
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

    def _serialize_tool_result_for_memory(self, result: ToolResult) -> str:
        """Serialize tool results with size guardrails to avoid memory bloat."""
        raw = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
        if len(raw) <= self._TOOL_RESULT_MEMORY_MAX_CHARS:
            return raw

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

            # Check MCP read-only prefixes (dynamic tools from MCP servers)
            if any(
                tool_name.startswith(prefix) or f"_{prefix.split('_')[-1]}" in tool_name for prefix in SAFE_MCP_PREFIXES
            ):
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

        while iteration_spent < iteration_budget:
            if not message.get("tool_calls"):
                break

            tool_calls = message["tool_calls"]
            tool_responses = []

            # Check for hallucination loop escalation
            if self._hallucination_detector.should_inject_correction_prompt():
                correction = self._hallucination_detector.get_correction_prompt()
                logger.warning(
                    f"Hallucination loop detected ({self._hallucination_detector.hallucination_count} consecutive), "
                    f"injecting correction prompt"
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

            # Check if we can execute tools in parallel
            if self._can_parallelize_tools(tool_calls):
                # Parse all arguments first
                parsed_calls = []
                for tool_call in tool_calls[:MAX_CONCURRENT_TOOLS]:  # Limit parallel calls
                    if not tool_call.get("function"):
                        continue
                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call.get("id") or str(uuid.uuid4())
                    function_args = await self.json_parser.parse(tool_call["function"]["arguments"])
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
                            "content": self._serialize_tool_result_for_memory(result),
                        }
                    )
            else:
                # Sequential execution for non-parallelizable tools (original behavior)
                for tool_call in tool_calls:
                    if not tool_call.get("function"):
                        continue

                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call.get("id") or str(uuid.uuid4())
                    function_args = await self.json_parser.parse(tool_call["function"]["arguments"])

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
                            "content": self._serialize_tool_result_for_memory(result),
                        }
                    )

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

        final_content = message.get("content")
        if not final_content:
            logger.warning("Agent produced empty final message — yielding fallback")
            final_content = "I was unable to produce a complete response. Please try again or rephrase your request."
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

        empty_response_count = 0
        max_empty_responses = 5

        for _retry in range(self.max_retries + max_empty_responses):
            try:
                message = await self.llm.ask(
                    self.memory.get_messages(),
                    tools=self.get_available_tools(),
                    response_format=response_format,
                    tool_choice=self.tool_choice,
                    model=self._step_model_override,  # DeepCode Phase 1: Adaptive model selection
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
            is_truncated = message.get("_finish_reason") == "length"

            if is_truncated and message.get("tool_calls"):
                # Truncated tool calls likely have malformed JSON — drop and retry
                logger.error("LLM response truncated with partial tool_calls — dropping and requesting continuation")
                await self._add_to_memory(
                    [
                        {"role": "assistant", "content": message.get("content") or ""},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was cut off due to length limits. "
                                "Please continue from where you stopped. Do not use tools — "
                                "provide your answer as text."
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

                # Use enhanced guidance if we have action-level analysis
                if action_analysis:
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

        Uses a two-stage strategy:
        1. Proactive compaction at 60% utilization (collapses verbose tool outputs in-place,
           preserving conversation history without discarding any turns).
        2. Hard-limit trim only if still over after compaction (discards oldest turns).
        """
        await self._ensure_memory()
        current_messages = self.memory.get_messages()

        # Stage 1: Proactive compaction before hitting the hard limit.
        # PRESSURE_THRESHOLDS["early_warning"] = 0.60 (defined in TokenManager).
        token_count = self._token_manager.count_messages_tokens(current_messages)
        early_threshold = self._token_manager.PRESSURE_THRESHOLDS["early_warning"]
        if token_count > self._token_manager._effective_limit * early_threshold:
            self.memory.smart_compact()
            current_messages = self.memory.get_messages()
            logger.debug(
                f"Proactive context compaction at {token_count} tokens "
                f"({token_count / self._token_manager._effective_limit:.0%} utilization)"
            )

        # Stage 2: Hard-limit trim if still over after compaction.
        if not self._token_manager.is_within_limit(current_messages):
            logger.warning("Memory exceeds token limit, trimming...")
            trimmed_messages, tokens_removed = self._token_manager.trim_messages(
                current_messages, preserve_system=True, preserve_recent=6
            )
            self.memory.messages = trimmed_messages
            await self._repository.save_memory(self._agent_id, self.name, self.memory)
            logger.info(f"Trimmed memory, removed {tokens_removed} tokens")

    async def _handle_token_limit_exceeded(self) -> None:
        """Handle token limit exceeded error by aggressively trimming context.

        Memory compaction and trimming are done synchronously (fast, in-memory),
        but the MongoDB save is done in the background to avoid blocking the retry loop.
        """
        await self._ensure_memory()

        # First compact verbose tool results (fast, in-memory)
        self.memory.smart_compact()

        # Then trim messages (fast, in-memory)
        trimmed_messages, tokens_removed = self._token_manager.trim_messages(
            self.memory.get_messages(),
            preserve_system=True,
            preserve_recent=4,  # More aggressive trim
        )
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

        # Reset per-agent efficiency monitor
        self._efficiency_monitor.reset()
        self._efficiency_nudges.clear()

        logger.debug("Reliability state reset")

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
