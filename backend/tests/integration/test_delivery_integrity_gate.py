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
    async def test_completed_plan_summary_downgrades_when_summary_and_pretrim_report_both_fail_grounding(
        self, executor, mock_llm
    ):
        """Telegram final delivery should downgrade (not block) when all steps completed.

        Even when neither summary nor draft passes grounding, the user deserves
        to see their completed work.  The delivery gate downgrades to a warning
        and delivers the report — this applies equally to Telegram and web UI.
        """
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

        # With all steps completed, the gate downgrades to warning and delivers
        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    @pytest.mark.asyncio
    async def test_completed_plan_summary_downgrades_hallucination_on_telegram(self, executor, mock_llm):
        """Hallucination ratio critical should downgrade to warning when all steps completed.

        The output_verifier already appends a disclaimer to the content.
        Blocking completed research entirely is worse UX than delivering
        with a quality notice — the user spent minutes waiting for results.
        """
        weak_summary = (
            "# Final Report\n\n## Findings\nSynthesized content beyond source snippets."
            "\n\n> **Note:** Some information in this response "
            "could not be fully verified against available sources."
        )

        executor._user_request = "Provide a grounded final report."
        executor._extract_report_from_file_write_memory = MagicMock(return_value=None)
        executor._needs_verification = MagicMock(return_value=False)
        executor._can_auto_repair_delivery_integrity = MagicMock(return_value=False)
        executor._run_delivery_integrity_gate = MagicMock(return_value=(False, ["hallucination_ratio_critical"]))
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

        # Downgraded: user receives their completed research with disclaimer
        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    @pytest.mark.asyncio
    async def test_structural_failure_still_blocks_even_when_all_steps_completed(self, executor, mock_llm):
        """Stream truncation (structural corruption) must always block — content is incomplete."""
        weak_summary = "# Final Report\n\n## Findings\nPartial content"

        executor._user_request = "Provide a grounded final report."
        executor._extract_report_from_file_write_memory = MagicMock(return_value=None)
        executor._needs_verification = MagicMock(return_value=False)
        executor._can_auto_repair_delivery_integrity = MagicMock(return_value=False)
        executor._run_delivery_integrity_gate = MagicMock(
            return_value=(False, ["stream_truncation_unresolved"])
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

        # Structural failure: never downgradable
        assert any(isinstance(event, ErrorEvent) for event in events)
        assert not any(isinstance(event, ReportEvent) for event in events)

    @pytest.mark.asyncio
    async def test_stream_error_salvages_accumulated_content_as_partial_report(self, executor, mock_llm):
        """When streaming fails mid-way, accumulated content should be delivered as partial report."""
        executor._user_request = "Research the topic in detail."
        mock_llm.ask.return_value = {"content": '["Follow-up question?"]'}

        accumulated_content = (
            "# Research Report\n\n"
            "## Findings\n"
            "The analysis revealed several key insights about the topic "
            "including market trends, competitive dynamics, and growth projections.\n\n"
            "## Details\n"
            "Detailed analysis with supporting evidence from multiple sources "
            "demonstrates that the sector has experienced consistent 15% year-over-year "
            "growth driven by technological innovation and changing consumer preferences."
        )

        async def stream_then_crash(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield accumulated_content
            raise ConnectionError()  # Simulates provider disconnect (empty str(e))

        mock_llm.ask_stream = stream_then_crash

        events = [event async for event in executor.summarize()]

        # Should salvage as partial report, NOT emit ErrorEvent
        report_events = [e for e in events if isinstance(e, ReportEvent)]
        assert len(report_events) == 1
        assert "[Partial]" in report_events[0].title
        assert "Research Report" in report_events[0].content
        assert not any(isinstance(e, ErrorEvent) for e in events)

    @pytest.mark.asyncio
    async def test_stream_error_with_no_content_emits_error_event(self, executor, mock_llm):
        """When streaming fails before producing content, ErrorEvent should be emitted."""
        executor._user_request = "Research the topic."
        mock_llm.ask.return_value = {"content": '["Follow-up question?"]'}

        async def immediate_crash(*args, **kwargs):
            mock_llm.last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "test",
            }
            raise TimeoutError()  # Crashes before yielding anything

            yield ""  # Make this an async generator

        mock_llm.ask_stream = immediate_crash

        events = [event async for event in executor.summarize()]

        # No content to salvage → ErrorEvent with diagnostic label
        assert any(isinstance(e, ErrorEvent) for e in events)
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert "TimeoutError" in error_events[0].error

    @pytest.mark.asyncio
    async def test_incomplete_plan_summary_blocks_on_telegram(self, executor, mock_llm):
        """Telegram final delivery should block when steps did NOT all complete."""
        weak_summary = "# Final Report\n\n## Findings\nIncomplete work.\n\n## Conclusion\nMissing steps."

        executor._user_request = "Provide a grounded final report."
        executor._extract_report_from_file_write_memory = MagicMock(return_value=None)
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

        # all_steps_completed=False — should block
        events = [event async for event in executor.summarize(all_steps_completed=False)]

        assert any(isinstance(event, ErrorEvent) for event in events)
        assert not any(isinstance(event, ReportEvent) for event in events)
