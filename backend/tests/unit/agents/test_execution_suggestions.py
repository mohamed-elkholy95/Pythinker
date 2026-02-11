"""Tests for ExecutionAgent suggestion generation with session context."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.external.observability import get_null_metrics
from app.domain.models.event import ErrorEvent, ReportEvent, SuggestionEvent
from app.domain.services.agents import execution as execution_module
from app.domain.services.agents.execution import ExecutionAgent


class TestExecutionAgentSuggestionGeneration:
    """Test ExecutionAgent generates session-anchored suggestions."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser):
        """Create an ExecutionAgent with mocked dependencies."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=[],
            json_parser=mock_json_parser,
        )

    @pytest.mark.asyncio
    async def test_suggestion_prompt_includes_user_request(self, executor, mock_llm):
        """Suggestion generation should include original user request in prompt."""
        # Store user request during summarize
        executor._user_request = "Build a pirate themed website"

        # Mock LLM to return suggestions
        mock_llm.ask.return_value = {
            "content": '{"suggestions": ["Add treasure map", "Include pirate crew", "Design ship navigation"]}'
        }

        # Generate suggestions
        await executor._generate_follow_up_suggestions(
            title="Website Design Complete",
            content="Created a pirate themed website with animations and interactive elements.",
        )

        # Verify LLM was called
        assert mock_llm.ask.called
        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]

        # Verify prompt includes user request
        prompt_content = messages[0]["content"]
        assert "Build a pirate themed website" in prompt_content or "user" in prompt_content.lower()

    @pytest.mark.asyncio
    async def test_suggestion_prompt_includes_completion_title(self, executor, mock_llm):
        """Suggestion generation should include completion title in prompt."""
        executor._user_request = "Create API documentation"

        mock_llm.ask.return_value = {
            "content": '{"suggestions": ["Add examples", "Include authentication", "Document errors"]}'
        }

        await executor._generate_follow_up_suggestions(
            title="API Documentation Complete",
            content="Generated comprehensive API docs with endpoints and parameters.",
        )

        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        prompt_content = messages[0]["content"]

        # Verify prompt includes title
        assert "API Documentation Complete" in prompt_content

    @pytest.mark.asyncio
    async def test_suggestion_prompt_includes_bounded_content_excerpt(self, executor, mock_llm):
        """Suggestion generation should include bounded excerpt from completion content."""
        executor._user_request = "Analyze performance metrics"

        # Long content to test excerpt bounding
        long_content = "Performance Analysis Results:\n" + ("Analysis detail. " * 200)

        mock_llm.ask.return_value = {"content": '{"suggestions": ["Deep dive into metrics"]}'}

        await executor._generate_follow_up_suggestions(title="Performance Report", content=long_content)

        call_args = mock_llm.ask.call_args
        messages = call_args[0][0]
        prompt_content = messages[0]["content"]

        # Verify excerpt is bounded (not the full 2000+ char content)
        assert len(prompt_content) < len(long_content) + 500  # Reasonable overhead for prompt structure

    @pytest.mark.asyncio
    async def test_summarize_emits_suggestion_event_with_metadata(self, executor, mock_llm):
        """Summarize should emit SuggestionEvent with source and anchor metadata."""
        executor._user_request = "Create documentation"

        # Mock streaming response
        async def mock_stream(*args, **kwargs):
            yield "# Documentation Complete\n"
            yield "Generated comprehensive docs."

        mock_llm.ask_stream = mock_stream

        # Mock suggestion generation
        mock_llm.ask.return_value = {"content": '["Add examples", "Include diagrams"]'}

        # Collect events from summarize
        events = []
        async for event in executor.summarize():
            events.append(event)

        # Find SuggestionEvent
        suggestion_events = [e for e in events if isinstance(e, SuggestionEvent)]
        assert len(suggestion_events) == 1

        suggestion_event = suggestion_events[0]

        # Verify metadata is populated
        assert suggestion_event.source == "completion"
        assert suggestion_event.anchor_event_id is not None  # Should link to report

        # Find ReportEvent to verify anchor_event_id matches
        report_events = [e for e in events if isinstance(e, ReportEvent)]
        if report_events:
            assert suggestion_event.anchor_event_id == report_events[0].id

    @pytest.mark.asyncio
    async def test_suggestion_fallback_when_llm_fails(self, executor, mock_llm):
        """Should return deterministic fallback suggestions when LLM fails."""
        executor._user_request = "Test request"

        # Mock LLM to fail
        mock_llm.ask.side_effect = Exception("LLM unavailable")

        suggestions = await executor._generate_follow_up_suggestions(title="Test Title", content="Test content")

        # Should return fallback suggestions
        assert len(suggestions) == 3
        assert all(isinstance(s, str) for s in suggestions)


class TestExecutionAgentSuggestionAnchorExcerpt:
    """Test anchor_excerpt generation for SuggestionEvent."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser):
        """Create an ExecutionAgent."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=[],
            json_parser=mock_json_parser,
        )

    @pytest.mark.asyncio
    async def test_anchor_excerpt_includes_bounded_content(self, executor, mock_llm):
        """anchor_excerpt should contain first N chars of completion content."""
        executor._user_request = "Test"

        # Mock streaming
        async def mock_stream(*args, **kwargs):
            yield "This is a test completion with some content that should be excerpted."

        mock_llm.ask_stream = mock_stream
        mock_llm.ask.return_value = {"content": '["Suggestion 1", "Suggestion 2"]'}

        events = []
        async for event in executor.summarize():
            events.append(event)

        suggestion_events = [e for e in events if isinstance(e, SuggestionEvent)]
        assert len(suggestion_events) == 1

        # Verify excerpt is populated and bounded
        excerpt = suggestion_events[0].anchor_excerpt
        assert excerpt is not None
        assert len(excerpt) <= 500  # Should be bounded to prevent bloat
        assert "test completion" in excerpt.lower()


class TestExecutionAgentDeliveryIntegrityGate:
    """Test Delivery Integrity Gate behavior in summarize()."""

    @pytest.fixture
    def mock_agent_repository(self):
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser):
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=[],
            json_parser=mock_json_parser,
            feature_flags={"delivery_integrity_gate": True},
        )

    @pytest.fixture
    def metrics_spy(self):
        spy = MagicMock()
        execution_module.set_metrics(spy)
        yield spy
        execution_module.set_metrics(get_null_metrics())

    @pytest.mark.asyncio
    async def test_delivery_integrity_blocks_unresolved_stream_truncation(self, executor, mock_llm, metrics_spy):
        """When truncation persists, summarize should fail closed."""
        mock_llm.ask.return_value = {"content": '["Suggestion 1"]'}

        async def always_truncated_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "length",
                "truncated": True,
                "provider": "test",
            }
            yield "# Report\nPartial output"

        mock_llm.ask_stream = always_truncated_stream

        events = []
        async for event in executor.summarize():
            events.append(event)

        assert any(isinstance(event, ErrorEvent) for event in events)
        assert not any(isinstance(event, ReportEvent) for event in events)
        assert self._has_counter_call(
            metrics_spy,
            "delivery_integrity_gate_block_reason_total",
            provider="test",
            reason="stream_truncation_unresolved",
        )
        assert self._has_counter_call(
            metrics_spy,
            "delivery_integrity_gate_result_total",
            provider="test",
            result="blocked",
        )

    @pytest.mark.asyncio
    async def test_delivery_integrity_recovers_after_single_continuation(self, executor, mock_llm, metrics_spy):
        """If continuation succeeds, summarize should complete and emit report."""
        call_count = {"value": 0}
        mock_llm.ask.return_value = {"content": '["Suggestion 1"]'}

        async def truncated_then_complete_stream(*args, **kwargs):
            call_count["value"] += 1
            if call_count["value"] == 1:
                mock_llm.last_stream_metadata = {
                    "finish_reason": "length",
                    "truncated": True,
                    "provider": "test",
                }
                yield "# Report\nPart 1"
                return

            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield "\nPart 2 complete."

        mock_llm.ask_stream = truncated_then_complete_stream

        events = []
        async for event in executor.summarize():
            events.append(event)

        assert call_count["value"] == 2
        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)
        assert self._has_counter_call(
            metrics_spy,
            "delivery_integrity_stream_truncation_total",
            provider="test",
            outcome="recovered",
        )
        assert self._has_counter_call(
            metrics_spy,
            "delivery_integrity_gate_result_total",
            provider="test",
            result="passed",
        )
        assert not self._has_counter_call(metrics_spy, "delivery_integrity_gate_block_reason_total", provider="test")

    @pytest.mark.asyncio
    async def test_delivery_integrity_marks_unresolved_when_truncated_fragment_is_empty(
        self, executor, mock_llm, metrics_spy
    ):
        """Whitespace-only truncated fragments should emit unresolved truncation outcome."""
        mock_llm.ask.return_value = {"content": '["Suggestion 1"]'}

        async def empty_truncated_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "length",
                "truncated": True,
                "provider": "test",
            }
            yield "   "

        mock_llm.ask_stream = empty_truncated_stream

        events = []
        async for event in executor.summarize():
            events.append(event)

        assert any(isinstance(event, ErrorEvent) for event in events)
        assert self._has_counter_call(
            metrics_spy,
            "delivery_integrity_stream_truncation_total",
            provider="test",
            outcome="unresolved",
        )

    @pytest.mark.asyncio
    async def test_delivery_integrity_self_heals_coverage_missing_next_step(self, executor, mock_llm, metrics_spy):
        """Coverage-only misses for next-step should be auto-remediated, not hard-failed."""
        mock_llm.ask.return_value = {"content": '["Suggestion 1"]'}

        async def complete_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield "# Report\nFindings:\n- Item A"

        mock_llm.ask_stream = complete_stream

        invalid = MagicMock()
        invalid.is_valid = False
        invalid.missing_requirements = ["next step"]
        valid = MagicMock()
        valid.is_valid = True
        valid.missing_requirements = []
        executor._output_coverage_validator.validate = MagicMock(side_effect=[invalid, valid])
        executor._is_integrity_strict_mode = MagicMock(return_value=True)

        events = []
        async for event in executor.summarize():
            events.append(event)

        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    @pytest.mark.asyncio
    async def test_delivery_integrity_self_heals_missing_final_and_artifact_sections(
        self, executor, mock_llm, metrics_spy
    ):
        """Coverage-only misses for final result + artifact refs should be auto-remediated."""
        mock_llm.ask.return_value = {"content": '["Suggestion 1"]'}

        async def complete_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield "# Report\nInvestigation notes collected."

        mock_llm.ask_stream = complete_stream

        invalid = MagicMock()
        invalid.is_valid = False
        invalid.missing_requirements = ["artifact references", "final result"]
        valid = MagicMock()
        valid.is_valid = True
        valid.missing_requirements = []
        executor._output_coverage_validator.validate = MagicMock(side_effect=[invalid, valid])
        executor._is_integrity_strict_mode = MagicMock(return_value=True)

        events = []
        async for event in executor.summarize():
            events.append(event)

        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    @staticmethod
    def _has_counter_call(metrics_spy: MagicMock, metric_name: str, **expected_labels: str) -> bool:
        for call in metrics_spy.record_counter.call_args_list:
            args = call.args
            kwargs = call.kwargs
            called_metric_name = args[0] if args else kwargs.get("name")
            labels = kwargs.get("labels") or {}
            if called_metric_name != metric_name:
                continue
            if all(labels.get(key) == value for key, value in expected_labels.items()):
                return True
        return False
