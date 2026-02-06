import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import get_feature_flags
from app.domain.external.llm import LLM
from app.domain.models.agent import Agent
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    MessageEvent,
    SearchToolContent,
    StreamEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.message import Message
from app.domain.models.search import SearchResultItem
from app.domain.models.state_manifest import StateEntry, StateManifest
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.error_handler import ErrorHandler, ErrorType, TokenLimitExceededError
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.security_assessor import ActionSecurityRisk, SecurityAssessor
from app.domain.services.agents.stuck_detector import StuckDetector
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
    "search",  # Fast text-only fetch (renamed from browser_get_content)
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

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        json_parser: JsonParser,
        tools: list[BaseTool] | None = None,
        state_manifest: StateManifest | None = None,
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

        # Context manager for Manus-style attention manipulation (optional)
        self.context_manager: SandboxContextManager | None = None

        # State manifest for blackboard architecture (optional)
        self.state_manifest: StateManifest | None = state_manifest

    def get_available_tools(self) -> list[dict[str, Any]] | None:
        """Get all available tools list"""
        available_tools = []
        for tool in self.tools:
            available_tools.extend(tool.get_tools())
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
            raise ValueError(correction)

        raise ValueError(f"Unknown tool: {function_name}")

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

        Implements Manus-style attention manipulation to prevent
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
            raise ValueError("No state manifest configured for this agent")

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
        except Exception:
            pass  # Non-critical, don't fail on recording errors

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

        # Populate tool_content for search tools (Manus-style search results display)
        tool_content = kwargs.pop("tool_content", None)
        if tool_content is None and status == ToolStatus.CALLED and function_name == "info_search_web":
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
                # Handle SearchResults object
                if hasattr(data, "results") and data.results:
                    results_list = [
                        SearchResultItem(
                            title=r.title or "No title",
                            link=r.link or "",
                            snippet=r.snippet or "",
                        )
                        for r in data.results[:5]
                    ]
                    tool_content = SearchToolContent(results=results_list)

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
        flags = get_feature_flags()
        if flags.get("tool_tracing"):
            tool_tracer = get_tool_tracer()
        start_time = time.perf_counter()

        # Log tool invocation with parameter preview
        logger.info(
            "Tool invocation started",
            extra={
                "function_name": function_name,
                "tool_name": tool.name,
                "argument_keys": list(arguments.keys()),
                "argument_preview": self._truncate_args_for_logging(arguments, max_len=100),
                "session_id": getattr(self, "_session_id", None),
                "agent_id": getattr(self, "_agent_id", None),
            },
        )

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
                logger.warning(f"Security blocked tool '{function_name}': {security_assessment.reason}")
                return ToolResult(success=False, message=f"Action blocked for security: {security_assessment.reason}")

            if security_assessment.risk_level == ActionSecurityRisk.HIGH:
                logger.info(f"High-risk tool call: {function_name} - {security_assessment.reason}")

        retries = 0
        current_interval = self.retry_interval
        last_error = ""
        result: ToolResult | None = None

        while retries <= self.max_retries:
            try:
                result = await tool.invoke_function(function_name, **arguments)

                # Record successful execution with profiler
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

                # Record for dynamic toolset prioritization
                self._record_tool_usage(
                    function_name, success=result.success if result else False, duration_ms=duration_ms
                )

                # Track tool action for stuck detection
                result_preview = str(result.message)[:500] if result else ""
                self._stuck_detector.track_tool_action(
                    tool_name=function_name,
                    tool_args=arguments,
                    success=result.success if result else False,
                    result=result_preview,
                    error=result.message if result and not result.success else None,
                )

                # Record action for reflection context (best-effort)
                try:
                    from app.domain.services.agents.task_state_manager import get_task_state_manager

                    task_state_manager = getattr(self, "_task_state_manager", None) or get_task_state_manager()
                    task_state_manager.record_action(
                        function_name=function_name,
                        success=result.success if result else False,
                        result=result.data
                        if result and result.data is not None
                        else result.message
                        if result
                        else None,
                        error=result.message if result and not result.success else None,
                    )
                except Exception:
                    pass

                return result
            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(current_interval)
                    current_interval *= self.retry_backoff  # Exponential backoff
                else:
                    logger.exception(f"Tool execution failed, {function_name}, {arguments}")
                    break

        # Record failed execution with profiler
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

        # Track failed action for stuck detection
        self._stuck_detector.track_tool_action(
            tool_name=function_name,
            tool_args=arguments,
            success=False,
            error=last_error[:200],
        )

        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            task_state_manager = getattr(self, "_task_state_manager", None) or get_task_state_manager()
            task_state_manager.record_action(
                function_name=function_name,
                success=False,
                result=None,
                error=last_error[:200],
            )
        except Exception:
            pass

        return ToolResult(success=False, message=last_error)

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

    def _can_parallelize_tools(self, tool_calls: list[dict]) -> bool:
        """Check if all tool calls in the list can be executed in parallel.

        Supports both explicit tool whitelist and MCP read-only patterns.
        """
        if len(tool_calls) <= 1:
            return False

        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")

            # Check explicit whitelist first
            if tool_name in SAFE_PARALLEL_TOOLS:
                continue

            # Check MCP read-only prefixes (dynamic tools from MCP servers)
            if any(
                tool_name.startswith(prefix) or f"_{prefix.split('_')[-1]}" in tool_name for prefix in SAFE_MCP_PREFIXES
            ):
                continue

            # Tool not in safe list
            return False

        return True

    async def _invoke_tool_with_semaphore(
        self, semaphore: asyncio.Semaphore, tool_call: dict, function_args: dict[str, Any]
    ) -> tuple[dict, BaseTool, ToolResult]:
        """Invoke a single tool with semaphore limiting concurrent executions"""
        async with semaphore:
            function_name = tool_call["function"]["name"]
            tool = self.get_tool(function_name)
            result = await self.invoke_tool(tool, function_name, function_args)
            return tool_call, tool, result

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
        return any(pattern in name_lower for pattern in read_only_patterns)

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
        warning_emitted = False
        graceful_completion_requested = False

        while iteration_spent < iteration_budget:
            if not message.get("tool_calls"):
                break

            tool_calls = message["tool_calls"]
            tool_responses = []

            # Calculate iteration cost for this cycle
            iteration_cost = self._calculate_iteration_cost(tool_calls)
            iteration_spent += iteration_cost

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
                    tool_call_id = tool_call["id"] or str(uuid.uuid4())
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
                        yield WaitEvent()
                        return

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

                # Process results and emit CALLED events
                for (tool_call, tool_call_id, function_args, tool, security_assessment), result in zip(
                    parsed_calls, results, strict=False
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
                            "content": result.model_dump_json() if hasattr(result, "model_dump_json") else str(result),
                        }
                    )
            else:
                # Sequential execution for non-parallelizable tools (original behavior)
                for tool_call in tool_calls:
                    if not tool_call.get("function"):
                        continue

                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"] or str(uuid.uuid4())
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
                        yield WaitEvent()
                        return
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

                    result = await self.invoke_tool(tool, function_name, function_args)

                    security_assessment = self._security_assessor.assess_action(function_name, function_args)
                    confirmation_state = "awaiting_confirmation" if security_assessment.requires_confirmation else None

                    # Generate event after tool call
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
                            "content": result.model_dump_json(),
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
                )
            )

        yield MessageEvent(message=message["content"])

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

        response_format = None
        if format:
            response_format = {"type": format}

        for _retry in range(self.max_retries):
            try:
                message = await self.llm.ask(
                    self.memory.get_messages(),
                    tools=self.get_available_tools(),
                    response_format=response_format,
                    tool_choice=self.tool_choice,
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

            filtered_message = {}
            if message.get("role") == "assistant":
                if not message.get("content") and not message.get("tool_calls"):
                    logger.warning("Assistant message has no content, retry")
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

            await self._add_to_memory([filtered_message])
            return filtered_message
        raise Exception(f"Empty response from LLM after {self.max_retries} retries")

    async def _ensure_within_token_limit(self) -> None:
        """Ensure memory is within token limits, trim if necessary"""
        await self._ensure_memory()
        current_messages = self.memory.get_messages()

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
        async def _save_background():
            try:
                await self._repository.save_memory(self._agent_id, self.name, self.memory)
                logger.debug("Background memory save completed after token limit handling")
            except Exception as e:
                logger.warning(f"Background memory save failed after token limit handling: {e}")

        task = asyncio.create_task(_save_background())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        logger.info(f"Handled token limit by trimming {tokens_removed} tokens (save in background)")

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

    def reset_reliability_state(self) -> None:
        """Reset all reliability tracking state.

        Call this when starting a new task or session.
        """
        self._stuck_detector.reset()
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

        # Check if LLM supports streaming
        if not hasattr(self.llm, "ask_stream"):
            # Fall back to non-streaming
            response = await self.ask(request, format)
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
