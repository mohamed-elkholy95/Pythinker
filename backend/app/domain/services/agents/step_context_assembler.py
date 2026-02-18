"""Step context assembly service.

Extracts context gathering from ExecutionAgent.execute_step() into a
single-responsibility class. Produces a StepExecutionContext that is
consumed by build_execution_prompt_from_context().

Dependencies are injected via constructor (follows ContextManager, AutonomyConfig patterns).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.step_execution_context import (
    PromptSignalConfig,
    StepExecutionContext,
)

if TYPE_CHECKING:
    from app.domain.models.message import Message
    from app.domain.models.plan import Plan, Step
    from app.domain.models.request_contract import RequestContract
    from app.domain.services.agents.context_manager import ContextManager
    from app.domain.services.agents.token_manager import TokenManager
    from app.domain.services.memory_service import MemoryService
    from app.domain.services.tools.base import BaseTool

logger = logging.getLogger(__name__)


class StepContextAssembler:
    """Assembles StepExecutionContext from various services.

    Single responsibility: gather all context signals for a step execution.
    Does NOT modify agent state or execute any LLM calls.

    Constructor takes long-lived dependencies (don't change between steps).
    assemble() takes per-step data and externally-provided context.
    """

    def __init__(
        self,
        context_manager: ContextManager,
        token_manager: TokenManager,
        memory_service: MemoryService | None = None,
        user_id: str | None = None,
        signal_config: PromptSignalConfig | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._token_manager = token_manager
        self._memory_service = memory_service
        self._user_id = user_id
        self._signal_config = signal_config or PromptSignalConfig()

    async def assemble(
        self,
        plan: Plan,
        step: Step,
        message: Message,
        *,
        tools: list[BaseTool] | None = None,
        memory_messages: list | None = None,
        pre_planning_search_context: str | None = None,
        conversation_context: str | None = None,
        request_contract: RequestContract | None = None,
    ) -> StepExecutionContext:
        """Assemble all context for a step execution.

        Args:
            plan: Current execution plan
            step: Step to execute
            message: User's original message
            tools: Available tools (for error context inference)
            memory_messages: Current LLM memory messages (for pressure calc)
            pre_planning_search_context: Search context from planning phase
            conversation_context: Qdrant conversation context (replaces _pending_conversation_context)
            request_contract: Entity fidelity contract

        Returns:
            Frozen StepExecutionContext ready for prompt building
        """
        # 1. Task state signal
        task_state = self._get_task_state_signal()

        # 2. Context pressure signal
        pressure_signal = self._get_pressure_signal(memory_messages)

        # 3. Memory context (long-term Qdrant memories)
        memory_context = await self._get_memory_context(step, tools or [])

        # 4. Error pattern signals
        error_pattern_signal = self._get_error_pattern_signal(step)

        # 5. Working context summary
        context_summary = self._context_manager.get_context_summary()

        # 6. Synthesized insights from previous steps
        synthesized_context = self._context_manager.get_synthesized_context(
            for_step_id=step.id,
        )
        blockers = self._context_manager.get_blockers()
        blocker_warnings = [b.content for b in blockers[:3]] if blockers else []

        # 7. Locked entity reminder
        locked_entity_reminder = self._get_locked_entity_reminder(request_contract)

        return StepExecutionContext(
            step_description=step.description,
            user_message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language,
            pressure_signal=pressure_signal,
            task_state=task_state,
            memory_context=memory_context,
            search_context=pre_planning_search_context,
            conversation_context=conversation_context,
            working_context_summary=context_summary or None,
            synthesized_context=synthesized_context or None,
            blocker_warnings=blocker_warnings,
            error_pattern_signal=error_pattern_signal,
            locked_entity_reminder=locked_entity_reminder,
            signal_config=self._signal_config,
        )

    def _get_task_state_signal(self) -> str | None:
        """Get task state context signal for recitation."""
        from app.domain.services.agents.task_state_manager import get_task_state_manager

        task_state_manager = get_task_state_manager()
        return task_state_manager.get_context_signal()

    def _get_pressure_signal(self, memory_messages: list | None) -> str | None:
        """Get context pressure signal if memory is under pressure."""
        if not memory_messages:
            return None
        pressure = self._token_manager.get_context_pressure(memory_messages)
        return pressure.to_context_signal()

    async def _get_memory_context(
        self,
        step: Step,
        tools: list[BaseTool],
    ) -> str | None:
        """Retrieve relevant memories for this step (Phase 6: Qdrant).

        Gathers:
        1. Similar tasks from past sessions
        2. Error context for likely tools
        3. Relevant memories with reranking + MMR
        """
        if not self._memory_service or not self._user_id:
            return None

        try:
            context_parts: list[str] = []

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
                logger.debug("Injected %d similar tasks into context", len(similar_tasks))

            # 2. Error context for tools being used (Phase 3)
            step_lower = step.description.lower()
            likely_tools = [t.name for t in tools if t.name.lower() in step_lower]

            for tool_name in likely_tools[:2]:
                error_context = await self._memory_service.get_error_context(
                    user_id=self._user_id,
                    tool_name=tool_name,
                    context=step.description,
                    limit=2,
                )
                if error_context:
                    context_parts.append(error_context)
                    logger.debug("Injected error context for tool: %s", tool_name)

            # 3. Relevant memories for this step (Phase 3: with reranking + MMR)
            memories = await self._memory_service.retrieve_for_task(
                user_id=self._user_id,
                task_description=step.description,
                limit=5,
            )
            if memories:
                memory_text = await self._memory_service.format_memories_for_context(memories, max_tokens=500)
                context_parts.append(memory_text)
                logger.debug("Injected %d memories into execution context", len(memories))

            return "\n\n".join(context_parts) if context_parts else None

        except Exception as e:
            logger.warning("Failed to retrieve memories for step: %s", e)
            return None

    def _get_error_pattern_signal(self, step: Step) -> str | None:
        """Get proactive error pattern signals."""
        try:
            from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer

            pattern_analyzer = get_error_pattern_analyzer()
            likely_tools = pattern_analyzer.infer_tools_from_description(step.description)
            signal = pattern_analyzer.get_proactive_signals(likely_tools)
            if signal:
                logger.debug("Proactive error warning for tools: %s", likely_tools)
            return signal
        except Exception as e:
            logger.warning("Failed to get error pattern signals: %s", e)
            return None

    def _get_locked_entity_reminder(
        self,
        request_contract: RequestContract | None,
    ) -> str | None:
        """Build locked entity reminder from request contract."""
        from app.core.config import get_settings

        settings = get_settings()

        if settings.enable_search_fidelity_guardrail and request_contract and request_contract.locked_entities:
            return (
                "\n\n## IMPORTANT\n"
                "The user's request specifically mentions: "
                + ", ".join(request_contract.locked_entities)
                + ". Preserve these exact terms in your response and search queries."
            )
        return None
