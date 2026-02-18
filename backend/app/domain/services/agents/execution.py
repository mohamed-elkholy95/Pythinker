import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.domain.external.llm import LLM
from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.agent_response import ExecutionStepResult
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    MessageEvent,
    ReportEvent,
    StepEvent,
    StepStatus,
    StreamEvent,
    SuggestionEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan, Step, StepType
from app.domain.models.source_citation import SourceCitation
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.chain_of_verification import ChainOfVerification, CoVeResult
from app.domain.services.agents.compliance_gates import GateStatus, get_compliance_gates
from app.domain.services.agents.context_manager import ContextManager, InsightType
from app.domain.services.agents.critic import CriticAgent, CriticConfig, CriticVerdict
from app.domain.services.agents.output_coverage_validator import OutputCoverageValidator
from app.domain.services.agents.prompt_adapter import PromptAdapter
from app.domain.services.agents.response_compressor import ResponseCompressor
from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode
from app.domain.services.agents.reward_scoring import RewardScorer
from app.domain.services.agents.step_context_assembler import StepContextAssembler
from app.domain.services.agents.task_state_manager import get_task_state_manager
from app.domain.services.attention_injector import AttentionInjector
from app.domain.services.prompts.execution import (
    CONFIRMATION_SUMMARY_PROMPT,
    EXECUTION_SYSTEM_PROMPT,
    STREAMING_SUMMARIZE_PROMPT,
    build_execution_prompt_from_context,
)
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.tool_tracing import get_tool_tracer
from app.domain.utils.json_parser import JsonParser

# Module-level metrics instance (can be overridden for testing)
_metrics: MetricsPort = get_null_metrics()


def set_metrics(metrics: MetricsPort) -> None:
    """Set the metrics instance for this module."""
    global _metrics
    _metrics = metrics


if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService
    from app.domain.utils.cancellation import CancellationToken

logger = logging.getLogger(__name__)

_SUGGESTION_LIST_ADAPTER = TypeAdapter(list[str])


class _SuggestionPayload(BaseModel):
    suggestions: list[str]


