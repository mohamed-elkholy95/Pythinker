import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, ClassVar

from app.domain.exceptions.base import AgentConfigurationException, ToolNotFoundException
from app.domain.external.llm import LLM
from app.domain.external.logging import get_agent_logger
from app.domain.models.agent import Agent
from app.domain.models.event import BaseEvent, MessageEvent, UsageEvent
from app.domain.models.message import Message
from app.domain.models.state_manifest import StateEntry, StateManifest
from app.domain.models.tool_permission import PermissionTier
from app.domain.models.tool_result import ToolResult
from app.domain.models.turn_summary import TurnSummary
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.compaction import CompactionConfig, CompactionResult
from app.domain.services.agents.error_handler import ErrorHandler
from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.llm_conversation_mixin import LlmConversationMixin
from app.domain.services.agents.security_assessor import SecurityAssessor
from app.domain.services.agents.stuck_detector import StuckDetector
from app.domain.services.agents.tool_invocation_mixin import (
    ToolInvocationMixin,
    _extract_url_from_args,  # noqa: F401  # re-exported for backward compat
)

if TYPE_CHECKING:
    from app.domain.external.circuit_breaker import CircuitBreakerPort
    from app.domain.services.agents.agent_context import AgentServiceContext
    from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
    from app.domain.services.agents.scratchpad import Scratchpad
    from app.domain.services.agents.tool_result_store import ToolResultStore
    from app.domain.services.agents.url_failure_guard import UrlFailureGuard
    from app.domain.services.tools.metadata_index import ToolMetadataIndex
    from app.domain.utils.cancellation import CancellationToken
from app.domain.models.tool_name import ToolName
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.context_manager import SandboxContextManager
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.dynamic_toolset import get_toolset_manager
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

# Tools that are safe to execute in parallel (read-only, no side effects)
# Canonical source: ToolName.safe_parallel_tools()
SAFE_PARALLEL_TOOLS = ToolName.safe_parallel_tools()





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




def _extract_embedded_json(text: str) -> str | None:
    """Extract a JSON object embedded in mixed prose+JSON text.

    Scans each line for a standalone JSON object (``{...}``).  Returns the
    first valid JSON string found, or ``None`` if no embedded JSON exists.
    This handles the common LLM pattern of wrapping valid JSON in prose:

        "Here is the result:\\n{\"success\": true, ...}\\nDone."
    """
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                json.loads(stripped)
                return stripped
            except (ValueError, TypeError):
                continue
    return None


