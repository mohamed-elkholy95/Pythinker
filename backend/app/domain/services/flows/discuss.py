"""
Discuss Flow
Simple Q&A conversation flow with search capabilities.
No task planning - direct responses with optional mode switching to Agent.
"""

import json
import logging
import re
from collections.abc import AsyncGenerator
from enum import Enum

from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ModeChangeEvent,
    SuggestionEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.message import Message
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.flows.base import BaseFlow
from app.domain.services.prompts.discuss import (
    DISCUSS_SYSTEM_PROMPT,
    build_discuss_prompt,
)
from app.domain.services.prompts.system import CORE_PROMPT
from app.domain.services.tools.agent_mode import AgentModeTool
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.search import SearchTool
from app.domain.utils.json_parser import JsonParser
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DiscussStatus(str, Enum):
    """Discuss flow status"""

    IDLE = "idle"
    RESPONDING = "responding"
    MODE_SWITCHING = "mode_switching"
    COMPLETED = "completed"
    ERROR = "error"


class DiscussAgent(BaseAgent):
    """
    Discuss agent for simple Q&A conversations.
    Limited tools: search and mode switching only.
    """

    name: str = "discuss"
    system_prompt: str = CORE_PROMPT + DISCUSS_SYSTEM_PROMPT
    format: str | None = None  # No strict JSON format for conversational responses

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: list[BaseTool],
        json_parser: JsonParser,
    ):
        super().__init__(
            agent_id=agent_id, agent_repository=agent_repository, llm=llm, json_parser=json_parser, tools=tools
        )


class DiscussFlow(BaseFlow):
    """
    Discuss Flow - lightweight conversation flow for simple Q&A.

    Features:
    - Direct conversational responses (no planning)
    - Search capability for information lookup
    - Mode switching to Agent mode for complex tasks
    - Suggestion extraction from responses
    """

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        session_id: str,
        session_repository: SessionRepository,
        llm: LLM,
        json_parser: JsonParser,
        search_engine: SearchEngine | None = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._llm = llm
        self._json_parser = json_parser

        self.status = DiscussStatus.IDLE
        self._mode_switch_task: str | None = None

        # Initialize tools - limited set for discuss mode
        self._agent_mode_tool = AgentModeTool()
        tools: list[BaseTool] = [self._agent_mode_tool]

        if search_engine:
            tools.append(SearchTool(search_engine))

        # Create discuss agent
        self._agent = DiscussAgent(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )

        logger.debug(f"DiscussFlow initialized for agent {agent_id}")

    @property
    def mode_switch_requested(self) -> bool:
        """Check if a mode switch to Agent mode was requested"""
        return self._agent_mode_tool.mode_switch_requested

    @property
    def mode_switch_task(self) -> str | None:
        """Get the task description for Agent mode if switch was requested"""
        return self._agent_mode_tool.task_description

    def _extract_suggestions(self, response: str) -> list[str]:
        """
        Extract suggestions from the response JSON block.

        Looks for:
        ```json
        {"suggestions": ["Suggestion 1", "Suggestion 2"]}
        ```

        Returns:
            List of suggestion strings, or empty list if not found
        """
        # Pattern to find JSON block with suggestions
        json_pattern = r'```json\s*(\{[^`]*"suggestions"[^`]*\})\s*```'
        match = re.search(json_pattern, response, re.DOTALL | re.IGNORECASE)

        if match:
            try:
                data = json.loads(match.group(1))
                suggestions = data.get("suggestions", [])
                if isinstance(suggestions, list):
                    return [str(s) for s in suggestions[:3]]  # Max 3 suggestions
            except json.JSONDecodeError:
                logger.warning("Failed to parse suggestions JSON")

        return []

    def _clean_response(self, response: str) -> str:
        """Remove the suggestions JSON block from the response for display"""
        # Remove JSON block with suggestions
        json_pattern = r'\s*```json\s*\{[^`]*"suggestions"[^`]*\}\s*```\s*'
        cleaned = re.sub(json_pattern, "", response, flags=re.DOTALL | re.IGNORECASE)
        return cleaned.strip()

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """
        Run the discuss flow for a single message.

        Args:
            message: User message to process

        Yields:
            Events including tool calls, messages, suggestions, and mode changes
        """
        self.status = DiscussStatus.RESPONDING

        try:
            # Build the discuss prompt
            settings = get_settings()
            prompt = build_discuss_prompt(
                message=message.message,
                attachments="\n".join(message.attachments) if message.attachments else "",
                language=settings.default_language,
            )

            # Execute through the agent
            async for event in self._agent.execute(prompt):
                if isinstance(event, ToolEvent):
                    # Check for mode switch request
                    if event.function_name == "agent_start_task" and event.status == ToolStatus.CALLED:
                        self._mode_switch_task = self._agent_mode_tool.task_description
                        self.status = DiscussStatus.MODE_SWITCHING

                        # Yield the tool event first
                        yield event

                        # Yield mode change event
                        yield ModeChangeEvent(
                            mode="agent", reason=f"Task requires Agent mode: {self._mode_switch_task}"
                        )

                        # Break out of the agent loop - mode switch should be handled by caller
                        logger.info("Mode switch requested, breaking out of discuss flow")
                        break
                    yield event

                elif isinstance(event, MessageEvent):
                    # Extract suggestions from response
                    raw_response = event.message
                    suggestions = self._extract_suggestions(raw_response)
                    clean_message = self._clean_response(raw_response)

                    # Yield cleaned message
                    yield MessageEvent(message=clean_message, role="assistant", attachments=event.attachments)

                    # Yield suggestions if found
                    if suggestions:
                        yield SuggestionEvent(suggestions=suggestions)

                elif isinstance(event, ErrorEvent):
                    self.status = DiscussStatus.ERROR
                    yield event

                else:
                    yield event

            # Check if mode switch was requested
            if self.mode_switch_requested and self._mode_switch_task:
                logger.info(f"Mode switch requested to Agent mode for task: {self._mode_switch_task}")
                # The mode change event was already yielded above

            self.status = DiscussStatus.COMPLETED

        except Exception as e:
            logger.exception(f"Error in DiscussFlow: {e}")
            self.status = DiscussStatus.ERROR
            yield ErrorEvent(error=str(e))

        yield DoneEvent()

    def is_done(self) -> bool:
        """Check if the flow is complete"""
        return self.status in (DiscussStatus.COMPLETED, DiscussStatus.IDLE)

    def reset(self) -> None:
        """Reset flow state for new conversation"""
        self.status = DiscussStatus.IDLE
        self._mode_switch_task = None
        self._agent_mode_tool.reset()
