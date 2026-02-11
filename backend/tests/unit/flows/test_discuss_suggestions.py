"""Tests for DiscussFlow suggestion generation with exchange context."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import MessageEvent, SuggestionEvent
from app.domain.models.message import Message
from app.domain.services.flows.discuss import DiscussFlow


class TestDiscussFlowSuggestionGeneration:
    """Test DiscussFlow generates context-aware suggestions."""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM."""
        llm = AsyncMock()
        llm.model_name = "gpt-4"  # Set as string, not AsyncMock
        llm.ask = AsyncMock()
        return llm

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def discuss_flow(self, mock_llm, mock_agent_repository, mock_json_parser):
        """Create DiscussFlow instance."""
        return DiscussFlow(
            agent_id="test-agent",
            agent_repository=mock_agent_repository,
            session_id="test-session",
            session_repository=AsyncMock(),
            llm=mock_llm,
            json_parser=mock_json_parser,
            search_engine=None,
            default_language="en",
        )

    @pytest.mark.asyncio
    async def test_discuss_suggestion_prompt_includes_user_message(self, discuss_flow, mock_llm):
        """Discuss suggestion generation should include user message in prompt."""
        user_msg = "What are pirates known for?"
        assistant_msg = "Pirates are known for sailing the high seas, searching for treasure."

        # Mock LLM response
        mock_llm.ask.return_value = {
            "content": '["Tell me about pirate ships", "What weapons did pirates use?", "Famous pirate captains?"]'
        }

        suggestions = await discuss_flow._generate_follow_up_suggestions(user_msg, assistant_msg)

        # Verify LLM was called
        assert mock_llm.ask.called
        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        prompt_content = messages[0]["content"]

        # Verify prompt includes both messages
        assert user_msg in prompt_content
        assert assistant_msg in prompt_content

    @pytest.mark.asyncio
    async def test_discuss_suggestion_prompt_includes_exchange_context(self, discuss_flow, mock_llm):
        """Discuss suggestions should be grounded in the user-assistant exchange."""
        user_msg = "Explain quantum computing"
        assistant_msg = "Quantum computing uses quantum bits (qubits) that can exist in superposition."

        mock_llm.ask.return_value = {"content": '["What is superposition?", "How do qubits work?"]'}

        suggestions = await discuss_flow._generate_follow_up_suggestions(user_msg, assistant_msg)

        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        prompt_content = messages[0]["content"]

        # Verify exchange context is present
        assert "exchange" in prompt_content.lower() or (user_msg in prompt_content and assistant_msg in prompt_content)

    @pytest.mark.asyncio
    async def test_discuss_emits_suggestion_event_with_metadata(self, discuss_flow, mock_llm):
        """DiscussFlow should emit SuggestionEvent with source='discuss' metadata."""
        # Mock agent.execute to yield MessageEvent
        async def mock_execute(prompt: str):
            yield MessageEvent(message="Test response about pirates", role="assistant")

        discuss_flow._agent.execute = mock_execute

        # Mock suggestion generation
        mock_llm.ask.return_value = {"content": '["Suggestion 1", "Suggestion 2", "Suggestion 3"]'}

        # Collect events
        events = []
        test_message = Message(message="Tell me about pirates")
        async for event in discuss_flow.run(test_message):
            events.append(event)

        # Find SuggestionEvent
        suggestion_events = [e for e in events if isinstance(e, SuggestionEvent)]
        assert len(suggestion_events) == 1

        suggestion_event = suggestion_events[0]

        # Verify metadata
        assert suggestion_event.source == "discuss"
        # anchor_event_id should link to the MessageEvent
        message_events = [e for e in events if isinstance(e, MessageEvent)]
        if message_events:
            assert suggestion_event.anchor_event_id == message_events[0].id

    @pytest.mark.asyncio
    async def test_discuss_suggestion_fallback_when_llm_fails(self, discuss_flow, mock_llm):
        """Should return fallback suggestions when LLM fails."""
        mock_llm.ask.side_effect = Exception("LLM error")

        suggestions = await discuss_flow._generate_follow_up_suggestions("User question", "Assistant reply")

        # Should return fallback
        assert len(suggestions) == 3
        assert all(isinstance(s, str) for s in suggestions)
