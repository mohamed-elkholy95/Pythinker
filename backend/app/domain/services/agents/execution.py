from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, TypeAdapter

from app.domain.exceptions.base import SandboxCrashError
from app.domain.external.llm import LLM
from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    MessageEvent,
    ReportEvent,
    SkillEvent,
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
from app.domain.services.tools.message import build_message_notify_delivery_metadata
from app.domain.services.tools.tool_tracing import get_tool_tracer
from app.domain.utils.json_parser import JsonParser
from app.domain.utils.json_repair import parse_json_response

_TOOL_MARKER_PATTERN = re.compile(r"^\[Attempted to call \w+ with ")

# P1-10: Refusal phrases that indicate the LLM is declining to answer.
# When these appear early in a response but the response continues for 500+
# chars afterward, the trailing content may contain unverified "padding".
_REFUSAL_PHRASES = [
    "I don't have access",
    "I cannot access",
    "not publicly available",
    "I cannot provide",
    "I can't provide",
    "I'm unable to provide",
    "I am unable to provide",
    "confidential information",
    "I don't have real-time",
    "I cannot verify",
    "I can't verify",
    "I don't have the ability",
    "beyond my capabilities",
    "I cannot browse",
    "I can't browse",
    "I do not have access",
]

_REFUSAL_PADDING_THRESHOLD = 500  # chars after refusal that trigger warning


def _detect_refusal_padding(content: str) -> None:
    """Log a warning if the response contains a refusal followed by substantial padding.

    This is a lightweight detection mechanism (not a hard block). When an LLM
    first refuses ("I don't have access to...") but then continues with 500+
    characters, those trailing claims may be unverified hallucinations used to
    fill space.
    """
    if not content or len(content) < _REFUSAL_PADDING_THRESHOLD:
        return

    content_lower = content.lower()
    for phrase in _REFUSAL_PHRASES:
        idx = content_lower.find(phrase.lower())
        if idx == -1:
            continue
        # Only flag if the refusal appears in the first 40% of the response
        # (a late mention is likely just referencing a limitation, not a refusal header)
        if idx > len(content) * 0.4:
            continue
        chars_after_refusal = len(content) - (idx + len(phrase))
        if chars_after_refusal > _REFUSAL_PADDING_THRESHOLD:
            logger.warning(
                "Refusal-padding detected: response contains '%s' at position %d "
                "followed by %d chars of additional content. The trailing content "
                "may contain unverified claims.",
                phrase,
                idx,
                chars_after_refusal,
            )
            return  # Log once per response


def _is_tool_marker_text(text: str) -> bool:
    """Detect tool-call marker text produced by message_normalizer.

    These strings are never valid step results — they are artifacts of
    orphaned tool_calls being converted to readable text.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    return bool(_TOOL_MARKER_PATTERN.match(stripped))


# Module-level metrics instance (can be overridden for testing)
_metrics: MetricsPort = get_null_metrics()
_metrics_warning_emitted: bool = False


def set_metrics(metrics: MetricsPort) -> None:
    """Set the metrics instance for this module."""
    global _metrics
    _metrics = metrics


def _warn_if_null_metrics() -> None:
    """Log a warning on first call if metrics are still NullMetrics."""
    global _metrics_warning_emitted
    if not _metrics_warning_emitted:
        _metrics_warning_emitted = True
        from app.domain.external.observability import NullMetrics

        if isinstance(_metrics, NullMetrics):
            logger.warning(
                "Agent execution using NullMetrics — Prometheus counters will not record. "
                "Call set_metrics() with a real MetricsPort to enable observability."
            )


if TYPE_CHECKING:
    from app.domain.external.config import DomainConfig
    from app.domain.services.agents.agent_context import AgentServiceContext
    from app.domain.services.memory_service import MemoryService
    from app.domain.utils.cancellation import CancellationToken

logger = logging.getLogger(__name__)

_SUGGESTION_LIST_ADAPTER = TypeAdapter(list[str])

SKILL_AWARENESS_PROMPT = """
<skill_awareness>
Before beginning execution, check if any available skills match the current task.
If you have the skill_invoke tool and the task involves a domain covered by an available skill,
invoke that skill first to get specialized instructions. Skill-guided execution produces
higher-quality results.

Available skill domains: {skill_names}
</skill_awareness>
"""

SKILL_ENFORCEMENT_PROMPT = """
<skill_enforcement>
## MANDATORY Skill Protocol

You MUST follow this protocol for EVERY task:

1. **CHECK**: Does the task match any available skill domain? ({skill_names})
2. **INVOKE**: If yes, call skill_invoke FIRST before any other tool
3. **FOLLOW**: Execute according to the loaded skill instructions
4. **REPORT**: Reference which skill guided your execution

