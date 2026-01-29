import logging
import asyncio
import uuid
from abc import ABC
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from app.domain.external.llm import LLM
from app.domain.models.agent import Agent
from app.domain.models.message import Message
from app.domain.services.tools.base import BaseTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.event import (
    BaseEvent,
    ToolEvent,
    ToolStatus,
    ErrorEvent,
    MessageEvent,
    StreamEvent,
    WaitEvent,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser
from app.domain.services.agents.stuck_detector import StuckDetector, LoopType, RecoveryStrategy
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.agents.error_handler import ErrorHandler, TokenLimitExceeded, ErrorType
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.security_assessor import SecurityAssessor, ActionSecurityRisk
from app.domain.services.tools.tool_profiler import get_tool_profiler
from app.domain.services.tools.dynamic_toolset import (
    DynamicToolsetManager,
    get_toolset_manager,
    ToolsetConfig
)
from app.domain.services.tools.command_formatter import CommandFormatter

logger = logging.getLogger(__name__)

# Tools that are safe to execute in parallel (read-only, no side effects)
SAFE_PARALLEL_TOOLS = {
    # Search operations
    "info_search_web",
    # File read operations
    "file_read",
    "file_search",
    "file_list_directory",
    # Browser read operations
    "browser_get_content",  # Fast text-only fetch
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
class BaseAgent(ABC):
    """
    Base agent class, defining the basic behavior of the agent
    """

    name: str = ""
    system_prompt: str = ""
    format: Optional[str] = None
    max_iterations: int = 200  # Increased for complex tasks
    max_retries: int = 3
    retry_interval: float = 0.3  # Faster retry with exponential backoff
    retry_backoff: float = 1.5  # Backoff multiplier (0.3s -> 0.45s -> 0.67s)
    tool_choice: Optional[str] = None

    # Iteration budget management
    iteration_warning_threshold: float = 0.8  # Warn at 80% of limit
    read_only_iteration_weight: float = 0.5  # Read-only ops count as half

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        json_parser: JsonParser,
        tools: List[BaseTool] = []
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self.llm = llm
        self.json_parser = json_parser
        self.tools = tools
        self.memory = None

        # Initialize reliability components
        self._stuck_detector = StuckDetector(window_size=5, threshold=3)
        self._token_manager = TokenManager(model_name=getattr(llm, 'model_name', 'gpt-4'))
        self._error_handler = ErrorHandler()

        # Initialize hallucination detector with available tool names
        tool_names = [t.get("function", {}).get("name", "") for t in self.get_available_tools() or []]
        self._hallucination_detector = ToolHallucinationDetector(tool_names)

        # Initialize security assessor for action risk evaluation
        self._security_assessor = SecurityAssessor(
            autonomy_level="autonomous",  # Default to autonomous mode
            allow_credential_access=False,
            allow_destructive_operations=False,
        )
    
    def get_available_tools(self) -> Optional[List[Dict[str, Any]]]:
        """Get all available tools list"""
        available_tools = []
        for tool in self.tools:
            available_tools.extend(tool.get_tools())
        return available_tools

    def get_filtered_tools(
        self,
        task_description: str,
        include_mcp: bool = True
    ) -> List[Dict[str, Any]]:
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
        filtered = manager.get_tools_for_task(
            task_description,
            include_mcp=include_mcp
        )

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
        correction = self._hallucination_detector.detect(function_name)
        if correction:
            raise ValueError(correction)

        raise ValueError(f"Unknown tool: {function_name}")

    def refresh_hallucination_detector(self) -> None:
        """Refresh the hallucination detector with current available tools.

        Call this after dynamically loading MCP tools.
        """
        tool_names = [t.get("function", {}).get("name", "") for t in self.get_available_tools() or []]
        self._hallucination_detector.update_available_tools(tool_names)

    def _record_tool_usage(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float
    ) -> None:
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
        function_args: Dict[str, Any],
        status: ToolStatus,
        **kwargs
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

        return ToolEvent(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            status=status,
            display_command=display_command,
            command_category=command_category,
            command_summary=command_summary,
            **kwargs
        )

    async def invoke_tool(
        self,
        tool: BaseTool,
        function_name: str,
        arguments: Dict[str, Any],
        skip_security: bool = False,
    ) -> ToolResult:
        """Invoke specified tool, with retry mechanism and exponential backoff.

        Integrates with:
        - ToolExecutionProfiler for timing and reliability tracking
        - SecurityAssessor for risk evaluation
        - StuckDetector for action pattern detection
        """
        import time
        profiler = get_tool_profiler()
        start_time = time.perf_counter()

        # Security assessment before execution (skip for user-confirmed actions)
        if not skip_security:
            security_assessment = self._security_assessor.assess_action(function_name, arguments)
            if security_assessment.blocked:
                logger.warning(
                    f"Security blocked tool '{function_name}': {security_assessment.reason}"
                )
                return ToolResult(
                    success=False,
                    message=f"Action blocked for security: {security_assessment.reason}"
                )

            if security_assessment.risk_level == ActionSecurityRisk.HIGH:
                logger.info(
                    f"High-risk tool call: {function_name} - {security_assessment.reason}"
                )

        retries = 0
        current_interval = self.retry_interval
        last_error = ""
        result: Optional[ToolResult] = None

        while retries <= self.max_retries:
            try:
                result = await tool.invoke_function(function_name, **arguments)

                # Record successful execution with profiler
                duration_ms = (time.perf_counter() - start_time) * 1000
                profiler.record_execution(
                    tool_name=function_name,
                    duration_ms=duration_ms,
                    success=result.success if result else False,
                    error=result.message if result and not result.success else None
                )

                # Record for dynamic toolset prioritization
                self._record_tool_usage(
                    function_name,
                    success=result.success if result else False,
                    duration_ms=duration_ms
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
            tool_name=function_name,
            duration_ms=duration_ms,
            success=False,
            error=last_error[:200]
        )

        # Track failed action for stuck detection
        self._stuck_detector.track_tool_action(
            tool_name=function_name,
            tool_args=arguments,
            success=False,
            error=last_error[:200],
        )

        return ToolResult(success=False, message=last_error)

    def _can_parallelize_tools(self, tool_calls: List[Dict]) -> bool:
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
            if any(tool_name.startswith(prefix) or f"_{prefix.split('_')[-1]}" in tool_name
                   for prefix in SAFE_MCP_PREFIXES):
                continue

            # Tool not in safe list
            return False

        return True

    async def _invoke_tool_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        tool_call: Dict,
        function_args: Dict[str, Any]
    ) -> Tuple[Dict, BaseTool, ToolResult]:
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
            "file_read", "file_search", "file_list", "file_info",
            # Shell read operations
            "shell_exec",  # Will check command content separately
            # Browser read operations
            "browser_view", "browser_screenshot", "browser_get_content",
            # Search
            "info_search", "search",
            # Code read operations
            "code_list", "code_read",
            # Git read operations
            "git_status", "git_diff", "git_log", "git_branches",
            # Workspace info
            "workspace_info", "workspace_tree",
            # Test list
            "test_list",
            # Export list
            "export_list",
        }
        name_lower = function_name.lower()
        return any(pattern in name_lower for pattern in read_only_patterns)

    def _calculate_iteration_cost(self, tool_calls: List[Dict]) -> float:
        """Calculate weighted iteration cost based on tool types."""
        cost = 0.0
        for tc in tool_calls:
            function_name = tc.get("function", {}).get("name", "")
            if self._is_read_only_tool(function_name):
                cost += self.read_only_iteration_weight
            else:
                cost += 1.0
        return max(1.0, cost)  # Minimum 1 iteration per cycle

    async def execute(self, request: str, format: Optional[str] = None) -> AsyncGenerator[BaseEvent, None]:
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
                    f"({budget_ratio*100:.0f}% used)"
                )
                warning_emitted = True

            # Request graceful completion when near limit
            if remaining_budget < 10 and not graceful_completion_requested:
                logger.warning(
                    f"Low iteration budget ({remaining_budget:.1f} remaining), "
                    "requesting completion on next cycle"
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
                    security_assessment = self._security_assessor.assess_action(
                        function_name, function_args
                    )
                    confirmation_state = (
                        "awaiting_confirmation"
                        if security_assessment.requires_confirmation
                        else None
                    )

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
                for tool_call, tool_call_id, function_args, tool in parsed_calls:
                    function_name = tool_call["function"]["name"]
                    tasks.append(
                        self._execute_parallel_tool(
                            semaphore, tool, function_name, function_args,
                            tool_call_id
                        )
                    )

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results and emit CALLED events
                for (tool_call, tool_call_id, function_args, tool, security_assessment), result in zip(parsed_calls, results):
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
                            "awaiting_confirmation"
                            if security_assessment.requires_confirmation
                            else None
                        ),
                    )

                    tool_responses.append({
                        "role": "tool",
                        "function_name": function_name,
                        "tool_call_id": tool_call_id,
                        "content": result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result)
                    })
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
                    security_assessment = self._security_assessor.assess_action(
                        function_name, function_args
                    )
                    confirmation_state = (
                        "awaiting_confirmation"
                        if security_assessment.requires_confirmation
                        else None
                    )
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

                    security_assessment = self._security_assessor.assess_action(
                        function_name, function_args
                    )
                    confirmation_state = (
                        "awaiting_confirmation"
                        if security_assessment.requires_confirmation
                        else None
                    )

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

                    tool_responses.append({
                        "role": "tool",
                        "function_name": function_name,
                        "tool_call_id": tool_call_id,
                        "content": result.model_dump_json()
                    })

            # If graceful completion was requested, add a hint to wrap up
            if graceful_completion_requested:
                tool_responses.append({
                    "role": "system",
                    "content": (
                        "[SYSTEM: Approaching execution limit. Please complete the current task "
                        "and provide a summary of your findings. If the task is not complete, "
                        "summarize what was accomplished and what remains to be done.]"
                    )
                })
                graceful_completion_requested = False  # Only inject once

            message = await self.ask_with_messages(tool_responses)
        else:
            # Budget exhausted - provide informative error with context
            logger.error(
                f"Iteration budget exhausted: {iteration_spent:.1f}/{iteration_budget} "
                f"after processing tool calls"
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
        function_args: Dict[str, Any],
        tool_call_id: str
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
                    logger.warning(
                        f"Agent {self._agent_id} not found in database, creating document defensively"
                    )
                    agent_model = Agent(id=self._agent_id)
                    await self._repository.save(agent_model)
                    self.memory = await self._repository.get_memory(self._agent_id, self.name)
                else:
                    raise
    
    async def _add_to_memory(self, messages: List[Dict[str, Any]]) -> None:
        """Update memory and save to repository"""
        await self._ensure_memory()
        if self.memory.empty:
            self.memory.add_message({
                "role": "system", "content": self.system_prompt,
            })
        self.memory.add_messages(messages)
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
    
    async def _roll_back_memory(self) -> None:
        await self._ensure_memory()
        self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    async def ask_with_messages(self, messages: List[Dict[str, Any]], format: Optional[str] = None) -> Dict[str, Any]:
        await self._add_to_memory(messages)

        # Check and handle token limits before making LLM call
        await self._ensure_within_token_limit()

        response_format = None
        if format:
            response_format = {"type": format}

        for retry in range(self.max_retries):
            try:
                message = await self.llm.ask(self.memory.get_messages(),
                                                tools=self.get_available_tools(),
                                                response_format=response_format,
                                                tool_choice=self.tool_choice)
            except TokenLimitExceeded as e:
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
                    await self._add_to_memory([
                        {"role": "assistant", "content": ""},
                        {"role": "user", "content": "no thinking, please continue"}
                    ])
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

            # Track response for stuck detection (response-level)
            is_response_stuck = self._stuck_detector.track_response(filtered_message)

            # Also check for action-level stuck patterns
            action_analysis = self._stuck_detector.get_analysis()
            is_action_stuck = action_analysis is not None

            is_stuck = is_response_stuck or is_action_stuck

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

                await self._add_to_memory([
                    filtered_message,
                    {"role": "user", "content": recovery_prompt}
                ])
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
                current_messages,
                preserve_system=True,
                preserve_recent=6
            )
            self.memory.messages = trimmed_messages
            await self._repository.save_memory(self._agent_id, self.name, self.memory)
            logger.info(f"Trimmed memory, removed {tokens_removed} tokens")

    async def _handle_token_limit_exceeded(self) -> None:
        """Handle token limit exceeded error by aggressively trimming context"""
        await self._ensure_memory()

        # First compact verbose tool results
        self.memory.smart_compact()

        # Then trim messages
        trimmed_messages, tokens_removed = self._token_manager.trim_messages(
            self.memory.get_messages(),
            preserve_system=True,
            preserve_recent=4  # More aggressive trim
        )
        self.memory.messages = trimmed_messages
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
        logger.info(f"Handled token limit by trimming {tokens_removed} tokens")

    async def ask(self, request: str, format: Optional[str] = None) -> Dict[str, Any]:
        return await self.ask_with_messages([
            {
                "role": "user", "content": request
            }
        ], format)
    
    async def roll_back(self, message: Message):
        await self._ensure_memory()
        last_message = self.memory.get_last_message()
        if (not last_message or 
            not last_message.get("tool_calls") or 
            len(last_message.get("tool_calls")) == 0):
            return
        tool_call = last_message.get("tool_calls")[0]
        function_name = tool_call.get("function", {}).get("name")
        tool_call_id = tool_call.get("id")
        if function_name == "message_ask_user":
            self.memory.add_message({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "function_name": function_name,
                "content": message.model_dump_json()
            })
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
        blocked_patterns: Optional[List[str]] = None,
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

    def get_reliability_stats(self) -> Dict[str, Any]:
        """Get comprehensive reliability statistics.

        Returns:
            Dictionary with stuck detection, security, and tool stats
        """
        return {
            "stuck_detector": self._stuck_detector.get_stats(),
            "security": self._security_assessor.get_risk_summary(),
            "hallucination_detector": {
                "available_tools": len(self._hallucination_detector._available_tools),
            },
        }

    def reset_reliability_state(self) -> None:
        """Reset all reliability tracking state.

        Call this when starting a new task or session.
        """
        self._stuck_detector.reset()
        logger.debug("Reliability state reset")

    async def ask_streaming(
        self,
        request: str,
        format: Optional[str] = None
    ) -> AsyncGenerator[BaseEvent, None]:
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
        if not hasattr(self.llm, 'ask_stream'):
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
                response_format=response_format
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
