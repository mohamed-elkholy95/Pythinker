import contextlib
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Optional

from pydantic import ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.domain.external.llm import LLM
from app.domain.models.long_term_memory import MemoryType
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, PhaseType, Plan, Step, StepType
from app.domain.models.skill import Skill
from app.domain.models.structured_outputs import (
    PlanOutput as StructuredPlanOutput,
)
from app.domain.models.structured_outputs import (
    build_validation_feedback,
    validate_llm_output,
)
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.requirement_extractor import (
    RequirementSet,
    extract_requirements,
)
from app.domain.services.prompts.planner import (
    PLANNER_SYSTEM_PROMPT,
    THINKING_PROMPT,
    UPDATE_PLAN_PROMPT,
    build_create_plan_prompt,
)
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.skill_loader import SkillLoader

if TYPE_CHECKING:
    from app.domain.external.search import SearchEngine
    from app.domain.services.memory_service import MemoryService
    from app.domain.utils.cancellation import CancellationToken
from app.domain.models.agent_response import PlanResponse, PlanUpdateResponse
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStatus,
    StreamEvent,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.tools.base import BaseTool
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

# Default step constraints (can be overridden by complexity-based limits)
DEFAULT_MIN_PLAN_STEPS = 2
DEFAULT_MAX_PLAN_STEPS = 4
MAX_MERGED_STEP_CHARS = 240

# Adaptive step constraints based on task complexity
COMPLEXITY_STEP_LIMITS = {
    "simple": (1, 2),
    "medium": (2, 4),
    "complex": (3, 8),
}
RESEARCH_STEP_CAP = 10
RESEARCH_COMPLEXITY_HINTS = [
    "research",
    "investigate",
    "compare",
    "analysis",
    "analyze",
    "benchmark",
    "multi-source",
    "multiple sources",
    "citation",
    "report",
    "cross-check",
    "validate findings",
]


def is_research_task_message(message: str) -> bool:
    """Heuristic for requests that should be treated as research-heavy."""
    lowered = message.lower()
    return any(hint in lowered for hint in RESEARCH_COMPLEXITY_HINTS)


def get_task_complexity(message: str, tools: list | None = None) -> str:
    """Determine task complexity based on message content.

    Args:
        message: The user's task request
        tools: Optional list of available tools

    Returns:
        Complexity level: 'simple', 'medium', or 'complex'
    """
    message_lower = message.lower()

    # Simple task indicators (single action, no conditionals)
    simple_indicators = [
        "just",
        "only",
        "simply",
        "quick",
        "single",
        "one file",
        "one thing",
        "basic",
    ]

    # Complex task indicators (research, multi-source, conditional logic)
    complex_indicators = [
        "research",
        "investigate",
        "compare",
        "analyze",
        "comprehensive",
        "detailed",
        "multiple sources",
        "if possible",
        "depending on",
        "various",
        "full report",
        "in-depth",
        "thorough",
    ]

    # Count indicators
    simple_count = sum(1 for ind in simple_indicators if ind in message_lower)
    complex_count = sum(1 for ind in complex_indicators if ind in message_lower)

    # Message length heuristic
    word_count = len(message.split())

    # Short messages with simple indicators -> simple
    if word_count < 15 and simple_count > 0 and complex_count == 0:
        return "simple"

    # Research tasks should default to complex even when phrased briefly.
    if is_research_task_message(message):
        return "complex"

    # Long messages or multiple complex indicators -> complex
    if word_count > 50 or complex_count >= 2:
        return "complex"

    # Check for multi-part requests (numbered items, bullets)
    numbered_items = len(re.findall(r"(?:^|\n)\s*\d+[\.\)]\s", message))
    bullet_items = len(re.findall(r"(?:^|\n)\s*[-*]\s", message))

    if numbered_items >= 3 or bullet_items >= 3:
        return "complex"

    # Default to medium
    return "medium"


def get_step_limits(complexity: str) -> tuple:
    """Get min/max step limits for a given complexity level.

    Args:
        complexity: 'simple', 'medium', or 'complex'

    Returns:
        Tuple of (min_steps, max_steps)
    """
    return COMPLEXITY_STEP_LIMITS.get(complexity, (DEFAULT_MIN_PLAN_STEPS, DEFAULT_MAX_PLAN_STEPS))