Skipping skill invocation when a matching skill exists is a protocol violation.
Skills are not optional suggestions — they are mandatory workflow enhancers.
</skill_enforcement>
"""

SKILL_ENFORCEMENT_NUDGE = (
    "REMINDER: You have not invoked a skill yet. Call skill_invoke to load specialized instructions before continuing."
)


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
        memory_service: MemoryService | None = None,
        user_id: str | None = None,
        attention_injector: AttentionInjector | None = None,
        circuit_breaker=None,
        feature_flags: dict[str, bool] | None = None,
        cancel_token: CancellationToken | None = None,
        tool_result_store=None,
        config: DomainConfig | None = None,
        service_context: AgentServiceContext | None = None,
    ):
        self._config = config
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
            service_context=service_context,
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

        # LLM-based grounding verification (replaces deprecated Chain-of-Verification)
        self._hallucination_verification_enabled = True  # Configured via feature flags

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
            context_manager=self._context_manager,
            source_tracker=self._source_tracker,
            metrics=_metrics,
            resolve_feature_flags_fn=self._resolve_feature_flags,
            hallucination_verification_enabled=self._hallucination_verification_enabled,
        )

        # Step-level execution helpers — delegated to StepExecutor (Phase 3A extraction)
        self._step_executor = StepExecutor(
            context_manager=self._context_manager,
            source_tracker=self._source_tracker,
            metrics=_metrics,
        )
        # (Backward-compatible aliases are provided as properties below)

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
        # Cached file_write markdown content from execution steps.
        # Populated as tool events arrive (immune to memory compaction/validation).
        self._file_write_report_cache: str | None = None
        self._delivery_channel: str | None = None
        self._report_output_path: str | None = None
        self._artifact_references: list[dict[str, str]] = []
        self._has_unexecuted_scripts: bool = False

    def set_request_contract(self, contract) -> None:
        """Set request contract for search fidelity and entity context (Phase 4)."""
        self._request_contract = contract

    def _get_config(self) -> DomainConfig:
        """Return the injected DomainConfig, falling back to get_settings lazily."""
        if self._config is not None:
            return self._config
        from app.core.config import get_settings

        return get_settings()

    def set_delivery_channel(self, delivery_channel: str | None) -> None:
        """Set the active delivery channel for final delivery policy decisions."""
        self._delivery_channel = delivery_channel

    def set_report_output_path(self, report_output_path: str | None) -> None:
        """Set the preferred report output directory for execution prompts."""
        self._report_output_path = report_output_path.rstrip("/") if report_output_path else None

    def set_response_policy(self, policy: ResponsePolicy | None) -> None:
        """Set per-run response policy for summarize stage."""
        self._response_policy = policy

    def set_artifact_references(self, references: list[dict[str, Any]] | None) -> None:
        """Set summarize-time artifact references from session deliverables."""
        self._artifact_references = [dict(reference) for reference in references or [] if isinstance(reference, dict)]
        self._set_response_generator_artifact_references()

    def _set_response_generator_artifact_references(self, report_event_id: str | None = None) -> None:
        """Sync known artifacts into the response generator, optionally including the report markdown."""
        references = [dict(reference) for reference in self._artifact_references]
        if report_event_id:
            report_filename = f"report-{report_event_id}.md"
            if not any((reference.get("filename") or "").strip() == report_filename for reference in references):
                references.insert(0, {"filename": report_filename, "content_type": "text/markdown"})
        self._response_generator.set_artifact_references(references)

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
        """Override to apply skill enforcement tracking and search fidelity."""
        # Phase 4a: Track skill_invoke calls and reset tool_choice after first turn
        if function_name == "skill_invoke":
            self._skill_invoked_this_step = True
            # Determine enforcement outcome for metrics
            was_forced = getattr(self, "_force_skill_invoke_first_turn", False)
            _metrics.increment(
                "pythinker_skill_invocation_enforcement_total",
                labels={"outcome": "forced" if was_forced else "voluntary"},
            )
            # Phase 1: Reset tool_choice after forced first turn
            if was_forced:
                self.tool_choice = None
                self._force_skill_invoke_first_turn = False
                logger.debug("Skill enforcement: tool_choice reset to auto after skill_invoke")

        from app.domain.services.agents.search_fidelity import check_search_fidelity

        settings = self._get_config()
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
        _warn_if_null_metrics()
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

        # Inject skill-awareness prompt when SkillInvokeTool is present in the agent's tool list.
        # This is a general nudge (always injected, not just when message.skills is populated).
        _skill_invoke_tool = next(
            (t for t in self.tools if getattr(t, "name", "") == "skill_invoke"),
            None,
        )
        if _skill_invoke_tool is not None:
            _available_skills = getattr(_skill_invoke_tool, "_available_skills", [])
            if _available_skills:
                _skill_names = ", ".join(s.name for s in _available_skills)
                _cfg = self._get_config()

                # Phase 3: Use hardened enforcement prompt when enabled, otherwise soft awareness
                if getattr(_cfg, "skill_enforcement_prompt_enabled", True):
                    self.system_prompt += SKILL_ENFORCEMENT_PROMPT.format(skill_names=_skill_names)
                    logger.debug(f"Injected skill-enforcement prompt for skills: {_skill_names}")
                else:
                    self.system_prompt += SKILL_AWARENESS_PROMPT.format(skill_names=_skill_names)
                    logger.debug(f"Injected skill-awareness prompt for skills: {_skill_names}")

                # Phase 1: Force skill_invoke on first turn when skills are available.
                # This ensures the "Loading skill" chip always appears in chat for UX visibility.
                if getattr(_cfg, "skill_force_first_invocation", True):
                    self._force_skill_invoke_first_turn = True
                    self._skill_invoked_this_step = False
                    self._skill_enforcement_nudge_sent = False
                    self._skill_enforcement_nudge_after = getattr(_cfg, "skill_enforcement_nudge_after_iterations", 3)
                    logger.debug("Skill enforcement: will force skill_invoke on first turn")

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

                # Log skill activation
                logger.info(
                    f"Skill context applied: skills={message.skills}, "
                    f"tool_restrictions={tool_restrictions}, "
                    f"prompt_chars={len(skill_context.prompt_addition) if skill_context.prompt_addition else 0}"
                )

                # Emit SkillEvent for activity bar + synthetic ToolEvent for chat chip.
                # Only emit the "Loading skill" chip ONCE per session (first step).
                _skill_settings = self._get_config()
                _already_emitted = getattr(self, "_skill_chips_emitted", set())
                if _skill_settings.skill_ui_events_enabled and skill_context.prompt_addition:
                    for sid in skill_context.skill_ids:
                        skill = await registry.get_skill(sid)
                        if skill:
                            yield SkillEvent(
                                skill_id=sid,
                                skill_name=skill.name,
                                action="activated",
                                reason=f"Step requires {skill.category.value} capabilities",
                                tools_affected=list(skill_context.allowed_tools)
                                if skill_context.allowed_tools
                                else None,
                            )
                            # Emit synthetic ToolEvent only on first load per skill
                            if sid not in _already_emitted:
                                _synth_id = f"skill_synth_{sid}_{uuid.uuid4().hex[:8]}"
                                yield ToolEvent(
                                    tool_call_id=_synth_id,
                                    tool_name="skill_invoke",
                                    function_name="skill_invoke",
                                    function_args={"skill_name": sid},
                                    status=ToolStatus.CALLED,
                                )
                                _already_emitted.add(sid)
                                self._skill_chips_emitted = _already_emitted
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
            report_output_path=self._report_output_path,
        )

        # Build execution prompt from assembled context (includes all appendages)
        base_prompt = build_execution_prompt_from_context(ctx)

        # P1-11: Inject source citation instruction when search tools are available.
        # This ensures the agent knows it must cite URLs from search results.
        _has_search_tool = any(
            getattr(t, "name", "") in ToolName._SEARCH or "search" in getattr(t, "name", "").lower() for t in self.tools
        )
        if _has_search_tool:
            base_prompt += (
                "\n\n<citation_policy>"
                "When you use search tools and receive results with URLs, you MUST include "
                "source URLs in your step result. Cite each source as [Title](URL) or as a "
                "numbered reference. Never present search-derived information without attribution."
                "</citation_policy>"
            )

        # Source-grounding constraint for report/deliverable steps.
        # Prevents the LLM from fabricating data when composing final output.
        # Triggered when the step description indicates writing a report, summary,
        # comparison, or deliverable.
        _step_desc_lower = step.description.lower()
        _report_keywords = {"write", "report", "compile", "compose", "summarize", "comparison", "deliverable", "draft"}
        if any(kw in _step_desc_lower for kw in _report_keywords):
            base_prompt += (
                "\n\n<source_grounding>"
                "CRITICAL: When writing your output, ONLY include facts, statistics, features, "
                "and pricing that you found in your search results and tool outputs during this session. "
                "Do NOT invent, fabricate, or guess any data. If specific information was not found "
                "in your research, explicitly state 'information not confirmed in available sources' "
                "rather than guessing. Accuracy is more important than completeness."
                "</source_grounding>"
            )

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
            _is_adaptive = self._get_config().adaptive_model_selection_enabled
            if _is_adaptive:
                logger.info("Adaptive model routing selected '%s' for step", selected_model)
            else:
                logger.debug("Model routing disabled, using default model '%s'", selected_model)

        # Phase 1: Force skill_invoke on first LLM turn via tool_choice
        # Phase 1: Save original tool_choice for restoration after step.
        # Skill visibility is handled by synthetic ToolEvent emission above;
        # tool_choice forcing is kept as a soft nudge via the enforcement prompt.
        _original_tool_choice = self.tool_choice

        step.status = ExecutionStatus.RUNNING
        yield StepEvent(status=StepStatus.STARTED, step=step)
        _step_start_time = time.monotonic()
        _tool_call_start_times: dict[str, float] = {}
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
                    _step_duration_ms = (time.monotonic() - _step_start_time) * 1000
                    yield StepEvent(status=StepStatus.FAILED, step=step, duration_ms=_step_duration_ms)
                elif isinstance(event, MessageEvent):
                    # Skip tool-marker artifacts from message_normalizer
                    if _is_tool_marker_text(event.message):
                        logger.warning("Step response is tool-marker text (normalizer artifact); skipping JSON parse")
                        continue
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

                    if not step.success:
                        step.status = ExecutionStatus.FAILED
                        _step_duration_ms = (time.monotonic() - _step_start_time) * 1000
                        yield StepEvent(status=StepStatus.FAILED, step=step, duration_ms=_step_duration_ms)
                        continue

                    step.status = ExecutionStatus.COMPLETED

                    # Apply hallucination verification on step results.
                    # Use _display_result so step.result (the structured domain object)
                    # is never mutated by display-layer post-processing.
                    _display_result: str | None = step.result

                    # Guard: extract clean text if _display_result is raw JSON
                    # (happens when LLM returns {"success":..,"result":..} as step.result)
                    if _display_result and _display_result.lstrip().startswith("{"):
                        try:
                            _parsed_display = json.loads(_display_result)
                            if isinstance(_parsed_display, dict) and "result" in _parsed_display:
                                _extracted = _parsed_display["result"]
                                if _extracted and isinstance(_extracted, str):
                                    _display_result = _extracted
                        except (json.JSONDecodeError, TypeError):
                            pass
                    if step.result and self._user_request:
                        result_str = str(step.result)
                        if self._needs_verification(result_str, self._user_request):
                            verified_result = await self._apply_hallucination_verification(
                                result_str, self._user_request
                            )
                            if verified_result != result_str:
                                _display_result = verified_result
                                logger.info("Hallucination verification refined step result")

                    _step_duration_ms = (time.monotonic() - _step_start_time) * 1000
                    yield StepEvent(status=StepStatus.COMPLETED, step=step, duration_ms=_step_duration_ms)
                    if _display_result:
                        yield MessageEvent(message=_display_result)
                    continue
                elif isinstance(event, ToolEvent):
                    # Record tool call start time for Prometheus latency tracking
                    if event.status == ToolStatus.CALLING and event.tool_call_id:
                        _tool_call_start_times[event.tool_call_id] = time.monotonic()

                    # Track tool usage for prompt adapter
                    if event.status == ToolStatus.CALLED:
                        success = event.function_result.success if event.function_result else True
                        error = event.function_result.message if event.function_result and not success else None
                        # Guard against None function_name
                        func_name = event.function_name or "unknown"
                        self._prompt_adapter.track_tool_use(func_name, success=success, error=error)

                        # Record Prometheus tool call metrics
                        with contextlib.suppress(Exception):
                            from app.core.prometheus_metrics import record_tool_call

                            _tool_latency = 0.0
                            if event.tool_call_id and event.tool_call_id in _tool_call_start_times:
                                _tool_latency = time.monotonic() - _tool_call_start_times.pop(event.tool_call_id)
                            record_tool_call(
                                tool=func_name,
                                status="success" if success else "error",
                                latency=_tool_latency,
                            )

                        # Track sources from tool events for report bibliography
                        self._track_sources_from_tool_event(event)

                        # Feed search evidence to verifier for grounding context
                        self._feed_search_evidence_to_verifier(func_name, event)

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
                                    # Cache markdown deliverable content for
                                    # summarization recovery.  This survives
                                    # memory compaction and orphan-conversion
                                    # that would strip tool_calls from memory.
                                    file_content = event.function_args.get("content", "")
                                    if (
                                        isinstance(file_content, str)
                                        and file_path.endswith(".md")
                                        and len(file_content) > 200
                                    ):
                                        self._file_write_report_cache = file_content
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

                    if event.function_name and event.function_name == "message_notify_user":
                        if event.status == ToolStatus.CALLING:
                            yield MessageEvent(
                                message=event.function_args.get("text", ""),
                                delivery_metadata=build_message_notify_delivery_metadata(event.function_args),
                            )
                        continue

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
            # If stuck recovery was exhausted, use TERMINATED so analytics can
            # distinguish force-terminated steps from genuine completions.
            if step.status != ExecutionStatus.FAILED:
                if self._stuck_recovery_exhausted:
                    step.status = ExecutionStatus.TERMINATED
                    step.success = False
                else:
                    step.status = ExecutionStatus.COMPLETED
                    if not step.success:
                        step.success = True
        except SandboxCrashError as e:
            # REL-009: Sandbox crashed — fail step immediately with critical error event
            logger.critical("Sandbox crash detected during step execution: %s", e)
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield ErrorEvent(
                error=str(e),
                error_type="sandbox_crash",
                recoverable=False,
                error_category="upstream",
                severity="critical",
                error_code="SANDBOX_CRASH",
            )
            yield StepEvent(status=StepStatus.FAILED, step=step)
        finally:
            # Always restore tools, system prompt, model override, and tool_choice after step
            self.tools = original_tools
            self.system_prompt = original_system_prompt
            self._step_model_override = None  # DeepCode Phase 1: Reset model override
            self.tool_choice = _original_tool_choice  # Phase 1: Restore tool_choice

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
                coverage sections and only eligible non-critical delivery-gate
                failures can be downgraded to warnings. Critical integrity
                failures still block final delivery.
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
                description="Writing report...",
                status=ExecutionStatus.RUNNING,
                step_type=StepType.FINALIZATION,
            ),
        )

        # Use streaming prompt (plain markdown, no JSON wrapper)
        # Phase 2: Switch to citation-aware prompt when sources were collected
        # Phase 3: Use unified build_summarize_prompt() with depth-aware length guidance
        from app.domain.services.prompts.execution import build_summarize_prompt, detect_comparison_intent

        _is_comparison = detect_comparison_intent(self._user_request or "")

        # Preallocate report_event_id so the artifact references block in
        # the prompt can reference the exact filename (report-<uuid>.md)
        # before generation starts.
        report_event_id: str | None = None
        if self._artifact_references or self._collected_sources:
            report_event_id = str(uuid.uuid4())

        # Build artifact references list for the prompt
        prompt_artifact_refs = [dict(ref) for ref in self._artifact_references]
        if report_event_id:
            prompt_artifact_refs.insert(
                0, {"filename": f"report-{report_event_id}.md", "content_type": "text/markdown"}
            )
        self._set_response_generator_artifact_references(report_event_id)

        if self._collected_sources:
            source_list = self._build_numbered_source_list()
            summarize_prompt = (
                build_summarize_prompt(
                    has_sources=True,
                    source_list=source_list,
                    research_depth=self._research_depth,
                    is_comparison=_is_comparison,
                    artifact_references=prompt_artifact_refs or None,
                )
                + f"\n\n## Available Sources\n{source_list}"
                # Pre-baked references anchor: injecting the complete numbered list
                # here guarantees the LLM can reference it at the end of its
                # response, even when output is near the token budget.
                + "\n\n⚠️ MANDATORY: Your response MUST end with a `## References` section "
                "that lists ONLY the sources you actually cited inline using [N] notation. "
                "Use the exact numbered format `[N] Title - URL` from 'Available Sources' above. "
                "Do NOT include sources you did not cite inline — every entry in References "
                "must correspond to an inline [N] citation in the report body."
            )
        else:
            summarize_prompt = build_summarize_prompt(
                has_sources=False,
                research_depth=self._research_depth,
                is_comparison=_is_comparison,
                artifact_references=prompt_artifact_refs or None,
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

        # Recency reinforcement: LLMs in large contexts attend most to the
        # last few messages.  Without this, the "write report NOW" instruction
        # gets lost in 100K+ chars of conversation and the LLM produces
        # meta-commentary like "I'll write the report now..." instead of
        # the actual report.  This short assistant+user turn pins attention
        # on the output format requirement.
        await self._add_to_memory(
            [
                {"role": "assistant", "content": "I'll begin writing the report now."},
                {
                    "role": "user",
                    "content": "No — do NOT narrate. Start DIRECTLY with `# ` (a markdown heading). Write the report content, not a description of it.",
                },
            ]
        )

        # Snapshot file_write content BEFORE token trimming.  If memory is
        # aggressively pruned the original report markdown (written to the
        # workspace via file_write) would be lost — caching it here allows
        # _extract_report_from_file_write_memory to recover it.
        self._pre_trim_report_cache = self._extract_report_from_file_write_memory()
        # Fallback: use the execution-time file_write cache if memory extraction
        # failed (e.g. because _validate_and_fix_messages converted the orphaned
        # tool_calls to "[Previously called file_write]" text before this point).
        if not self._pre_trim_report_cache and self._file_write_report_cache:
            self._pre_trim_report_cache = self._file_write_report_cache
            logger.info(
                "Pre-trim cache populated from execution file_write cache (%d chars)",
                len(self._pre_trim_report_cache),
            )
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
            # Save original messages before Stage-1 mutates stream_messages for
            # continuation turns; Stage-2 uses this snapshot so it only ever
            # prepends the system + last-user messages (no duplicate history).
            original_stream_messages = stream_messages
            stream_metadata: dict[str, Any] = {}
            truncation_exhausted = False
            max_stream_continuations = 2 if delivery_integrity_enabled else 1
            stream_attempt = 0

            # Use fast model for report streaming — long-form text generation doesn't need 80B.
            # Falls back to the default model when FAST_MODEL is not configured.
            _summarize_model: str | None = self._get_config().fast_model or None
            _summarize_max_tokens: int = self._get_config().summarization_max_tokens

            if self._can_deliver_pretrim_report_directly(
                response_policy=active_policy,
                all_steps_completed=all_steps_completed,
                delivery_channel=delivery_channel,
            ):
                message_content = self._clean_report_content(self._pre_trim_report_cache or "")
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
                        _powerful_model: str | None = self._get_config().powerful_model or None
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
                    # Try file_write memory before LLM retry — the report may
                    # already exist on disk from a prior step's file_write call.
                    # This is deterministic and avoids depending on the LLM.
                    _fw_report = self._extract_report_from_file_write_memory()
                    if _fw_report and len(_fw_report) > 200:
                        logger.info(
                            "Recovered report from file_write memory (%d chars), skipping LLM retry",
                            len(_fw_report),
                        )
                        message_content = _fw_report
                        _metrics.record_counter(
                            "pythinker_summarization_meta_commentary_total",
                            labels={"recovery": "file_write_memory"},
                        )
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
                    # Try file_write memory before LLM retry — the report may
                    # already exist on disk from a prior step's file_write call.
                    _fw_report = self._extract_report_from_file_write_memory()
                    if _fw_report and len(_fw_report) > len(message_content):
                        logger.info(
                            "Recovered report from file_write memory for quality gate (%d chars)",
                            len(_fw_report),
                        )
                        message_content = _fw_report
                        _metrics.record_counter(
                            "pythinker_summarization_low_quality_total",
                            labels={"recovery": "file_write_memory"},
                        )
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

                        # Request continuation using pattern-specific prompt.
                        # Use original_stream_messages (pre-Stage-1-mutation snapshot) so
                        # the context is never duplicated across continuation turns.
                        continuation_messages = [
                            *original_stream_messages,
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
                                _powerful = self._get_config().powerful_model or None
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

                            # Update continuation messages for next attempt.
                            # Use original_stream_messages snapshot to avoid duplication.
                            continuation_messages = [
                                *original_stream_messages,
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

            # Emit the final stream sentinel AFTER all Stage-2 continuations have
            # completed so the frontend never sees is_final=True mid-stream.
            # The pretrim fast-path already emits its own is_final sentinel above.
            if stream_metadata.get("provider") != "pretrim_cache":
                yield StreamEvent(content="", is_final=True, phase="summarizing")

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
            _phantom_prune_count = 0
            try:
                from app.domain.services.agents.citation_integrity import repair_citations, validate_citations

                cite_result = validate_citations(message_content)
                if not cite_result.is_valid:
                    _phantom_prune_count = len(cite_result.phantom_references) if cite_result.phantom_references else 0
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
                _verification_desc = "Verification complete"
                if _phantom_prune_count > 0:
                    _verification_desc = f"Verified ({_phantom_prune_count} ungrounded citation{'s' if _phantom_prune_count != 1 else ''} removed)"
                yield StepEvent(
                    status=StepStatus.RUNNING,
                    step=Step(
                        id="finalization",
                        description=_verification_desc,
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

            # Reuse preallocated report_event_id from prompt build phase,
            # or allocate a new one if none was preallocated.
            if not report_event_id and (
                "artifact references" in {section.lower() for section in _required_sections}
                or self._is_report_structure(message_content)
                or len(message_content) > 500
                or bool(self._pre_trim_report_cache)
            ):
                report_event_id = str(uuid.uuid4())
                self._set_response_generator_artifact_references(report_event_id)

            coverage_result = self._output_coverage_validator.validate(
                output=message_content,
                user_request=self._user_request or "",
                required_sections=_required_sections,
            )
            if not coverage_result.is_valid:
                missing = coverage_result.missing_requirements or []
                logger.warning(
                    "Summary coverage missing required elements before compression: %s",
                    ", ".join(missing) or "unknown",
                )

                # Proactively inject artifact references if the LLM omitted them.
                # This prevents the delivery gate from flagging a boilerplate
                # "No artifacts" section and ensures compression preserves them.
                # NOTE: We check the *response_generator's* artifact list (not
                # self._artifact_references) because _set_response_generator_artifact_references()
                # enriches the list with the report markdown even when the executor's
                # copy is empty (upstream session_files may be unavailable at this point).
                if "artifact references" in {m.lower() for m in missing}:
                    artifact_section = self._response_generator.get_artifact_references_section_if_present()
                    if artifact_section:
                        message_content = message_content.rstrip() + "\n\n" + artifact_section
                        # Re-validate after injection
                        coverage_result = self._output_coverage_validator.validate(
                            output=message_content,
                            user_request=self._user_request or "",
                            required_sections=_required_sections,
                        )
                        if coverage_result.is_valid:
                            logger.info("Artifact references injected — coverage now valid")

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

            if not gate_passed and self._can_auto_repair_delivery_integrity(gate_issues, message_content):
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
                if all_steps_completed and self._can_downgrade_delivery_integrity_issues(gate_issues):
                    # All plan steps succeeded — blocking the report is worse than
                    # delivering it with minor integrity gaps.  Downgrade to warning
                    # and proceed with delivery so the user sees their completed work.
                    # This applies equally to Telegram and web UI channels — Telegram
                    # users should not receive a worse experience than web users.
                    logger.warning(
                        "Delivery integrity gate failed but all steps completed — "
                        "downgrading to warning and delivering report (channel=%s): %s",
                        delivery_channel or "web",
                        issue_text,
                    )
                    _metrics.record_counter(
                        "delivery_gate_downgraded_total",
                        labels={"reason": "all_steps_completed", "channel": delivery_channel or "web"},
                    )
                    # When hallucination rewrite failed and we're downgrading,
                    # add a prominent user-facing warning so the user knows the
                    # content may be unreliable.
                    if "hallucination_ratio_critical" in issue_text:
                        _halluc_notice = (
                            "\n\n> **⚠️ Content Advisory:** Parts of this report could not "
                            "be fully verified against available sources. Automated "
                            "fact-checking flagged some claims as unverifiable. Please "
                            "cross-reference critical data points independently."
                        )
                        message_content += _halluc_notice
                        logger.info("Added hallucination downgrade advisory to report")
                    # Enhance disclaimer if unexecuted scripts detected (write-without-execute audit)
                    if "hallucination" in issue_text and getattr(self, "_has_unexecuted_scripts", False):
                        _bench_notice = (
                            "\n\n> **Note:** Benchmark data in this report is based on "
                            "web research and published benchmarks, not actual execution "
                            "results. The benchmark script was created but not run in "
                            "the sandbox environment."
                        )
                        message_content += _bench_notice
                        logger.info("Added unexecuted-script disclaimer to report")
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
                    user_error = (
                        "I couldn't send the final response for this request. Please send it again."
                        if telegram_final_delivery
                        else f"Delivery integrity gate blocked output: {issue_text}"
                    )
                    yield ErrorEvent(error=user_error)
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

            # P1-10: Refusal-padding detection — warn if the LLM refuses but then
            # pads the response with potentially unverified claims.
            _detect_refusal_padding(message_content)

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

            # Final safety net: reject content that is only orphaned tool-call
            # placeholders (e.g. "[Previously called file_write]").  These are
            # internal context-compression markers and must never reach the UI.
            _placeholder_re = re.compile(r"\[Previously called \w+\]")
            if _placeholder_re.search(message_content):
                logger.warning("Report content contains orphaned tool-call placeholder — stripping")
                message_content = _placeholder_re.sub("", message_content).strip()
            if not message_content and self._pre_trim_report_cache:
                logger.info(
                    "Recovering report from pre-trim cache after placeholder stripping (%d chars)",
                    len(self._pre_trim_report_cache),
                )
                message_content = self._clean_report_content(self._pre_trim_report_cache)

            # Layer 2: Richness fallback — if the LLM produced a shallow summary
            # but the pre-trim cache contains a much richer report, prefer the cache.
            message_content = self._richness_fallback(message_content, self._pre_trim_report_cache)

            # Emit final report/message event
            is_substantial = len(message_content) > 500
            has_title = bool(message_title)
            is_report_structure = self._is_report_structure(message_content)

            # Track report event ID for suggestion anchoring
            message_event_id = None
            if is_substantial or has_title or is_report_structure:
                title = message_title or "Summary"
                sources = self.get_collected_sources() if self._collected_sources else None

                report_event_id = report_event_id or str(uuid.uuid4())
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
            # Many exception types (TimeoutError, httpx.ReadTimeout, RemoteProtocolError)
            # produce empty str(e).  Always log the type + repr for diagnostics.
            _exc_label = f"{type(e).__name__}: {e!r}" if not str(e).strip() else f"{type(e).__name__}: {e}"
            logger.error("Error during summarization: %s", _exc_label, exc_info=True)

            # Salvage accumulated content — the stream may have produced a usable
            # partial report before the exception.  Same strategy as CancelledError above.
            # Also check the coalescing buffer for unflushed content that wasn't
            # yielded before the error (e.g. small final chunk still in buffer).
            _coalesce_pending = getattr(self._response_generator, "_coalesce_pending", "") or ""
            _current_attempt_extra = attempt_text + _coalesce_pending
            # Proper merge: when both sides have content use merge helper to avoid
            # duplication; when only one side has content use it directly.
            if accumulated_text and _current_attempt_extra:
                _salvage = self._merge_stream_continuation(accumulated_text, _current_attempt_extra)
            else:
                _salvage = accumulated_text or _current_attempt_extra
            if _salvage.strip():
                _salvage_clean = self._clean_report_content(_salvage.strip())
                if _salvage_clean and len(_salvage_clean) > 200:
                    _salvage_clean = sanitize_report_output(_salvage_clean)
                    _salvage_title = self._extract_title(_salvage_clean) or "Research Summary"
                    _salvage_notice = (
                        "> **Partial Report:** An error occurred during report generation. "
                        "The content below represents findings collected before the error.\n\n"
                    )
                    yield ReportEvent(
                        id=str(uuid.uuid4()),
                        title=f"[Partial] {_salvage_title}",
                        content=_salvage_notice + _salvage_clean,
                    )
                    logger.warning(
                        "Summarize error recovery: emitted %d-char partial report from accumulated stream",
                        len(_salvage_clean),
                    )
                    return

            yield ErrorEvent(error=f"Failed to generate summary: {_exc_label}")

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
        """Return whether the cached draft can bypass the summarize LLM call.

        Previously restricted to Telegram-only; now any channel can use the
        pre-trim cache when all quality gates pass.  The coverage validator
        and delivery integrity gate already enforce structural quality.
        """
        pretrim_report = self._pre_trim_report_cache or ""
        pretrim_report_stripped = pretrim_report.strip()
        if not pretrim_report_stripped:
            return False
        if not all_steps_completed:
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
        """Allow downgrade only for non-critical integrity failures.

        When all plan steps completed, minor structural gaps can still be
        downgraded so users receive their completed work.  Structural
        failures (truncation, broken citations) remain non-downgradable.

        Critical grounding failure (``hallucination_ratio_critical``) is always
        non-downgradable: fact-checking found a high unsupported-claim ratio
        and rewrite failed — delivering anyway would ship materially unreliable
        answers. The user sees an error and can retry; this matches fail-closed
        grounding policy (2026-03 monitoring report).
        """
        # Hard non-downgradable: structurally broken output or unsafe to ship
        hard_non_downgradable = {
            "stream_truncation_unresolved",
            "citation_integrity_unresolved",
            "hallucination_ratio_critical",
        }
        for issue in issues:
            token = (issue or "").split(":", 1)[0].strip().lower()
            if token in hard_non_downgradable:
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

    def _richness_fallback(
        self,
        llm_content: str,
        pre_trim_cache: str | None,
    ) -> str:
        """Prefer the pre-trim cache when the LLM output is significantly shorter.

        Returns the richer content (cache or llm_content).  The cache must be
        at least 2.5x longer AND at least 2000 characters to qualify — this
        prevents replacing a good summary with a tiny or partial cache.
        """
        if not pre_trim_cache:
            return llm_content

        cache_len = len(pre_trim_cache.strip())
        llm_len = len(llm_content.strip()) or 1  # avoid division by zero

        if cache_len >= 2000 and cache_len >= llm_len * 2.5:
            logger.info(
                "Richness fallback: pre-trim cache (%d chars) is %.1fx longer "
                "than LLM summary (%d chars) — substituting cached report",
                cache_len,
                cache_len / llm_len,
                llm_len,
            )
            return pre_trim_cache

        return llm_content

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

        Attempt 1: uses response_format=json_object (enforced by the API).
        Attempt 2: falls back to plain-text mode with an explicit "JSON only"
        instruction in the prompt — handles providers that reject json_object format.

        Uses local JSON extraction/repair on the correction result to avoid hard
        failing on prose-prefixed responses.
        """
        schema = '{"success": boolean, "result": string|null, "attachments": string[]}'
        preview = raw_message[:1800]
        # Each tuple: (prompt_text, use_json_format)
        correction_attempts: list[tuple[str, bool]] = [
            (
                "Your previous response was not valid JSON.\n"
                f'Previous response:\n"""\n{preview}\n"""\n\n'
                f"You MUST respond with ONLY valid JSON matching this schema: {schema}\n"
                "No prose. No markdown. JSON object only.",
                True,  # attempt 1: enforce via response_format
            ),
            (
                "Return ONLY a valid JSON object. "
                f"Schema: {schema}. "
                "No explanation, no markdown, and no surrounding text. "
                "Respond only with valid JSON.",
                False,  # attempt 2: plain mode with explicit instruction
            ),
        ]

        for attempt_index, (correction_prompt, use_json_format) in enumerate(correction_attempts, start=1):
            response_format: dict[str, str] | None = {"type": "json_object"} if use_json_format else None
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
                    response_format=response_format,
                    enable_caching=False,
                    model=self._step_model_override,
                )
            except Exception as correction_err:
                logger.warning(
                    "Step JSON correction retry failed on attempt %d (json_format=%s): %s",
                    attempt_index,
                    use_json_format,
                    correction_err,
                )
                if use_json_format:
                    # json_object format rejected by provider — fall through to plain attempt
                    logger.info("Falling through to plain-mode JSON correction retry")
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
        self._output_verifier._research_depth = self._research_depth
        return await self._output_verifier.apply_hallucination_verification(content, query)

    async def _verify_hallucination(self, content: str, query: str):
        """Run hallucination verification and return structured gating signals."""
        self._output_verifier._metrics = _metrics  # sync module-level metrics
        self._output_verifier._research_depth = self._research_depth
        return await self._output_verifier.verify_hallucination(content, query)

    def _build_source_context(self) -> list[str]:
        """Build grounding context from collected sources (delegated to OutputVerifier)."""
        return self._output_verifier.build_source_context()

    def _needs_verification(self, content: str, query: str) -> bool:
        """Determine if content needs hallucination verification (delegated)."""
        return self._output_verifier.needs_verification(content, query)

    def _is_report_structure(self, content: str) -> bool:
        """Check if content has report-like structure (delegated to ResponseGenerator)."""
        return self._response_generator.is_report_structure(content)

    # ── Backward-compatible StepExecutor property aliases ─────────────
    # These proxy through _step_executor so they always reflect live state
    # rather than stale snapshot values set at __init__ time.

    @property
    def _view_operation_count(self) -> int:
        return self._step_executor._view_operation_count

    @_view_operation_count.setter
    def _view_operation_count(self, value: int) -> None:
        self._step_executor._view_operation_count = value

    @property
    def _multimodal_findings(self) -> list:
        return self._step_executor._multimodal_findings

    @_multimodal_findings.setter
    def _multimodal_findings(self, value: list) -> None:
        self._step_executor._multimodal_findings = value

    @property
    def _view_tools(self) -> set:
        return self._step_executor._view_tools

    @_view_tools.setter
    def _view_tools(self, value: set) -> None:
        self._step_executor._view_tools = value

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

    def _feed_search_evidence_to_verifier(self, tool_name: str, event: ToolEvent) -> None:
        """Extract search snippets from tool results and feed to verifier for grounding."""
        if self._output_verifier is None:
            return
        if tool_name not in ("info_search_web", "wide_research"):
            return
        # Search results are in event.function_result.message as text with embedded snippets
        result = event.function_result
        if result is None:
            return
        output_text = str(getattr(result, "message", "") or "")
        if len(output_text) > 100:  # Only meaningful results
            self._output_verifier.add_step_source(
                title=f"Search results: {tool_name}",
                url="",
                snippet=output_text[:2000],
            )

    def _build_numbered_source_list(self) -> str:
        """Build a numbered source list for citation-aware summarization."""
        return self._source_tracker.build_numbered_source_list()

    def get_collected_sources(self) -> list[SourceCitation]:
        """Get all collected source citations."""
        return self._source_tracker.get_collected_sources()

    def restore_collected_sources(self, sources: list[SourceCitation]) -> None:
        """Restore persisted sources from a prior session.

        Used during session reactivation to hydrate grounding context so
        hallucination verification retains access to original sources.
        """
        self._source_tracker.restore_sources(sources)