class ExecutionAgent(BaseAgent):
    """
    Execution agent class, defining the basic behavior of execution
    """

    name: str = "execution"
    system_prompt: str = SYSTEM_PROMPT + EXECUTION_SYSTEM_PROMPT
    format: str = "json_object"

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: list[BaseTool],
        json_parser: JsonParser,
        critic_config: CriticConfig | None = None,
        memory_service: Optional["MemoryService"] = None,
        user_id: str | None = None,
        attention_injector: AttentionInjector | None = None,
        circuit_breaker=None,
        feature_flags: dict[str, bool] | None = None,
        cancel_token: "CancellationToken | None" = None,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
            circuit_breaker=circuit_breaker,
            feature_flags=feature_flags,
            cancel_token=cancel_token,
        )
        # Initialize prompt adapter for dynamic context injection
        self._prompt_adapter = PromptAdapter()

        # Attention injector for goal recitation (Pythinker AI pattern)
        self._attention_injector = attention_injector or AttentionInjector()
        self.current_goal: str | None = None
        self.current_todo: list[str] = []

        # Initialize critic agent for output quality assurance
        self._critic = CriticAgent(
            llm=llm,
            json_parser=json_parser,
            config=critic_config or CriticConfig(enabled=True, auto_approve_simple_tasks=True, max_revision_attempts=2),
        )
        self._user_request: str | None = None  # Track for critic context

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

        # Pre-planning search context for real-time web info propagation
        self._pre_planning_search_context: str | None = None

        # Context manager for execution continuity (Phase 1)
        self._context_manager = ContextManager(max_context_tokens=8000)

        # Step context assembler — gathers all context signals for prompt building
        self._context_assembler = StepContextAssembler(
            context_manager=self._context_manager,
            token_manager=self._token_manager,
            memory_service=memory_service,
            user_id=user_id,
        )

        # Chain-of-Verification for hallucination reduction (Phase 2 — deprecated)
        self._cove = ChainOfVerification(
            llm=llm,
            json_parser=json_parser,
            max_questions=5,
            parallel_verification=True,
            min_response_length=200,
        )
        self._cove_enabled = False  # Deprecated: use LettuceDetect instead

        # LettuceDetect encoder-based hallucination verification (replaces CoVe)
        self._lettuce_enabled = True  # Configured via feature flags

        # Source citation tracking for reports (capped to prevent unbounded growth)
        self._max_collected_sources: int = 200
        self._collected_sources: list[SourceCitation] = []
        self._seen_urls: set[str] = set()

        # Citation index for inline references [1], [2] (Phase 2: MindSearch-inspired)
        self._citation_counter: int = 0
        self._url_to_citation: dict[str, int] = {}

        # Parallel research context injected by PlanActFlow (MindSearch-inspired)
        self._parallel_research_context: str | None = None

        # Multimodal information persistence (P5.2)
        # Per Pythinker pattern: persist key findings every 2 view operations
        self._view_operation_count: int = 0
        self._multimodal_findings: list[dict] = []
        self._view_tools = {"file_view", "browser_view", "browser_get_content", "browser_agent_extract"}

        # Adaptive response policy controls
        self._response_policy: ResponsePolicy | None = None
        self._output_coverage_validator = OutputCoverageValidator()
        self._response_compressor = ResponseCompressor()
        # Phase 1/4: Request contract for entity fidelity (set by PlanActFlow)
        self._request_contract = None

    def set_request_contract(self, contract) -> None:
        """Set request contract for search fidelity and entity context (Phase 4)."""
        self._request_contract = contract

    def set_response_policy(self, policy: ResponsePolicy | None) -> None:
        """Set per-run response policy for summarize stage."""
        self._response_policy = policy

    def _select_model_for_step(self, step_description: str) -> str | None:
        """Select appropriate model for the current step using unified ModelRouter.

        Unified Hybrid Approach:
        - Uses ModelRouter for complexity-based routing
        - Pulls configuration from Settings
        - Includes Prometheus metrics
        - Returns model name for LLM override

        Args:
            step_description: The step description to analyze

        Returns:
            Model name for the selected tier. When adaptive selection is
            disabled, returns the balanced (default) model name.

        Context7 validated: ModelRouter integration, Settings feature flag.
        """
        from app.domain.services.agents.model_router import ModelRouter, ModelTier, get_model_router

        try:
            # If user selected a non-auto thinking mode, force the tier
            thinking_mode = getattr(self, "_user_thinking_mode", None)
            if thinking_mode == "fast":
                router: ModelRouter = ModelRouter(force_tier=ModelTier.FAST, metrics=_metrics)
                config = router.route(step_description)
                logger.debug(f"Model routing (forced fast): model={config.model_name}")
                return config.model_name
            if thinking_mode == "deep_think":
                router = ModelRouter(force_tier=ModelTier.POWERFUL, metrics=_metrics)
                config = router.route(step_description)
                logger.debug(f"Model routing (forced deep_think): model={config.model_name}")
                return config.model_name

            # Default: auto — complexity-based routing via singleton
            router = get_model_router(metrics=_metrics)
            config = router.route(step_description)

            logger.debug(
                f"Model routing: tier={config.tier.value}, model={config.model_name}, "
                f"temp={config.temperature}, max_tokens={config.max_tokens}"
            )

            return config.model_name

        except Exception as e:
            logger.warning(f"Model routing failed, using default: {e}")
            return None

    async def invoke_tool(
        self,
        tool: BaseTool,
        function_name: str,
        arguments: dict[str, Any],
        skip_security: bool = False,
    ):
        """Override to apply search fidelity check for search tools (Phase 4)."""
        from app.core.config import get_settings
        from app.domain.services.agents.search_fidelity import check_search_fidelity

        settings = get_settings()
        if (
            settings.enable_search_fidelity_guardrail
            and self._request_contract
            and function_name in ("info_search_web", "search", "wide_research")
        ):
            query = arguments.get("query", "")
            if isinstance(query, str) and query.strip():
                passed, repaired = check_search_fidelity(query, self._request_contract)
                if not passed:
                    arguments = {**arguments, "query": repaired}
                    logger.info("Search fidelity repair: prepended entity to query")

        return await super().invoke_tool(tool, function_name, arguments, skip_security)

    async def execute_step(
        self,
        plan: Plan,
        step: Step,
        message: Message,
        *,
        conversation_context: str | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        # Store user request for critic context
        self._user_request = message.message

        # Set current step for inter-step context synthesis (Phase 2.5)
        self._context_manager.set_current_step(step.id)

        # Build skill context if skills are explicitly enabled by the user
        # Save/restore tools and system_prompt to avoid permanent mutation across steps
        original_tools = list(self.tools)
        original_system_prompt = self.system_prompt
        if message.skills:
            logger.info(f"Loading skill context for skills: {message.skills}")
            try:
                from app.domain.services.skill_registry import get_skill_registry

                registry = await get_skill_registry()
                # Ensure registry is fresh so newly-created skills are visible immediately
                await registry._ensure_fresh()
                skill_context = await registry.build_context(
                    message.skills,
                    expand_dynamic=True,
                )

                # Validate that skills were actually loaded
                if not skill_context.skill_ids:
                    logger.warning(f"No skills found in registry for IDs: {message.skills}")

                if skill_context.prompt_addition:
                    # Extend system prompt with skill context (restored after step)
                    self.system_prompt = SYSTEM_PROMPT + EXECUTION_SYSTEM_PROMPT + skill_context.prompt_addition
                    logger.info(
                        f"✓ Injected skill context for skills: {skill_context.skill_ids} "
                        f"({len(skill_context.prompt_addition)} chars) "
                        f"(prompt_addition present: True, tool_restrictions: {skill_context.has_tool_restrictions()})"
                    )
                else:
                    logger.warning(f"Skill context built but no prompt_addition for: {message.skills}")

                # Phase 3.5: Apply tool restrictions from skills (restored after step)
                tool_restrictions = None
                if skill_context.has_tool_restrictions():
                    original_count = len(self.tools)
                    allowed = skill_context.allowed_tools
                    self.tools = [t for t in self.tools if t.name in allowed]
                    tool_restrictions = list(allowed) if allowed else None
                    logger.info(
                        f"Applied skill tool restrictions: {original_count} → {len(self.tools)} tools "
                        f"(allowed: {allowed})"
                    )

                # Log skill activation (event is emitted once by agent_domain_service)
                logger.info(
                    f"Skill context applied: skills={message.skills}, "
                    f"tool_restrictions={tool_restrictions}, "
                    f"prompt_chars={len(skill_context.prompt_addition) if skill_context.prompt_addition else 0}"
                )
            except Exception as e:
                logger.warning(f"Failed to build skill context: {e}")

        # Increment iteration counter for prompt adapter
        self._prompt_adapter.increment_iteration()

        # Assemble all context signals via StepContextAssembler
        ctx = await self._context_assembler.assemble(
            plan=plan,
            step=step,
            message=message,
            tools=self.tools,
            memory_messages=self.memory.get_messages() if self.memory else None,
            pre_planning_search_context=self._pre_planning_search_context,
            conversation_context=conversation_context,
            request_contract=self._request_contract,
        )

        # Build execution prompt from assembled context (includes all appendages)
        base_prompt = build_execution_prompt_from_context(ctx)

        # Adapt prompt with context-specific guidance if applicable
        if self._prompt_adapter.should_inject_guidance():
            execution_message = self._prompt_adapter.adapt_prompt(base_prompt)
            logger.debug("Injected context guidance into execution prompt")
        else:
            execution_message = base_prompt

        # DeepCode Phase 1: Select model tier based on step complexity
        selected_model = self._select_model_for_step(step.description)
        if selected_model:
            self._step_model_override = selected_model
            logger.info(f"Using adaptive model for step: {selected_model}")

        step.status = ExecutionStatus.RUNNING
        yield StepEvent(status=StepStatus.STARTED, step=step)
        try:
            async for event in self.execute(execution_message):
                if isinstance(event, ErrorEvent):
                    step.status = ExecutionStatus.FAILED
                    step.error = event.error
                    # Track error for prompt adapter
                    self._prompt_adapter.track_tool_use("error", success=False, error=event.error)
                    # Record error as insight for inter-step context (Phase 2.5)
                    self._context_manager.add_insight(
                        insight_type=InsightType.ERROR_LEARNING,
                        content=f"Step failed: {event.error[:200]}",
                        confidence=0.95,
                        tags=["error", "step_failure"],
                    )
                    yield StepEvent(status=StepStatus.FAILED, step=step)
                elif isinstance(event, MessageEvent):
                    step.status = ExecutionStatus.COMPLETED
                    parsed_response: Any = None
                    try:
                        parsed_response = await self.json_parser.parse(event.message)
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse step response as JSON: {parse_err}")

                    # Validate structured output and degrade safely when malformed.
                    if not self._apply_step_result_payload(
                        step=step, parsed_response=parsed_response, raw_message=event.message
                    ):
                        logger.warning("Step response payload missing/invalid schema; marking step as unsuccessful")

                    # Apply hallucination verification on step results
                    if step.result and self._user_request:
                        result_str = str(step.result)
                        if self._needs_verification(result_str, self._user_request):
                            verified_result = await self._apply_hallucination_verification(
                                result_str, self._user_request
                            )
                            if verified_result != result_str:
                                step.result = verified_result
                                logger.info("Hallucination verification refined step result")

                    yield StepEvent(status=StepStatus.COMPLETED, step=step)
                    if step.result:
                        yield MessageEvent(message=step.result)
                    continue
                elif isinstance(event, ToolEvent):
                    # Track tool usage for prompt adapter
                    if event.status == ToolStatus.CALLED:
                        success = event.function_result.success if event.function_result else True
                        error = event.function_result.message if event.function_result and not success else None
                        # Guard against None function_name
                        func_name = event.function_name or "unknown"
                        self._prompt_adapter.track_tool_use(func_name, success=success, error=error)

                        # Track sources from tool events for report bibliography
                        self._track_sources_from_tool_event(event)

                        # Track multimodal findings (P5.2 - Pythinker pattern)
                        self._track_multimodal_findings(event)

                        # Track in context manager (Phase 1)
                        if success and event.function_result:
                            # Track file operations
                            if func_name in ["file_write", "file_create"]:
                                file_path = event.function_args.get("path", "")
                                if file_path:
                                    self._context_manager.track_file_operation(
                                        path=file_path,
                                        operation="created",
                                        content_summary=f"Created via {func_name}",
                                    )
                            elif func_name == "file_read":
                                file_path = event.function_args.get("path", "")
                                if file_path:
                                    self._context_manager.track_file_operation(
                                        path=file_path,
                                        operation="read",
                                    )

                            # Track tool executions for non-file operations
                            if not func_name.startswith("file_"):
                                result_summary = (
                                    str(event.function_result.message)[:200]
                                    if hasattr(event.function_result, "message")
                                    else "Success"
                                )
                                self._context_manager.track_tool_execution(
                                    tool_name=event.tool_name or "unknown",
                                    summary=result_summary,
                                )

                            # Record insights for inter-step context synthesis (Phase 2.5)
                            result_text = (
                                str(event.function_result.message)[:500]
                                if hasattr(event.function_result, "message")
                                else str(event.function_result)[:500]
                            )
                            self._context_manager.record_tool_insight(
                                tool_name=func_name or "unknown",
                                result=result_text,
                                success=success,
                                args=event.function_args,
                            )

                    if event.function_name and event.function_name == "message_ask_user":
                        if event.status == ToolStatus.CALLING:
                            yield MessageEvent(message=event.function_args.get("text", ""))
                        elif event.status == ToolStatus.CALLED:
                            # Mark step as completed before waiting for user input
                            step.status = ExecutionStatus.COMPLETED
                            step.success = True
                            step.result = "Waiting for user input"
                            # Emit StepEvent so it's persisted for session resume
                            yield StepEvent(status=StepStatus.COMPLETED, step=step)
                            yield WaitEvent()
                            return
                        continue
                yield event
            # Only mark as COMPLETED if not already set to FAILED
            if step.status != ExecutionStatus.FAILED:
                step.status = ExecutionStatus.COMPLETED
        finally:
            # Always restore tools, system prompt, and model override after step
            self.tools = original_tools
            self.system_prompt = original_system_prompt
            self._step_model_override = None  # DeepCode Phase 1: Reset model override

    async def summarize(self, response_policy: ResponsePolicy | None = None) -> AsyncGenerator[BaseEvent, None]:
        """
        Summarize the completed task, streaming tokens for live display.
        Uses ask_stream() to yield StreamEvent chunks so the frontend can render
        the report progressively. CoVe and Critic run as post-processing on the
        accumulated text after streaming completes.
        """
        active_policy = (
            response_policy
            or self._response_policy
            or ResponsePolicy(
                mode=VerbosityMode.STANDARD, min_required_sections=["final result"], allow_compression=False
            )
        )

        yield StepEvent(
            status=StepStatus.RUNNING,
            step=Step(
                id="finalization",
                description="Composing report...",
                status=ExecutionStatus.RUNNING,
                step_type=StepType.FINALIZATION,
            ),
        )

        # Use streaming prompt (plain markdown, no JSON wrapper)
        # Phase 2: Switch to citation-aware prompt when sources were collected
        if self._collected_sources:
            from app.domain.services.prompts.execution import CITATION_AWARE_SUMMARIZE_PROMPT

            source_list = self._build_numbered_source_list()
            summarize_prompt = f"{CITATION_AWARE_SUMMARIZE_PROMPT}\n\n## Available Sources\n{source_list}"
        else:
            summarize_prompt = STREAMING_SUMMARIZE_PROMPT

        if active_policy.mode == VerbosityMode.CONCISE:
            summarize_prompt += (
                "\n\nKeep the final response concise while preserving: final result, key artifacts, "
                "critical caveats, and one practical next step."
            )
        elif active_policy.mode == VerbosityMode.DETAILED:
            summarize_prompt += (
                "\n\nProvide a detailed and well-structured response with clear reasoning, deliverables, and caveats."
            )

        # Inject parallel research findings into memory before summarization
        if self._parallel_research_context:
            await self._add_to_memory(
                [
                    {
                        "role": "user",
                        "content": (
                            "Here are the research findings from parallel search:\n\n" + self._parallel_research_context
                        ),
                    }
                ]
            )

        await self._add_to_memory([{"role": "user", "content": summarize_prompt}])
        await self._ensure_within_token_limit()

        try:
            flags = self._resolve_feature_flags()
            delivery_integrity_enabled = flags.get("delivery_integrity_gate", False)
            accumulated_text = ""
            stream_messages = list(self.memory.get_messages())
            stream_metadata: dict[str, Any] = {}
            truncation_exhausted = False
            max_stream_continuations = 2 if delivery_integrity_enabled else 0
            stream_attempt = 0

            # Phase 1: Stream tokens live via StreamEvent
            while True:
                stream_attempt += 1
                attempt_text = ""

                stream_iter = self.llm.ask_stream(stream_messages, tools=None, tool_choice=None)
                async with aclosing(stream_iter) as stream:
                    async for chunk in stream:
                        attempt_text += chunk
                        yield StreamEvent(content=chunk, is_final=False, phase="summarizing")

                if stream_attempt == 1:
                    accumulated_text = attempt_text
                else:
                    accumulated_text = self._merge_stream_continuation(accumulated_text, attempt_text)

                stream_metadata = self._get_last_stream_metadata()
                is_truncated_stream = (
                    bool(stream_metadata.get("truncated")) or stream_metadata.get("finish_reason") == "length"
                )
                if delivery_integrity_enabled and is_truncated_stream:
                    self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="detected")
                if not (delivery_integrity_enabled and is_truncated_stream):
                    break

                if stream_attempt > max_stream_continuations:
                    truncation_exhausted = True
                    logger.warning(
                        "Delivery integrity: stream remained truncated after %d continuation attempts",
                        max_stream_continuations,
                    )
                    self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="unresolved")
                    break

                logger.warning(
                    "Delivery integrity: stream truncation detected (finish_reason=%s), requesting continuation (%d/%d)",
                    stream_metadata.get("finish_reason"),
                    stream_attempt,
                    max_stream_continuations,
                )
                assistant_fragment = attempt_text.strip() or accumulated_text[-2000:]
                if not assistant_fragment.strip():
                    truncation_exhausted = True
                    logger.warning("Delivery integrity: truncation detected with empty fragment, aborting continuation")
                    self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="unresolved")
                    break

                stream_messages = [
                    *stream_messages,
                    {"role": "assistant", "content": assistant_fragment},
                    {"role": "user", "content": self._build_continuation_prompt()},
                ]
                self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="continuation_requested")

            if delivery_integrity_enabled and stream_attempt > 1 and not truncation_exhausted:
                is_final_truncated = (
                    bool(stream_metadata.get("truncated")) or stream_metadata.get("finish_reason") == "length"
                )
                if not is_final_truncated:
                    self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="recovered")

            # Signal streaming complete
            yield StreamEvent(content="", is_final=True, phase="summarizing")

            message_content = accumulated_text.strip()
            message_content = self._collapse_duplicate_report_payload(message_content)

            # Strip hallucinated tool-call XML and boilerplate that the LLM
            # may reproduce from earlier conversation history during summarization.
            message_content = self._clean_report_content(message_content)
            message_content = self._collapse_duplicate_report_payload(message_content)

            if not message_content:
                logger.warning(
                    "Summarization produced only tool-call XML / boilerplate (%d raw chars) — retrying with strict prompt",
                    len(accumulated_text),
                )

                # Retry once with a strict anti-XML reinforcement prompt
                retry_prompt = (
                    "Your previous response contained only XML tool-call syntax, which is invalid here. "
                    "You MUST write a plain Markdown report. Do NOT output any XML tags. "
                    "Start your response with a # heading and write the report content directly."
                )
                await self._add_to_memory(
                    [
                        {
                            "role": "assistant",
                            "content": "(Previous summarization attempt produced invalid XML output.)",
                        },
                        {"role": "user", "content": retry_prompt},
                    ]
                )
                retry_text = ""
                retry_stream = self.llm.ask_stream(list(self.memory.get_messages()), tools=None, tool_choice=None)
                async with aclosing(retry_stream) as stream:
                    async for chunk in stream:
                        retry_text += chunk
                        yield StreamEvent(content=chunk, is_final=False, phase="summarizing")

                yield StreamEvent(content="", is_final=True, phase="summarizing")
                message_content = self._clean_report_content(retry_text.strip())

            if not message_content:
                # Both attempts failed — extract fallback from conversation memory
                logger.warning("Summarization retry also empty — extracting fallback from conversation memory")
                message_content = self._extract_fallback_summary()

            if not message_content:
                logger.warning("Summarization failed: no content from LLM or conversation memory")
                yield StepEvent(
                    status=StepStatus.FAILED,
                    step=Step(
                        id="finalization",
                        description="Summary contained no usable content",
                        status=ExecutionStatus.FAILED,
                        step_type=StepType.FINALIZATION,
                    ),
                )
                yield ErrorEvent(error="Summary generation failed: LLM produced no report content")
                return

            # DeepCode Phase 2.2: Pattern-based truncation detection
            # Enhances finish_reason="length" detection with content pattern matching
            if delivery_integrity_enabled and not truncation_exhausted:
                try:
                    from app.domain.services.agents.truncation_detector import get_truncation_detector

                    truncation_detector = get_truncation_detector()
                    truncation_assessment = truncation_detector.detect(
                        content=message_content,
                        finish_reason=stream_metadata.get("finish_reason"),
                        max_tokens_used=bool(stream_metadata.get("truncated")),
                    )

                    # Request continuation if pattern-based detector finds truncation
                    # (even if finish_reason was not "length")
                    if truncation_detector.should_request_continuation(
                        truncation_assessment, confidence_threshold=0.85
                    ):
                        logger.warning(
                            f"Truncation detector: pattern-based truncation detected "
                            f"(type={truncation_assessment.truncation_type}, "
                            f"confidence={truncation_assessment.confidence:.2f}, "
                            f"evidence={truncation_assessment.evidence})"
                        )

                        # Record metric for pattern-based detection
                        _metrics.increment(
                            "pythinker_output_truncations_total",
                            labels={
                                "detection_method": "pattern",
                                "truncation_type": truncation_assessment.truncation_type or "unknown",
                                "confidence_tier": "high" if truncation_assessment.confidence >= 0.9 else "medium",
                            },
                        )

                        # Request continuation using pattern-specific prompt
                        continuation_messages = [
                            *stream_messages,
                            {"role": "assistant", "content": message_content},
                            {"role": "user", "content": truncation_assessment.continuation_prompt},
                        ]

                        # Single continuation attempt for pattern-based detection
                        logger.info("Requesting continuation based on content patterns...")
                        continuation_text = ""
                        continuation_iter = self.llm.ask_stream(continuation_messages, tools=None, tool_choice=None)
                        async with aclosing(continuation_iter) as cont_stream:
                            async for chunk in cont_stream:
                                continuation_text += chunk
                                yield StreamEvent(content=chunk, is_final=False, phase="completing")

                        accumulated_text = self._merge_stream_continuation(accumulated_text, continuation_text)
                        message_content = self._collapse_duplicate_report_payload(accumulated_text.strip())

                        # Record outcome
                        _metrics.increment(
                            "pythinker_output_truncations_total",
                            labels={
                                "detection_method": "pattern",
                                "truncation_type": truncation_assessment.truncation_type or "unknown",
                                "confidence_tier": "continuation_completed",
                            },
                        )

                        logger.info(
                            f"Truncation recovery: added {len(continuation_text)} chars via pattern-based continuation"
                        )

                except Exception as e:
                    logger.debug(f"Pattern-based truncation detection failed: {e}")

            # Extract title from first # heading
            message_title = self._extract_title(message_content)

            # Phase 2: Post-processing — hallucination verification
            should_run_verification = (
                bool(self._user_request)
                and len(message_content) > 300
                and self._needs_verification(message_content, self._user_request)
            )
            if should_run_verification:
                # Emit progress event — frontend will update the existing card's sub-stage
                yield StepEvent(
                    status=StepStatus.RUNNING,
                    step=Step(
                        id="finalization",
                        description="Verifying factual claims...",
                        status=ExecutionStatus.RUNNING,
                        step_type=StepType.FINALIZATION,
                    ),
                )
                message_content = await self._apply_hallucination_verification(message_content, self._user_request)

            # Critic revision loop disabled — the 5-check framework produces
            # unreliable results with the current LLM (unknown check names, excessive
            # revision loops) and adds 30-60s latency. CoVe verification above
            # already handles factual accuracy. Re-enable when the LLM supports
            # reliable structured output for the 5-check framework.

            coverage_result = self._output_coverage_validator.validate(
                output=message_content,
                user_request=self._user_request or "",
                required_sections=active_policy.min_required_sections,
            )
            if not coverage_result.is_valid:
                logger.warning(
                    "Summary coverage missing required elements before compression: %s",
                    ", ".join(coverage_result.missing_requirements) or "unknown",
                )

            if active_policy.allow_compression and active_policy.mode == VerbosityMode.CONCISE:
                compressed_content = self._response_compressor.compress(
                    message_content, mode=active_policy.mode, max_chars=active_policy.max_chars
                )
                compressed_coverage = self._output_coverage_validator.validate(
                    output=compressed_content,
                    user_request=self._user_request or "",
                    required_sections=active_policy.min_required_sections,
                )
                if compressed_coverage.is_valid and len(compressed_content) < len(message_content):
                    message_content = compressed_content
                    coverage_result = compressed_coverage
                else:
                    _metrics.record_counter(
                        "compression_rejected_total",
                        labels={"reason": "coverage_drop"},
                    )

            gate_passed, gate_issues = self._run_delivery_integrity_gate(
                content=message_content,
                response_policy=active_policy,
                coverage_result=coverage_result,
                stream_metadata=stream_metadata,
                truncation_exhausted=truncation_exhausted,
            )
            if not gate_passed and self._can_auto_repair_delivery_integrity(gate_issues):
                repaired_content = self._append_delivery_integrity_fallback(message_content, gate_issues)
                repaired_coverage = self._output_coverage_validator.validate(
                    output=repaired_content,
                    user_request=self._user_request or "",
                    required_sections=active_policy.min_required_sections,
                )
                repaired_passed, repaired_issues = self._run_delivery_integrity_gate(
                    content=repaired_content,
                    response_policy=active_policy,
                    coverage_result=repaired_coverage,
                    stream_metadata=stream_metadata,
                    truncation_exhausted=truncation_exhausted,
                )
                if repaired_passed:
                    logger.info(
                        "Delivery integrity auto-repair succeeded for issues: %s",
                        "; ".join(gate_issues) or "coverage_missing:unknown",
                    )
                    message_content = repaired_content
                    coverage_result = repaired_coverage
                    gate_passed = True
                    gate_issues = []
                else:
                    gate_issues = repaired_issues

            if not gate_passed:
                issue_text = "; ".join(gate_issues)
                yield StepEvent(
                    status=StepStatus.FAILED,
                    step=Step(
                        id="finalization",
                        description="Summary failed delivery integrity checks",
                        status=ExecutionStatus.FAILED,
                        step_type=StepType.FINALIZATION,
                    ),
                )
                yield ErrorEvent(error=f"Delivery integrity gate blocked output: {issue_text}")
                return

            _metrics.record_counter("response_policy_mode_total", labels={"mode": active_policy.mode.value})
            _metrics.record_histogram(
                "final_response_tokens",
                value=max(1, len(message_content) // 4),
                labels={"mode": active_policy.mode.value},
            )

            # Reward hacking detection (log-only)
            if flags.get("reward_hacking_detection"):
                try:
                    task_state_manager = get_task_state_manager()
                    recent_actions = task_state_manager.get_recent_actions() if task_state_manager else []
                    traces = get_tool_tracer().get_recent_traces(limit=20)
                    score = RewardScorer().score_output(
                        output=message_content,
                        user_request=self._user_request or "",
                        recent_actions=recent_actions,
                        tool_traces=traces,
                    )
                    if score.signals:
                        for signal in score.signals:
                            _metrics.record_reward_hacking_signal(signal.signal_type, signal.severity)
                        logger.warning(
                            "Reward hacking signals detected (log-only)",
                            extra={
                                "signals": [s.signal_type for s in score.signals],
                                "overall_score": score.overall,
                            },
                        )
                except Exception as e:
                    logger.debug(f"Reward hacking detection failed: {e}")

            yield StepEvent(
                status=StepStatus.COMPLETED,
                step=Step(
                    id="finalization",
                    description="Report finalized",
                    status=ExecutionStatus.COMPLETED,
                    step_type=StepType.FINALIZATION,
                ),
            )

            # Emit final report/message event
            is_substantial = len(message_content) > 500
            has_title = bool(message_title)
            is_report_structure = self._is_report_structure(message_content)

            # Track report event ID for suggestion anchoring
            report_event_id = None
            message_event_id = None
            if is_substantial or has_title or is_report_structure:
                title = message_title or "Summary"
                sources = self.get_collected_sources() if self._collected_sources else None

                report_event_id = str(uuid.uuid4())
                yield ReportEvent(
                    id=report_event_id,
                    title=title,
                    content=message_content,
                    attachments=None,
                    sources=sources,
                )
            else:
                message_event = MessageEvent(message=message_content)
                message_event_id = message_event.id
                yield message_event

            suggestions = await self._generate_follow_up_suggestions(
                title=message_title or "Summary",
                content=message_content,
            )
            if suggestions:
                # Emit suggestion with session-anchored metadata
                content_excerpt = message_content[:500] + ("..." if len(message_content) > 500 else "")
                yield SuggestionEvent(
                    suggestions=suggestions,
                    source="completion",
                    anchor_event_id=report_event_id or message_event_id,
                    anchor_excerpt=content_excerpt,
                )

        except asyncio.CancelledError:
            logger.info("Summarization cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            yield ErrorEvent(error=f"Failed to generate summary: {e!s}")

    def _get_last_stream_metadata(self) -> dict[str, Any]:
        """Safely read stream metadata from the LLM adapter."""
        metadata = getattr(self.llm, "last_stream_metadata", None)
        if isinstance(metadata, dict):
            return metadata
        return {}

    def _build_continuation_prompt(self) -> str:
        """Prompt used when stream truncation is detected."""
        return (
            "Your previous response was truncated by token limits. Continue exactly where you stopped, "
            "without repeating prior sections. Complete any unfinished heading, list, or code block."
        )

    def _merge_stream_continuation(self, base_text: str, continuation_text: str) -> str:
        """Merge continuation output while avoiding duplicated overlap."""
        base = base_text or ""
        continuation = continuation_text or ""

        if not continuation.strip():
            return base
        if not base.strip():
            return continuation
        if continuation in base:
            return base
        if base in continuation and len(continuation) >= int(len(base) * 0.8):
            return continuation

        base_tail = base[-4000:]
        continuation_head = continuation[:4000]
        max_overlap = min(len(base_tail), len(continuation_head), 1200)
        min_overlap = 80

        for overlap_size in range(max_overlap, min_overlap - 1, -1):
            if base_tail[-overlap_size:] == continuation_head[:overlap_size]:
                return base + continuation[overlap_size:]

        if base.endswith("\n") or continuation.startswith("\n"):
            return base + continuation
        return base + "\n" + continuation

    def _collapse_duplicate_report_payload(self, content: str) -> str:
        """Collapse duplicate full-report payloads caused by continuation retries."""
        normalized = (content or "").strip()
        if len(normalized) < 300:
            return normalized

        heading_matches = list(self._REPORT_H1_RE.finditer(normalized))
        if len(heading_matches) < 2:
            return normalized

        first_heading = heading_matches[0]
        first_title = first_heading.group(1).strip().lower()

        duplicate_heading = None
        for heading in heading_matches[1:]:
            if heading.group(1).strip().lower() == first_title:
                duplicate_heading = heading
                break

        if duplicate_heading is None:
            return normalized

        first_index = first_heading.start()
        duplicate_index = duplicate_heading.start()
        if duplicate_index <= first_index:
            return normalized

        first_block = normalized[first_index:duplicate_index].strip()
        second_block = normalized[duplicate_index:].strip()
        if len(second_block) < 200:
            return normalized

        first_score = self._report_quality_score(first_block)
        second_score = self._report_quality_score(second_block)
        chosen_block = second_block if (second_score < first_score) else first_block
        if second_score == first_score and len(second_block) >= len(first_block):
            chosen_block = second_block

        prefix = normalized[:first_index].strip()
        if prefix:
            return f"{prefix}\n\n{chosen_block}".strip()
        return chosen_block

    def _report_quality_score(self, report_block: str) -> int:
        """Score report quality; lower score is better."""
        if not report_block:
            return 10_000

        marker_count = len(self._VERIFICATION_TAG_RE.findall(report_block))
        dangling_brackets = abs(report_block.count("[") - report_block.count("]"))
        short_penalty = 1 if len(report_block) < 500 else 0
        return marker_count * 5 + dangling_brackets + short_penalty

    def _run_delivery_integrity_gate(
        self,
        content: str,
        response_policy: ResponsePolicy,
        coverage_result: Any,
        stream_metadata: dict[str, Any],
        truncation_exhausted: bool,
    ) -> tuple[bool, list[str]]:
        """Fail-closed delivery gate for truncation/completeness risks."""
        flags = self._resolve_feature_flags()
        if not flags.get("delivery_integrity_gate", False):
            return True, []

        strict_mode = self._is_integrity_strict_mode(content, response_policy)
        issues: list[str] = []
        warnings: list[str] = []

        finish_reason = str(stream_metadata.get("finish_reason") or "")
        is_stream_truncated = bool(stream_metadata.get("truncated")) or finish_reason == "length"
        if truncation_exhausted:
            issues.append("stream_truncation_unresolved")
        elif is_stream_truncated:
            warnings.append("stream_truncation_detected")

        completeness_result = get_compliance_gates().check_content_completeness(content)
        if completeness_result.status == GateStatus.WARNING:
            if strict_mode:
                issues.append("content_completeness_warning")
            else:
                warnings.append("content_completeness_warning")

        if not getattr(coverage_result, "is_valid", True):
            missing = getattr(coverage_result, "missing_requirements", [])
            if missing:
                # "next step" is forward-looking boilerplate, not a completeness indicator.
                # It should never block delivery — finalization steps have no next step.
                non_blocking = {"next step"}
                blocking_missing = [r for r in missing if r.lower() not in non_blocking]
                warning_only = [r for r in missing if r.lower() in non_blocking]

                if warning_only:
                    warnings.append(f"coverage_missing:{', '.join(warning_only)}")

                # When the stream finished normally (not truncated), coverage misses
                # are likely false positives. Only block on coverage when truncated.
                if blocking_missing:
                    missing_text = ", ".join(blocking_missing)
                    if strict_mode and is_stream_truncated:
                        issues.append(f"coverage_missing:{missing_text}")
                    else:
                        warnings.append(f"coverage_missing:{missing_text}")
            else:
                # is_valid=False with no missing requirements means addresses_user_request
                # failed.  Term-overlap heuristic has high false-positive rate — always warn.
                warnings.append("coverage_relevance_low")

        if warnings:
            logger.warning("Delivery integrity warnings: %s", "; ".join(warnings))

        self._record_delivery_integrity_gate_metrics(
            stream_metadata=stream_metadata,
            strict_mode=strict_mode,
            warnings=warnings,
            issues=issues,
        )

        if issues:
            logger.warning(
                "Delivery integrity gate blocked output (strict_mode=%s): %s",
                strict_mode,
                "; ".join(issues),
            )
            return False, issues

        return True, []

    def _is_integrity_strict_mode(self, content: str, response_policy: ResponsePolicy) -> bool:
        """Enable strict integrity checks for report/evidence-heavy outputs."""
        return (
            response_policy.mode == VerbosityMode.DETAILED
            or "artifact references" in response_policy.min_required_sections
            or self._is_report_structure(content)
        )

    def _can_auto_repair_delivery_integrity(self, issues: list[str]) -> bool:
        """Allow safe remediation for coverage-only misses with deterministic fallbacks."""
        if not issues:
            return False
        if any(issue == "stream_truncation_unresolved" for issue in issues):
            return False
        if not all(issue.startswith("coverage_missing:") for issue in issues):
            return False

        reparable_requirements = {"final result", "artifact references", "key caveat", "next step"}
        missing = self._extract_missing_coverage_requirements(issues)
        return bool(missing) and missing.issubset(reparable_requirements)

    def _extract_missing_coverage_requirements(self, issues: list[str]) -> set[str]:
        """Extract normalized missing requirement labels from gate issues."""
        missing: set[str] = set()
        for issue in issues:
            if not issue.startswith("coverage_missing:"):
                continue
            raw_requirements = issue.split(":", 1)[1]
            for item in raw_requirements.split(","):
                normalized = item.strip().lower()
                if normalized:
                    missing.add(normalized)
        return missing

    def _append_delivery_integrity_fallback(self, content: str, issues: list[str]) -> str:
        """Append deterministic fallback sections for reparable coverage misses."""
        missing = self._extract_missing_coverage_requirements(issues)
        sections: list[str] = []

        if "final result" in missing:
            sections.append("## Final Result\nThe requested work has been completed as summarized above.")
        if "artifact references" in missing:
            sections.append("## Artifact References\n- No file artifacts were created or referenced in this response.")
        if "key caveat" in missing:
            sections.append("## Key Caveat\n- Validate the output with targeted checks before relying on it.")
        if "next step" in missing:
            sections.append(
                "## Next Step\n1. Execute the highest-priority remaining action, then verify the outcome with "
                "targeted checks."
            )

        if not sections:
            return content
        return f"{content}\n\n" + "\n\n".join(sections) + "\n"

    def _record_delivery_integrity_gate_metrics(
        self,
        stream_metadata: dict[str, Any],
        strict_mode: bool,
        warnings: list[str],
        issues: list[str],
    ) -> None:
        """Record delivery-integrity gate outcomes with low-cardinality labels."""
        provider = self._normalize_metric_label(
            str(stream_metadata.get("provider") or getattr(self.llm, "provider", "unknown")),
            fallback="unknown",
        )
        strict_label = "true" if strict_mode else "false"
        result = "blocked" if issues else "passed"

        _metrics.record_counter(
            "delivery_integrity_gate_result_total",
            labels={"provider": provider, "result": result, "strict_mode": strict_label},
        )
        for warning in warnings:
            _metrics.record_counter(
                "delivery_integrity_gate_warning_total",
                labels={
                    "provider": provider,
                    "reason": self._normalize_integrity_reason(warning),
                    "strict_mode": strict_label,
                },
            )
        for issue in issues:
            _metrics.record_counter(
                "delivery_integrity_gate_block_reason_total",
                labels={
                    "provider": provider,
                    "reason": self._normalize_integrity_reason(issue),
                    "strict_mode": strict_label,
                },
            )

    def _record_stream_truncation_metric(self, stream_metadata: dict[str, Any], outcome: str) -> None:
        """Record stream truncation lifecycle events for tuning retries."""
        provider = self._normalize_metric_label(
            str(stream_metadata.get("provider") or getattr(self.llm, "provider", "unknown")),
            fallback="unknown",
        )
        finish_reason = self._normalize_metric_label(str(stream_metadata.get("finish_reason") or "unknown"))
        _metrics.record_counter(
            "delivery_integrity_stream_truncation_total",
            labels={"provider": provider, "finish_reason": finish_reason, "outcome": outcome},
        )

    def _normalize_integrity_reason(self, reason: str) -> str:
        """Normalize a gate issue/warning reason for metric labels."""
        base_reason = (reason or "").split(":", 1)[0]
        return self._normalize_metric_label(base_reason, fallback="unknown")

    def _normalize_metric_label(self, value: str, fallback: str = "unknown") -> str:
        """Convert label values to predictable, low-cardinality token format."""
        raw = (value or "").strip().lower()
        if not raw:
            return fallback

        normalized_chars = [char if char.isalnum() else "_" for char in raw]
        normalized = "".join(normalized_chars).strip("_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized or fallback

    def _extract_title(self, content: str) -> str:
        """Extract a title from markdown content."""
        import re

        lines = content.strip().split("\n")

        # Try to find h1 heading
        for line in lines[:10]:  # Check first 10 lines
            h1_match = re.match(r"^#\s+(.+)$", line.strip())
            if h1_match:
                return h1_match.group(1).strip()

        # Try to find h2 heading
        for line in lines[:10]:
            h2_match = re.match(r"^##\s+(.+)$", line.strip())
            if h2_match:
                return h2_match.group(1).strip()

        # Fallback: use first non-empty line, truncated
        for line in lines[:5]:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # Remove markdown formatting and truncate
                clean = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                clean = re.sub(r"\*(.+?)\*", r"\1", clean)
                return clean[:80] + ("..." if len(clean) > 80 else "")

        return "Task Report"

    # Pre-compiled patterns for _clean_report_content (module-level would be
    # cleaner but keeping them close to usage for clarity).
    _TOOL_CALL_RE = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL)
    _FUNCTION_CALL_RE = re.compile(r"<function_call>.*?</function_call>", re.DOTALL)
    _BOILERPLATE_FINAL_RESULT_RE = re.compile(
        r"##\s*Final Result\s*\n+"
        r"(?:The requested work has been completed[^\n]*\n*)+",
    )
    _BOILERPLATE_ARTIFACT_REFS_RE = re.compile(
        r"##\s*Artifact References?\s*\n+"
        r"(?:-\s*No (?:file )?artifacts? (?:were |was )[^\n]*\n*)+",
    )
    _EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
    _REPORT_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
    _VERIFICATION_TAG_RE = re.compile(r"\[(?:unverified|verified|not verified)[^\]]*\]?", re.IGNORECASE)

    # Pattern matching JSON tool result objects (possibly wrapped in ```json blocks)
    _JSON_CODEBLOCK_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\s*\n?```$", re.DOTALL)

    def _clean_report_content(self, content: str) -> str:
        """Strip hallucinated tool-call XML, JSON tool results, and boilerplate.

        During summarization the LLM sometimes reproduces tool-call XML from
        earlier conversation history (e.g. ``<tool_call>file_read...</tool_call>``)
        and appends boilerplate sections ("Final Result", "Artifact References")
        instead of actual report content.

        It may also echo raw JSON tool results (e.g. from file_write) like:
        ``{"success": true, "result": "...", "attachments": [...]}``
        This method detects that pattern and replaces it with actual report
        content extracted from the agent's conversation memory.
        """
        if not content:
            return content

        original_len = len(content)

        # 0. Detect JSON tool result objects echoed by the LLM during summarization.
        #    If the entire content is a JSON tool result, recover the actual report
        #    from the file_write tool call arguments in conversation memory.
        cleaned = self._resolve_json_tool_result(content)
        if cleaned != content:
            logger.info(
                "Resolved JSON tool result (%d chars) to actual report content (%d chars)",
                len(content),
                len(cleaned),
            )
            # Re-run remaining cleanup on the resolved content
            content = cleaned

        # 1. Strip <tool_call>...</tool_call> and <function_call>...</function_call> blocks
        cleaned = self._TOOL_CALL_RE.sub("", content)
        cleaned = self._FUNCTION_CALL_RE.sub("", cleaned)

        # 2. Strip boilerplate sections with generic/empty content
        cleaned = self._BOILERPLATE_FINAL_RESULT_RE.sub("", cleaned)
        cleaned = self._BOILERPLATE_ARTIFACT_REFS_RE.sub("", cleaned)

        # 3. Collapse excess blank lines left by removals
        cleaned = self._EXCESS_BLANK_LINES_RE.sub("\n\n", cleaned)
        cleaned = cleaned.strip()

        removed = original_len - len(cleaned)
        if removed > 0:
            logger.info(
                "Cleaned %d chars of hallucinated tool-call XML / boilerplate from report content",
                removed,
            )

        return cleaned

    def _extract_fallback_summary(self) -> str:
        """Extract a fallback summary from the agent's conversation memory.

        Scans assistant messages in reverse for substantive content that can
        serve as a degraded-but-usable summary when the summarization LLM call
        produces no usable output.

        Returns:
            A string with fallback content, or empty string if nothing usable found.
        """
        if not self.memory:
            return ""

        messages = self.memory.get_messages()
        # Walk backwards through assistant messages looking for substantial content
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if not content or len(content) < 50:
                continue
            # Skip messages that are just tool-call XML
            cleaned = self._TOOL_CALL_RE.sub("", content)
            cleaned = self._FUNCTION_CALL_RE.sub("", cleaned).strip()
            if len(cleaned) >= 50:
                logger.info(
                    "Extracted fallback summary from conversation memory (%d chars)",
                    len(cleaned),
                )
                return f"# Task Summary\n\n{cleaned}"

        return ""

    def _resolve_json_tool_result(self, content: str) -> str:
        """If content is a JSON tool result, recover the actual report content.

        Some LLMs echo the raw tool result JSON during summarization instead of
        writing a proper report. For example::

            {
                "success": true,
                "result": "Delivered professional research report...",
                "attachments": ["/workspace/report.md"],
            }

        This method detects that pattern and:
        1. Searches conversation memory for the file_write tool call that produced
           the result, extracting the actual markdown content from its arguments.
        2. Falls back to the ``result`` description string if memory search fails.

        Returns the original content unchanged if it's not a JSON tool result.
        """
        stripped = content.strip()

        # Unwrap ```json ... ``` code blocks
        codeblock_match = self._JSON_CODEBLOCK_RE.match(stripped)
        if codeblock_match:
            stripped = codeblock_match.group(1).strip()

        # Quick check: must look like a JSON object
        if not (stripped.startswith("{") and stripped.endswith("}")):
            return content

        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return content

        # Must be a tool result dict with "success" key
        if not isinstance(parsed, dict) or "success" not in parsed:
            return content

        logger.warning(
            "Summarization output is a JSON tool result (success=%s), recovering actual report content",
            parsed.get("success"),
        )

        # Strategy 1: Search conversation memory for the file_write call that
        # produced this result.  The actual report markdown is in the tool call's
        # ``content`` argument.
        report_from_memory = self._extract_report_from_file_write_memory()
        if report_from_memory:
            return report_from_memory

        # Strategy 2: Use the ``result`` description string as fallback
        result_text = parsed.get("result", "")
        if isinstance(result_text, str) and len(result_text.strip()) > 30:
            logger.info("Using tool result 'result' field as fallback report content")
            return result_text.strip()

        # Strategy 3: Return empty so the caller can handle the failure
        return ""

    def _extract_report_from_file_write_memory(self) -> str | None:
        """Search conversation memory for the last file_write tool call with markdown content.

        Scans messages in reverse order looking for an assistant message with a
        ``file_write`` or ``file_create`` tool call whose arguments include a
        ``content`` field containing substantial markdown (>200 chars).

        Returns the extracted markdown content, or None if not found.
        """
        if not self.memory:
            return None

        messages = self.memory.get_messages()

        # Walk messages in reverse to find the most recent file_write call
        for msg in reversed(messages):
            tool_calls = msg.get("tool_calls")
            if not tool_calls or msg.get("role") != "assistant":
                continue

            for tc in tool_calls:
                func = tc.get("function", {})
                func_name = func.get("name", "")
                if func_name not in ("file_write", "file_create"):
                    continue

                # Parse the arguments JSON
                args_str = func.get("arguments", "")
                if not args_str:
                    continue

                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, ValueError):
                    continue

                file_content = args.get("content", "")
                file_path = args.get("path", "")

                # Only recover markdown files with substantial content
                if (
                    isinstance(file_content, str)
                    and len(file_content.strip()) > 200
                    and isinstance(file_path, str)
                    and file_path.endswith(".md")
                ):
                    logger.info(
                        "Recovered report content from file_write memory (path=%s, %d chars)",
                        file_path,
                        len(file_content),
                    )
                    return file_content.strip()

        return None

    async def _generate_confirmation_summary(self, report_content: str, title: str | None) -> str | None:
        """Generate a brief confirmation message summarizing key findings.

        Emitted as a MessageEvent before the ReportEvent so the user sees
        a quick overview above the full report preview.
        """
        try:
            # Use first ~2000 chars to keep the prompt small
            excerpt = report_content[:2000]
            prompt = CONFIRMATION_SUMMARY_PROMPT.format(report_content=excerpt)
            response = await self.llm.ask(
                [{"role": "user", "content": prompt}],
                tools=None,
                tool_choice=None,
            )
            confirmation = response.get("content", "")
            if isinstance(confirmation, str) and len(confirmation.strip()) > 30:
                return confirmation.strip()
        except Exception as e:
            logger.debug(f"Confirmation summary generation failed: {e}")
        return None

    async def _generate_follow_up_suggestions(self, title: str, content: str) -> list[str]:
        """Generate follow-up suggestions grounded in session context.

        Enriches suggestion generation with:
        - Original user request
        - Completion title
        - Bounded content excerpt (first 500 chars)

        Args:
            title: Report title
            content: Full report content

        Returns:
            List of 3 contextual suggestion strings
        """
        try:
            # Build session-contextual prompt
            user_request_context = f'User request: "{self._user_request}"\n' if self._user_request else ""
            content_excerpt = content[:500] + ("..." if len(content) > 500 else "")
            recent_session_context = self._build_recent_memory_context_excerpt()
            recent_context_block = (
                f"Recent session context:\n{recent_session_context}\n\n" if recent_session_context else ""
            )

            suggestion_response = await self.llm.ask(
                [
                    {
                        "role": "user",
                        "content": (
                            f"{user_request_context}"
                            f"{recent_context_block}"
                            f'Completion title: "{title}"\n'
                            f"Summary excerpt: {content_excerpt}\n\n"
                            "Generate exactly 3 short follow-up questions (5-15 words each) that are grounded "
                            "in the actual completion results and user's original request. "
                            "Suggestions should help the user explore next steps or dive deeper into specific aspects. "
                            'Return ONLY a JSON object in this format: {"suggestions": ["...", "...", "..."]}.'
                        ),
                    }
                ],
                tools=None,
                response_format={"type": "json_object"},
                tool_choice=None,
            )
            raw = suggestion_response.get("content", {"suggestions": []})
            suggestions = self._parse_suggestions_payload(raw)
            normalized = [str(s).strip() for s in suggestions if str(s).strip()]
            if normalized:
                return normalized[:3]
        except Exception as e:
            logger.debug(f"Suggestion generation failed, using fallback suggestions: {e}")

        return self._default_follow_up_suggestions(title=title, content=content)

    def _default_follow_up_suggestions(self, title: str, content: str) -> list[str]:
        """Deterministic fallback suggestions used when LLM suggestion generation fails."""
        combined = f"{title} {content}".lower()
        if "pirate" in combined or "arrr" in combined:
            return [
                "Tell me a pirate story.",
                "What's your favorite pirate saying?",
                "How do pirates find treasure?",
            ]

        topic_hint = self._extract_topic_hint(f"{self._user_request or ''} {title} {content}")
        if topic_hint:
            return [
                f"Can you expand on {topic_hint} with a concrete example?",
                f"What should I prioritize next for {topic_hint}?",
                f"What risks should I watch for with {topic_hint}?",
            ]

        return [
            "Can you summarize this in three key points?",
            "What should I prioritize as next steps?",
            "Can you provide a practical example for this?",
        ]

    def _parse_suggestions_payload(self, payload: Any) -> list[str]:
        """Parse suggestion payload from LLM output using strict validation first."""
        if isinstance(payload, str):
            try:
                return _SuggestionPayload.model_validate_json(payload).suggestions
            except ValidationError:
                return _SUGGESTION_LIST_ADAPTER.validate_json(payload)

        if isinstance(payload, dict):
            return _SuggestionPayload.model_validate(payload).suggestions

        if isinstance(payload, list):
            return _SUGGESTION_LIST_ADAPTER.validate_python(payload)

        raise TypeError("Unsupported suggestion payload type")

    def _apply_step_result_payload(self, step: Step, parsed_response: Any, raw_message: str) -> bool:
        """Apply execution step payload with strict schema validation and safe fallback."""
        try:
            step_result = ExecutionStepResult.model_validate(parsed_response)
            step.success = step_result.success
            step.result = step_result.result or raw_message
            step.attachments = list(step_result.attachments)
            step.error = None if step_result.success else (step.error or "Step reported failure")
            return True
        except ValidationError as validation_err:
            logger.warning(f"Step response validation failed: {validation_err}")

        # Best-effort extraction for partially structured payloads.
        if isinstance(parsed_response, dict) and any(
            key in parsed_response for key in ("success", "result", "attachments")
        ):
            success_value = parsed_response.get("success")
            step.success = success_value if isinstance(success_value, bool) else False

            result_value = parsed_response.get("result")
            step.result = str(result_value) if result_value is not None else raw_message

            attachments_value = parsed_response.get("attachments")
            if isinstance(attachments_value, list):
                step.attachments = [str(item) for item in attachments_value]
            else:
                step.attachments = []

            if not step.success:
                error_value = parsed_response.get("error")
                step.error = str(error_value) if error_value else "Step payload validation failed"
            return False

        step.success = False
        step.result = raw_message
        step.attachments = []
        step.error = "Step response did not match expected JSON schema"
        return False

    def _build_recent_memory_context_excerpt(self, max_messages: int = 6, max_chars: int = 900) -> str:
        """Build a short user/assistant transcript excerpt from in-memory session messages."""
        if not self.memory:
            return ""

        try:
            messages = self.memory.get_messages()
        except Exception:
            return ""

        if not messages:
            return ""

        lines: list[str] = []
        for entry in reversed(messages):
            if not isinstance(entry, dict):
                continue

            role = str(entry.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue

            raw_content = entry.get("content")
            if isinstance(raw_content, str):
                text = raw_content.strip()
            else:
                text = str(raw_content).strip() if raw_content is not None else ""

            if not text:
                continue

            speaker = "User" if role == "user" else "Assistant"
            lines.append(f"{speaker}: {text[:220]}")
            if len(lines) >= max_messages:
                break

        if not lines:
            return ""

        transcript = "\n".join(reversed(lines))
        return transcript[:max_chars]

    def _extract_topic_hint(self, text: str) -> str | None:
        """Extract a compact topic hint from free text for fallback suggestion templates."""
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        tokens = [token for token in cleaned.split() if len(token) >= 4]
        if not tokens:
            return None

        stopwords = {
            "that",
            "this",
            "with",
            "from",
            "have",
            "what",
            "when",
            "where",
            "which",
            "would",
            "could",
            "should",
            "your",
            "about",
            "into",
            "there",
            "them",
            "then",
            "only",
            "more",
            "next",
        }
        filtered = [token for token in tokens if token not in stopwords]
        candidates = filtered or tokens
        return " ".join(candidates[:3]) if candidates else None

    async def _apply_critic_revision(self, message_content: str, attachments: list[FileInfo]) -> str:
        """Apply critic review with actual revision support.

        This method implements a revision loop that actually improves the output
        based on critic feedback, rather than just appending notes.

        Args:
            message_content: The original message content
            attachments: List of file attachments

        Returns:
            Revised content (or original if approved/revision failed)
        """
        max_revisions = self._critic.config.max_revision_attempts
        current_content = message_content
        revision_count = 0

        while revision_count < max_revisions:
            try:
                review = await self._critic.review_output(
                    user_request=self._user_request,
                    output=current_content,
                    task_context="Task completion summary",
                    files=[f.file_path for f in attachments] if attachments else None,
                )

                logger.info(
                    f"Critic review (attempt {revision_count + 1}): {review.verdict.value} ({review.confidence:.2f})"
                )

                # If approved, return the current content
                if review.verdict == CriticVerdict.APPROVE:
                    logger.debug("Critic approved output")
                    return current_content

                # If rejected, log and return original (can't fix fundamental issues)
                if review.verdict == CriticVerdict.REJECT:
                    logger.warning(f"Critic rejected output: {review.summary}")
                    return current_content

                # If revision needed, actually revise the content
                if review.verdict == CriticVerdict.REVISE and review.issues:
                    revision_count += 1
                    logger.info(f"Critic requested revision {revision_count}: {review.summary}")

                    # Build revision prompt
                    revision_guidance = await self._critic.get_revision_guidance(current_content, review)

                    # Ask LLM to revise the content
                    try:
                        revision_messages = [
                            {
                                "role": "system",
                                "content": (
                                    "You are revising your previous output based on quality feedback. "
                                    "Make the specific improvements requested while preserving the good parts. "
                                    "Return the complete revised output in the same format."
                                ),
                            },
                            {"role": "user", "content": revision_guidance},
                        ]

                        response = await self.llm.ask(revision_messages, tools=None, tool_choice=None)

                        revised_content = response.get("content", "")
                        if revised_content and len(revised_content) > 100:
                            logger.info(
                                f"Revision {revision_count} applied "
                                f"(original: {len(current_content)} chars, "
                                f"revised: {len(revised_content)} chars)"
                            )
                            current_content = revised_content
                        else:
                            logger.warning("Revision produced insufficient content, keeping original")
                            break

                    except Exception as e:
                        logger.warning(f"Revision attempt failed: {e}")
                        break
                else:
                    # No issues identified, accept current content
                    break

            except Exception as e:
                logger.warning(f"Critic review failed (continuing with current content): {e}")
                break

        # If we exhausted revisions, add a note about best-effort improvement
        if revision_count >= max_revisions:
            logger.info(f"Max revisions ({max_revisions}) reached, delivering best version")

        return current_content

    async def _apply_hallucination_verification(self, content: str, query: str) -> str:
        """Apply hallucination verification using LettuceDetect (or CoVe fallback).

        LettuceDetect uses a ModernBERT encoder to classify each token in the
        answer as supported or hallucinated, grounded against collected source
        context. This runs in ~100ms with zero LLM calls.

        Falls back to CoVe if LettuceDetect is disabled or unavailable.

        Args:
            content: The content to verify.
            query: Original user query for context.

        Returns:
            Verified content (hallucinated spans redacted if detected).
        """
        flags = self._resolve_feature_flags()

        # Try LettuceDetect first (preferred: fast, no LLM cost)
        if self._lettuce_enabled and flags.get("lettuce_verification", True):
            try:
                from app.domain.services.agents.lettuce_verifier import get_lettuce_verifier

                verifier = get_lettuce_verifier()

                # Build grounding context from collected sources
                source_context = self._build_source_context()

                result = verifier.verify(
                    context=source_context,
                    question=query,
                    answer=content,
                )

                if not result.skipped and result.has_hallucinations:
                    logger.warning(
                        "LettuceDetect: %d hallucinated span(s), confidence: %.2f, ratio: %.1f%%",
                        len(result.hallucinated_spans),
                        result.confidence_score,
                        result.hallucination_ratio * 100,
                    )
                    self._context_manager.add_insight(
                        insight_type=InsightType.ERROR_LEARNING,
                        content=(
                            f"LettuceDetect found {len(result.hallucinated_spans)} hallucinated span(s) "
                            f"({result.hallucination_ratio:.1%} of text)"
                        ),
                        confidence=0.9,
                        tags=["hallucination", "lettuce", "verification"],
                    )

                    # Record Prometheus metric
                    _metrics.increment(
                        "pythinker_hallucination_detections_total",
                        labels={
                            "method": "lettuce",
                            "span_count": str(len(result.hallucinated_spans)),
                        },
                    )

                    # Do NOT inline-replace with verification tags — that
                    # breaks markdown tables, sentences, and structured output.
                    # Instead, append a brief disclaimer when the hallucination
                    # ratio is significant enough to warrant user notice.
                    if result.hallucination_ratio > 0.2:
                        disclaimer = (
                            "\n\n> **Note:** Some information in this response "
                            "could not be fully verified against available sources."
                        )
                        return content + disclaimer
                    return content

                if not result.skipped:
                    logger.info("LettuceDetect: %s", result.get_summary())

                return content

            except Exception as e:
                logger.warning("LettuceDetect failed, falling back to CoVe: %s", e)

        # Fallback: CoVe (deprecated, disabled by default)
        if self._cove_enabled and flags.get("chain_of_verification", False):
            verified, _ = await self._apply_cove_verification(content, query)
            return verified

        return content

    def _build_source_context(self) -> list[str]:
        """Build grounding context from collected sources for hallucination verification.

        Returns each source snippet as a separate list element — LettuceDetect's
        predict() API expects list[str] where each item is an independent
        context chunk. Truncation to 4K total chars is handled by LettuceVerifier.

        Returns:
            List of source context strings.
        """
        if not self._collected_sources:
            return []

        chunks: list[str] = []
        for source in self._collected_sources:
            snippet = source.snippet or ""
            if snippet.strip():
                chunks.append(snippet)

        return chunks

    def _needs_verification(self, content: str, query: str) -> bool:
        """Determine if content needs hallucination verification.

        Delegates to _needs_cove_verification which contains the heuristic
        for detecting research/factual/comparative content.
        """
        return self._needs_cove_verification(content, query)

    async def _apply_cove_verification(self, content: str, query: str) -> tuple[str, CoVeResult | None]:
        """Apply Chain-of-Verification to reduce hallucinations in factual content.

        CoVe works by:
        1. Generating verification questions for key claims
        2. Answering those questions independently (without seeing original)
        3. Revising the response based on verification results

        This is particularly effective for:
        - Research tasks with specific metrics/benchmarks
        - Comparative analyses (where data asymmetry often occurs)
        - Factual summaries with dates, numbers, or statistics

        Args:
            content: The content to verify
            query: Original user query for context

        Returns:
            Tuple of (verified_content, CoVeResult or None if skipped)
        """
        if not self._cove_enabled:
            return content, None

        # Check feature flags
        flags = self._resolve_feature_flags()
        if not flags.get("chain_of_verification", True):
            return content, None

        # Detect if this is a factual/research task that needs verification
        if not self._needs_cove_verification(content, query):
            logger.debug("CoVe: Skipping - content doesn't require verification")
            return content, None

        try:
            logger.info("CoVe: Starting verification pipeline...")
            result = await self._cove.verify_and_refine(
                query=query,
                response=content,
                skip_if_short=True,
            )

            if result.has_contradictions:
                logger.warning(
                    f"CoVe: Found {result.claims_contradicted} contradictions, "
                    f"confidence: {result.confidence_score:.2f}"
                )
                # Record insight about hallucination detection
                self._context_manager.add_insight(
                    insight_type=InsightType.ERROR_LEARNING,
                    content=f"CoVe detected {result.claims_contradicted} contradicted claims",
                    confidence=0.9,
                    tags=["hallucination", "cove", "verification"],
                )
                return result.verified_response, result
            if result.claims_uncertain > 0:
                logger.info(
                    f"CoVe: {result.claims_verified} verified, "
                    f"{result.claims_uncertain} uncertain, "
                    f"confidence: {result.confidence_score:.2f}"
                )
                # If many uncertain claims, still use refined response
                if result.claims_uncertain > result.claims_verified:
                    return result.verified_response, result
            else:
                logger.info(
                    f"CoVe: All {result.claims_verified} claims verified, confidence: {result.confidence_score:.2f}"
                )

            return content, result

        except Exception as e:
            logger.warning(f"CoVe verification failed (continuing with original): {e}")
            return content, None

    def _needs_cove_verification(self, content: str, query: str) -> bool:
        """Determine if content needs Chain-of-Verification.

        We apply CoVe selectively to:
        - Research/factual tasks (not creative writing)
        - Content with specific metrics, benchmarks, or statistics
        - Comparative analyses (high risk of data asymmetry)
        - Content over a minimum length threshold

        Args:
            content: Content to potentially verify
            query: Original query for context

        Returns:
            True if content should be verified
        """
        # Length threshold — lowered to catch hallucinations in shorter responses
        if len(content) < 200:
            return False

        query_lower = query.lower() if query else ""
        content_lower = content.lower()

        # Research/factual task indicators
        research_indicators = [
            "research",
            "analyze",
            "compare",
            "benchmark",
            "statistics",
            "study",
            "report",
            "data",
            "metrics",
            "performance",
            "evaluate",
            "assessment",
            "findings",
            "results",
        ]

        # Comparative task indicators (high hallucination risk)
        comparison_indicators = [
            "compare",
            "comparison",
            "versus",
            " vs ",
            " vs.",
            "difference",
            "better than",
            "worse than",
            "ranking",
            "ranked",
            "top ",
        ]

        # Metric/number patterns in content
        import re

        has_percentages = bool(re.search(r"\d+(\.\d+)?%", content))
        has_benchmarks = any(
            bench in content_lower for bench in ["mmlu", "humaneval", "gsm8k", "hellaswag", "arc", "winogrande"]
        )
        has_dates = bool(re.search(r"\b20\d{2}\b", content))

        # Decision logic
        is_research_task = any(ind in query_lower for ind in research_indicators)
        is_comparison = any(ind in query_lower or ind in content_lower for ind in comparison_indicators)
        has_factual_claims = has_percentages or has_benchmarks or has_dates

        # Apply CoVe if:
        # 1. It's a research task with factual claims, OR
        # 2. It's a comparison (high data asymmetry risk), OR
        # 3. It has benchmarks (often hallucinated)
        should_verify = (is_research_task and has_factual_claims) or is_comparison or has_benchmarks

        if should_verify:
            logger.debug(
                f"CoVe needed: research={is_research_task}, comparison={is_comparison}, "
                f"factual={has_factual_claims}, benchmarks={has_benchmarks}"
            )

        return should_verify

    def _is_report_structure(self, content: str) -> bool:
        """Check if content has report-like structure (headings, sections)."""
        import re

        if not content:
            return False

        # Check for markdown headings (##, ###, etc.)
        heading_count = len(re.findall(r"^#{1,4}\s+.+", content, re.MULTILINE))
        if heading_count >= 2:
            return True

        # Check for bold section headers pattern (e.g., **Section:**)
        bold_headers = len(re.findall(r"\*\*[^*]+:\*\*", content))
        if bold_headers >= 2:
            return True

        # Check for numbered sections (1. Section, 2. Section)
        numbered_sections = len(re.findall(r"^\d+\.\s+[A-Z]", content, re.MULTILINE))
        return numbered_sections >= 2

    # Context Manager Integration (Phase 1)
    def get_context_manager(self) -> ContextManager:
        """Get the context manager for this execution agent.

        Returns:
            ContextManager instance tracking execution context
        """
        return self._context_manager

    def mark_deliverable(self, file_path: str) -> None:
        """Mark a file as a deliverable.

        Args:
            file_path: Path to the deliverable file
        """
        self._context_manager.mark_deliverable_complete(file_path)
        logger.info(f"Marked deliverable: {file_path}")

    def get_deliverables(self) -> list[str]:
        """Get list of completed deliverables.

        Returns:
            List of deliverable file paths
        """
        return self._context_manager.get_deliverables()

    def clear_context(self) -> None:
        """Clear execution context (use between tasks)."""
        self._context_manager.clear()
        self._collected_sources = []
        self._seen_urls = set()
        self._view_operation_count = 0
        self._multimodal_findings = []
        logger.debug("Cleared execution context")

    # Attention Injection (Pythinker AI Pattern)
    def _apply_attention(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply attention injection to messages.

        Implements Pythinker AI's attention manipulation pattern to
        prevent goal drift in long conversations.

        Args:
            messages: The current message history.

        Returns:
            Messages with attention context injected.
        """
        return self._attention_injector.inject(
            messages,
            goal=self.current_goal,
            todo=self.current_todo,
        )

    # Multimodal Information Persistence (P5.2 - Pythinker Pattern)
    def _track_multimodal_findings(self, event: ToolEvent) -> None:
        """Track and persist key findings from view operations.

        Per Pythinker pattern: save key findings every 2 view/browser operations.
        This ensures important visual information is persisted and available
        for later reference even if context is compressed.

        Args:
            event: ToolEvent from a view operation
        """
        if event.function_name not in self._view_tools:
            return

        if not event.function_result or not event.function_result.success:
            return

        # Increment view operation counter
        self._view_operation_count += 1

        # Extract key findings from the view result
        finding = self._extract_multimodal_finding(event)
        if finding:
            self._multimodal_findings.append(finding)

        # Persist every 2 operations (Pythinker pattern)
        if self._view_operation_count >= 2:
            self._persist_key_findings()
            self._view_operation_count = 0

    def _extract_multimodal_finding(self, event: ToolEvent) -> dict | None:
        """Extract structured finding from a view operation.

        Args:
            event: ToolEvent containing view results

        Returns:
            Dict with finding data, or None if no significant finding
        """
        if not event.function_result:
            return None

        # ToolResult uses 'data' for the typed result and 'message' for text
        # Handle both ToolResult and raw string/dict results
        func_result = event.function_result
        if hasattr(func_result, "data"):
            data = func_result.data or {}
            result = (
                func_result.message
                if hasattr(func_result, "message")
                else str(func_result.data)
                if func_result.data
                else ""
            )
        elif hasattr(func_result, "result"):
            # Legacy result format
            result = func_result.result
            data = {}
        else:
            # Raw result (string, dict, etc.)
            result = str(func_result) if func_result else ""
            data = func_result if isinstance(func_result, dict) else {}

        # Build finding structure
        finding = {
            "tool": event.function_name,
            "timestamp": event.started_at.isoformat() if event.started_at else None,
            "source": event.function_args.get("file") or event.function_args.get("url", ""),
        }

        # Extract content based on tool type
        if event.function_name == "file_view":
            # File view findings
            finding["type"] = "file_view"
            finding["file_type"] = data.get("file_type", "unknown") if isinstance(data, dict) else "unknown"
            finding["content_preview"] = result[:500] if result else ""

            # Include extracted text for documents
            if isinstance(data, dict) and data.get("extracted_text"):
                finding["extracted_text"] = data["extracted_text"][:1000]

        elif event.function_name in {"browser_view", "browser_get_content"}:
            # Browser view findings
            finding["type"] = "browser_view"
            finding["url"] = event.function_args.get("url", "")
            finding["content_preview"] = result[:500] if result else ""

        elif event.function_name == "browser_agent_extract":
            # Browser extraction findings
            finding["type"] = "extraction"
            finding["extraction_goal"] = event.function_args.get("goal", "")
            finding["result"] = result[:1000] if result else ""

        return finding if finding.get("content_preview") or finding.get("result") else None

    def _persist_key_findings(self) -> None:
        """Persist accumulated multimodal findings.

        Adds findings to context manager for long-term availability
        and optionally stores in memory service.
        """
        if not self._multimodal_findings:
            return

        # Format findings for context
        findings_text = self._format_findings_for_context()

        # Add to context manager as important observation
        self._context_manager.add_observation(
            observation_type="multimodal_findings",
            content=findings_text,
            importance=0.8,  # High importance for visual findings
        )

        # Clear findings after persistence
        self._multimodal_findings = []
        logger.debug("Persisted multimodal findings to context")

    def _format_findings_for_context(self) -> str:
        """Format multimodal findings as a context string.

        Returns:
            Formatted string of findings for context injection
        """
        if not self._multimodal_findings:
            return ""

        parts = ["## Key Visual Findings\n"]

        for i, finding in enumerate(self._multimodal_findings, 1):
            finding_type = finding.get("type", "view")
            source = finding.get("source") or finding.get("url", "")

            parts.append(f"### Finding {i}: {finding_type}")
            if source:
                parts.append(f"**Source:** {source}")

            if finding.get("content_preview"):
                parts.append(f"**Preview:** {finding['content_preview'][:300]}...")
            elif finding.get("result"):
                parts.append(f"**Result:** {finding['result'][:300]}...")

            if finding.get("extracted_text"):
                parts.append(f"**Text:** {finding['extracted_text'][:200]}...")

            parts.append("")

        return "\n".join(parts)

    def get_multimodal_findings(self) -> list[dict]:
        """Get accumulated multimodal findings.

        Returns:
            List of finding dictionaries
        """
        return self._multimodal_findings.copy()

    # Source Citation Tracking
    def _track_sources_from_tool_event(self, event: ToolEvent) -> None:
        """Extract and track source citations from tool events.

        Collects URLs and titles from search results and browser navigation
        to build a bibliography for the final report.

        Args:
            event: ToolEvent that completed execution
        """
        if not event.function_result or not event.function_result.success:
            return

        access_time = event.started_at or datetime.now(UTC)

        # Extract sources from search results
        if event.function_name == "info_search_web":
            self._extract_search_sources(event, access_time)

        # Extract sources from browser navigation
        elif event.function_name in ["browser_navigate", "browser_get_content", "browser_view"]:
            self._extract_browser_source(event, access_time)

    def _extract_search_sources(self, event: ToolEvent, access_time: datetime) -> None:
        """Extract sources from search tool results.

        Args:
            event: Search tool event
            access_time: When the search was performed
        """
        # Try to get results from tool_content (SearchToolContent)
        results = []
        if event.tool_content and hasattr(event.tool_content, "results"):
            results = event.tool_content.results or []
        # Fallback: try to parse from function_result
        elif event.function_result and hasattr(event.function_result, "data"):
            data = event.function_result.data
            if isinstance(data, dict) and "results" in data:
                results = data["results"]
            elif isinstance(data, list):
                results = data

        for result in results:
            # Handle both dict and SearchResultItem objects
            if hasattr(result, "link"):
                url = result.link
                title = result.title
                snippet = getattr(result, "snippet", None)
            elif isinstance(result, dict):
                url = result.get("link") or result.get("url", "")
                title = result.get("title", "")
                snippet = result.get("snippet")
            else:
                continue

            if url and url not in self._seen_urls and len(self._collected_sources) < self._max_collected_sources:
                self._seen_urls.add(url)
                self._collected_sources.append(
                    SourceCitation(
                        url=url,
                        title=title or url,
                        snippet=snippet[:300] if snippet else None,
                        access_time=access_time,
                        source_type="search",
                    )
                )
                # Assign citation index for inline references
                self._citation_counter += 1
                self._url_to_citation[url] = self._citation_counter
                logger.debug(f"Tracked search source [{self._citation_counter}]: {title[:50] if title else url[:50]}")

    def _extract_browser_source(self, event: ToolEvent, access_time: datetime) -> None:
        """Extract source from browser navigation events.

        Args:
            event: Browser tool event
            access_time: When the page was accessed
        """
        url = event.function_args.get("url", "")
        if not url or url in self._seen_urls or len(self._collected_sources) >= self._max_collected_sources:
            return

        # Try to extract title from page content or result
        title = url
        if event.tool_content and hasattr(event.tool_content, "content"):
            content = event.tool_content.content
            if content:
                # Try to extract title from HTML/content
                title = self._extract_title_from_content(content) or url

        self._seen_urls.add(url)
        self._collected_sources.append(
            SourceCitation(url=url, title=title, snippet=None, access_time=access_time, source_type="browser")
        )
        logger.debug(f"Tracked browser source: {title[:50]}")

    def _extract_title_from_content(self, content: str) -> str | None:
        """Extract page title from HTML or text content.

        Args:
            content: Page content (HTML or text)

        Returns:
            Extracted title or None
        """
        import re

        # Try to find HTML title tag
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", content, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()[:200]

        # Try to find first h1 tag
        h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", content, re.IGNORECASE)
        if h1_match:
            return h1_match.group(1).strip()[:200]

        # Try to find first markdown h1
        md_h1_match = re.match(r"^#\s+(.+)$", content, re.MULTILINE)
        if md_h1_match:
            return md_h1_match.group(1).strip()[:200]

        return None

    def _track_parallel_research_source(self, url: str, query: str) -> None:
        """Track a source discovered during parallel research execution.

        Called by PlanActFlow._execute_parallel_research_steps() to register
        sources from the WideResearchOrchestrator into the executor's citation
        index, so they appear in the final report.

        Args:
            url: Source URL
            query: The search query that discovered this source
        """
        if not url or url in self._seen_urls or len(self._collected_sources) >= self._max_collected_sources:
            return

        self._seen_urls.add(url)

        # Assign citation index
        self._citation_counter += 1
        self._url_to_citation[url] = self._citation_counter

        self._collected_sources.append(
            SourceCitation(
                url=url,
                title=query[:100],
                snippet=None,
                access_time=datetime.now(UTC),
                source_type="search",
            )
        )

    def _build_numbered_source_list(self) -> str:
        """Build a numbered source list for citation-aware summarization.

        Returns:
            Formatted string like:
            [1] Title - URL
            [2] Title - URL
        """
        lines = []
        for i, source in enumerate(self._collected_sources, start=1):
            title = source.title or source.url
            lines.append(f"[{i}] {title} - {source.url}")
            # Ensure url_to_citation mapping is up to date
            if source.url not in self._url_to_citation:
                self._url_to_citation[source.url] = i
        return "\n".join(lines)

    def get_collected_sources(self) -> list[SourceCitation]:
        """Get all collected source citations.

        Returns:
            List of deduplicated source citations
        """
        return self._collected_sources.copy()
