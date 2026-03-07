import asyncio
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, TypeAdapter

from app.domain.external.llm import LLM
from app.domain.external.observability import MetricsPort, get_null_metrics
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
from app.domain.models.tool_name import ToolName
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.chain_of_verification import ChainOfVerification, CoVeResult
from app.domain.services.agents.context_manager import ContextManager, InsightType
from app.domain.services.agents.critic import CriticAgent, CriticConfig
from app.domain.services.agents.output_coverage_validator import OutputCoverageValidator
from app.domain.services.agents.output_verifier import OutputVerifier
from app.domain.services.agents.prompt_adapter import PromptAdapter
from app.domain.services.agents.report_output_sanitizer import sanitize_report_output
from app.domain.services.agents.response_compressor import ResponseCompressor
from app.domain.services.agents.response_generator import ResponseGenerator
from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode
from app.domain.services.agents.reward_scoring import RewardScorer
from app.domain.services.agents.source_tracker import SourceTracker
from app.domain.services.agents.step_context_assembler import StepContextAssembler
from app.domain.services.agents.step_executor import StepExecutor
from app.domain.services.agents.task_state_manager import get_task_state_manager
from app.domain.services.attention_injector import AttentionInjector
from app.domain.services.prompts.execution import (
    EXECUTION_SYSTEM_PROMPT,
    build_execution_prompt_from_context,
)
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.tool_tracing import get_tool_tracer
from app.domain.utils.json_parser import JsonParser
from app.domain.utils.json_repair import parse_json_response

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
    SUMMARY_STREAM_COALESCE_MAX_CHARS: int = 320
    SUMMARY_STREAM_COALESCE_FLUSH_SECONDS: float = 0.05
    MIN_DIRECT_DELIVERY_REPORT_LENGTH: int = 1200

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
        tool_result_store=None,
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
            tool_result_store=tool_result_store,
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
        self._research_depth: str = "STANDARD"  # Set by PlanActFlow before summarization

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

        # Pre-planning search context for real-time web info propagation
        self._pre_planning_search_context: str | None = None
        self._pre_planning_search_queries: list[str] = []

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

        # Source citation tracking — delegated to SourceTracker (Phase 3A extraction)
        # (OutputVerifier composed after SourceTracker below)
        self._source_tracker = SourceTracker(max_sources=200)
        # Backward-compatible alias: _collected_sources is a mutable list shared
        # by reference so reads (if/for) in summarize/verifier remain valid.
        self._collected_sources = self._source_tracker._collected_sources

        # Output verification — delegated to OutputVerifier (Phase 3A extraction)
        self._output_verifier = OutputVerifier(
            llm=llm,
            critic=self._critic,
            cove=self._cove,
            context_manager=self._context_manager,
            source_tracker=self._source_tracker,
            metrics=_metrics,
            resolve_feature_flags_fn=self._resolve_feature_flags,
            cove_enabled=self._cove_enabled,
            lettuce_enabled=self._lettuce_enabled,
        )

        # Step-level execution helpers — delegated to StepExecutor (Phase 3A extraction)
        self._step_executor = StepExecutor(
            context_manager=self._context_manager,
            source_tracker=self._source_tracker,
            metrics=_metrics,
        )
        # Backward-compatible aliases for test access
        self._view_operation_count = self._step_executor._view_operation_count
        self._multimodal_findings = self._step_executor._multimodal_findings
        self._view_tools = self._step_executor._view_tools

        # Adaptive response policy controls
        self._response_policy: ResponsePolicy | None = None
        self._output_coverage_validator = OutputCoverageValidator()
        self._response_compressor = ResponseCompressor()
        # Phase 1/4: Request contract for entity fidelity (set by PlanActFlow)
        self._request_contract = None

        # Response generation helpers — delegated to ResponseGenerator (Phase 3A extraction)
        self._response_generator = ResponseGenerator(
            llm=llm,
            memory=self.memory,
            source_tracker=self._source_tracker,
            metrics=_metrics,
            resolve_feature_flags_fn=self._resolve_feature_flags,
            coalesce_max_chars=self.SUMMARY_STREAM_COALESCE_MAX_CHARS,
            coalesce_flush_seconds=self.SUMMARY_STREAM_COALESCE_FLUSH_SECONDS,
        )

        # Pre-trim report cache: stores file_write content extracted from memory
        # *before* token trimming, so summarization recovery can find it even
        # after aggressive context pruning.
        self._pre_trim_report_cache: str | None = None
        self._delivery_channel: str | None = None

    def set_request_contract(self, contract) -> None:
        """Set request contract for search fidelity and entity context (Phase 4)."""
        self._request_contract = contract

    def set_delivery_channel(self, delivery_channel: str | None) -> None:
        """Set the active delivery channel for final delivery policy decisions."""
        self._delivery_channel = delivery_channel

    def set_response_policy(self, policy: ResponsePolicy | None) -> None:
        """Set per-run response policy for summarize stage."""
        self._response_policy = policy

    def _select_model_for_step(self, step_description: str) -> str | None:
        """Select model for the step (delegated to StepExecutor)."""
        return self._step_executor.select_model_for_step(
            step_description,
            user_thinking_mode=getattr(self, "_user_thinking_mode", None),
        )

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
        if settings.enable_search_fidelity_guardrail and self._request_contract and function_name in ToolName._SEARCH:
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
        profile_patch_text: str | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        # Store user request for critic context
        self._user_request = message.message

        # Propagate pre-planning search context to SearchTool so dedup-blocked
        # queries return cached results instead of failing with 0 results.
        if self._pre_planning_search_context is not None:
            for t in self.tools:
                if hasattr(t, "_pre_planning_context"):
                    t._pre_planning_context = self._pre_planning_search_context
                    break

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

        # Generate MCP context snippet for prompt injection
        mcp_context: str | None = None
        for t in self.tools:
            if t.name == "mcp" and hasattr(t, "generate_prompt_context"):
                mcp_context = t.generate_prompt_context()
                break

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
            profile_patch_text=profile_patch_text,
            mcp_context=mcp_context,
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
            from app.core.config import get_settings as _get_settings

            _is_adaptive = _get_settings().adaptive_model_selection_enabled
            if _is_adaptive:
                logger.info("Adaptive model routing selected '%s' for step", selected_model)
            else:
                logger.debug("Model routing disabled, using default model '%s'", selected_model)

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
                    parsed_response: Any = None
                    try:
                        parsed_response = await self.json_parser.parse(event.message, tier="B")
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse step response as JSON: {parse_err}")
                        parsed_response = parse_json_response(event.message, default=None)
                        if parsed_response is not None:
                            logger.info("Recovered step response JSON via local repair fallback")
                        else:
                            known_unparseable_prefixes = ("I was unable to produce a complete response.",)
                            normalized_message = (event.message or "").lstrip()
                            if any(normalized_message.startswith(prefix) for prefix in known_unparseable_prefixes):
                                logger.info("Skipping JSON correction retry for known unparseable fallback message")
                                parsed_response = None
                            else:
                                parsed_response = await self._retry_step_result_json(event.message)

                    # Validate structured output and degrade safely when malformed.
                    payload_valid = self._apply_step_result_payload(
                        step=step, parsed_response=parsed_response, raw_message=event.message
                    )
                    if not payload_valid:
                        logger.warning("Step response payload missing/invalid schema; marking step as unsuccessful")
                        step.status = ExecutionStatus.FAILED
                        yield StepEvent(status=StepStatus.FAILED, step=step)
                        continue

                    step.status = ExecutionStatus.COMPLETED

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
                            raw_wait_reason = event.function_args.get("wait_reason")
                            wait_reason = (
                                raw_wait_reason.strip()
                                if isinstance(raw_wait_reason, str) and raw_wait_reason.strip()
                                else "user_input"
                            )
                            raw_takeover = event.function_args.get("suggest_user_takeover")
                            suggest_user_takeover = (
                                raw_takeover.strip()
                                if isinstance(raw_takeover, str) and raw_takeover.strip()
                                else "none"
                            )
                            yield WaitEvent(
                                wait_reason=wait_reason,
                                suggest_user_takeover=suggest_user_takeover,
                            )
                            return
                        continue
                yield event
            # Only mark as COMPLETED if not already set to FAILED.
            # Also set step.success so plan_act.py's belt-and-suspenders
            # status sync does not override COMPLETED → FAILED.
            if step.status != ExecutionStatus.FAILED:
                step.status = ExecutionStatus.COMPLETED
                if not step.success:
                    step.success = True
        finally:
            # Always restore tools, system prompt, and model override after step
            self.tools = original_tools
            self.system_prompt = original_system_prompt
            self._step_model_override = None  # DeepCode Phase 1: Reset model override

    async def summarize(
        self,
        response_policy: ResponsePolicy | None = None,
        all_steps_completed: bool = False,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Summarize the completed task, streaming tokens for live display.
        Uses ask_stream() to yield StreamEvent chunks so the frontend can render
        the report progressively. CoVe and Critic run as post-processing on the
        accumulated text after streaming completes.

        Args:
            response_policy: Override default response policy for summarization.
            all_steps_completed: When True, "next step" is dropped from required
                coverage sections and delivery-gate failures are downgraded to
                warnings (the task is done — blocking the report is worse than
                delivering it with minor coverage gaps).
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
        # Phase 3: Use unified build_summarize_prompt() with depth-aware length guidance
        from app.domain.services.prompts.execution import build_summarize_prompt, detect_comparison_intent

        _is_comparison = detect_comparison_intent(self._user_request or "")
        if self._collected_sources:
            source_list = self._build_numbered_source_list()
            summarize_prompt = (
                build_summarize_prompt(
                    has_sources=True,
                    source_list=source_list,
                    research_depth=self._research_depth,
                    is_comparison=_is_comparison,
                )
                + f"\n\n## Available Sources\n{source_list}"
                # Pre-baked references anchor: injecting the complete numbered list
                # here guarantees the LLM can copy it verbatim at the end of its
                # response, even when output is near the token budget.  This is the
                # root-cause fix for phantom/orphan citations: the LLM always has the
                # full list in context and is explicitly instructed to include it.
                + "\n\n⚠️ MANDATORY: Your response MUST end with a `## References` section "
                "that lists **every** source from 'Available Sources' above, in the same "
                "numbered format `[N] Title - URL`. Do NOT omit any entries."
            )
        else:
            summarize_prompt = build_summarize_prompt(
                has_sources=False,
                research_depth=self._research_depth,
                is_comparison=_is_comparison,
            )

        # Topic anchor: prevent hallucination by pinning the user's original question
        if self._user_request:
            topic_anchor = (
                f"\n\n## TOPIC ANCHOR (MANDATORY)\n"
                f"The user's original request was:\n"
                f'"""\n{self._user_request}\n"""\n'
                f"Your report MUST address THIS topic. Do NOT write about any other topic."
            )
            summarize_prompt = topic_anchor + "\n\n" + summarize_prompt

        if active_policy.mode == VerbosityMode.CONCISE:
            summarize_prompt += (
                "\n\nKeep the final response concise while preserving: final result, key artifacts, "
                "critical caveats, and one practical next step."
            )
        elif active_policy.mode == VerbosityMode.DETAILED:
            summarize_prompt += (
                "\n\nProvide a detailed and well-structured response with clear reasoning, deliverables, and caveats."
            )

        await self._add_to_memory([{"role": "user", "content": summarize_prompt}])

        # Snapshot file_write content BEFORE token trimming.  If memory is
        # aggressively pruned the original report markdown (written to the
        # workspace via file_write) would be lost — caching it here allows
        # _extract_report_from_file_write_memory to recover it.
        self._pre_trim_report_cache = self._extract_report_from_file_write_memory()
        if self._pre_trim_report_cache:
            logger.info(
                "Pre-trim report cache populated (%d chars) — will survive memory trimming",
                len(self._pre_trim_report_cache),
            )

        await self._ensure_within_token_limit()

        try:
            flags = self._resolve_feature_flags()
            delivery_integrity_enabled = flags.get("delivery_integrity_gate", False)
            delivery_channel = getattr(self, "_delivery_channel", None)
            accumulated_text = ""
            attempt_text = ""  # pre-initialised so CancelledError handler can always read it
            stream_messages = list(self.memory.get_messages())
            stream_metadata: dict[str, Any] = {}
            truncation_exhausted = False
            max_stream_continuations = 2 if delivery_integrity_enabled else 1
            stream_attempt = 0

            # Use fast model for report streaming — long-form text generation doesn't need 80B.
            # Falls back to the default model when FAST_MODEL is not configured.
            from app.core.config import get_settings as _get_settings

            _summarize_model: str | None = _get_settings().fast_model or None
            _summarize_max_tokens: int = _get_settings().summarization_max_tokens

            if self._can_deliver_pretrim_report_directly(
                response_policy=active_policy,
                all_steps_completed=all_steps_completed,
                delivery_channel=delivery_channel,
            ):
                message_content = self._pre_trim_report_cache or ""
                stream_metadata = {"provider": "pretrim_cache", "finish_reason": "stop", "truncated": False}
                logger.info(
                    "Skipping summarization — pre-trim draft passed gate directly (%d chars)",
                    len(message_content),
                )
                yield StreamEvent(content="", is_final=True, phase="summarizing")
            else:
                # Phase 1: Stream tokens live via StreamEvent
                while True:
                    stream_attempt += 1
                    attempt_text = ""

                    stream_iter = self.llm.ask_stream(
                        stream_messages,
                        tools=None,
                        tool_choice=None,
                        model=_summarize_model,
                        max_tokens=_summarize_max_tokens,
                    )
                    async for stream_event in self._iter_coalesced_stream_events(stream_iter, phase="summarizing"):
                        attempt_text += stream_event.content
                        yield stream_event

                    if stream_attempt == 1:
                        accumulated_text = attempt_text
                    else:
                        accumulated_text = self._merge_stream_continuation(accumulated_text, attempt_text)

                    stream_metadata = self._get_last_stream_metadata()
                    _est_output_tokens = max(len(attempt_text) // 4, 1)
                    _near_token_limit = _est_output_tokens >= int(_summarize_max_tokens * 0.85)
                    is_truncated_stream = (
                        bool(stream_metadata.get("truncated"))
                        or stream_metadata.get("finish_reason") == "length"
                        or _near_token_limit
                    )
                    if delivery_integrity_enabled and is_truncated_stream:
                        if _near_token_limit and not (
                            bool(stream_metadata.get("truncated")) or stream_metadata.get("finish_reason") == "length"
                        ):
                            logger.warning(
                                "Truncation heuristic: ~%d est. output tokens at %.0f%% of %d-token "
                                "budget (finish_reason=%r) — treating as silently truncated",
                                _est_output_tokens,
                                _est_output_tokens * 100.0 / _summarize_max_tokens,
                                _summarize_max_tokens,
                                stream_metadata.get("finish_reason"),
                            )
                        self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="detected")
                    if not (delivery_integrity_enabled and is_truncated_stream):
                        break

                    if stream_attempt > max_stream_continuations:
                        _powerful_model: str | None = _get_settings().powerful_model or None
                        _can_escalate = _powerful_model and _summarize_model and _powerful_model != _summarize_model
                        if _can_escalate:
                            logger.info(
                                "Delivery integrity: fast model exhausted after %d attempts, "
                                "escalating to powerful model (%s) for final continuation",
                                max_stream_continuations,
                                _powerful_model,
                            )
                            assistant_fragment = attempt_text.strip() or accumulated_text[-4000:]
                            if assistant_fragment.strip():
                                _esc_sys = [m for m in stream_messages if m.get("role") == "system"]
                                _esc_last_user = next(
                                    (m for m in reversed(stream_messages) if m.get("role") == "user"), None
                                )
                                _esc_base = [*_esc_sys, *([_esc_last_user] if _esc_last_user else [])]
                                stream_messages = [
                                    *_esc_base,
                                    {"role": "assistant", "content": assistant_fragment},
                                    {"role": "user", "content": self._build_continuation_prompt(accumulated_text)},
                                ]
                                escalation_text = ""
                                stream_iter = self.llm.ask_stream(
                                    stream_messages,
                                    tools=None,
                                    tool_choice=None,
                                    model=_powerful_model,
                                    max_tokens=_summarize_max_tokens,
                                )
                                async for stream_event in self._iter_coalesced_stream_events(
                                    stream_iter, phase="summarizing"
                                ):
                                    escalation_text += stream_event.content
                                    yield stream_event
                                accumulated_text = self._merge_stream_continuation(accumulated_text, escalation_text)
                                escalation_meta = self._get_last_stream_metadata()
                                escalation_truncated = (
                                    bool(escalation_meta.get("truncated"))
                                    or escalation_meta.get("finish_reason") == "length"
                                )
                                if not escalation_truncated:
                                    self._record_stream_truncation_metric(
                                        stream_metadata=escalation_meta, outcome="recovered_escalation"
                                    )
                                    break
                                self._record_stream_truncation_metric(
                                    stream_metadata=escalation_meta,
                                    outcome="unresolved_after_escalation",
                                )
                        else:
                            _can_escalate = False

                        truncation_exhausted = True
                        logger.warning(
                            "Delivery integrity: stream remained truncated after %d continuation attempts"
                            + (" + escalation" if _can_escalate else ""),
                            max_stream_continuations,
                        )
                        self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="unresolved")
                        break

                    logger.warning(
                        "Delivery integrity: stream truncation detected (finish_reason=%s, model=%s), "
                        "requesting continuation (%d/%d)",
                        stream_metadata.get("finish_reason"),
                        _summarize_model or "default",
                        stream_attempt,
                        max_stream_continuations,
                    )
                    assistant_fragment = attempt_text.strip() or accumulated_text[-2000:]
                    if not assistant_fragment.strip():
                        truncation_exhausted = True
                        logger.warning(
                            "Delivery integrity: truncation detected with empty fragment, aborting continuation"
                        )
                        self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="unresolved")
                        break

                    _sys_msgs = [m for m in stream_messages if m.get("role") == "system"]
                    _last_user = next((m for m in reversed(stream_messages) if m.get("role") == "user"), None)
                    _continuation_base = [*_sys_msgs, *([_last_user] if _last_user else [])]
                    stream_messages = [
                        *_continuation_base,
                        {"role": "assistant", "content": assistant_fragment},
                        {"role": "user", "content": self._build_continuation_prompt(accumulated_text)},
                    ]
                    self._record_stream_truncation_metric(
                        stream_metadata=stream_metadata,
                        outcome="continuation_requested",
                    )

                if delivery_integrity_enabled and stream_attempt > 1 and not truncation_exhausted:
                    is_final_truncated = (
                        bool(stream_metadata.get("truncated")) or stream_metadata.get("finish_reason") == "length"
                    )
                    if not is_final_truncated:
                        self._record_stream_truncation_metric(stream_metadata=stream_metadata, outcome="recovered")

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
                retry_stream = self.llm.ask_stream(
                    list(self.memory.get_messages()),
                    tools=None,
                    tool_choice=None,
                    model=_summarize_model,
                    max_tokens=_summarize_max_tokens,
                )
                async for stream_event in self._iter_coalesced_stream_events(retry_stream, phase="summarizing"):
                    retry_text += stream_event.content
                    yield stream_event

                yield StreamEvent(content="", is_final=True, phase="summarizing")
                message_content = self._clean_report_content(retry_text.strip())

            # Meta-commentary detection: the LLM described what it did instead
            # of delivering the actual report content.  Recover from the
            # pre-trim report cache or retry with an explicit prompt.
            if message_content and self._is_meta_commentary(message_content):
                logger.warning(
                    "Summarization produced meta-commentary (%d chars) instead of report content: %.120s",
                    len(message_content),
                    message_content,
                )
                _metrics.record_counter(
                    "pythinker_summarization_meta_commentary_total",
                    labels={"recovery": "attempted"},
                )

                # Try pre-trim cache first (most reliable)
                if self._pre_trim_report_cache and len(self._pre_trim_report_cache) > 200:
                    logger.info(
                        "Recovered full report from pre-trim cache (%d chars)",
                        len(self._pre_trim_report_cache),
                    )
                    message_content = self._pre_trim_report_cache
                else:
                    # Retry with explicit anti-meta prompt
                    retry_prompt = (
                        "Your previous response was a brief description of the report instead of the "
                        "report itself. You said: " + message_content[:200] + "\n\n"
                        "This is NOT acceptable. You MUST write the FULL research report with actual "
                        "data, findings, analysis, and citations. Start with a # heading and write "
                        "the complete report content directly. Do NOT describe or summarize what "
                        "you would write — write it."
                    )
                    await self._add_to_memory(
                        [
                            {"role": "assistant", "content": message_content},
                            {"role": "user", "content": retry_prompt},
                        ]
                    )
                    await self._ensure_within_token_limit()

                    retry_text = ""
                    retry_stream = self.llm.ask_stream(
                        list(self.memory.get_messages()),
                        tools=None,
                        tool_choice=None,
                        model=_summarize_model,
                        max_tokens=_summarize_max_tokens,
                    )
                    async for stream_event in self._iter_coalesced_stream_events(retry_stream, phase="summarizing"):
                        retry_text += stream_event.content
                        yield stream_event

                    yield StreamEvent(content="", is_final=True, phase="summarizing")
                    retry_content = self._clean_report_content(retry_text.strip())

                    # Accept retry only if it's longer and not meta-commentary again
                    if (
                        retry_content
                        and len(retry_content) > len(message_content)
                        and not self._is_meta_commentary(retry_content)
                    ):
                        message_content = retry_content
                    elif self._pre_trim_report_cache:
                        # Retry also failed, last resort: use cache even if short
                        message_content = self._pre_trim_report_cache

            # Structural quality gate: even if meta-commentary detection missed
            # the pattern, catch degenerate outputs that lack report structure.
            # A real report has markdown headings; a short excuse/refusal does not.
            if message_content and self._is_low_quality_summary(message_content):
                logger.warning(
                    "Summarization output failed structural quality gate (%d chars, no headings): %.200s",
                    len(message_content),
                    message_content,
                )
                _metrics.record_counter(
                    "pythinker_summarization_low_quality_total",
                    labels={"recovery": "attempted"},
                )

                # Try pre-trim cache first (most reliable)
                if self._pre_trim_report_cache and len(self._pre_trim_report_cache) > len(message_content):
                    logger.info(
                        "Replacing low-quality summary with pre-trim cache (%d chars)",
                        len(self._pre_trim_report_cache),
                    )
                    message_content = self._pre_trim_report_cache
                else:
                    # Retry with explicit anti-degenerate prompt
                    retry_prompt = (
                        "Your previous response was only: " + message_content[:200] + "\n\n"
                        "This is NOT a report — it is a preamble or meta-commentary. "
                        "You MUST write the FULL research report with actual data, findings, "
                        "analysis, and citations. Start IMMEDIATELY with a # heading on the "
                        "first line. Do NOT describe what you will write — write it."
                    )
                    await self._add_to_memory(
                        [
                            {"role": "assistant", "content": message_content},
                            {"role": "user", "content": retry_prompt},
                        ]
                    )
                    await self._ensure_within_token_limit()

                    retry_text = ""
                    retry_stream = self.llm.ask_stream(
                        list(self.memory.get_messages()), tools=None, tool_choice=None, model=_summarize_model
                    )
                    async for stream_event in self._iter_coalesced_stream_events(retry_stream, phase="summarizing"):
                        retry_text += stream_event.content
                        yield stream_event

                    yield StreamEvent(content="", is_final=True, phase="summarizing")
                    retry_content = self._clean_report_content(retry_text.strip())

                    if (
                        retry_content
                        and len(retry_content) > len(message_content)
                        and not self._is_low_quality_summary(retry_content)
                    ):
                        message_content = retry_content
                    elif self._pre_trim_report_cache:
                        message_content = self._pre_trim_report_cache

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
            if (
                delivery_integrity_enabled
                and not truncation_exhausted
                and stream_metadata.get("provider") != "pretrim_cache"
            ):
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

                        # Up to 4 continuation attempts for pattern-based detection
                        # (attempt 1 uses balanced model; attempts 2-4 escalate to powerful model)
                        _max_pattern_continuations = 4
                        _stage2_resolved = False
                        for _pattern_attempt in range(1, _max_pattern_continuations + 1):
                            _cont_model = _summarize_model
                            # Escalate to powerful model from 2nd attempt onward
                            if _pattern_attempt > 1:
                                _powerful = _get_settings().powerful_model or None
                                if _powerful and _powerful != _summarize_model:
                                    _cont_model = _powerful
                                    logger.info(
                                        "Pattern-based truncation: escalating to powerful model (%s) for attempt %d",
                                        _powerful,
                                        _pattern_attempt,
                                    )
                                else:
                                    break  # No escalation available, stop early

                            logger.info(
                                "Requesting continuation based on content patterns (attempt %d, model=%s)...",
                                _pattern_attempt,
                                _cont_model or "default",
                            )
                            continuation_text = ""
                            continuation_iter = self.llm.ask_stream(
                                continuation_messages, tools=None, tool_choice=None, model=_cont_model
                            )
                            async for stream_event in self._iter_coalesced_stream_events(
                                continuation_iter, phase="summarizing"
                            ):
                                continuation_text += stream_event.content
                                yield stream_event

                            accumulated_text = self._merge_stream_continuation(accumulated_text, continuation_text)
                            message_content = self._collapse_duplicate_report_payload(accumulated_text.strip())

                            logger.info(
                                "Truncation recovery: added %d chars via pattern-based continuation (attempt %d)",
                                len(continuation_text),
                                _pattern_attempt,
                            )

                            # Re-check for truncation after continuation
                            post_assessment = truncation_detector.detect(
                                content=message_content,
                                finish_reason=None,
                                max_tokens_used=False,
                            )
                            if not truncation_detector.should_request_continuation(
                                post_assessment, confidence_threshold=0.85
                            ):
                                _stage2_resolved = True
                                break  # Content looks complete

                            # Update continuation messages for next attempt
                            continuation_messages = [
                                *stream_messages,
                                {"role": "assistant", "content": message_content},
                                {"role": "user", "content": post_assessment.continuation_prompt},
                            ]

                        # Mark exhausted if Stage 2 failed to resolve truncation
                        # (covers both loop exhaustion AND early break without resolution)
                        if not _stage2_resolved:
                            truncation_exhausted = True
                            logger.warning(
                                "Stage 2 pattern-based truncation exhausted after %d attempts "
                                "(type=%s, confidence=%.2f)",
                                _max_pattern_continuations,
                                truncation_assessment.truncation_type or "unknown",
                                post_assessment.confidence if post_assessment else truncation_assessment.confidence,
                            )

                        # Record outcome
                        _metrics.increment(
                            "pythinker_output_truncations_total",
                            labels={
                                "detection_method": "pattern",
                                "truncation_type": truncation_assessment.truncation_type or "unknown",
                                "confidence_tier": "exhausted" if truncation_exhausted else "continuation_completed",
                            },
                        )

                except Exception as e:
                    logger.debug(f"Pattern-based truncation detection failed: {e}")

            # Guaranteed fallback: inject complete References section if truncated/missing
            message_content = self._ensure_complete_references(message_content)

            # Prepend incomplete-report warning header when truncation was unresolvable OR
            # when the content still carries `[…]` streaming artifacts.
            if truncation_exhausted or self._has_truncation_artifacts(message_content):
                truncation_notice = (
                    "> **Incomplete Report:** This report contains sections that were not fully "
                    "generated due to output length limits. Sections marked `[…]` contain truncated "
                    "content. The available research findings are included below.\n\n"
                )
                message_content = truncation_notice + message_content
                logger.warning(
                    "Prepended truncation notice to report (truncation_exhausted=%s, artifacts=%s)",
                    truncation_exhausted,
                    self._has_truncation_artifacts(message_content),
                )

            delivery_gate_additional_issues: list[str] = []
            delivery_gate_additional_warnings: list[str] = []

            # Citation integrity: validate and auto-repair orphan citations
            try:
                from app.domain.services.agents.citation_integrity import repair_citations, validate_citations

                cite_result = validate_citations(message_content)
                if not cite_result.is_valid:
                    source_list = self._build_numbered_source_list() if self._collected_sources else ""
                    repaired_content = repair_citations(message_content, source_list)
                    if repaired_content != message_content:
                        message_content = repaired_content
                        cite_result = validate_citations(message_content)

                    if cite_result.is_valid:
                        logger.info("Citation integrity auto-repair resolved detected issues")
                    else:
                        # Orphan citations (inline [N] with no reference) are cosmetic issues,
                        # not data integrity failures.  Blocking the entire report delivery
                        # because of citation formatting is the wrong trade-off — the research
                        # content is correct, only the numbering is off.  Downgrade to warning.
                        delivery_gate_additional_warnings.append("citation_integrity_warning")
                        logger.warning(
                            "Citation integrity issues: orphans=%s, phantoms=%s, gaps=%s, dupes=%d",
                            cite_result.orphan_citations,
                            cite_result.phantom_references,
                            cite_result.citation_gaps,
                            len(cite_result.duplicate_urls),
                        )
                        _metrics.record_counter(
                            "pythinker_citation_integrity_issues_total",
                            labels={"type": "orphan" if cite_result.orphan_citations else "other"},
                        )
            except Exception as e:
                logger.debug("Citation integrity check failed: %s", e)
                delivery_gate_additional_warnings.append("citation_integrity_check_failed")

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
                        description="Fact-checking sources...",
                        status=ExecutionStatus.RUNNING,
                        step_type=StepType.FINALIZATION,
                    ),
                )
                verification_result = await self._verify_hallucination(message_content, self._user_request)
                message_content = verification_result.content
                if verification_result.blocking_issues:
                    delivery_gate_additional_issues.extend(verification_result.blocking_issues)
                if verification_result.warnings:
                    delivery_gate_additional_warnings.extend(verification_result.warnings)

                # Emit verification complete so the frontend shows it as done
                yield StepEvent(
                    status=StepStatus.RUNNING,
                    step=Step(
                        id="finalization",
                        description="Verification complete",
                        status=ExecutionStatus.RUNNING,
                        step_type=StepType.FINALIZATION,
                    ),
                )

            # Critic revision loop disabled — the 5-check framework produces
            # unreliable results with the current LLM (unknown check names, excessive
            # revision loops) and adds 30-60s latency. CoVe verification above
            # already handles factual accuracy. Re-enable when the LLM supports
            # reliable structured output for the 5-check framework.

            # When all plan steps completed, "next step" is meaningless — drop it
            # from required sections to avoid false coverage failures on terminal tasks.
            _required_sections = active_policy.min_required_sections
            if all_steps_completed:
                _required_sections = [s for s in _required_sections if s.lower() != "next step"]

            coverage_result = self._output_coverage_validator.validate(
                output=message_content,
                user_request=self._user_request or "",
                required_sections=_required_sections,
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
                    required_sections=_required_sections,
                )
                if compressed_coverage.is_valid and len(compressed_content) < len(message_content):
                    message_content = compressed_content
                    coverage_result = compressed_coverage
                else:
                    _metrics.record_counter(
                        "compression_rejected_total",
                        labels={"reason": "coverage_drop"},
                    )

            telegram_final_delivery = (delivery_channel or "").strip().lower() == "telegram"

            gate_passed, gate_issues = self._run_delivery_integrity_gate(
                content=message_content,
                response_policy=active_policy,
                coverage_result=coverage_result,
                stream_metadata=stream_metadata,
                truncation_exhausted=truncation_exhausted,
                additional_issues=delivery_gate_additional_issues,
                additional_warnings=delivery_gate_additional_warnings,
                delivery_channel=delivery_channel,
            )
            if not gate_passed and self._pre_trim_report_cache:
                pretrim_content = self._pre_trim_report_cache
                if pretrim_content.strip() and pretrim_content != message_content:
                    pretrim_coverage = self._output_coverage_validator.validate(
                        output=pretrim_content,
                        user_request=self._user_request or "",
                        required_sections=_required_sections,
                    )
                    fallback_passed, fallback_issues = self._run_delivery_integrity_gate(
                        content=pretrim_content,
                        response_policy=active_policy,
                        coverage_result=pretrim_coverage,
                        stream_metadata={"provider": "pretrim_cache", "finish_reason": "stop", "truncated": False},
                        truncation_exhausted=False,
                        additional_issues=delivery_gate_additional_issues,
                        additional_warnings=delivery_gate_additional_warnings,
                        delivery_channel=delivery_channel,
                    )
                    if fallback_passed:
                        logger.info(
                            "Summary failed gate but pre-trim draft passed (%d chars) — using draft",
                            len(pretrim_content),
                        )
                        message_content = pretrim_content
                        coverage_result = pretrim_coverage
                        gate_passed = True
                        gate_issues = []
                    else:
                        gate_issues = fallback_issues

            if (
                not gate_passed
                and not telegram_final_delivery
                and self._can_auto_repair_delivery_integrity(gate_issues, message_content)
            ):
                repaired_content = self._append_delivery_integrity_fallback(message_content, gate_issues)
                repaired_coverage = self._output_coverage_validator.validate(
                    output=repaired_content,
                    user_request=self._user_request or "",
                    required_sections=_required_sections,
                )
                # Pass truncation_exhausted=False: the notice was already appended above,
                # so re-flagging it in the verification pass would re-block the repair.
                repaired_passed, repaired_issues = self._run_delivery_integrity_gate(
                    content=repaired_content,
                    response_policy=active_policy,
                    coverage_result=repaired_coverage,
                    stream_metadata=stream_metadata,
                    truncation_exhausted=False,
                    additional_issues=delivery_gate_additional_issues,
                    additional_warnings=delivery_gate_additional_warnings,
                    delivery_channel=delivery_channel,
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
                if (
                    all_steps_completed
                    and not telegram_final_delivery
                    and self._can_downgrade_delivery_integrity_issues(gate_issues)
                ):
                    # All plan steps succeeded — blocking the report is worse than
                    # delivering it with minor integrity gaps.  Downgrade to warning
                    # and proceed with delivery so the user sees their completed work.
                    logger.warning(
                        "Delivery integrity gate failed but all steps completed — "
                        "downgrading to warning and delivering report: %s",
                        issue_text,
                    )
                    _metrics.record_counter(
                        "delivery_gate_downgraded_total",
                        labels={"reason": "all_steps_completed"},
                    )
                else:
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

            message_content = sanitize_report_output(message_content)
            message_title = self._extract_title(message_content)

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

                # Enhancement 7: optional brief confirmation MessageEvent after report
                if flags.get("confirmation_summary_enabled", False):
                    try:
                        confirmation = await self._generate_confirmation_summary(message_content, message_title)
                        if confirmation:
                            yield MessageEvent(message=confirmation)
                    except Exception as _ce:
                        logger.debug("Confirmation summary skipped: %s", _ce)
            else:
                message_event = MessageEvent(message=message_content)
                message_event_id = message_event.id
                yield message_event

            # Follow-up suggestions — graceful degradation (non-critical)
            try:
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
            except Exception as _se:
                logger.debug("Follow-up suggestions skipped: %s", _se)

        except asyncio.CancelledError:
            # Emit a partial report if content was collected before the timeout cancelled the task.
            # Use whichever buffer has more content: the merged `accumulated_text` or the
            # in-progress `attempt_text` from the current streaming attempt.
            _cancel_best = accumulated_text or attempt_text or ""
            if _cancel_best.strip():
                _cancel_partial = self._clean_report_content(_cancel_best.strip())
                if _cancel_partial:
                    _cancel_partial = sanitize_report_output(_cancel_partial)
                    _cancel_notice = (
                        "> **Partial Report:** Generation was interrupted by a time limit. "
                        "The content below represents findings collected before the interrupt.\n\n"
                    )
                    _cancel_title = self._extract_title(_cancel_partial) or "Research Summary"
                    yield ReportEvent(
                        id=str(uuid.uuid4()),
                        title=f"[Partial] {_cancel_title}",
                        content=_cancel_notice + _cancel_partial,
                    )
                    logger.warning("Summarize interrupted: emitted %d-char partial report", len(_cancel_partial))
            raise
        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            yield ErrorEvent(error=f"Failed to generate summary: {e!s}")

    # ── Response generation helpers (delegated to ResponseGenerator) ──

    def _get_last_stream_metadata(self) -> dict[str, Any]:
        """Safely read stream metadata (delegated to ResponseGenerator)."""
        return self._response_generator.get_last_stream_metadata()

    async def _iter_coalesced_stream_events(
        self,
        stream_iter: AsyncGenerator[str, None],
        *,
        phase: str = "summarizing",
    ) -> AsyncGenerator[StreamEvent, None]:
        """Coalesce small LLM chunks (delegated to ResponseGenerator)."""
        async for event in self._response_generator.iter_coalesced_stream_events(stream_iter, phase=phase):
            yield event

    def _build_continuation_prompt(self, accumulated_text: str = "") -> str:
        """Prompt used when stream truncation is detected (delegated)."""
        source_list = self._build_numbered_source_list() if self._collected_sources else ""
        return self._response_generator.build_continuation_prompt(
            accumulated_text=accumulated_text,
            source_list=source_list,
        )

    def _ensure_complete_references(self, content: str) -> str:
        """Inject authoritative References section if truncated or missing.

        Guaranteed fallback: if collected sources exist and the markdown has a
        truncated/missing References section, appends the source list from
        SourceTracker. Skips injection if the LLM-generated reference count
        already meets or exceeds the expected count.
        """
        if not self._collected_sources:
            return content

        source_list = self._build_numbered_source_list()
        if not source_list.strip():
            return content

        expected_count = len(self._collected_sources)

        # Check if References heading exists
        ref_match = re.search(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE)

        if ref_match:
            ref_section = content[ref_match.end() :].strip()
            existing_count = len(re.findall(r"^\s*\[?\d+\]", ref_section, re.MULTILINE))

            # Duplication guard: if LLM already generated enough references, leave untouched
            if existing_count >= expected_count:
                return content

            # Replace the incomplete References section with the authoritative one
            logger.info(
                "Injecting complete References section (had %d/%d entries)",
                existing_count,
                expected_count,
            )
            content_before_refs = content[: ref_match.start()].rstrip()
            return f"{content_before_refs}\n\n## References\n{source_list}\n"

        # No References heading — check if content looks like a report with inline citations
        has_inline_citations = bool(re.search(r"\[\d+\]", content))
        has_headings = bool(re.search(r"^#{1,3}\s+", content, re.MULTILINE))

        if has_inline_citations and has_headings:
            logger.info(
                "Appending missing References section (%d sources)",
                expected_count,
            )
            return f"{content.rstrip()}\n\n## References\n{source_list}\n"

        return content

    def _merge_stream_continuation(self, base_text: str, continuation_text: str) -> str:
        """Merge continuation output (delegated to ResponseGenerator)."""
        return self._response_generator.merge_stream_continuation(base_text, continuation_text)

    def _collapse_duplicate_report_payload(self, content: str) -> str:
        """Collapse duplicate full-report payloads (delegated to ResponseGenerator)."""
        return self._response_generator.collapse_duplicate_report_payload(content)

    def _can_deliver_pretrim_report_directly(
        self,
        *,
        response_policy: ResponsePolicy,
        all_steps_completed: bool,
        delivery_channel: str | None = None,
    ) -> bool:
        """Return whether the cached draft can bypass the summarize LLM call."""
        pretrim_report = self._pre_trim_report_cache or ""
        pretrim_report_stripped = pretrim_report.strip()
        if not pretrim_report_stripped:
            return False
        if not all_steps_completed:
            return False
        if (delivery_channel or "").strip().lower() != "telegram":
            return False
        if len(pretrim_report_stripped) < self.MIN_DIRECT_DELIVERY_REPORT_LENGTH:
            return False

        coverage_validator = getattr(self, "_output_coverage_validator", None)
        if coverage_validator is None:
            return False

        required_sections = response_policy.min_required_sections
        if all_steps_completed:
            required_sections = [section for section in required_sections if section.lower() != "next step"]

        coverage_result = coverage_validator.validate(
            output=pretrim_report,
            user_request=self._user_request or "",
            required_sections=required_sections,
        )
        gate_passed, _ = self._run_delivery_integrity_gate(
            content=pretrim_report,
            response_policy=response_policy,
            coverage_result=coverage_result,
            stream_metadata={"provider": "pretrim_cache", "finish_reason": "stop", "truncated": False},
            truncation_exhausted=False,
            delivery_channel=delivery_channel,
        )
        return gate_passed

    def _run_delivery_integrity_gate(
        self,
        content: str,
        response_policy: ResponsePolicy,
        coverage_result: Any,
        stream_metadata: dict[str, Any],
        truncation_exhausted: bool,
        additional_issues: list[str] | None = None,
        additional_warnings: list[str] | None = None,
        delivery_channel: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Fail-closed delivery gate (delegated to ResponseGenerator)."""
        self._response_generator._metrics = _metrics  # sync module-level metrics
        return self._response_generator.run_delivery_integrity_gate(
            content,
            response_policy,
            coverage_result,
            stream_metadata,
            truncation_exhausted,
            additional_issues=additional_issues,
            additional_warnings=additional_warnings,
            delivery_channel=delivery_channel,
        )

    def _can_downgrade_delivery_integrity_issues(self, issues: list[str]) -> bool:
        """Allow downgrade only for non-critical integrity failures."""
        critical_issue_tokens = {
            "stream_truncation_unresolved",
            "hallucination_ratio_critical",
            "citation_integrity_unresolved",
        }
        for issue in issues:
            token = (issue or "").split(":", 1)[0].strip().lower()
            if token in critical_issue_tokens:
                return False
        return True

    def _can_auto_repair_delivery_integrity(self, issues: list[str], content: str = "") -> bool:
        """Allow safe remediation for coverage-only misses (delegated)."""
        return self._response_generator.can_auto_repair_delivery_integrity(issues, content)

    def _append_delivery_integrity_fallback(self, content: str, issues: list[str]) -> str:
        """Append deterministic fallback sections (delegated to ResponseGenerator)."""
        return self._response_generator.append_delivery_integrity_fallback(content, issues)

    def _record_stream_truncation_metric(self, stream_metadata: dict[str, Any], outcome: str) -> None:
        """Record stream truncation metric (delegated to ResponseGenerator)."""
        self._response_generator._metrics = _metrics  # sync module-level metrics
        self._response_generator.record_stream_truncation_metric(stream_metadata, outcome)

    def _extract_title(self, content: str) -> str:
        """Extract a title from markdown content (delegated to ResponseGenerator)."""
        return self._response_generator.extract_title(content)

    # Backward-compatible class-level regex aliases (now in response_generator module)
    from app.domain.services.agents.response_generator import (
        _FUNCTION_CALL_RE,
        _TOOL_CALL_RE,
    )

    def _is_meta_commentary(self, content: str) -> bool:
        """Detect meta-commentary (delegated to ResponseGenerator)."""
        return self._response_generator.is_meta_commentary(content)

    def _is_low_quality_summary(self, content: str) -> bool:
        """Structural quality gate (delegated to ResponseGenerator)."""
        return self._response_generator.is_low_quality_summary(content, self._research_depth)

    def _clean_report_content(self, content: str) -> str:
        """Strip hallucinated tool-call XML and boilerplate (delegated)."""
        self._response_generator.set_pre_trim_report_cache(self._pre_trim_report_cache)
        return self._response_generator.clean_report_content(content)

    def _has_truncation_artifacts(self, content: str) -> bool:
        """Detect `[…]` streaming truncation artifacts (delegated)."""
        return self._response_generator.has_truncation_artifacts(content)

    def _extract_fallback_summary(self) -> str:
        """Extract fallback summary from memory (delegated to ResponseGenerator)."""
        self._response_generator.set_pre_trim_report_cache(self._pre_trim_report_cache)
        return self._response_generator.extract_fallback_summary()

    def _resolve_json_tool_result(self, content: str) -> str:
        """Recover actual report from JSON tool result (delegated)."""
        self._response_generator.set_pre_trim_report_cache(self._pre_trim_report_cache)
        return self._response_generator.resolve_json_tool_result(content)

    def _extract_report_from_file_write_memory(self) -> str | None:
        """Search memory for file_write with markdown (delegated to ResponseGenerator)."""
        return self._response_generator.extract_report_from_file_write_memory()

    async def _generate_confirmation_summary(self, report_content: str, title: str | None) -> str | None:
        """Generate brief confirmation message (delegated to ResponseGenerator)."""
        return await self._response_generator.generate_confirmation_summary(report_content, title)

    async def _generate_follow_up_suggestions(self, title: str, content: str) -> list[str]:
        """Generate follow-up suggestions (delegated to ResponseGenerator)."""
        self._response_generator.set_user_request(self._user_request)
        self._response_generator._memory = self.memory  # sync in case test/caller replaced memory
        return await self._response_generator.generate_follow_up_suggestions(title, content)

    def _apply_step_result_payload(self, step: Step, parsed_response: Any, raw_message: str) -> bool:
        """Apply step result payload (delegated to StepExecutor)."""
        return StepExecutor.apply_step_result_payload(step, parsed_response, raw_message)

    async def _retry_step_result_json(self, raw_message: str) -> dict[str, Any] | None:
        """Two-pass correction retry for non-JSON step outputs.

        Uses the LLM as a strict formatter and then runs local JSON extraction/repair
        on the correction result to avoid hard failing on prose-prefixed responses.
        """
        schema = '{"success": boolean, "result": string|null, "attachments": string[]}'
        preview = raw_message[:1800]
        correction_prompts = [
            (
                "Your previous response was not valid JSON.\n"
                f'Previous response:\n"""\n{preview}\n"""\n\n'
                f"You MUST respond with ONLY valid JSON matching this schema: {schema}\n"
                "No prose. No markdown. JSON object only."
            ),
            (
                "Return ONLY a valid JSON object. "
                f"Schema: {schema}. "
                "No explanation, no markdown, and no surrounding text."
            ),
        ]

        for attempt_index, correction_prompt in enumerate(correction_prompts, start=1):
            try:
                correction = await self.llm.ask(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a strict JSON formatter. Output valid JSON only.",
                        },
                        {"role": "user", "content": correction_prompt},
                    ],
                    tools=None,
                    response_format={"type": "json_object"},
                    enable_caching=False,
                    model=self._step_model_override,
                )
            except Exception as correction_err:
                logger.warning("Step JSON correction retry failed on attempt %d: %s", attempt_index, correction_err)
                continue

            corrected_content = str(correction.get("content", "") or "")
            corrected = parse_json_response(corrected_content, default=None)
            if isinstance(corrected, dict):
                logger.info("Recovered step response JSON via correction retry (attempt %d)", attempt_index)
                return corrected
            logger.warning("Correction retry attempt %d did not return a valid JSON object", attempt_index)

        return None

    # ── Output verification helpers (delegated to OutputVerifier) ─────

    async def _apply_critic_revision(self, message_content: str, attachments: list[FileInfo]) -> str:
        """Apply critic review with revision loop (delegated to OutputVerifier)."""
        self._output_verifier.set_user_request(self._user_request)
        return await self._output_verifier.apply_critic_revision(message_content, attachments)

    async def _apply_hallucination_verification(self, content: str, query: str) -> str:
        """Apply hallucination verification (delegated to OutputVerifier)."""
        self._output_verifier._metrics = _metrics  # sync module-level metrics
        return await self._output_verifier.apply_hallucination_verification(content, query)

    async def _verify_hallucination(self, content: str, query: str):
        """Run hallucination verification and return structured gating signals."""
        self._output_verifier._metrics = _metrics  # sync module-level metrics
        return await self._output_verifier.verify_hallucination(content, query)

    def _build_source_context(self) -> list[str]:
        """Build grounding context from collected sources (delegated to OutputVerifier)."""
        return self._output_verifier.build_source_context()

    def _needs_verification(self, content: str, query: str) -> bool:
        """Determine if content needs hallucination verification (delegated)."""
        return self._output_verifier.needs_verification(content, query)

    async def _apply_cove_verification(self, content: str, query: str) -> tuple[str, CoVeResult | None]:
        """Apply Chain-of-Verification (delegated to OutputVerifier)."""
        return await self._output_verifier.apply_cove_verification(content, query)

    def _needs_cove_verification(self, content: str, query: str) -> bool:
        """Heuristic gate for verification need (delegated to OutputVerifier)."""
        return self._output_verifier._needs_cove_verification(content, query)

    def _is_report_structure(self, content: str) -> bool:
        """Check if content has report-like structure (delegated to ResponseGenerator)."""
        return self._response_generator.is_report_structure(content)

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
        self._source_tracker.clear()
        self._step_executor.clear()
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
        """Track multimodal findings (delegated to StepExecutor)."""
        self._step_executor.track_multimodal_findings(event)

    def get_multimodal_findings(self) -> list[dict]:
        """Get accumulated multimodal findings (delegated to StepExecutor)."""
        return self._step_executor.get_multimodal_findings()

    # ── Source Citation Tracking (delegated to SourceTracker) ──────────

    def _track_sources_from_tool_event(self, event: ToolEvent) -> None:
        """Extract and track source citations from tool events."""
        self._source_tracker.track_tool_event(event)

    def _build_numbered_source_list(self) -> str:
        """Build a numbered source list for citation-aware summarization."""
        return self._source_tracker.build_numbered_source_list()

    def get_collected_sources(self) -> list[SourceCitation]:
        """Get all collected source citations."""
        return self._source_tracker.get_collected_sources()
