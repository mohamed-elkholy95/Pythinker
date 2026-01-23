from typing import AsyncGenerator, Optional, List
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.external.file import FileStorage
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.execution import (
    EXECUTION_SYSTEM_PROMPT,
    EXECUTION_PROMPT,
    SUMMARIZE_PROMPT,
    build_execution_prompt
)
from app.domain.services.agents.task_state_manager import get_task_state_manager
from app.domain.services.agents.token_manager import TokenManager
from app.domain.models.event import (
    BaseEvent,
    StepEvent,
    StepStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.message import MessageTool
from app.domain.utils.json_parser import JsonParser
from app.domain.services.agents.prompt_adapter import PromptAdapter
import logging

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
        tools: List[BaseTool],
        json_parser: JsonParser,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools
        )
        # Initialize prompt adapter for dynamic context injection
        self._prompt_adapter = PromptAdapter()
    
    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
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

        # Build execution prompt with context signals
        base_prompt = build_execution_prompt(
            step=step.description,
            message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language,
            pressure_signal=pressure_signal,
            task_state=task_state_signal
        )

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
                    self._prompt_adapter.track_tool_use(event.function_name, success=success, error=error)

                if event.function_name == "message_ask_user":
                    if event.status == ToolStatus.CALLING:
                        yield MessageEvent(message=event.function_args.get("text", ""))
                    elif event.status == ToolStatus.CALLED:
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
        yield StepEvent(status=StepStatus.RUNNING, step=Step(
            id="summarize",
            description="Preparing final summary...",
            status=ExecutionStatus.IN_PROGRESS
        ))

        # Add summarize prompt to memory and ask LLM directly (no tools)
        await self._add_to_memory([{"role": "user", "content": SUMMARIZE_PROMPT}])
        await self._ensure_within_token_limit()

        try:
            # Call LLM WITHOUT tools to get a pure text summary
            response = await self.llm.ask(
                self.memory.get_messages(),
                tools=None,  # No tools during summarization
                response_format={"type": "json_object"},
                tool_choice=None
            )

            content = response.get("content", "")
            logger.debug(f"Execution agent summary response: {content}")

            # Parse and yield the summary message
            parsed_response = await self.json_parser.parse(content)
            message = Message.model_validate(parsed_response)
            attachments = [FileInfo(file_path=file_path) for file_path in message.attachments]

            # Mark summarize step as completed
            yield StepEvent(status=StepStatus.COMPLETED, step=Step(
                id="summarize",
                description="Summary complete",
                status=ExecutionStatus.COMPLETED
            ))

            yield MessageEvent(message=message.message, attachments=attachments)

        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            yield ErrorEvent(error=f"Failed to generate summary: {str(e)}")