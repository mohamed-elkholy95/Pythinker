from typing import Dict, Any, List, AsyncGenerator, Optional, TYPE_CHECKING
import json
import logging
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.models.memory import Memory
from app.domain.external.llm import LLM
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.planner import (
    CREATE_PLAN_PROMPT,
    UPDATE_PLAN_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    THINKING_PROMPT,
    build_create_plan_prompt,
)
from app.domain.models.long_term_memory import MemoryType

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
    StreamEvent,
)
from app.domain.models.agent_response import PlanResponse, PlanUpdateResponse
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.shell import ShellTool
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

# Default step constraints (can be overridden by complexity-based limits)
DEFAULT_MIN_PLAN_STEPS = 3
DEFAULT_MAX_PLAN_STEPS = 6
MAX_MERGED_STEP_CHARS = 240

# Adaptive step constraints based on task complexity
COMPLEXITY_STEP_LIMITS = {
    "simple": (1, 3),
    "medium": (3, 6),
    "complex": (5, 12),
}


def get_task_complexity(message: str, tools: list = None) -> str:
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
        "just", "only", "simply", "quick", "single",
        "one file", "one thing", "basic",
    ]

    # Complex task indicators (research, multi-source, conditional logic)
    complex_indicators = [
        "research", "investigate", "compare", "analyze",
        "comprehensive", "detailed", "multiple sources",
        "if possible", "depending on", "various",
        "full report", "in-depth", "thorough",
    ]

    # Count indicators
    simple_count = sum(1 for ind in simple_indicators if ind in message_lower)
    complex_count = sum(1 for ind in complex_indicators if ind in message_lower)

    # Message length heuristic
    word_count = len(message.split())

    # Short messages with simple indicators -> simple
    if word_count < 15 and simple_count > 0 and complex_count == 0:
        return "simple"

    # Long messages or complex indicators -> complex
    if word_count > 50 or complex_count >= 2:
        return "complex"

    # Check for multi-part requests (numbered items, bullets)
    import re
    numbered_items = len(re.findall(r'(?:^|\n)\s*\d+[\.\)]\s', message))
    bullet_items = len(re.findall(r'(?:^|\n)\s*[-*]\s', message))

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