def _step_from_description(index: int, desc) -> Step:
    """Create a Step from a StepDescription, preserving phase metadata."""

    def _safe_text_attr(name: str) -> str | None:
        value = getattr(desc, name, None)
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    step = Step(id=str(index + 1), description=_safe_text_attr("description") or f"Step {index + 1}")

    phase_value = getattr(desc, "phase", None)
    if isinstance(phase_value, PhaseType):
        phase_text = phase_value.value
    elif isinstance(phase_value, str):
        phase_text = phase_value.strip()
    else:
        phase_text = None

    if phase_text:
        try:
            PhaseType(phase_text)  # Validate it's a known phase
            step.metadata = step.metadata or {}
            step.metadata["planner_phase"] = phase_text
        except ValueError:
            pass

    step_type_value = getattr(desc, "step_type", None)
    if isinstance(step_type_value, StepType):
        step.step_type = step_type_value
    elif isinstance(step_type_value, str):
        with contextlib.suppress(ValueError):
            step.step_type = StepType(step_type_value.strip())

    # Phase 2: Map structured fields from StepDescription
    action_verb = _safe_text_attr("action_verb")
    if action_verb:
        step.action_verb = action_verb

    target_object = _safe_text_attr("target_object")
    if target_object:
        step.target_object = target_object

    tool_hint = _safe_text_attr("tool_hint")
    if tool_hint:
        step.tool_hint = tool_hint

    expected_output = _safe_text_attr("expected_output")
    if expected_output:
        step.expected_output = expected_output

    return step


