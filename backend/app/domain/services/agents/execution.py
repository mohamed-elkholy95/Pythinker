from typing import AsyncGenerator, Optional, List, TYPE_CHECKING
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
from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer
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
    ReportEvent,
)
from app.domain.models.agent_response import ExecutionStepResult, SummarizeResponse
import uuid
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.message import MessageTool
from app.domain.utils.json_parser import JsonParser
from app.domain.services.agents.prompt_adapter import PromptAdapter
from app.domain.services.agents.critic import CriticAgent, CriticVerdict, CriticConfig
from app.domain.services.agents.context_manager import ContextManager
import logging

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
        tools: List[BaseTool],
        json_parser: JsonParser,
        critic_config: Optional[CriticConfig] = None,
        memory_service: Optional["MemoryService"] = None,
        user_id: Optional[str] = None,
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

        # Initialize critic agent for output quality assurance
        self._critic = CriticAgent(
            llm=llm,
            json_parser=json_parser,
            config=critic_config or CriticConfig(
                enabled=True,
                auto_approve_simple_tasks=True,
                max_revision_attempts=2
            )
        )
        self._user_request: Optional[str] = None  # Track for critic context

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

        # Context manager for execution continuity (Phase 1)
        self._context_manager = ContextManager(max_context_tokens=8000)
    
    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
        # Store user request for critic context
        self._user_request = message.message

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
                    user_id=self._user_id,
                    task_description=step.description,
                    limit=5
                )
                if memories:
                    memory_context = self._memory_service.format_memories_for_context(
                        memories,
                        max_tokens=500
                    )
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

        # Build execution prompt with context signals
        base_prompt = build_execution_prompt(
            step=step.description,
            message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language,
            pressure_signal=pressure_signal,
            task_state=task_state_signal,
            memory_context=memory_context
        )

        # Add working context if available
        if context_summary:
            base_prompt = f"{base_prompt}\n\n## Working Context\n{context_summary}"
            logger.debug("Injected working context into execution prompt")

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

                    # Track in context manager (Phase 1)
                    if success and event.function_result:
                        # Track file operations
                        if event.function_name in ["file_write", "file_create"]:
                            file_path = event.function_args.get("path", "")
                            if file_path:
                                self._context_manager.track_file_operation(
                                    path=file_path,
                                    operation="created",
                                    content_summary=f"Created via {event.function_name}",
                                )
                        elif event.function_name == "file_read":
                            file_path = event.function_args.get("path", "")
                            if file_path:
                                self._context_manager.track_file_operation(
                                    path=file_path,
                                    operation="read",
                                )

                        # Track tool executions for non-file operations
                        if not event.function_name.startswith("file_"):
                            result_summary = str(event.function_result.message)[:200] if hasattr(event.function_result, 'message') else "Success"
                            self._context_manager.track_tool_execution(
                                tool_name=event.tool_name,
                                summary=result_summary,
                            )

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
            status=ExecutionStatus.RUNNING
        ))

        # Add summarize prompt to memory and ask LLM directly (no tools)
        await self._add_to_memory([{"role": "user", "content": SUMMARIZE_PROMPT}])
        await self._ensure_within_token_limit()

        try:
            summary_response = None
            message_content = ""
            message_title = None
            message_attachments: List[str] = []

            # Try structured output first
            if hasattr(self.llm, 'ask_structured'):
                try:
                    summary_response = await self.llm.ask_structured(
                        self.memory.get_messages(),
                        response_model=SummarizeResponse,
                        tools=None,
                        tool_choice=None
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
                    self.memory.get_messages(),
                    tools=None,
                    response_format={"type": "json_object"},
                    tool_choice=None
                )

                content = response.get("content", "")
                logger.debug(f"Execution agent summary response: {content}")

                parsed_response = await self.json_parser.parse(content)
                message = Message.model_validate(parsed_response)
                message_content = message.message
                message_title = message.title
                message_attachments = message.attachments

            attachments = [FileInfo(file_path=file_path) for file_path in message_attachments]

            # Run critic review on the summary with actual revision support
            if len(message_content) > 200 and self._user_request:
                message_content = await self._apply_critic_revision(
                    message_content,
                    attachments
                )

            # Mark summarize step as completed
            yield StepEvent(status=StepStatus.COMPLETED, step=Step(
                id="summarize",
                description="Summary complete",
                status=ExecutionStatus.COMPLETED
            ))

            # Emit ReportEvent if there are attachments or substantial content
            # Otherwise emit a simple MessageEvent
            has_attachments = len(attachments) > 0
            is_substantial = len(message_content) > 500
            has_title = bool(message_title)
            is_report_structure = self._is_report_structure(message_content)

            if has_attachments or is_substantial or has_title or is_report_structure:
                title = message_title or self._extract_title(message_content)
                yield ReportEvent(
                    id=str(uuid.uuid4()),
                    title=title,
                    content=message_content,
                    attachments=attachments if attachments else None
                )
            else:
                yield MessageEvent(message=message_content, attachments=attachments)

        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            yield ErrorEvent(error=f"Failed to generate summary: {str(e)}")

    def _extract_title(self, content: str) -> str:
        """Extract a title from markdown content."""
        import re
        lines = content.strip().split('\n')

        # Try to find h1 heading
        for line in lines[:10]:  # Check first 10 lines
            h1_match = re.match(r'^#\s+(.+)$', line.strip())
            if h1_match:
                return h1_match.group(1).strip()

        # Try to find h2 heading
        for line in lines[:10]:
            h2_match = re.match(r'^##\s+(.+)$', line.strip())
            if h2_match:
                return h2_match.group(1).strip()

        # Fallback: use first non-empty line, truncated
        for line in lines[:5]:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                # Remove markdown formatting and truncate
                clean = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
                clean = re.sub(r'\*(.+?)\*', r'\1', clean)
                return clean[:80] + ('...' if len(clean) > 80 else '')

        return "Task Report"

    async def _apply_critic_revision(
        self,
        message_content: str,
        attachments: List[FileInfo]
    ) -> str:
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
                    files=[f.file_path for f in attachments] if attachments else None
                )

                logger.info(
                    f"Critic review (attempt {revision_count + 1}): "
                    f"{review.verdict.value} ({review.confidence:.2f})"
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
                    revision_guidance = await self._critic.get_revision_guidance(
                        current_content,
                        review
                    )

                    # Ask LLM to revise the content
                    try:
                        revision_messages = [
                            {
                                "role": "system",
                                "content": (
                                    "You are revising your previous output based on quality feedback. "
                                    "Make the specific improvements requested while preserving the good parts. "
                                    "Return the complete revised output in the same format."
                                )
                            },
                            {
                                "role": "user",
                                "content": revision_guidance
                            }
                        ]

                        response = await self.llm.ask(
                            revision_messages,
                            tools=None,
                            tool_choice=None
                        )

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

    def _is_report_structure(self, content: str) -> bool:
        """Check if content has report-like structure (headings, sections)."""
        import re
        if not content:
            return False

        # Check for markdown headings (##, ###, etc.)
        heading_count = len(re.findall(r'^#{1,4}\s+.+', content, re.MULTILINE))
        if heading_count >= 2:
            return True

        # Check for bold section headers pattern (e.g., **Section:**)
        bold_headers = len(re.findall(r'\*\*[^*]+:\*\*', content))
        if bold_headers >= 2:
            return True

        # Check for numbered sections (1. Section, 2. Section)
        numbered_sections = len(re.findall(r'^\d+\.\s+[A-Z]', content, re.MULTILINE))
        if numbered_sections >= 2:
            return True

        return False

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

    def get_deliverables(self) -> List[str]:
        """Get list of completed deliverables.

        Returns:
            List of deliverable file paths
        """
        return self._context_manager.get_deliverables()

    def clear_context(self) -> None:
        """Clear execution context (use between tasks)."""
        self._context_manager.clear()
        logger.debug("Cleared execution context")