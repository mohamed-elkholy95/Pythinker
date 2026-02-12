import asyncio
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import datetime
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
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.models.source_citation import SourceCitation
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.chain_of_verification import ChainOfVerification, CoVeResult
from app.domain.services.agents.compliance_gates import GateStatus, get_compliance_gates
from app.domain.services.agents.context_manager import ContextManager, InsightType
from app.domain.services.agents.critic import CriticAgent, CriticConfig, CriticVerdict
from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer
from app.domain.services.agents.output_coverage_validator import OutputCoverageValidator
from app.domain.services.agents.prompt_adapter import PromptAdapter
from app.domain.services.agents.response_compressor import ResponseCompressor
from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode
from app.domain.services.agents.reward_scoring import RewardScorer
from app.domain.services.agents.task_state_manager import get_task_state_manager
from app.domain.services.attention_injector import AttentionInjector
from app.domain.services.prompts.execution import (
    CONFIRMATION_SUMMARY_PROMPT,
    EXECUTION_SYSTEM_PROMPT,
    STREAMING_SUMMARIZE_PROMPT,
    build_execution_prompt,
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
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
            circuit_breaker=circuit_breaker,
            feature_flags=feature_flags,
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

        # Context manager for execution continuity (Phase 1)
        self._context_manager = ContextManager(max_context_tokens=8000)

        # Chain-of-Verification for hallucination reduction (Phase 2)
        self._cove = ChainOfVerification(
            llm=llm,
            json_parser=json_parser,
            max_questions=5,
            parallel_verification=True,
            min_response_length=200,  # Lowered to catch more hallucinations
        )
        self._cove_enabled = True  # Can be configured via feature flags

        # Source citation tracking for reports (capped to prevent unbounded growth)
        self._max_collected_sources: int = 200
        self._collected_sources: list[SourceCitation] = []
        self._seen_urls: set[str] = set()

        # Multimodal information persistence (P5.2)
        # Per Pythinker pattern: persist key findings every 2 view operations
        self._view_operation_count: int = 0
        self._multimodal_findings: list[dict] = []
        self._view_tools = {"file_view", "browser_view", "browser_get_content", "browser_agent_extract"}

        # Adaptive response policy controls
        self._response_policy: ResponsePolicy | None = None
        self._output_coverage_validator = OutputCoverageValidator()
        self._response_compressor = ResponseCompressor()

    def set_response_policy(self, policy: ResponsePolicy | None) -> None:
        """Set per-run response policy for summarize stage."""
        self._response_policy = policy

    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
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

        # Get task state context signal for recitation
        task_state_manager = get_task_state_manager()
        task_state_signal = task_state_manager.get_context_signal()

        # Get context pressure signal if memory is under pressure
        pressure_signal = None
        if self.memory:
            pressure = self._token_manager.get_context_pressure(self.memory.get_messages())
            pressure_signal = pressure.to_context_signal()

        # Retrieve relevant memories for this step (Phase 6: Qdrant integration)
        # Phase 3: Enhanced with cross-session intelligence
        memory_context = None
        if self._memory_service and self._user_id:
            try:
                context_parts = []

                # 1. Similar tasks from past sessions (Phase 3)
                similar_tasks = await self._memory_service.find_similar_tasks(
                    user_id=self._user_id,
                    task_description=step.description,
                    limit=3,
                )
                if similar_tasks:
                    task_context_lines = ["## Past Similar Tasks"]
                    for task in similar_tasks:
                        outcome = "✓ Success" if task.get("success") else "✗ Failed"
                        summary = task.get("content_summary", "")[:200]
                        task_context_lines.append(f"- {outcome}: {summary}")
                    context_parts.append("\n".join(task_context_lines))
                    logger.debug(f"Injected {len(similar_tasks)} similar tasks into context")

                # 2. Error context for tools being used (Phase 3)
                # Infer likely tools from step description
                step_lower = step.description.lower()
                likely_tools = [tool.name for tool in self.tools if tool.name.lower() in step_lower]

                if likely_tools:
                    for tool_name in likely_tools[:2]:  # Limit to 2 tools
                        error_context = await self._memory_service.get_error_context(
                            user_id=self._user_id,
                            tool_name=tool_name,
                            context=step.description,
                            limit=2,
                        )
                        if error_context:
                            context_parts.append(error_context)
                            logger.debug(f"Injected error context for tool: {tool_name}")

                # 3. Relevant memories for this step (Phase 3: with reranking + MMR)
                memories = await self._memory_service.retrieve_for_task(
                    user_id=self._user_id, task_description=step.description, limit=5
                )
                if memories:
                    memory_text = await self._memory_service.format_memories_for_context(memories, max_tokens=500)
                    context_parts.append(memory_text)
                    logger.debug(f"Injected {len(memories)} memories into execution context")

                # Combine all context parts
                if context_parts:
                    memory_context = "\n\n".join(context_parts)

            except Exception as e:
                logger.warning(f"Failed to retrieve memories for step: {e}")

        # Get proactive error pattern signals
        error_pattern_signal = None
        try:
            pattern_analyzer = get_error_pattern_analyzer()
            likely_tools = pattern_analyzer.infer_tools_from_description(step.description)
            error_pattern_signal = pattern_analyzer.get_proactive_signals(likely_tools)
            if error_pattern_signal:
                logger.debug(f"Injecting proactive error warning for tools: {likely_tools}")
        except Exception as e:
            logger.warning(f"Failed to get error pattern signals: {e}")

        # Get working context summary for execution continuity (Phase 1)
        context_summary = self._context_manager.get_context_summary()

        # Get synthesized insights from previous steps (Phase 2.5)
        synthesized_context = self._context_manager.get_synthesized_context(for_step_id=step.id)
        blockers = self._context_manager.get_blockers()

        # Build execution prompt with context signals
        base_prompt = build_execution_prompt(
            step=step.description,
            message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language,
            pressure_signal=pressure_signal,
            task_state=task_state_signal,
            memory_context=memory_context,
        )

        # Add working context if available
        if context_summary:
            base_prompt = f"{base_prompt}\n\n## Working Context\n{context_summary}"
            logger.debug("Injected working context into execution prompt")

        # Add synthesized insights from previous steps (Phase 2.5)
        if synthesized_context:
            base_prompt = f"{base_prompt}\n\n{synthesized_context}"
            logger.debug("Injected synthesized context from previous steps")

        # Add blocker warnings if any
        if blockers:
            blocker_text = "\n".join([f"- {b.content}" for b in blockers[:3]])
            base_prompt = f"{base_prompt}\n\n## ⚠️ Active Blockers\n{blocker_text}"
            logger.debug(f"Injected {len(blockers)} blocker warnings")

        # Add proactive error warnings if any
        if error_pattern_signal:
            base_prompt = f"{base_prompt}\n\n## Proactive Guidance\n{error_pattern_signal}"

        # Adapt prompt with context-specific guidance if applicable
        if self._prompt_adapter.should_inject_guidance():
            execution_message = self._prompt_adapter.adapt_prompt(base_prompt)
            logger.debug("Injected context guidance into execution prompt")
        else:
            execution_message = base_prompt

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

                    # Apply CoVe on step results for factual content (step-level verification)
                    if step.result and self._cove_enabled and self._user_request:
                        result_str = str(step.result)
                        if self._needs_cove_verification(result_str, self._user_request):
                            verified_result, cove_result = await self._apply_cove_verification(
                                result_str, self._user_request
                            )
                            if cove_result and cove_result.has_contradictions:
                                step.result = verified_result
                                logger.info(
                                    f"CoVe refined step result: {cove_result.claims_contradicted} claims corrected"
                                )

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
            # Always restore tools and system prompt after step, even on early return/exception
            self.tools = original_tools
            self.system_prompt = original_system_prompt

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
            step=Step(id="summarize", description="Composing final report...", status=ExecutionStatus.RUNNING),
        )

        # Use streaming prompt (plain markdown, no JSON wrapper)
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
                        accumulated_text += chunk
                        yield StreamEvent(content=chunk, is_final=False, phase="summarizing")

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

            # Extract title from first # heading
            message_title = self._extract_title(message_content)

            # Phase 2: Post-processing (CoVe + Critic on complete text)
            if len(message_content) > 300 and self._user_request:
                # Emit progress event before CoVe to prevent SSE timeout during verification
                yield StepEvent(
                    status=StepStatus.RUNNING,
                    step=Step(
                        id="cove_verification",
                        description="Verifying factual claims...",
                        status=ExecutionStatus.RUNNING,
                    ),
                )
                message_content, cove_result = await self._apply_cove_verification(message_content, self._user_request)
                if cove_result and cove_result.has_contradictions:
                    logger.info(
                        f"CoVe refined output: {cove_result.claims_contradicted} claims corrected, "
                        f"new confidence: {cove_result.confidence_score:.2f}"
                    )
                yield StepEvent(
                    status=StepStatus.COMPLETED,
                    step=Step(
                        id="cove_verification", description="Factual claims verified", status=ExecutionStatus.COMPLETED
                    ),
                )

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
                        id="summarize",
                        description="Summary failed delivery integrity checks",
                        status=ExecutionStatus.FAILED,
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
                step=Step(id="summarize", description="Summary complete", status=ExecutionStatus.COMPLETED),
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

                # Emit confirmation summary above the report preview
                confirmation = await self._generate_confirmation_summary(message_content, message_title)
                if confirmation:
                    yield MessageEvent(message=confirmation)

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
            missing_text = ", ".join(missing) if missing else "unknown_requirements"
            if strict_mode:
                issues.append(f"coverage_missing:{missing_text}")
            else:
                warnings.append(f"coverage_missing:{missing_text}")

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
    def _apply_attention(self, messages: list[dict]) -> list[dict]:
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

        access_time = event.started_at or datetime.now()

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
                logger.debug(f"Tracked search source: {title[:50] if title else url[:50]}")

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

    def get_collected_sources(self) -> list[SourceCitation]:
        """Get all collected source citations.

        Returns:
            List of deduplicated source citations
        """
        return self._collected_sources.copy()