class PlannerAgent(BaseAgent):
    """
    Planner agent class, defining the basic behavior of planning
    """

    name: str = "planner"
    system_prompt: str = SYSTEM_PROMPT + PLANNER_SYSTEM_PROMPT
    format: str | None = "json_object"
    tool_choice: str | None = "none"

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: list[BaseTool],
        json_parser: JsonParser,
        memory_service: Optional["MemoryService"] = None,
        user_id: str | None = None,
        skill_loader: SkillLoader | None = None,
        thought_tree_explorer=None,
        feature_flags: dict[str, bool] | None = None,
        cancel_token: "CancellationToken | None" = None,
        search_engine: "SearchEngine | None" = None,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
            feature_flags=feature_flags,
            cancel_token=cancel_token,
        )
        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

        # Requirement tracking for user prompt adherence
        self._current_requirements: RequirementSet | None = None

        # Skill loader for discovering relevant skills (Phase 3: Skills Integration)
        self._skill_loader = skill_loader

        # Optional Tree-of-Thoughts explorer for complex tasks
        self._thought_tree_explorer = thought_tree_explorer

        # Pre-planning search engine for real-time web context
        self._search_engine = search_engine
        self._last_search_context: str | None = None

    async def _stream_thinking(self, message: str) -> AsyncGenerator[BaseEvent, None]:
        """Stream thinking process before creating a plan.

        Uses the LLM's streaming capability to show reasoning in real-time.

        Args:
            message: The user message to think about

        Yields:
            StreamEvent for each content chunk
        """
        thinking_prompt = THINKING_PROMPT.format(message=message)

        # Check if LLM supports streaming
        if not hasattr(self.llm, "ask_stream"):
            logger.debug("LLM does not support streaming, skipping thinking phase")
            return

        try:
            # Use a fresh message list for thinking (don't pollute main memory)
            thinking_messages = [
                {"role": "system", "content": "You are a thoughtful assistant. Think through problems step by step."},
                {"role": "user", "content": thinking_prompt},
            ]

            async for chunk in self.llm.ask_stream(thinking_messages, tools=None, response_format=None):
                yield StreamEvent(content=chunk, is_final=False)

            # Signal end of thinking stream
            yield StreamEvent(content="", is_final=True)

        except Exception as e:
            logger.warning(f"Thinking stream failed, continuing with plan creation: {e}")
            # Don't yield error - just continue to plan creation

    async def create_plan(self, message: Message, replan_context: str | None = None) -> AsyncGenerator[BaseEvent, None]:
        """Create an execution plan for the given message.

        Emits ProgressEvents for instant user feedback during planning:
        - RECEIVED: Message acknowledged
        - ANALYZING: Analyzing complexity
        - PLANNING: LLM generating plan
        - FINALIZING: Validating and preparing plan

        Args:
            message: The user message to create a plan for
            replan_context: Optional feedback from verification for replanning

        Yields:
            ProgressEvent for instant feedback, StreamEvent during thinking,
            then PlanEvent with the created plan
        """
        # Save original system prompt so skill context doesn't bleed across messages
        original_system_prompt = self.system_prompt
        try:
            async for event in self._create_plan_inner(message, replan_context):
                yield event
        finally:
            self.system_prompt = original_system_prompt

    async def _create_plan_inner(
        self, message: Message, replan_context: str | None = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Inner implementation of create_plan, wrapped by try/finally for prompt restore."""
        from app.domain.models.event import PlanningPhase, ProgressEvent

        # Build skill context if skills are enabled for this message (Phase 3: Custom Skills)
        # Phase 3.5: Use SkillRegistry for cached skill context
        if message.skills:
            try:
                from app.domain.services.skill_registry import get_skill_registry

                registry = await get_skill_registry()
                skill_context = await registry.build_context(
                    message.skills,
                    expand_dynamic=True,
                )

                if skill_context.prompt_addition:
                    # Extend system prompt with skill context for skill-aware planning
                    self.system_prompt = SYSTEM_PROMPT + PLANNER_SYSTEM_PROMPT + skill_context.prompt_addition
                    logger.info(
                        f"Planner injected skill context for skills: {message.skills} "
                        f"({len(skill_context.prompt_addition)} chars)"
                    )
            except Exception as e:
                logger.warning(f"Planner failed to build skill context: {e}")

        # Instant acknowledgment - user sees feedback immediately
        yield ProgressEvent(
            phase=PlanningPhase.RECEIVED, message="Message received, starting to process...", progress_percent=10
        )

        # --- Fire pre-planning search in background (zero-lag pattern) ---
        # The search runs concurrently with thinking/ToT/memory below.
        import asyncio

        from app.domain.services.flows.pre_planning_search import (
            PrePlanningSearchDetector,
            PrePlanningSearchExecutor,
            PrePlanningSearchResult,
        )

        search_task: asyncio.Task[PrePlanningSearchResult] | None = None
        if self._search_engine and not replan_context:
            should_search, search_reasons = PrePlanningSearchDetector.should_search(message.message)
            if should_search:
                executor = PrePlanningSearchExecutor(self._search_engine)
                search_task = asyncio.create_task(executor.execute(message.message, search_reasons))
                logger.info(f"Pre-planning search fired: reasons={search_reasons}")

        # Extract user requirements for tracking (Quick Win: User Prompt Adherence)
        self._current_requirements = extract_requirements(message.message)
        if self._current_requirements.requirements:
            logger.info(
                f"Extracted {len(self._current_requirements.requirements)} requirements "
                f"({len(self._current_requirements.must_haves)} must-haves)"
            )

        # Stream thinking phase for initial plans (skip on replans for speed)
        if not replan_context:
            yield ProgressEvent(
                phase=PlanningPhase.ANALYZING, message="Analyzing task complexity...", progress_percent=20
            )
            async for event in self._stream_thinking(message.message):
                yield event

        # Tree-of-Thoughts exploration for complex tasks
        tot_context = None
        if self._thought_tree_explorer and not replan_context:
            complexity = get_task_complexity(message.message)
            if complexity == "complex":
                try:
                    from app.domain.services.agents.reasoning.thought_tree import ExplorationMode

                    result = await self._thought_tree_explorer.explore(message.message, mode=ExplorationMode.BEAM)
                    if result.best_path and result.best_path.get_conclusion():
                        tot_context = (
                            f"\n\n## Pre-Analysis (Tree-of-Thoughts)\n"
                            f"{result.best_path.get_conclusion()}\n"
                            f"(Explored {result.nodes_explored} reasoning paths, "
                            f"pruned {result.nodes_pruned})"
                        )
                        logger.info(
                            f"ToT exploration completed: {result.nodes_explored} nodes, "
                            f"best path confidence={result.best_path.average_confidence:.2f}"
                        )
                except Exception as e:
                    logger.warning(f"Tree-of-Thoughts exploration failed, continuing without: {e}")

        # Retrieve similar past tasks and outcomes (Phase 3: Cross-session intelligence + Phase 6: Qdrant)
        task_memory = None
        if self._memory_service and self._user_id:
            try:
                # Phase 3: Find similar tasks from past sessions
                similar_tasks = await self._memory_service.find_similar_tasks(
                    user_id=self._user_id,
                    task_description=message.message,
                    limit=5,
                )

                # Also retrieve relevant memories (error patterns, outcomes)
                memories = await self._memory_service.retrieve_relevant(
                    user_id=self._user_id,
                    context=message.message,
                    limit=3,
                    memory_types=[MemoryType.TASK_OUTCOME, MemoryType.ERROR_PATTERN],
                    min_relevance=0.4,
                )

                # Combine into task memory context
                if similar_tasks or memories:
                    context_parts = []

                    # Add similar task guidance
                    if similar_tasks:
                        task_lines = ["Past experience with similar tasks:"]
                        for task in similar_tasks:
                            outcome = "succeeded" if task.get("success") else "failed"
                            summary = task.get("content_summary", "")[:150]
                            task_lines.append(f"- {summary} ({outcome})")
                        context_parts.append("\n".join(task_lines))

                    # Add memory context
                    if memories:
                        mem_text = self._format_task_memory(memories)
                        context_parts.append(mem_text)

                    task_memory = "\n\n".join(context_parts)
                    logger.debug(
                        f"Injected {len(similar_tasks)} similar tasks + {len(memories)} memories into planning"
                    )
            except Exception as e:
                logger.warning(f"Failed to retrieve task memories for planning: {e}")

        # --- Await pre-planning search (should already be done by now) ---
        search_context: str | None = None
        if search_task is not None:
            try:
                search_result = await asyncio.wait_for(search_task, timeout=3.0)
                if search_result.triggered and search_result.search_context:
                    search_context = search_result.search_context
                    logger.info(
                        f"Pre-planning search completed: {search_result.total_results} results "
                        f"in {search_result.duration_ms:.0f}ms, queries={search_result.queries}"
                    )
            except TimeoutError:
                logger.warning("Pre-planning search timed out at await point, continuing without")
                search_task.cancel()
            except Exception:
                logger.warning("Pre-planning search failed at await point", exc_info=True)

        # Store for propagation to execution agent
        self._last_search_context = search_context

        # Extract just filenames from attachment paths for cleaner display
        attachment_names = []
        for path in message.attachments:
            filename = path.split("/")[-1] if "/" in path else path
            attachment_names.append(filename)

        base_prompt = build_create_plan_prompt(
            message=message.message,
            attachments="\n".join(attachment_names) if attachment_names else "None",
            task_memory=task_memory,
            search_context=search_context,
        )

        # Enrich prompt with ToT analysis if available
        if tot_context:
            base_prompt = base_prompt + tot_context

        # Add replan context if provided (from verification feedback)
        if replan_context:
            prompt = f"{base_prompt}\n\n## Replanning Guidance\nThe previous plan was flagged for revision:\n{replan_context}\n\nPlease create a revised plan that addresses these issues."
            logger.info("Creating revised plan based on verification feedback")
        else:
            prompt = base_prompt

        # Progress: Starting plan generation
        yield ProgressEvent(phase=PlanningPhase.PLANNING, message="Creating execution plan...", progress_percent=40)

        # Try structured output first for type-safe response
        # Phase 4: Use Tenacity retry with validation feedback when feature enabled
        flags = self._resolve_feature_flags()
        use_structured = flags.get("structured_outputs", False)

        try:
            await self._add_to_memory([{"role": "user", "content": prompt}])
            await self._ensure_within_token_limit()

            # Phase 4: Validated structured output with retry
            if use_structured and hasattr(self.llm, "ask_structured"):
                plan = await self._create_validated_plan(
                    message=message,
                    prompt=prompt,
                    replan_context=replan_context,
                )
                if plan:
                    # Progress: Finalizing plan
                    yield ProgressEvent(
                        phase=PlanningPhase.FINALIZING,
                        message="Validating plan structure...",
                        estimated_steps=len(plan.steps),
                        progress_percent=80,
                    )
                    logger.info(f"Created plan using validated structured output: {plan.title}")
                    await self._add_to_memory([{"role": "assistant", "content": plan.model_dump_json()}])

                    # Final progress before yielding plan
                    yield ProgressEvent(
                        phase=PlanningPhase.FINALIZING,
                        message=f"Ready to execute {len(plan.steps)} steps!",
                        estimated_steps=len(plan.steps),
                        progress_percent=95,
                    )
                    yield PlanEvent(status=PlanStatus.CREATED, plan=plan)
                    return

            # Check if LLM supports structured outputs (fallback without validation retry)
            elif hasattr(self.llm, "ask_structured"):
                try:
                    plan_response = await self.llm.ask_structured(
                        self.memory.get_messages(), response_model=PlanResponse, tools=None, tool_choice=None
                    )

                    # Progress: Finalizing plan
                    yield ProgressEvent(
                        phase=PlanningPhase.FINALIZING,
                        message="Finalizing plan...",
                        estimated_steps=len(plan_response.steps),
                        progress_percent=80,
                    )

                    # Convert to Plan model
                    plan = Plan(
                        goal=plan_response.goal,
                        title=plan_response.title,
                        language=plan_response.language,
                        message=plan_response.message,
                        steps=self._normalize_plan_steps(
                            [_step_from_description(i, s) for i, s in enumerate(plan_response.steps)],
                            task_message=message.message,
                        ),
                    )
                    logger.info(f"Created plan using structured output: {plan.title}")
                    await self._add_to_memory([{"role": "assistant", "content": plan.model_dump_json()}])
                    yield ProgressEvent(
                        phase=PlanningPhase.FINALIZING,
                        message=f"Ready to execute {len(plan.steps)} steps!",
                        estimated_steps=len(plan.steps),
                        progress_percent=95,
                    )
                    yield PlanEvent(status=PlanStatus.CREATED, plan=plan)
                    return
                except Exception as e:
                    logger.warning(f"Structured output failed, falling back to JSON parser: {e}")
        except Exception as e:
            logger.warning(f"Memory preparation failed: {e}")

        # Fallback to original approach with JSON parser
        async for event in self.execute(prompt):
            if isinstance(event, MessageEvent):
                logger.info(event.message)
                parsed_response = await self.json_parser.parse(event.message)
                plan = Plan.model_validate(parsed_response)
                plan.steps = self._normalize_plan_steps(plan.steps, task_message=message.message)
                yield ProgressEvent(
                    phase=PlanningPhase.FINALIZING,
                    message=f"Ready to execute {len(plan.steps)} steps!",
                    estimated_steps=len(plan.steps),
                    progress_percent=95,
                )
                yield PlanEvent(status=PlanStatus.CREATED, plan=plan)
            else:
                yield event

    async def update_plan(self, plan: Plan, step: Step) -> AsyncGenerator[BaseEvent, None]:
        prompt = UPDATE_PLAN_PROMPT.format(plan=plan.dump_json(), step=step.model_dump_json())
        max_steps_limit = DEFAULT_MAX_PLAN_STEPS
        complexity_source = plan.message or plan.goal
        if complexity_source:
            complexity = get_task_complexity(complexity_source)
            _, max_steps_limit = get_step_limits(complexity)
            if is_research_task_message(complexity_source):
                max_steps_limit = max(max_steps_limit, RESEARCH_STEP_CAP)

        # Helper to apply update steps to plan
        def apply_plan_update(new_steps: list[Step]) -> None:
            # Completed and remaining steps in current plan
            remaining_pending = [s for s in plan.steps if not s.is_done()]

            # SAFEGUARD: If LLM returns empty steps but we still have pending steps,
            # keep the original pending steps (prevent premature task completion)
            if len(new_steps) == 0 and len(remaining_pending) >= 1:
                logger.warning(
                    f"LLM returned empty steps but {len(remaining_pending)} steps remain. "
                    "Keeping original pending steps."
                )
                # Ensure the just-completed step is marked done
                for s in plan.steps:
                    if s.id == step.id and not s.is_done():
                        s.status = ExecutionStatus.COMPLETED
                        s.success = True
                        break
                new_steps = [s for s in plan.steps if not s.is_done()]

            completed_steps = [s for s in plan.steps if s.is_done()]

            # If we have more completed steps than our display cap and still pending work,
            # keep the most recent completed steps to make room for remaining items.
            if new_steps and len(completed_steps) >= max_steps_limit:
                completed_steps = completed_steps[-(max_steps_limit - 1) :]

            remaining_slots = max(max_steps_limit - len(completed_steps), 0)
            normalized_pending = self._normalize_update_steps(
                new_steps, remaining_slots, id_offset=len(completed_steps)
            )

            plan.steps = completed_steps + normalized_pending

        # Try structured output first
        try:
            await self._add_to_memory([{"role": "user", "content": prompt}])
            await self._ensure_within_token_limit()

            if hasattr(self.llm, "ask_structured"):
                try:
                    update_response = await self.llm.ask_structured(
                        self.memory.get_messages(), response_model=PlanUpdateResponse, tools=None, tool_choice=None
                    )
                    new_steps = [_step_from_description(i, s) for i, s in enumerate(update_response.steps)]
                    apply_plan_update(new_steps)
                    logger.debug("Updated plan using structured output")
                    await self._add_to_memory(
                        [{"role": "assistant", "content": json.dumps({"steps": [s.model_dump() for s in new_steps]})}]
                    )
                    yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)
                    return
                except Exception as e:
                    logger.warning(f"Structured output failed for update, falling back: {e}")
        except Exception as e:
            logger.warning(f"Memory preparation failed: {e}")

        # Fallback to original approach
        async for event in self.execute(prompt):
            if isinstance(event, MessageEvent):
                logger.debug(f"Planner agent update plan: {event.message}")
                parsed_response = await self.json_parser.parse(event.message)
                updated_plan = Plan.model_validate(parsed_response)
                new_steps = [Step.model_validate(s) for s in updated_plan.steps]
                apply_plan_update(new_steps)
                yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)
            else:
                yield event

    @staticmethod
    def _consolidate_similar_steps(steps: list[Step]) -> list[Step]:
        """Merge sequential steps with similar actions into single steps.

        Detects patterns like search→browse→extract and consolidates them.
        Stores original sub-steps in metadata for execution context.
        """
        if len(steps) <= 2:
            return steps

        # Keywords indicating web research micro-steps
        search_keywords = {"search", "find", "look up", "query", "discover"}
        browse_keywords = {"browse", "visit", "navigate", "open", "click", "extract", "read"}
        deliver_keywords = {"deliver", "send", "share", "present", "hand off", "output"}
        validate_keywords = {"validate", "verify", "review", "check", "cross-check", "confirm"}

        def _desc_lower(step: Step) -> str:
            return (step.description or "").lower()

        def _matches(desc: str, keywords: set[str]) -> bool:
            return any(kw in desc for kw in keywords)

        consolidated: list[Step] = []
        i = 0
        while i < len(steps):
            desc = _desc_lower(steps[i])

            # Pattern: search + browse + extract → single "Research X" step
            if _matches(desc, search_keywords) and i + 1 < len(steps):
                next_desc = _desc_lower(steps[i + 1])
                if _matches(next_desc, browse_keywords):
                    # Merge search + browse (and possibly extract) into one
                    merged_from = [steps[i].description, steps[i + 1].description]
                    targets = [t for t in [steps[i].target_object, steps[i + 1].target_object] if t]
                    merged_step = Step(
                        description=steps[i].description,
                        action_verb=steps[i].action_verb or "Research",
                        target_object="; ".join(targets) if targets else None,
                        metadata={"merged_from": len(merged_from), "original_descriptions": merged_from},
                    )
                    consolidated.append(merged_step)
                    i += 2
                    continue

            # Pattern: deliver + validate → single step
            if _matches(desc, deliver_keywords) and i + 1 < len(steps):
                next_desc = _desc_lower(steps[i + 1])
                if _matches(next_desc, validate_keywords):
                    merged_step = Step(
                        description="Review, validate, and deliver final output",
                        metadata={
                            "merged_from": 2,
                            "original_descriptions": [steps[i].description, steps[i + 1].description],
                        },
                    )
                    consolidated.append(merged_step)
                    i += 2
                    continue

            consolidated.append(steps[i])
            i += 1

        return consolidated

    def _normalize_plan_steps(self, steps: list[Step], task_message: str = "") -> list[Step]:
        """Clamp plan length and merge overflow steps into the final step.

        Uses adaptive step limits based on task complexity.

        Args:
            steps: The plan steps to normalize
            task_message: The original task message for complexity analysis
        """
        if not steps:
            return steps

        # Consolidate similar steps before applying limits
        steps = self._consolidate_similar_steps(steps)

        # Determine complexity and get adaptive limits
        complexity = get_task_complexity(task_message) if task_message else "medium"
        min_steps, max_steps = get_step_limits(complexity)
        logger.debug(f"Task complexity: {complexity}, limits: ({min_steps}, {max_steps})")

        existing_text = " ".join(s.description.lower() for s in steps if s.description)

        # Only add filler steps if we're below minimum and not a simple task
        if len(steps) < min_steps and complexity != "simple":
            fillers: list[str] = []
            if not any(keyword in existing_text for keyword in ["verify", "validate", "test", "check"]):
                fillers.append("Validate results and address any issues")
            if not any(keyword in existing_text for keyword in ["deliver", "final", "hand off", "share"]):
                fillers.append("Deliver final output to the user")
            fallback_fillers = [
                "Review outputs for completeness and consistency",
                "Summarize outcomes and note any limitations",
            ]
            for filler in fallback_fillers:
                if len(steps) + len(fillers) >= min_steps:
                    break
                if filler.lower() not in existing_text:
                    fillers.append(filler)
            if fillers:
                steps = steps + [Step(description=filler) for filler in fillers][: max(0, min_steps - len(steps))]

        if len(steps) <= max_steps:
            for i, s in enumerate(steps):
                s.id = str(i + 1)
            return steps

        head = steps[: max_steps - 1]
        tail = steps[max_steps - 1 :]

        # Phase 2: Preserve target_objects when merging overflow steps
        targets = [s.target_object for s in tail if s.target_object]
        if targets:
            merged_desc = "Consolidate: " + "; ".join(targets)
        else:
            merged_desc = "Consolidate remaining items: " + "; ".join(s.description for s in tail if s.description)
        if len(merged_desc) > MAX_MERGED_STEP_CHARS:
            merged_desc = merged_desc[: MAX_MERGED_STEP_CHARS - 3].rstrip() + "..."

        merged_step = Step(
            id=str(max_steps),
            description=merged_desc,
            target_object="; ".join(targets) if targets else None,
            action_verb="Complete",
            metadata={
                "merged_from": len(tail),
                "original_descriptions": [s.description for s in tail if s.description],
            },
        )
        normalized = [*head, merged_step]

        for i, s in enumerate(normalized):
            s.id = str(i + 1)

        return normalized

    def _normalize_update_steps(self, steps: list[Step], max_steps: int, id_offset: int = 0) -> list[Step]:
        """Normalize remaining steps during plan updates without inflating total steps."""
        if not steps or max_steps <= 0:
            return []

        if len(steps) <= max_steps:
            for i, s in enumerate(steps):
                s.id = str(id_offset + i + 1)
            return steps

        head = steps[: max_steps - 1]
        tail = steps[max_steps - 1 :]
        merged_desc = "Consolidate remaining items: " + "; ".join(s.description for s in tail if s.description)
        if len(merged_desc) > MAX_MERGED_STEP_CHARS:
            merged_desc = merged_desc[: MAX_MERGED_STEP_CHARS - 3].rstrip() + "..."

        merged_step = Step(
            id=str(id_offset + max_steps),
            description=merged_desc,
            metadata={
                "merged_from": len(tail),
                "original_descriptions": [s.description for s in tail if s.description],
            },
        )
        normalized = [*head, merged_step]

        for i, s in enumerate(normalized):
            s.id = str(id_offset + i + 1)

        return normalized

    def get_requirements(self) -> RequirementSet | None:
        """Get the current requirement set.

        Returns:
            RequirementSet if requirements were extracted, None otherwise
        """
        return self._current_requirements

    def get_requirements_summary(self) -> str:
        """Get a summary of requirements for injection into prompts.

        Returns:
            Formatted requirements summary, or empty string if none
        """
        if self._current_requirements:
            return self._current_requirements.get_summary()
        return ""

    def get_unaddressed_reminder(self) -> str | None:
        """Get a reminder about unaddressed requirements.

        Returns:
            Reminder string if there are unaddressed requirements, None otherwise
        """
        if self._current_requirements:
            return self._current_requirements.get_unaddressed_reminder()
        return None

    def mark_requirement_addressed(self, step_id: str, step_description: str) -> None:
        """Mark requirements addressed by a completed step.

        Args:
            step_id: The ID of the completed step
            step_description: Description of the completed step
        """
        if not self._current_requirements:
            return

        from app.domain.services.agents.requirement_extractor import get_requirement_extractor

        extractor = get_requirement_extractor()

        for req in self._current_requirements.requirements:
            if not req.addressed:
                score = extractor.match_requirement_to_step(req, step_description)
                if score >= 0.3:  # 30% match threshold
                    req.mark_addressed(step_id)
                    logger.debug(f"Requirement {req.id} addressed by step {step_id} (score: {score:.2f})")

    async def _discover_relevant_skills(self, task: str) -> list[Skill]:
        """Discover skills relevant to the current task.

        Uses skill metadata (level 1 disclosure) to identify
        which skills might help with the task.

        Args:
            task: The task description to match against skill metadata.

        Returns:
            List of Skill objects that are relevant to the task.
        """
        if not self._skill_loader:
            return []

        all_skills = await self._skill_loader.discover_skills()

        # Simple keyword matching for relevance
        task_lower = task.lower()
        relevant: list[Skill] = []

        for skill in all_skills:
            # Check if skill name or description matches task keywords
            skill_text = f"{skill.name} {skill.description}".lower()
            if any(word in skill_text for word in task_lower.split() if len(word) > 3):
                relevant.append(skill)

        logger.debug(f"Discovered {len(relevant)} relevant skills for task: {task[:50]}...")
        return relevant

    async def _build_planning_context(self, task: str) -> str:
        """Build context including relevant skills.

        Constructs additional planning context by discovering skills
        that may be useful for the given task.

        Args:
            task: The task description to build context for.

        Returns:
            Formatted context string with available skills, or empty string if none.
        """
        context_parts: list[str] = []

        # Add relevant skills
        relevant_skills = await self._discover_relevant_skills(task)
        if relevant_skills:
            skill_info = "\n".join([f"- **{s.name}**: {s.description}" for s in relevant_skills])
            context_parts.append(f"## Available Skills\n{skill_info}")

        return "\n\n".join(context_parts)

    def _format_task_memory(self, memories) -> str:
        """Format task memories for planning context.

        Args:
            memories: List of MemorySearchResult from similar past tasks

        Returns:
            Formatted string with relevant task outcomes and patterns
        """
        if not memories:
            return ""

        lines = []
        for result in memories[:3]:  # Limit to 3 most relevant
            mem = result.memory
            mem_type = mem.memory_type.value if hasattr(mem.memory_type, "value") else str(mem.memory_type)

            if mem_type == "task_outcome":
                lines.append(f"- [Past Task] {mem.content[:200]}...")
            elif mem_type == "error_pattern":
                lines.append(f"- [Error Pattern] {mem.content[:200]}...")
            else:
                lines.append(f"- [{mem_type}] {mem.content[:150]}...")

        return "\n".join(lines)

    async def recreate_tasks_from_understanding(
        self,
        original_message: str,
        new_understanding: str,
        completed_steps: list[dict] | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Recreate tasks based on improved understanding of requirements.

        This is called when the agent, during execution, realizes it needs
        to restructure the tasks based on better understanding of the user's
        requirements (e.g., after reading a long document or specification).

        Args:
            original_message: The user's original request
            new_understanding: The agent's new understanding of what's needed
            completed_steps: Optional list of already completed steps to preserve

        Yields:
            PlanEvent with the recreated plan
        """
        from app.domain.models.event import PlanningPhase, ProgressEvent

        yield ProgressEvent(
            phase=PlanningPhase.PLANNING,
            message="Recreating tasks based on new understanding...",
            progress_percent=30,
        )

        # Build recreation prompt
        completed_context = ""
        if completed_steps:
            completed_list = "\n".join(
                f"- {step.get('description', 'Unknown step')}: {step.get('result', 'Done')}" for step in completed_steps
            )
            completed_context = f"\n\n## Already Completed:\n{completed_list}"

        recreation_prompt = f"""Based on a deeper understanding of the user's requirements, recreate the task plan.

## Original Request:
{original_message}

## New Understanding:
{new_understanding}
{completed_context}

Create a revised plan with clear, actionable steps that address the user's actual needs.
Focus on what still needs to be done, considering any completed work.

Respond with a JSON plan containing:
- goal: The refined goal based on new understanding
- title: A descriptive title
- steps: Array of step objects with description
- message: Brief explanation of the revised approach
"""

        try:
            await self._add_to_memory([{"role": "user", "content": recreation_prompt}])
            await self._ensure_within_token_limit()

            if hasattr(self.llm, "ask_structured"):
                try:
                    plan_response = await self.llm.ask_structured(
                        self.memory.get_messages(),
                        response_model=PlanResponse,
                        tools=None,
                        tool_choice=None,
                    )

                    yield ProgressEvent(
                        phase=PlanningPhase.FINALIZING,
                        message="Finalizing recreated plan...",
                        estimated_steps=len(plan_response.steps),
                        progress_percent=80,
                    )

                    # Convert to Plan model
                    plan = Plan(
                        goal=plan_response.goal,
                        title=plan_response.title,
                        language=plan_response.language,
                        message=plan_response.message,
                        steps=self._normalize_plan_steps(
                            [_step_from_description(i, s) for i, s in enumerate(plan_response.steps)],
                            task_message=original_message,
                        ),
                    )

                    logger.info(f"Recreated plan with {len(plan.steps)} steps: {plan.title}")
                    await self._add_to_memory([{"role": "assistant", "content": plan.model_dump_json()}])
                    yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)
                    return

                except Exception as e:
                    logger.warning(f"Structured output failed for recreation: {e}")

            # Fallback to JSON parser
            async for event in self.execute(recreation_prompt):
                if isinstance(event, MessageEvent):
                    parsed_response = await self.json_parser.parse(event.message)
                    plan = Plan.model_validate(parsed_response)
                    plan.steps = self._normalize_plan_steps(plan.steps, task_message=original_message)
                    yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)
                else:
                    yield event

        except Exception as e:
            logger.error(f"Task recreation failed: {e}")
            yield ErrorEvent(error=f"Failed to recreate tasks: {e}")

    async def _create_validated_plan(
        self,
        message: Message,
        prompt: str,
        replan_context: str | None = None,
        prev_error: str | None = None,
    ) -> Plan | None:
        """Create a plan with validation and retry.

        Phase 4 Enhancement: Uses Tenacity retry with validation feedback
        to ensure plans meet quality standards.

        Args:
            message: Original user message
            prompt: Planning prompt
            replan_context: Optional context for replanning
            prev_error: Previous validation error (for retry)

        Returns:
            Validated Plan or None if validation fails after retries
        """
        max_attempts = 3

        # Build context with previous error if retrying
        context_addition = ""
        if prev_error:
            context_addition = f"\n\n## FIX THIS VALIDATION ERROR:\n{prev_error}"

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                retry=retry_if_exception_type(ValidationError),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            ):
                with attempt:
                    attempt_num = attempt.retry_state.attempt_number
                    logger.debug(f"Plan creation attempt {attempt_num}/{max_attempts}")

                    # Add validation feedback to prompt if this is a retry
                    effective_prompt = prompt
                    if attempt_num > 1 and prev_error:
                        effective_prompt = prompt + context_addition

                    # Get LLM response
                    messages = self.memory.get_messages()
                    if attempt_num > 1 and prev_error:
                        messages = [*messages[:-1], {"role": "user", "content": effective_prompt}]
                    response = await self.llm.ask(
                        messages,
                        response_format={"type": "json_object"},
                    )

                    content = response.get("content", "{}")

                    # Validate using structured output model
                    parsed, result = validate_llm_output(content, StructuredPlanOutput)

                    if not result.is_valid:
                        # Build feedback for next attempt
                        prev_error = build_validation_feedback(result)
                        logger.warning(f"Plan validation failed (attempt {attempt_num}): {prev_error[:200]}")
                        raise ValidationError.from_exception_data(
                            "Plan validation failed",
                            [{"type": "value_error", "loc": (), "msg": prev_error, "input": content}],
                        )

                    # Convert validated structured output to Plan model
                    plan = Plan(
                        goal=parsed.goal,
                        title=parsed.title,
                        language=parsed.language,
                        message=parsed.message,
                        steps=self._normalize_plan_steps(
                            [_step_from_description(i, s) for i, s in enumerate(parsed.steps)],
                            task_message=message.message,
                        ),
                    )

                    logger.info(f"Plan validated successfully on attempt {attempt_num}")
                    return plan

        except Exception as e:
            from app.infrastructure.external.key_pool import APIKeysExhaustedError

            if isinstance(e, APIKeysExhaustedError):
                logger.debug("Plan creation skipped: %s", e)
            else:
                logger.error(f"Plan creation failed after {max_attempts} attempts: {e}")
            return None

        return None