class PlannerAgent(BaseAgent):
    """
    Planner agent class, defining the basic behavior of planning
    """

    name: str = "planner"
    system_prompt: str = SYSTEM_PROMPT + PLANNER_SYSTEM_PROMPT
    format: Optional[str] = "json_object"
    tool_choice: Optional[str] = "none"

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: List[BaseTool],
        json_parser: JsonParser,
        memory_service: Optional["MemoryService"] = None,
        user_id: Optional[str] = None,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
        )
        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

    async def _stream_thinking(
        self,
        message: str
    ) -> AsyncGenerator[BaseEvent, None]:
        """Stream thinking process before creating a plan.

        Uses the LLM's streaming capability to show reasoning in real-time.

        Args:
            message: The user message to think about

        Yields:
            StreamEvent for each content chunk
        """
        thinking_prompt = THINKING_PROMPT.format(message=message)

        # Check if LLM supports streaming
        if not hasattr(self.llm, 'ask_stream'):
            logger.debug("LLM does not support streaming, skipping thinking phase")
            return

        try:
            # Use a fresh message list for thinking (don't pollute main memory)
            thinking_messages = [
                {"role": "system", "content": "You are a thoughtful assistant. Think through problems step by step."},
                {"role": "user", "content": thinking_prompt}
            ]

            async for chunk in self.llm.ask_stream(
                thinking_messages,
                tools=None,
                response_format=None
            ):
                yield StreamEvent(content=chunk, is_final=False)

            # Signal end of thinking stream
            yield StreamEvent(content="", is_final=True)

        except Exception as e:
            logger.warning(f"Thinking stream failed, continuing with plan creation: {e}")
            # Don't yield error - just continue to plan creation

    async def create_plan(
        self,
        message: Message,
        replan_context: Optional[str] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Create an execution plan for the given message.

        Args:
            message: The user message to create a plan for
            replan_context: Optional feedback from verification for replanning

        Yields:
            StreamEvent during thinking, then PlanEvent with the created plan
        """
        # Stream thinking phase for initial plans (skip on replans for speed)
        if not replan_context:
            async for event in self._stream_thinking(message.message):
                yield event

        # Retrieve similar past tasks and outcomes (Phase 6: Qdrant integration)
        task_memory = None
        if self._memory_service and self._user_id:
            try:
                memories = await self._memory_service.retrieve_relevant(
                    user_id=self._user_id,
                    context=message.message,
                    limit=3,
                    memory_types=[MemoryType.TASK_OUTCOME, MemoryType.ERROR_PATTERN],
                    min_relevance=0.4
                )
                if memories:
                    task_memory = self._format_task_memory(memories)
                    logger.debug(f"Injected {len(memories)} memories into planning context")
            except Exception as e:
                logger.warning(f"Failed to retrieve task memories for planning: {e}")

        base_prompt = build_create_plan_prompt(
            message=message.message,
            attachments="\n".join(message.attachments),
            task_memory=task_memory
        )

        # Add replan context if provided (from verification feedback)
        if replan_context:
            prompt = f"{base_prompt}\n\n## Replanning Guidance\nThe previous plan was flagged for revision:\n{replan_context}\n\nPlease create a revised plan that addresses these issues."
            logger.info("Creating revised plan based on verification feedback")
        else:
            prompt = base_prompt

        # Try structured output first for type-safe response
        try:
            await self._add_to_memory([{"role": "user", "content": prompt}])
            await self._ensure_within_token_limit()

            # Check if LLM supports structured outputs
            if hasattr(self.llm, 'ask_structured'):
                try:
                    plan_response = await self.llm.ask_structured(
                        self.memory.get_messages(),
                        response_model=PlanResponse,
                        tools=None,
                        tool_choice=None
                    )
                    # Convert to Plan model
                    plan = Plan(
                        goal=plan_response.goal,
                        title=plan_response.title,
                        language=plan_response.language,
                        message=plan_response.message,
                        steps=self._normalize_plan_steps(
                            [
                                Step(id=str(i + 1), description=s.description)
                                for i, s in enumerate(plan_response.steps)
                            ],
                            task_message=message.message
                        )
                    )
                    logger.info(f"Created plan using structured output: {plan.title}")
                    await self._add_to_memory([{"role": "assistant", "content": plan.model_dump_json()}])
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

        # Helper to apply update steps to plan
        def apply_plan_update(new_steps: List[Step]) -> None:
            # Completed and remaining steps in current plan
            remaining_pending = [s for s in plan.steps if not s.is_done()]

            # SAFEGUARD: If LLM returns empty steps but we still have pending steps,
            # keep the original pending steps (prevent premature task completion)
            if len(new_steps) == 0 and len(remaining_pending) > 1:
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
                completed_steps = completed_steps[-(max_steps_limit - 1):]

            remaining_slots = max(max_steps_limit - len(completed_steps), 0)
            normalized_pending = self._normalize_update_steps(
                new_steps,
                remaining_slots,
                id_offset=len(completed_steps)
            )

            plan.steps = completed_steps + normalized_pending

        # Try structured output first
        try:
            await self._add_to_memory([{"role": "user", "content": prompt}])
            await self._ensure_within_token_limit()

            if hasattr(self.llm, 'ask_structured'):
                try:
                    update_response = await self.llm.ask_structured(
                        self.memory.get_messages(),
                        response_model=PlanUpdateResponse,
                        tools=None,
                        tool_choice=None
                    )
                    new_steps = [Step(id=str(i+1), description=s.description)
                                 for i, s in enumerate(update_response.steps)]
                    apply_plan_update(new_steps)
                    logger.debug(f"Updated plan using structured output")
                    await self._add_to_memory([{"role": "assistant", "content": json.dumps({"steps": [s.model_dump() for s in new_steps]})}])
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

    def _normalize_plan_steps(
        self,
        steps: List[Step],
        task_message: str = ""
    ) -> List[Step]:
        """Clamp plan length and merge overflow steps into the final step.

        Uses adaptive step limits based on task complexity.

        Args:
            steps: The plan steps to normalize
            task_message: The original task message for complexity analysis
        """
        if not steps:
            return steps

        # Determine complexity and get adaptive limits
        complexity = get_task_complexity(task_message) if task_message else "medium"
        min_steps, max_steps = get_step_limits(complexity)
        logger.debug(f"Task complexity: {complexity}, limits: ({min_steps}, {max_steps})")

        existing_text = " ".join(s.description.lower() for s in steps if s.description)

        # Only add filler steps if we're below minimum and not a simple task
        if len(steps) < min_steps and complexity != "simple":
            fillers: List[str] = []
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

        # Store original descriptions in metadata when merging
        merged_desc = "Consolidate remaining items: " + "; ".join(
            s.description for s in tail if s.description
        )
        if len(merged_desc) > MAX_MERGED_STEP_CHARS:
            merged_desc = merged_desc[: MAX_MERGED_STEP_CHARS - 3].rstrip() + "..."

        merged_step = Step(
            id=str(max_steps),
            description=merged_desc,
            metadata={
                "merged_from": len(tail),
                "original_descriptions": [s.description for s in tail if s.description]
            }
        )
        normalized = head + [merged_step]

        for i, s in enumerate(normalized):
            s.id = str(i + 1)

        return normalized

    def _normalize_update_steps(
        self,
        steps: List[Step],
        max_steps: int,
        id_offset: int = 0
    ) -> List[Step]:
        """Normalize remaining steps during plan updates without inflating total steps."""
        if not steps or max_steps <= 0:
            return []

        if len(steps) <= max_steps:
            for i, s in enumerate(steps):
                s.id = str(id_offset + i + 1)
            return steps

        head = steps[: max_steps - 1]
        tail = steps[max_steps - 1 :]
        merged_desc = "Consolidate remaining items: " + "; ".join(
            s.description for s in tail if s.description
        )
        if len(merged_desc) > MAX_MERGED_STEP_CHARS:
            merged_desc = merged_desc[: MAX_MERGED_STEP_CHARS - 3].rstrip() + "..."

        merged_step = Step(
            id=str(id_offset + max_steps),
            description=merged_desc,
            metadata={
                "merged_from": len(tail),
                "original_descriptions": [s.description for s in tail if s.description],
            }
        )
        normalized = head + [merged_step]

        for i, s in enumerate(normalized):
            s.id = str(id_offset + i + 1)

        return normalized

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
            mem_type = mem.memory_type.value if hasattr(mem.memory_type, 'value') else str(mem.memory_type)

            if mem_type == "task_outcome":
                lines.append(f"- [Past Task] {mem.content[:200]}...")
            elif mem_type == "error_pattern":
                lines.append(f"- [Error Pattern] {mem.content[:200]}...")
            else:
                lines.append(f"- [{mem_type}] {mem.content[:150]}...")

        return "\n".join(lines)
