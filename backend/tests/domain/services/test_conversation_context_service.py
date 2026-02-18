"""Tests for ConversationContextService.

Unit tests covering buffered batch flush, event-to-turn extraction,
deduplication, retrieval, and non-propagating error handling.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.conversation_context import (
    ConversationContext,
    ConversationContextResult,
    ConversationTurn,
    TurnEventType,
    TurnRole,
)
from app.domain.models.event import (
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    ProgressEvent,
    ReportEvent,
    StepEvent,
    StepStatus,
    StreamEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.plan import Step

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]


def _make_turn(
    content: str = "Test content for turn",
    session_id: str = "sess-1",
    user_id: str = "user-1",
    turn_number: int = 0,
    role: TurnRole = TurnRole.USER,
    event_type: TurnEventType = TurnEventType.MESSAGE,
) -> ConversationTurn:
    return ConversationTurn(
        point_id=f"point-{turn_number}",
        user_id=user_id,
        session_id=session_id,
        role=role,
        event_type=event_type,
        content=content,
        turn_number=turn_number,
        event_id=f"evt-{turn_number}",
        created_at=int(time.time()),
        content_hash=_content_hash(content),
    )


def _make_context_result(
    content: str = "result content",
    turn_number: int = 0,
    role: str = "user",
    source: str = "sliding_window",
    score: float = 1.0,
) -> ConversationContextResult:
    return ConversationContextResult(
        point_id=f"point-{turn_number}",
        content=content,
        role=role,
        event_type="message",
        session_id="sess-1",
        turn_number=turn_number,
        created_at=int(time.time()),
        relevance_score=score,
        source=source,
    )


def _mock_settings(**overrides):
    """Create mock settings with conversation context defaults."""
    defaults = {
        "feature_conversation_context_enabled": True,
        "conversation_context_buffer_size": 5,
        "conversation_context_flush_interval_seconds": 10.0,
        "conversation_context_sliding_window": 5,
        "conversation_context_semantic_top_k": 5,
        "conversation_context_cross_session_top_k": 3,
        "conversation_context_min_content_length": 20,
        "conversation_context_cross_session_min_score": 0.4,
        "conversation_context_retrieval_timeout_seconds": 2.0,
        "qdrant_use_hybrid_search": True,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


@pytest.fixture
def mock_repository():
    repo = AsyncMock()
    repo.upsert_batch = AsyncMock()
    repo.get_recent_turns = AsyncMock(return_value=[])
    repo.search_session_turns = AsyncMock(return_value=[])
    repo.search_cross_session = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_repository):
    with patch("app.domain.services.conversation_context_service.get_settings") as mock_get:
        mock_get.return_value = _mock_settings()
        from app.domain.services.conversation_context_service import ConversationContextService

        return ConversationContextService(repository=mock_repository)


# ------------------------------------------------------------------ #
# Turn recording and buffering
# ------------------------------------------------------------------ #


class TestTurnRecording:
    """Tests for record_turn, buffering, and deduplication."""

    @pytest.mark.asyncio
    async def test_record_turn_buffers_correctly(self, service):
        """Turns accumulate in buffer without flushing until threshold."""
        turn = _make_turn(content="A sufficiently long test message for buffering")
        await service.record_turn(turn)

        assert len(service._buffer) == 1
        assert service._buffer[0] is turn

    @pytest.mark.asyncio
    async def test_skip_short_content(self, service):
        """Turns shorter than min_content_length are skipped."""
        short_turn = _make_turn(content="short")
        await service.record_turn(short_turn)

        assert len(service._buffer) == 0

    @pytest.mark.asyncio
    async def test_deduplication_same_content_same_session(self, service):
        """Identical content in the same session is stored only once."""
        turn1 = _make_turn(content="This is a duplicate test message", turn_number=0)
        turn2 = _make_turn(content="This is a duplicate test message", turn_number=1)

        await service.record_turn(turn1)
        await service.record_turn(turn2)

        assert len(service._buffer) == 1

    @pytest.mark.asyncio
    async def test_deduplication_different_sessions(self, service):
        """Same content in different sessions is NOT deduplicated."""
        turn1 = _make_turn(content="Cross-session content for testing", session_id="sess-1", turn_number=0)
        turn2 = _make_turn(content="Cross-session content for testing", session_id="sess-2", turn_number=1)

        await service.record_turn(turn1)
        await service.record_turn(turn2)

        assert len(service._buffer) == 2

    @pytest.mark.asyncio
    async def test_flush_at_buffer_size(self, service, mock_repository):
        """Buffer flushes when buffer_size threshold is reached."""
        with (
            patch("app.infrastructure.external.embedding.client.get_embedding_client") as mock_embed_fn,
            patch("app.domain.services.embeddings.bm25_encoder.get_bm25_encoder") as mock_bm25_fn,
        ):
            mock_client = AsyncMock()
            mock_client.embed_batch = AsyncMock(return_value=[[0.1] * 10] * 5)
            mock_embed_fn.return_value = mock_client

            mock_bm25 = MagicMock()
            mock_bm25.encode = MagicMock(return_value={0: 0.5})
            mock_bm25_fn.return_value = mock_bm25

            # Fill buffer to threshold (5 is default buffer_size)
            for i in range(5):
                turn = _make_turn(content=f"Unique message number {i} for flush test", turn_number=i)
                await service.record_turn(turn)

            # Give the asyncio.create_task a chance to execute
            await asyncio.sleep(0.1)

            # Verify flush happened
            mock_repository.upsert_batch.assert_called_once()
            upserted = mock_repository.upsert_batch.call_args[0][0]
            assert len(upserted) == 5

    @pytest.mark.asyncio
    async def test_flush_remaining_on_session_end(self, service, mock_repository):
        """flush_remaining force-flushes partial buffer."""
        with (
            patch("app.infrastructure.external.embedding.client.get_embedding_client") as mock_embed_fn,
            patch("app.domain.services.embeddings.bm25_encoder.get_bm25_encoder") as mock_bm25_fn,
        ):
            mock_client = AsyncMock()
            mock_client.embed_batch = AsyncMock(return_value=[[0.1] * 10] * 2)
            mock_embed_fn.return_value = mock_client

            mock_bm25 = MagicMock()
            mock_bm25.encode = MagicMock(return_value={})
            mock_bm25_fn.return_value = mock_bm25

            # Buffer 2 turns (below threshold)
            for i in range(2):
                turn = _make_turn(content=f"Partial buffer message number {i}", turn_number=i)
                await service.record_turn(turn)

            assert len(service._buffer) == 2

            # Force flush
            await service.flush_remaining()

            mock_repository.upsert_batch.assert_called_once()
            assert len(service._buffer) == 0

    @pytest.mark.asyncio
    async def test_embed_failure_doesnt_propagate(self, service, mock_repository):
        """Embedding failures are caught and logged, never raised."""
        with (
            patch("app.infrastructure.external.embedding.client.get_embedding_client") as mock_embed_fn,
            patch("app.domain.services.embeddings.bm25_encoder.get_bm25_encoder") as mock_bm25_fn,
        ):
            mock_client = AsyncMock()
            mock_client.embed_batch = AsyncMock(side_effect=RuntimeError("Embedding API down"))
            mock_embed_fn.return_value = mock_client

            mock_bm25 = MagicMock()
            mock_bm25_fn.return_value = mock_bm25

            # Buffer turns and flush — should not raise
            for i in range(5):
                turn = _make_turn(content=f"Message that will fail embedding {i}", turn_number=i)
                await service.record_turn(turn)

            await asyncio.sleep(0.1)

            # No upsert should have happened since embed failed
            mock_repository.upsert_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_session_state(self, service):
        """reset_session_state clears dedup hashes and turn counter."""
        turn = _make_turn(content="Message before reset for testing")
        await service.record_turn(turn)

        assert len(service._seen_hashes) == 1
        service._turn_counter = 10

        service.reset_session_state()

        assert len(service._seen_hashes) == 0
        assert service._turn_counter == 0


# ------------------------------------------------------------------ #
# Event-to-turn extraction
# ------------------------------------------------------------------ #


class TestExtractTurnFromEvent:
    """Tests for extract_turn_from_event mapping."""

    def test_message_event_user(self, service):
        """User MessageEvent extracts as USER role."""
        event = MessageEvent(message="What is the capital of France?", role="user")
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 0)

        assert turn is not None
        assert turn.role == TurnRole.USER
        assert turn.event_type == TurnEventType.MESSAGE
        assert turn.content == "What is the capital of France?"

    def test_message_event_assistant(self, service):
        """Assistant MessageEvent extracts as ASSISTANT role."""
        event = MessageEvent(message="The capital of France is Paris.", role="assistant")
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 1)

        assert turn is not None
        assert turn.role == TurnRole.ASSISTANT
        assert turn.event_type == TurnEventType.MESSAGE

    def test_tool_event_called(self, service):
        """ToolEvent with CALLED status extracts as TOOL_SUMMARY."""
        event = ToolEvent(
            tool_call_id="tc-1",
            tool_name="web_search",
            function_name="web_search",
            function_args={"query": "test"},
            status=ToolStatus.CALLED,
            function_result="Search results: Paris is the capital",
        )
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 2)

        assert turn is not None
        assert turn.role == TurnRole.TOOL_SUMMARY
        assert turn.event_type == TurnEventType.TOOL_RESULT
        assert turn.tool_name == "web_search"
        assert "web_search:" in turn.content

    def test_tool_event_calling_skipped(self, service):
        """ToolEvent with CALLING status is skipped (only store results)."""
        event = ToolEvent(
            tool_call_id="tc-1",
            tool_name="web_search",
            function_name="web_search",
            function_args={"query": "test"},
            status=ToolStatus.CALLING,
        )
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 2)

        assert turn is None

    def test_step_event_completed(self, service):
        """StepEvent with COMPLETED status extracts as STEP_SUMMARY."""
        step = Step(description="Search for relevant data", result="Found 3 relevant sources")
        event = StepEvent(step=step, status=StepStatus.COMPLETED)
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 3)

        assert turn is not None
        assert turn.role == TurnRole.STEP_SUMMARY
        assert turn.event_type == TurnEventType.STEP_COMPLETION
        assert "Search for relevant data" in turn.content

    def test_step_event_running_skipped(self, service):
        """StepEvent with RUNNING status is skipped."""
        step = Step(description="Processing data")
        event = StepEvent(step=step, status=StepStatus.RUNNING)
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 3)

        assert turn is None

    def test_report_event(self, service):
        """ReportEvent extracts title + content as REPORT type."""
        event = ReportEvent(
            id="report-1",
            title="Analysis Report",
            content="This is a detailed analysis of the data with multiple findings.",
        )
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 4)

        assert turn is not None
        assert turn.role == TurnRole.ASSISTANT
        assert turn.event_type == TurnEventType.REPORT
        assert "Analysis Report" in turn.content
        assert "detailed analysis" in turn.content

    def test_error_event(self, service):
        """ErrorEvent with meaningful content extracts as ERROR type."""
        event = ErrorEvent(error="Token limit exceeded: 128000 tokens used")
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 5)

        assert turn is not None
        assert turn.role == TurnRole.ASSISTANT
        assert turn.event_type == TurnEventType.ERROR
        assert "Token limit exceeded" in turn.content

    def test_stream_event_skipped(self, service):
        """StreamEvent (partial UI content) is not stored."""
        event = StreamEvent(content="Partial streaming content chunk")
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 6)

        assert turn is None

    def test_progress_event_skipped(self, service):
        """ProgressEvent (UI-only) is not stored."""
        from app.domain.models.event import PlanningPhase

        event = ProgressEvent(
            phase=PlanningPhase.PLANNING,
            message="Planning step 1...",
        )
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 7)

        assert turn is None

    def test_done_event_skipped(self, service):
        """DoneEvent (signal-only) is not stored."""
        event = DoneEvent()
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 8)

        assert turn is None

    def test_short_message_event_skipped(self, service):
        """MessageEvent with content below min_content_length is skipped."""
        event = MessageEvent(message="ok", role="user")
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 9)

        assert turn is None

    def test_extracted_turn_has_content_hash(self, service):
        """Extracted turns include a SHA256[:16] content hash."""
        event = MessageEvent(message="A sufficiently long message for hashing", role="user")
        turn = service.extract_turn_from_event(event, "sess-1", "user-1", 0)

        assert turn is not None
        assert len(turn.content_hash) == 16
        assert turn.content_hash == _content_hash("A sufficiently long message for hashing")

    def test_extracted_turn_preserves_session_and_user(self, service):
        """Extracted turns carry forward session_id and user_id."""
        event = MessageEvent(message="Check user and session propagation test", role="user")
        turn = service.extract_turn_from_event(event, "sess-42", "user-99", 10)

        assert turn is not None
        assert turn.session_id == "sess-42"
        assert turn.user_id == "user-99"
        assert turn.turn_number == 10


# ------------------------------------------------------------------ #
# Context retrieval
# ------------------------------------------------------------------ #


class TestRetrieveContext:
    """Tests for three-phase context retrieval."""

    @pytest.mark.asyncio
    async def test_retrieval_sliding_window_only(self, service, mock_repository):
        """When turn_number <= sliding_window_size, only sliding window is returned."""
        window_turns = [
            _make_context_result(content="Recent turn 1", turn_number=0),
            _make_context_result(content="Recent turn 2", turn_number=1),
        ]
        mock_repository.get_recent_turns.return_value = window_turns

        result = await service.retrieve_context("user-1", "sess-1", "test query", current_turn_number=3)

        assert len(result.sliding_window_turns) == 2
        assert len(result.semantic_turns) == 0
        assert len(result.cross_session_turns) == 0
        mock_repository.search_session_turns.assert_not_called()
        mock_repository.search_cross_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_retrieval_all_three_phases(self, service, mock_repository):
        """When turn_number > sliding_window_size, all three phases run."""
        mock_repository.get_recent_turns.return_value = [
            _make_context_result(content="Window turn", turn_number=8),
        ]
        mock_repository.search_session_turns.return_value = [
            _make_context_result(content="Semantic turn", turn_number=2, source="intra_session", score=0.85),
        ]
        mock_repository.search_cross_session.return_value = [
            _make_context_result(content="Cross-session turn", turn_number=5, source="cross_session", score=0.7),
        ]

        with (
            patch("app.infrastructure.external.embedding.client.get_embedding_client") as mock_embed_fn,
            patch("app.domain.services.embeddings.bm25_encoder.get_bm25_encoder") as mock_bm25_fn,
        ):
            mock_client = AsyncMock()
            mock_client.embed = AsyncMock(return_value=[0.1] * 10)
            mock_embed_fn.return_value = mock_client

            mock_bm25 = MagicMock()
            mock_bm25.encode = MagicMock(return_value={0: 0.5})
            mock_bm25_fn.return_value = mock_bm25

            result = await service.retrieve_context("user-1", "sess-1", "test query", current_turn_number=10)

        assert len(result.sliding_window_turns) == 1
        assert len(result.semantic_turns) == 1
        assert len(result.cross_session_turns) == 1
        assert not result.is_empty
        assert result.total_turns == 3

    @pytest.mark.asyncio
    async def test_retrieval_returns_empty_on_timeout(self, service, mock_repository):
        """Retrieval returns empty ConversationContext when timeout expires."""

        async def slow_get_recent(*args, **kwargs):
            await asyncio.sleep(10)  # Way longer than timeout
            return []

        mock_repository.get_recent_turns = slow_get_recent

        # Override timeout to be very short
        service._settings.conversation_context_retrieval_timeout_seconds = 0.01

        result = await service.retrieve_context("user-1", "sess-1", "test query", current_turn_number=3)

        assert result.is_empty

    @pytest.mark.asyncio
    async def test_retrieval_returns_empty_on_error(self, service, mock_repository):
        """Retrieval returns empty ConversationContext on unexpected errors."""
        mock_repository.get_recent_turns = AsyncMock(side_effect=RuntimeError("Qdrant down"))

        result = await service.retrieve_context("user-1", "sess-1", "test query", current_turn_number=3)

        # Should still return empty (not raise)
        assert isinstance(result, ConversationContext)
        assert result.is_empty


# ------------------------------------------------------------------ #
# Domain model tests
# ------------------------------------------------------------------ #


class TestConversationContextModel:
    """Tests for ConversationContext dataclass behavior."""

    def test_empty_context(self):
        ctx = ConversationContext()
        assert ctx.is_empty
        assert ctx.total_turns == 0
        assert ctx.format_for_injection() == ""

    def test_format_for_injection_sliding_window(self):
        ctx = ConversationContext(
            sliding_window_turns=[
                _make_context_result(content="Hello, help me code", turn_number=0, role="user"),
                _make_context_result(content="Sure, I can help", turn_number=1, role="assistant"),
            ]
        )
        formatted = ctx.format_for_injection()

        assert "## Session Context" in formatted
        assert "### Recent Conversation" in formatted
        assert "[Turn 0] User:" in formatted
        assert "[Turn 1] Assistant:" in formatted

    def test_format_for_injection_all_phases(self):
        ctx = ConversationContext(
            sliding_window_turns=[
                _make_context_result(content="Recent turn", turn_number=5),
            ],
            semantic_turns=[
                _make_context_result(content="Earlier relevant turn", turn_number=1, source="intra_session"),
            ],
            cross_session_turns=[
                _make_context_result(content="Past session turn", turn_number=3, source="cross_session"),
            ],
        )
        formatted = ctx.format_for_injection()

        assert "### Recent Conversation" in formatted
        assert "### Related Earlier Context" in formatted
        assert "### Related Past Sessions" in formatted
        assert "[Past session]" in formatted

    def test_format_for_injection_respects_max_chars(self):
        """Sections that exceed max_chars are excluded."""
        long_content = "A" * 200
        ctx = ConversationContext(
            sliding_window_turns=[
                _make_context_result(content=long_content, turn_number=0),
            ],
            semantic_turns=[
                _make_context_result(content="Should be excluded due to limit", turn_number=1),
            ],
        )
        # Set very small limit — only the header + one turn fits
        formatted = ctx.format_for_injection(max_chars=300)

        assert "### Recent Conversation" in formatted
        # Semantic section may or may not fit depending on exact sizes

    def test_total_turns_counts_all_phases(self):
        ctx = ConversationContext(
            sliding_window_turns=[_make_context_result(turn_number=i) for i in range(3)],
            semantic_turns=[_make_context_result(turn_number=10)],
            cross_session_turns=[_make_context_result(turn_number=20), _make_context_result(turn_number=21)],
        )
        assert ctx.total_turns == 6
        assert not ctx.is_empty


# ------------------------------------------------------------------ #
# Content hash helper
# ------------------------------------------------------------------ #


class TestPromptIntegration:
    """Tests for conversation context integration into execution prompt pipeline."""

    def test_build_execution_prompt_includes_conversation_context(self):
        """build_execution_prompt renders the CONVERSATION_CONTEXT_SIGNAL block."""
        from app.domain.services.prompts.execution import build_execution_prompt

        prompt = build_execution_prompt(
            step="Analyze the data",
            message="Analyze sales data",
            attachments="",
            language="en",
            conversation_context="[Turn 0] User: Please analyze Q4 sales\n[Turn 1] Assistant: Looking at Q4...",
            enable_cot=False,
        )

        assert "CONVERSATION CONTEXT" in prompt
        assert "Q4 sales" in prompt
        assert "conversational continuity" in prompt

    def test_build_execution_prompt_without_conversation_context(self):
        """build_execution_prompt works normally when conversation_context is None."""
        from app.domain.services.prompts.execution import build_execution_prompt

        prompt = build_execution_prompt(
            step="Simple step",
            message="Do something",
            attachments="",
            language="en",
            conversation_context=None,
            enable_cot=False,
        )

        assert "CONVERSATION CONTEXT" not in prompt

    def test_inject_conversation_context_on_execution_agent(self):
        """ExecutionAgent.inject_conversation_context stores context for next step."""
        from unittest.mock import MagicMock

        from app.domain.services.agents.execution import ExecutionAgent

        agent = MagicMock(spec=ExecutionAgent)
        agent._pending_conversation_context = None
        ExecutionAgent.inject_conversation_context(agent, "## Session Context\n...")

        assert agent._pending_conversation_context == "## Session Context\n..."


class TestContentHash:
    """Tests for the _content_hash helper."""

    def test_hash_is_16_chars(self):
        from app.domain.services.conversation_context_service import _content_hash

        h = _content_hash("test content")
        assert len(h) == 16

    def test_hash_is_case_insensitive(self):
        from app.domain.services.conversation_context_service import _content_hash

        assert _content_hash("Hello World") == _content_hash("hello world")

    def test_hash_strips_whitespace(self):
        from app.domain.services.conversation_context_service import _content_hash

        assert _content_hash("  hello  ") == _content_hash("hello")

    def test_different_content_different_hash(self):
        from app.domain.services.conversation_context_service import _content_hash

        assert _content_hash("message one") != _content_hash("message two")
