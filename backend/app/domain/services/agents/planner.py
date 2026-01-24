from typing import Dict, Any, List, AsyncGenerator, Optional, TYPE_CHECKING
import json
import logging
from app.domain.models.plan import Plan, Step
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.models.memory import Memory
from app.domain.external.llm import LLM
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.planner import (
    CREATE_PLAN_PROMPT,
    UPDATE_PLAN_PROMPT,
    PLANNER_SYSTEM_PROMPT,
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
)
from app.domain.models.agent_response import PlanResponse, PlanUpdateResponse
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.shell import ShellTool
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

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
            PlanEvent with the created plan
        """
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
                        steps=[Step(id=str(i+1), description=s.description)
                               for i, s in enumerate(plan_response.steps)]
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
                yield PlanEvent(status=PlanStatus.CREATED, plan=plan)
            else:
                yield event

    async def update_plan(self, plan: Plan, step: Step) -> AsyncGenerator[BaseEvent, None]:
        prompt = UPDATE_PLAN_PROMPT.format(plan=plan.dump_json(), step=step.model_dump_json())

        # Helper to apply update steps to plan
        def apply_plan_update(new_steps: List[Step]) -> None:
            # Find remaining pending steps in current plan
            remaining_pending = [s for s in plan.steps if not s.is_done()]

            # SAFEGUARD: If LLM returns empty/fewer steps but we have pending steps,
            # keep the original pending steps (prevent premature task completion)
            if len(new_steps) == 0 and len(remaining_pending) > 1:
                logger.warning(
                    f"LLM returned empty steps but {len(remaining_pending)} steps remain. "
                    "Keeping original pending steps."
                )
                # Mark current step as done and keep the rest
                for s in plan.steps:
                    if s.id == step.id:
                        s.mark_done()
                        break
                return

            # Find the index of the first pending step
            first_pending_index = None
            for i, s in enumerate(plan.steps):
                if not s.is_done():
                    first_pending_index = i
                    break

            # If there are pending steps, replace all pending steps
            if first_pending_index is not None:
                # Keep completed steps
                updated_steps = plan.steps[:first_pending_index]
                # Add new steps
                updated_steps.extend(new_steps)
                # Update steps in plan
                plan.steps = updated_steps

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