"""Integration tests for delivery integrity behavior in summarization."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import ErrorEvent, ReportEvent
from app.domain.services.agents.execution import ExecutionAgent


class TestDeliveryIntegrityGateIntegration:
    """End-to-end summarization checks around stream truncation handling."""

    @pytest.fixture
    def mock_agent_repository(self):
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        return ExecutionAgent(
            agent_id="integration-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
            feature_flags={"delivery_integrity_gate": True},
        )

    @pytest.mark.asyncio
    async def test_completed_plan_summary_recovers_stream_truncation(self, executor, mock_llm, plan_factory):
        """A completed plan should still produce a report after one continuation retry."""
        plan = plan_factory(steps=[{"id": "1", "description": "Collect findings"}])
        plan.steps[0].status = plan.steps[0].status.COMPLETED
        plan.steps[0].success = True
        plan.steps[0].result = "Findings collected"

        # Prime context to resemble post-execution summarize stage.
        executor._user_request = "Provide a detailed report of collected findings"
        executor._context_manager.add_key_fact("Step 1 completed with actionable findings")

        call_count = {"value": 0}
        mock_llm.ask.return_value = {"content": '["Follow-up question?"]'}

        async def truncated_then_complete_stream(*args, **kwargs):
            call_count["value"] += 1
            if call_count["value"] == 1:
                mock_llm.last_stream_metadata = {
                    "finish_reason": "length",
                    "truncated": True,
                    "provider": "test",
                }
                yield "# Final Report\nSection 1 content"
                return

            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield "\nSection 2 content with conclusion."

        mock_llm.ask_stream = truncated_then_complete_stream

        events = [event async for event in executor.summarize()]

        assert call_count["value"] == 2
        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    @pytest.mark.asyncio
    async def test_completed_plan_summary_blocks_when_truncation_never_resolves(self, executor, mock_llm, plan_factory):
        """If truncation persists past retries, delivery integrity blocks final report delivery."""
        plan = plan_factory(steps=[{"id": "1", "description": "Collect findings"}])
        plan.steps[0].status = plan.steps[0].status.COMPLETED
        plan.steps[0].success = True
        plan.steps[0].result = "Findings collected"

        executor._user_request = "Provide a detailed report of collected findings"
        mock_llm.ask.return_value = {"content": '["Follow-up question?"]'}

        async def always_truncated_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "length",
                "truncated": True,
                "provider": "test",
            }
            yield "# Final Report\nPartial content only"

        mock_llm.ask_stream = always_truncated_stream

        events = [event async for event in executor.summarize()]

        assert any(isinstance(event, ErrorEvent) for event in events)
        assert not any(isinstance(event, ReportEvent) for event in events)
