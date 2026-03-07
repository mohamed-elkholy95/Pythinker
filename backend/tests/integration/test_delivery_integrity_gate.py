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
        executor = ExecutionAgent(
            agent_id="integration-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
            feature_flags={"delivery_integrity_gate": True},
        )
        executor.set_delivery_channel("telegram")
        return executor

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

    @pytest.mark.asyncio
    async def test_completed_plan_summary_uses_pretrim_report_when_summary_drops_references(self, executor, mock_llm):
        """Weak report-shaped summaries should fall back to the grounded pre-trim draft."""
        weak_summary = (
            "# Final Report\n\n"
            "## Findings\n"
            "The summary omitted references but still looks like a polished report.\n\n"
            "## Conclusion\n"
            "Delivery should not use this version."
        )
        grounded_pretrim = (
            "# Final Report\n\n"
            "## Findings\n"
            "Grounded finding tied to a source [1].\n\n"
            "## References\n"
            "[1] https://example.com/source"
        )
        gate_inputs: list[str] = []

        executor._user_request = "Provide a grounded final report."
        executor._extract_report_from_file_write_memory = MagicMock(return_value=grounded_pretrim)
        executor._needs_verification = MagicMock(return_value=False)
        executor._can_auto_repair_delivery_integrity = MagicMock(return_value=False)

        def gate_side_effect(*args, **kwargs):
            content = kwargs.get("content", args[0] if args else "")
            gate_inputs.append(content)
            if content == grounded_pretrim:
                return True, []
            return False, ["coverage_missing:artifact references"]

        executor._run_delivery_integrity_gate = MagicMock(side_effect=gate_side_effect)
        mock_llm.ask.return_value = {"content": '["Follow-up question?"]'}

        async def weak_summary_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield weak_summary

        mock_llm.ask_stream = weak_summary_stream

        events = [event async for event in executor.summarize(all_steps_completed=True)]

        report = next(event for event in events if isinstance(event, ReportEvent))
        assert report.content == grounded_pretrim
        assert any(content == grounded_pretrim for content in gate_inputs)
        assert report.content != weak_summary

    @pytest.mark.asyncio
    async def test_completed_plan_summary_blocks_when_summary_and_pretrim_report_both_fail_grounding(
        self, executor, mock_llm
    ):
        """Telegram final delivery should fail closed when neither summary nor draft is grounded."""
        weak_summary = (
            "# Final Report\n\n"
            "## Findings\n"
            "This summary still lacks the required evidence trail.\n\n"
            "## Conclusion\n"
            "Do not deliver this."
        )
        weak_pretrim = (
            "# Final Report\n\n"
            "## Findings\n"
            "This cached draft is also missing citations and references.\n\n"
            "## Conclusion\n"
            "Still not grounded."
        )

        executor._user_request = "Provide a grounded final report."
        executor._extract_report_from_file_write_memory = MagicMock(return_value=weak_pretrim)
        executor._needs_verification = MagicMock(return_value=False)
        executor._can_auto_repair_delivery_integrity = MagicMock(return_value=False)
        executor._run_delivery_integrity_gate = MagicMock(
            return_value=(False, ["coverage_missing:artifact references"])
        )
        mock_llm.ask.return_value = {"content": '["Follow-up question?"]'}

        async def weak_summary_stream(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield weak_summary

        mock_llm.ask_stream = weak_summary_stream

        events = [event async for event in executor.summarize(all_steps_completed=True)]

        assert any(isinstance(event, ErrorEvent) for event in events)
        assert not any(isinstance(event, ReportEvent) for event in events)