class BaseAgent(ToolInvocationMixin, LlmConversationMixin):
    """
    Base agent class, defining the basic behavior of the agent
    """

    name: str = ""
    system_prompt: str = ""
    format: str | None = None
    max_iterations: int = 400  # Doubled for complex tasks — overridden by settings.max_iterations
    max_retries: int = 3  # Overridden by settings.agent_max_retries
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
        service_context: "AgentServiceContext | None" = None,
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
        self._metadata_index: ToolMetadataIndex | None = None  # Lazy-built from self.tools
        self._active_phase: str | None = None  # Phase-based tool filtering (set by orchestrator)
        self._active_tier: PermissionTier = PermissionTier.DANGER
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

        # Override class-level defaults from application settings
        from app.core.config import get_settings as _get_base_settings

        _base_cfg = _get_base_settings()
        self.max_iterations = _base_cfg.max_iterations
        self.max_retries = _base_cfg.agent_max_retries
        self.max_step_iterations = _base_cfg.agent_max_step_iterations

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
        # _hallucination_count_this_step removed — managed by HallucinationGuardMiddleware
        self._compression_cycles_this_step: int = 0
        self._compression_guard_active: bool = False
        self._step_start_time: float | None = None

        # Consecutive hard context cap hits — drives escalating truncation.
        # When the graduated truncation can't keep pace with context growth,
        # each consecutive hit tightens limits further.  Reset when context
        # drops below 90 % of the cap.
        self._consecutive_cap_hits: int = 0

        # Per-session hallucination rate tracking (for model escalation)
        self._total_hallucinations: int = 0
        self._total_tool_calls: int = 0
        self._hallucination_escalated: bool = False

        # Phase 2: Proactive token budget manager (feature-flagged)
        self._token_budget: Any = None  # TokenBudget — set by orchestrator via set_token_budget()
        self._token_budget_manager: Any = None  # TokenBudgetManager
        self._sliding_window: Any = None  # SlidingWindowContextManager

        # Middleware pipeline (backward compatible: uses service_context if provided,
        # otherwise builds default pipeline from embedded services above)
        if service_context:
            self._pipeline = service_context.middleware_pipeline
        else:
            self._pipeline = self._build_default_pipeline()

        from app.domain.services.agents.agent_loop import AgentLoop
        from app.domain.services.agents.tool_dispatcher import ToolDispatcher

        self._tool_dispatcher = ToolDispatcher(self)
        self._agent_loop = AgentLoop(self, self._tool_dispatcher)

        self._reset_turn_accounting()

    def _build_default_pipeline(self) -> "MiddlewarePipeline":
        """Build default middleware pipeline from existing embedded services.

        Backward compatible: reproduces identical behavior to current inline code.
        Called when no service_context is provided.
        """
        from app.domain.services.agents.middleware_adapters.efficiency_monitor import EfficiencyMonitorMiddleware
        from app.domain.services.agents.middleware_adapters.error_handler import ErrorHandlerMiddleware
        from app.domain.services.agents.middleware_adapters.hallucination_guard import HallucinationGuardMiddleware
        from app.domain.services.agents.middleware_adapters.permission_gate import PermissionGateMiddleware
        from app.domain.services.agents.middleware_adapters.security_assessment import SecurityAssessmentMiddleware
        from app.domain.services.agents.middleware_adapters.stuck_detection import StuckDetectionMiddleware
        from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline
        from app.domain.services.tools.metadata_index import ToolMetadataIndex

        pipeline = MiddlewarePipeline()
        metadata_index = ToolMetadataIndex(self.tools)
        pipeline.use(
            SecurityAssessmentMiddleware(
                assessor=self._security_assessor,
                tool_metadata_index=metadata_index,
            )
        )
        pipeline.use(PermissionGateMiddleware(tool_metadata_index=metadata_index))
        pipeline.use(HallucinationGuardMiddleware(detector=self._hallucination_detector))
        pipeline.use(EfficiencyMonitorMiddleware(monitor=self._efficiency_monitor))
        pipeline.use(StuckDetectionMiddleware(detector=self._stuck_detector))
        pipeline.use(ErrorHandlerMiddleware(handler=self._error_handler))
        return pipeline

    def _resolve_feature_flags(self) -> dict[str, bool]:
        """Return injected feature flags, falling back to core config."""
        if self._feature_flags is not None:
            return self._feature_flags
        from app.core.config import get_feature_flags

        return get_feature_flags()

    def set_active_tier(self, tier: PermissionTier) -> None:
        """Set the active tool permission tier for subsequent tool dispatch."""
        self._active_tier = tier

    def _should_block_tool_at_pressure_level(self, tool_name: str, level: str) -> bool:
        """Expose wall-clock pressure blocking to extracted loop helpers."""
        return _should_block_tool_at_pressure(tool_name, level)

    def _extract_embedded_json(self, text: str) -> str | None:
        """Expose embedded-JSON extraction to extracted loop helpers."""
        return _extract_embedded_json(text)

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

    def set_metrics(self, metrics: Any) -> None:
        """Replace the default NullMetrics with a real MetricsPort implementation.

        Called by the orchestration layer after agent construction to inject
        Prometheus-backed metrics recording.
        """
        self._metrics = metrics

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

    @property
    def metadata_index(self) -> "ToolMetadataIndex":
        """Lazily build and cache the tool metadata index."""
        metadata_index = getattr(self, "_metadata_index", None)
        if metadata_index is None:
            from app.domain.services.tools.metadata_index import ToolMetadataIndex

            tools = getattr(self, "tools", []) or []
            metadata_index = ToolMetadataIndex(tools)
            self._metadata_index = metadata_index
        return metadata_index

    def _can_parallelize_tools(self, tool_calls: list[dict]) -> bool:
        """Check if tool calls can be executed in parallel using dependency detection.

        Uses ToolMetadataIndex as primary lookup (Phase 1B), falling back to
        SAFE_PARALLEL_TOOLS frozenset and ToolName MCP patterns as safety nets.

        Also uses ParallelToolExecutor.detect_dependencies() to catch data-flow
        dependencies (e.g. write-then-read same file) that metadata alone can't detect.
        """
        from app.domain.services.agents.parallel_executor import ParallelToolExecutor

        if len(tool_calls) <= 1:
            return False

        index = self.metadata_index

        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")

            # Check blacklist first — these must never run in parallel
            if tool_name in ParallelToolExecutor.SEQUENTIAL_ONLY_TOOLS:
                return False

            # Primary: metadata index (per-function metadata from @tool decorator)
            if index.is_safe_parallel(tool_name):
                continue

            # Fallback safety net: static frozenset (catches tools not yet annotated)
            if tool_name in SAFE_PARALLEL_TOOLS:
                continue

            # Tool not in any safe list
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
        from app.core.config import get_settings

        _settings = get_settings()
        _session_timeout = getattr(_settings, "max_session_wall_clock_seconds", 3600)
        self._reset_turn_accounting()
        self._turn_started_at = time.monotonic()

        try:
            async with asyncio.timeout(_session_timeout if _session_timeout > 0 else None):
                async for _event in self._execute_inner(request, format):
                    yield _event
                yield self._usage_event_from_summary(self._build_turn_summary())
        except TimeoutError:
            logger.warning(
                "Agent session wall-clock timeout after %ds (session=%s)",
                _session_timeout,
                getattr(self, "_session_id", "unknown"),
            )
            _timeout_content = json.dumps(
                {
                    "success": False,
                    "result": (
                        "The session reached the maximum allowed time and was stopped. "
                        "Any work completed up to this point has been saved."
                    ),
                    "attachments": [],
                    "error": f"Session wall-clock limit of {_session_timeout}s exceeded.",
                }
            )
            yield MessageEvent(message=_timeout_content)
            yield self._usage_event_from_summary(self._build_turn_summary())
            await self.cleanup_background_tasks()

    def _reset_turn_accounting(self) -> None:
        self._turn_iterations = 0
        self._turn_prompt_tokens = 0
        self._turn_completion_tokens = 0
        self._turn_tools_called: list[str] = []
        self._turn_started_at: float | None = None

    def _estimate_prompt_tokens(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> int:
        prompt_tokens = self._token_manager.count_messages_tokens(messages)
        if tools:
            with contextlib.suppress(TypeError, ValueError):
                prompt_tokens += self._token_manager.count_tokens(json.dumps(tools))
        return prompt_tokens

    def _estimate_completion_tokens(self, response: dict[str, Any]) -> int:
        completion_tokens = 0
        content = response.get("content")
        if isinstance(content, str) and content:
            completion_tokens += self._token_manager.count_tokens(content)

        tool_calls = response.get("tool_calls")
        if tool_calls:
            with contextlib.suppress(TypeError, ValueError):
                completion_tokens += self._token_manager.count_tokens(json.dumps(tool_calls))
        return completion_tokens

    def _build_turn_summary(self) -> TurnSummary:
        from app.core.config import get_settings

        settings = get_settings()
        input_price = float(getattr(settings, "llm_input_price_per_million", 0.0) or 0.0)
        output_price = float(getattr(settings, "llm_output_price_per_million", 0.0) or 0.0)
        duration_seconds = 0.0
        if self._turn_started_at is not None:
            duration_seconds = max(0.0, time.monotonic() - self._turn_started_at)

        estimated_cost_usd = (self._turn_prompt_tokens / 1_000_000) * input_price + (
            self._turn_completion_tokens / 1_000_000
        ) * output_price

        return TurnSummary(
            iterations=max(1, self._turn_iterations),
            tools_called=list(self._turn_tools_called),
            prompt_tokens=self._turn_prompt_tokens,
            completion_tokens=self._turn_completion_tokens,
            estimated_cost_usd=estimated_cost_usd,
            duration_seconds=duration_seconds,
        )

    @staticmethod
    def _usage_event_from_summary(summary: TurnSummary) -> UsageEvent:
        return UsageEvent(
            iterations=summary.iterations,
            prompt_tokens=summary.prompt_tokens,
            completion_tokens=summary.completion_tokens,
            estimated_cost_usd=summary.estimated_cost_usd,
            duration_seconds=summary.duration_seconds,
        )

    async def _execute_inner(self, request: str, format: str | None = None) -> AsyncGenerator[BaseEvent, None]:
        async for event in self._agent_loop.run(request, format):
            yield event

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

    async def _ensure_memory(self) -> None:
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

    async def roll_back(self, message: Message) -> None:
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

    async def compact(
        self,
        config: CompactionConfig | None = None,
    ) -> CompactionResult:
        """Compact memory through a small, explicit contract."""
        from app.domain.services.agents.compaction import (
            CompactionConfig,
            CompactionResult,
            CompactionStrategy,
        )
        from app.domain.services.agents.memory_manager import get_memory_manager

        config = config or CompactionConfig()

        await self._ensure_memory()
        before_messages = list(self.memory.get_messages())
        tokens_before = self._token_manager.count_messages_tokens(before_messages)

        if config.strategy == CompactionStrategy.TRUNCATE:
            trim_manager = TokenManager(
                model_name=getattr(self.llm, "model_name", "gpt-4"),
                max_context_tokens=config.target_tokens,
                safety_margin=0,
            )
            trimmed_messages, _tokens_removed = trim_manager.trim_messages(
                before_messages,
                preserve_system=True,
                preserve_recent=config.preserve_last_n_messages,
            )
            self.memory.messages = trimmed_messages
        elif config.strategy == CompactionStrategy.SUMMARIZE:
            memory_manager = get_memory_manager()
            compacted_messages, _tokens_saved = await memory_manager.structured_compact(
                before_messages,
                self.llm,
                preserve_recent=config.preserve_last_n_messages,
            )
            self.memory.messages = compacted_messages
        else:
            memory_manager = get_memory_manager()
            optimized_messages, _report = memory_manager.optimize_context(
                before_messages,
                preserve_recent=config.preserve_last_n_messages,
                token_threshold=config.target_tokens,
            )
            self.memory.messages = optimized_messages

        after_messages = list(self.memory.messages)
        tokens_after = self._token_manager.count_messages_tokens(after_messages)
        messages_removed = max(0, len(before_messages) - len(after_messages))

        await self._repository.save_memory(self._agent_id, self.name, self.memory)

        return CompactionResult(
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=messages_removed,
            strategy_used=config.strategy,
        )

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
        # _hallucination_count_this_step removed — managed by HallucinationGuardMiddleware
        self._compression_cycles_this_step = 0
        self._compression_guard_active = False
        self._step_start_time = None

        # Reset per-agent efficiency monitor
        self._efficiency_monitor.reset()
        self._efficiency_nudges.clear()

        logger.debug("Reliability state reset")
