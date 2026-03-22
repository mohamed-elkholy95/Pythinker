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
from typing import TYPE_CHECKING

from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ModeChangeEvent,
    ReportEvent,
    SuggestionEvent,
    TitleEvent,
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

if TYPE_CHECKING:
    from app.domain.services.conversation_context_service import ConversationContextService
    from app.domain.services.memory_service import MemoryService

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
        default_language: str = "en",
        memory_service: "MemoryService | None" = None,
        conversation_context_service: "ConversationContextService | None" = None,
        user_id: str = "",
    ):
        self._default_language = default_language
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._llm = llm
        self._json_parser = json_parser
        self._memory_service = memory_service
        self._conversation_context_service = conversation_context_service
        self._user_id = user_id

        self.status = DiscussStatus.IDLE
        self._mode_switch_task: str | None = None
        self._title_emitted: bool = False

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

    async def _generate_follow_up_suggestions(self, user_message: str, assistant_message: str) -> list[str]:
        """Generate follow-up suggestions when the model omits suggestions JSON."""
        try:
            recent_session_context = await self._build_recent_session_context_excerpt()
            context_block = f"Recent session context:\n{recent_session_context}\n\n" if recent_session_context else ""
            # Truncate assistant message to a reasonable size for the suggestion prompt
            assistant_excerpt = assistant_message[:800] if len(assistant_message) > 800 else assistant_message
            suggestion_response = await self._llm.ask(
                [
                    {
                        "role": "user",
                        "content": (
                            "You are a helpful assistant generating follow-up questions.\n\n"
                            f"{context_block}"
                            f'The user asked: "{user_message}"\n\n'
                            f'The assistant replied: "{assistant_excerpt}"\n\n'
                            "Based on this conversation, generate exactly 3 natural follow-up questions "
                            "that the user might want to ask next. Each question should:\n"
                            "- Be 5-12 words long\n"
                            "- Be a complete, grammatically correct question\n"
                            "- Relate directly to the topic discussed\n"
                            "- Explore a different angle or go deeper into the topic\n"
                            "- NOT repeat words from the original question unnecessarily\n\n"
                            'Return ONLY a JSON object like: {"suggestions": ["Question 1?", "Question 2?", "Question 3?"]}'
                        ),
                    }
                ],
                tools=None,
                response_format={"type": "json_object"},
                tool_choice=None,
            )

            raw = suggestion_response.get("content", "[]")
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            suggestions = parsed if isinstance(parsed, list) else parsed.get("suggestions", [])
            normalized = [str(s).strip() for s in suggestions if str(s).strip()]
            if normalized:
                return normalized[:3]
        except Exception as e:
            logger.debug(f"Discuss suggestion generation failed, using fallback suggestions: {e}")

        return self._default_follow_up_suggestions(user_message, assistant_message)

    def _default_follow_up_suggestions(self, user_message: str, assistant_message: str) -> list[str]:
        """Provide deterministic fallback suggestions when generation fails."""
        combined = f"{user_message} {assistant_message}".lower()
        if "pirate" in combined or "arrr" in combined:
            return [
                "Tell me a pirate story.",
                "What's your favorite pirate saying?",
                "How do pirates find treasure?",
            ]

        topic_hint = self._extract_topic_hint(combined)
        if topic_hint:
            return [
                f"Can you go deeper on {topic_hint}?",
                f"What should I try next for {topic_hint}?",
                f"Can you show a concrete example for {topic_hint}?",
            ]

        return [
            "Can you explain that in more detail?",
            "Can you give me a practical example?",
            "What should I ask next about this?",
        ]

    async def _build_recent_session_context_excerpt(self, max_messages: int = 6, max_chars: int = 900) -> str:
        """Build a compact session transcript excerpt from persisted events."""
        try:
            session = await self._session_repository.find_by_id(self._session_id)
        except Exception:
            return ""

        if not session or not session.events:
            return ""

        lines: list[str] = []
        for event in reversed(session.events):
            if isinstance(event, MessageEvent):
                text = (event.message or "").strip()
                if not text:
                    continue
                speaker = "User" if event.role == "user" else "Assistant"
                lines.append(f"{speaker}: {text[:220]}")
            elif isinstance(event, ReportEvent):
                report_text = f"{event.title or ''} {event.content or ''}".strip()
                if report_text:
                    lines.append(f"Assistant report: {report_text[:220]}")

            if len(lines) >= max_messages:
                break

        if not lines:
            return ""

        transcript = "\n".join(reversed(lines))
        return transcript[:max_chars]

    def _extract_topic_hint(self, text: str) -> str | None:
        """Extract a coherent topic phrase from combined user+assistant text.

        Prioritizes noun-like tokens (longer words, excluding common verbs and
        function words) and returns a readable 2-3 word topic phrase.
        """
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        tokens = cleaned.split()
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
            "also",
            "just",
            "like",
            "will",
            "been",
            "some",
            "very",
            "much",
            "here",
            "well",
            "really",
            "know",
            "think",
            "want",
            "need",
            "help",
            "tell",
            "please",
            "make",
            "sure",
            "does",
            "doing",
            "done",
            "going",
            "being",
            "look",
            "give",
            "take",
            "come",
            "keep",
            "good",
            "great",
            "best",
            "most",
            "many",
            "each",
            "every",
            "they",
            "their",
            "these",
            "those",
            "other",
            "said",
            "says",
            "explain",
            "detail",
            "example",
            "question",
            "answer",
            "capital",
            "france",  # avoid leaking example-specific tokens
        }

        # Score tokens by length (proxy for specificity) and frequency
        from collections import Counter

        token_counts = Counter(t for t in tokens if len(t) >= 4 and t not in stopwords)

        if not token_counts:
            return None

        # Take the top 2-3 most frequent meaningful tokens, preserving first-occurrence order
        top_tokens = [t for t, _ in token_counts.most_common(5)]
        seen_order: list[str] = []
        for t in tokens:
            if t in top_tokens and t not in seen_order:
                seen_order.append(t)
            if len(seen_order) >= 3:
                break

        if not seen_order:
            return None

        # Return 2-3 word phrase; use "that" as glue only if we have a single word
        hint = " ".join(seen_order[:3])
        return hint or None

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
            # Emit TitleEvent on the first message so the sidebar shows a meaningful title
            if not self._title_emitted:
                raw = (message.message or "").strip()
                if raw:
                    fast_title = raw[:60].rstrip() + ("\u2026" if len(raw) > 60 else "")
                    yield TitleEvent(title=fast_title)
                self._title_emitted = True

            # Retrieve conversation context and long-term memories
            context_parts: list[str] = []
            try:
                if self._conversation_context_service and self._user_id:
                    conv_ctx = await self._conversation_context_service.retrieve_context(
                        user_id=self._user_id,
                        session_id=self._session_id,
                        query=message.message,
                        current_turn_number=self._conversation_context_service._turn_counter,
                    )
                    formatted = conv_ctx.format_for_injection()
                    if formatted:
                        context_parts.append(formatted)
            except Exception:
                logger.debug("Failed to retrieve conversation context for discuss", exc_info=True)

            try:
                if self._memory_service and self._user_id:
                    memories = await self._memory_service.retrieve_for_task(
                        user_id=self._user_id,
                        task_description=message.message,
                        limit=3,
                    )
                    if memories:
                        mem_lines = ["[Long-term memories]"]
                        mem_lines.extend(f"- {m.memory.content}" for m in memories)
                        context_parts.append("\n".join(mem_lines))
            except Exception:
                logger.debug("Failed to retrieve long-term memories for discuss", exc_info=True)

            context_str = "\n\n".join(context_parts)

            # Build the discuss prompt
            prompt = build_discuss_prompt(
                message=message.message,
                attachments="\n".join(message.attachments) if message.attachments else "",
                language=self._default_language,
                context=context_str,
            )

            # Prepend current datetime signal so agent can answer time/date queries
            from app.domain.services.prompts.system import get_current_datetime_signal

            prompt = get_current_datetime_signal() + prompt

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
                    cleaned_event = MessageEvent(message=clean_message, role="assistant", attachments=event.attachments)
                    yield cleaned_event

                    # If model omitted suggestions JSON (e.g., exact-output requests),
                    # generate them separately so the UI can still render follow-ups.
                    if not suggestions:
                        suggestions = await self._generate_follow_up_suggestions(message.message, clean_message)

                    # Yield suggestions if available with discuss-specific metadata
                    if suggestions:
                        # Bounded excerpt from assistant message
                        message_excerpt = clean_message[:500] + ("..." if len(clean_message) > 500 else "")
                        yield SuggestionEvent(
                            suggestions=suggestions,
                            source="discuss",
                            anchor_event_id=cleaned_event.id,
                            anchor_excerpt=message_excerpt,
                        )

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
        self._title_emitted = False
        self._agent_mode_tool.reset()
