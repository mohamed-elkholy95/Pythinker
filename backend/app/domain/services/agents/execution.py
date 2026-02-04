import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from app.core.config import get_feature_flags
from app.domain.external.llm import LLM
from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.agent_response import SummarizeResponse
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    MessageEvent,
    ReportEvent,
    StepEvent,
    StepStatus,
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
from app.domain.services.agents.context_manager import ContextManager, InsightType
from app.domain.services.agents.critic import CriticAgent, CriticConfig, CriticVerdict
from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer
from app.domain.services.agents.prompt_adapter import PromptAdapter
from app.domain.services.agents.reward_scoring import RewardScorer
from app.domain.services.agents.task_state_manager import get_task_state_manager
from app.domain.services.attention_injector import AttentionInjector
from app.domain.services.prompts.execution import EXECUTION_SYSTEM_PROMPT, SUMMARIZE_PROMPT, build_execution_prompt
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
    ):
        super().__init__(
            agent_id=agent_id, agent_repository=agent_repository, llm=llm, json_parser=json_parser, tools=tools
        )
        # Initialize prompt adapter for dynamic context injection
        self._prompt_adapter = PromptAdapter()

        # Attention injector for goal recitation (Manus AI pattern)
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
            min_response_length=300,  # Only verify substantial responses
        )
        self._cove_enabled = True  # Can be configured via feature flags

        # Source citation tracking for reports
        self._collected_sources: list[SourceCitation] = []
        self._seen_urls: set = set()

        # Multimodal information persistence (P5.2)
        # Per Manus pattern: persist key findings every 2 view operations
        self._view_operation_count: int = 0
        self._multimodal_findings: list[dict] = []
        self._view_tools = {"file_view", "browser_view", "browser_get_content", "browser_agent_extract"}

    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
        # Store user request for critic context
        self._user_request = message.message

        # Set current step for inter-step context synthesis (Phase 2.5)
        self._context_manager.set_current_step(step.id)

        # Phase 3.5: Auto-detect skills from message and merge with explicitly selected ones
        try:
            from app.domain.services.skill_trigger_matcher import get_skill_trigger_matcher

            matcher = await get_skill_trigger_matcher()
            suggested_skills = await matcher.get_suggested_skills(
                message.message,
                max_suggestions=2,
            )
            existing = set(message.skills or [])
            merged = existing.union(set(suggested_skills or []))
            if merged and merged != existing:
                message.skills = list(merged)
                logger.info(
                    f"Skills selected (explicit + auto): explicit={list(existing)} auto={suggested_skills} merged={message.skills}"
                )
        except Exception as e:
            logger.debug(f"Skill auto-detection skipped: {e}")

        # Build skill context if skills are enabled for this message (Phase 3: Custom Skills)
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
                    # Extend system prompt with skill context
                    self.system_prompt = SYSTEM_PROMPT + EXECUTION_SYSTEM_PROMPT + skill_context.prompt_addition
                    logger.info(
                        f"✓ Injected skill context for skills: {skill_context.skill_ids} "
                        f"({len(skill_context.prompt_addition)} chars) "
                        f"(prompt_addition present: True, tool_restrictions: {skill_context.has_tool_restrictions()})"
                    )
                else:
                    logger.warning(f"Skill context built but no prompt_addition for: {message.skills}")

                # Phase 3.5: Apply tool restrictions from skills
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

                # Emit skill activation event for frontend debugging
                from app.domain.models.event import SkillActivationEvent

                skills_loaded = await registry.get_skills(message.skills)
                yield SkillActivationEvent(
                    skill_ids=message.skills,
                    skill_names=[s.name for s in skills_loaded],
                    tool_restrictions=tool_restrictions,
                    prompt_chars=len(skill_context.prompt_addition) if skill_context.prompt_addition else 0,
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
        memory_context = None
        if self._memory_service and self._user_id:
            try:
                memories = await self._memory_service.retrieve_for_task(
                    user_id=self._user_id, task_description=step.description, limit=5
                )
                if memories:
                    memory_context = self._memory_service.format_memories_for_context(memories, max_tokens=500)
                    logger.debug(f"Injected {len(memories)} memories into execution context")
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
                parsed_response = await self.json_parser.parse(event.message)
                new_step = Step.model_validate(parsed_response)
                step.success = new_step.success
                step.result = new_step.result
                step.attachments = new_step.attachments
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

                    # Track multimodal findings (P5.2 - Manus pattern)
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
                        func_name = event.function_name or ""
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
        step.status = ExecutionStatus.COMPLETED

    async def summarize(self) -> AsyncGenerator[BaseEvent, None]:
        """
        Summarize the completed task without tool execution.
        This method asks the LLM for a summary directly, bypassing the tool loop.
        """
        # Yield a status event to indicate summarizing phase
        yield StepEvent(
            status=StepStatus.RUNNING,
            step=Step(id="summarize", description="Preparing final summary...", status=ExecutionStatus.RUNNING),
        )

        # Add summarize prompt to memory and ask LLM directly (no tools)
        await self._add_to_memory([{"role": "user", "content": SUMMARIZE_PROMPT}])
        await self._ensure_within_token_limit()

        try:
            summary_response = None
            message_content = ""
            message_title = None
            message_attachments: list[str] = []

            # Try structured output first
            if hasattr(self.llm, "ask_structured"):
                try:
                    summary_response = await self.llm.ask_structured(
                        self.memory.get_messages(), response_model=SummarizeResponse, tools=None, tool_choice=None
                    )
                    message_content = summary_response.message
                    message_title = summary_response.title
                    message_attachments = summary_response.attachments
                    logger.debug(f"Summarize using structured output: {message_title}")
                except Exception as e:
                    logger.warning(f"Structured summarize failed, falling back: {e}")
                    summary_response = None

            # Fallback to regular JSON parsing
            if summary_response is None:
                response = await self.llm.ask(
                    self.memory.get_messages(), tools=None, response_format={"type": "json_object"}, tool_choice=None
                )

                content = response.get("content", "")
                logger.debug(f"Execution agent summary response: {content}")

                parsed_response = await self.json_parser.parse(content)
                message = Message.model_validate(parsed_response)
                message_content = message.message
                message_title = message.title
                message_attachments = message.attachments

            attachments = [FileInfo(file_path=file_path) for file_path in message_attachments]

            # Apply Chain-of-Verification for factual/research content (Phase 2)
            # CoVe runs BEFORE critic to catch hallucinations early
            cove_result = None
            if len(message_content) > 300 and self._user_request:
                message_content, cove_result = await self._apply_cove_verification(message_content, self._user_request)
                if cove_result and cove_result.has_contradictions:
                    logger.info(
                        f"CoVe refined output: {cove_result.claims_contradicted} claims corrected, "
                        f"new confidence: {cove_result.confidence_score:.2f}"
                    )

            # Run critic review on the summary with actual revision support
            # Critic runs AFTER CoVe to catch remaining issues
            if len(message_content) > 200 and self._user_request:
                message_content = await self._apply_critic_revision(message_content, attachments)

            # Reward hacking detection (log-only)
            flags = get_feature_flags()
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

            # Mark summarize step as completed
            yield StepEvent(
                status=StepStatus.COMPLETED,
                step=Step(id="summarize", description="Summary complete", status=ExecutionStatus.COMPLETED),
            )

            # Emit ReportEvent if there are attachments or substantial content
            # Otherwise emit a simple MessageEvent
            has_attachments = len(attachments) > 0
            is_substantial = len(message_content) > 500
            has_title = bool(message_title)
            is_report_structure = self._is_report_structure(message_content)

            if has_attachments or is_substantial or has_title or is_report_structure:
                title = message_title or self._extract_title(message_content)
                # Include collected sources in the report
                sources = self.get_collected_sources() if self._collected_sources else None
                yield ReportEvent(
                    id=str(uuid.uuid4()),
                    title=title,
                    content=message_content,
                    attachments=attachments if attachments else None,
                    sources=sources,
                )
            else:
                yield MessageEvent(message=message_content, attachments=attachments)

        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            yield ErrorEvent(error=f"Failed to generate summary: {e!s}")

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
        flags = get_feature_flags()
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
        # Length threshold
        if len(content) < 300:
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

    # Attention Injection (Manus AI Pattern)
    def _apply_attention(self, messages: list[dict]) -> list[dict]:
        """Apply attention injection to messages.

        Implements Manus AI's attention manipulation pattern to
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

    # Multimodal Information Persistence (P5.2 - Manus Pattern)
    def _track_multimodal_findings(self, event: ToolEvent) -> None:
        """Track and persist key findings from view operations.

        Per Manus pattern: save key findings every 2 view/browser operations.
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

        # Persist every 2 operations (Manus pattern)
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

        # Store in memory service if available
        if self._memory_service and self._user_id:
            try:
                # Store as a memory for future reference
                for finding in self._multimodal_findings:
                    self._memory_service.store_observation(
                        user_id=self._user_id,
                        observation_type=finding.get("type", "view"),
                        content=finding.get("content_preview") or finding.get("result", ""),
                        metadata=finding,
                    )
            except Exception as e:
                logger.debug(f"Failed to persist finding to memory: {e}")

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

            if url and url not in self._seen_urls:
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
        if not url or url in self._seen_urls:
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
