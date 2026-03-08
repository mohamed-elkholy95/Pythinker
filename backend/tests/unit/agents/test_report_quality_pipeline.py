"""Tests for the report quality pipeline fixes.

Covers:
- Trailing meta-commentary stripping in ResponseGenerator.clean_report_content()
- has_truncation_artifacts() detects […] markers
- output_verifier uses disclaimer (not span redaction) for 10-25% hallucination ratio
- execution.py prepends truncation notice header when truncation_exhausted or artifacts
- CancelledError in summarize() emits partial ReportEvent then re-raises
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.agents.response_generator import ResponseGenerator


def _make_rg() -> ResponseGenerator:
    """Minimal ResponseGenerator for unit testing its cleaning/detection methods."""
    llm = MagicMock()
    memory = MagicMock()
    memory.get_messages.return_value = []
    source_tracker = MagicMock()
    source_tracker.get_collected_sources.return_value = []
    metrics = MagicMock()
    return ResponseGenerator(
        llm=llm,
        memory=memory,
        source_tracker=source_tracker,
        metrics=metrics,
        resolve_feature_flags_fn=lambda: {"delivery_integrity_gate": True},
    )


class TestStripTrailingMetaCommentary:
    def test_strips_i_see_the_issue(self):
        rg = _make_rg()
        content = "# Report\n\nSome content here.\n\nI see the issue — let me save this now."
        result = rg.strip_trailing_meta_commentary(content)
        assert result == "# Report\n\nSome content here."

    def test_strips_let_me_save(self):
        rg = _make_rg()
        content = "# Analysis\n\nFindings here.\n\nLet me save this file to disk."
        result = rg.strip_trailing_meta_commentary(content)
        assert result == "# Analysis\n\nFindings here."

    def test_strips_writing_report_to(self):
        rg = _make_rg()
        content = "# My Report\n\nContent.\n\nWriting the report to /tmp/output.md"
        result = rg.strip_trailing_meta_commentary(content)
        assert result == "# My Report\n\nContent."

    def test_strips_saving_to_file(self):
        rg = _make_rg()
        content = "# Summary\n\nResults.\n\nSaving to file report.md\nAdditional line here."
        result = rg.strip_trailing_meta_commentary(content)
        assert result == "# Summary\n\nResults."

    def test_strips_output_was_cut(self):
        rg = _make_rg()
        content = "# Results\n\nData here.\n\nNote: The model output was cut short."
        result = rg.strip_trailing_meta_commentary(content)
        assert result == "# Results\n\nData here."

    def test_strips_generation_was_interrupted(self):
        rg = _make_rg()
        content = "# Report\n\nFindings.\n\nThe generation was interrupted by token limit."
        result = rg.strip_trailing_meta_commentary(content)
        assert result == "# Report\n\nFindings."

    def test_no_change_when_no_trailing_meta(self):
        rg = _make_rg()
        content = "# Report\n\nThis is a clean report with no trailing commentary."
        result = rg.strip_trailing_meta_commentary(content)
        assert result == content

    def test_no_change_on_empty_string(self):
        rg = _make_rg()
        assert rg.strip_trailing_meta_commentary("") == ""

    def test_meta_in_middle_not_stripped(self):
        """Meta-commentary followed by a heading must NOT be stripped.
        The pattern only removes lines at the very end with no heading after them."""
        rg = _make_rg()
        content = "# Report\n\nI see the issue here with performance.\n\n## Findings\n\nHere are the detailed findings."
        result = rg.strip_trailing_meta_commentary(content)
        assert "## Findings" in result
        assert "Here are the detailed findings." in result

    def test_clean_report_content_strips_trailing_meta_as_last_step(self):
        """clean_report_content() must invoke strip_trailing_meta_commentary."""
        rg = _make_rg()
        content = "# Report\n\nMain body.\n\nLet me now save this content."
        result = rg.clean_report_content(content)
        assert "Let me now save" not in result
        assert "Main body." in result


class TestHasTruncationArtifacts:
    def test_detects_ellipsis_marker(self):
        rg = _make_rg()
        assert rg.has_truncation_artifacts("Some content […] more content") is True

    def test_detects_three_dots_bracket(self):
        rg = _make_rg()
        assert rg.has_truncation_artifacts("Text [...] rest") is True

    def test_returns_false_for_clean_content(self):
        rg = _make_rg()
        assert rg.has_truncation_artifacts("Clean report with no artifacts.") is False

    def test_returns_false_for_empty_string(self):
        rg = _make_rg()
        assert rg.has_truncation_artifacts("") is False

    def test_detects_artifact_in_table_cell(self):
        rg = _make_rg()
        table = "| Column A | Column B |\n|---|---|\n| Value | […] |"
        assert rg.has_truncation_artifacts(table) is True

    def test_detects_artifact_in_mermaid(self):
        rg = _make_rg()
        mermaid = "```mermaid\ngraph TD\n  A --> […]\n```"
        assert rg.has_truncation_artifacts(mermaid) is True


class TestTelegramDeliveryIntegrityGate:
    def test_delivery_integrity_gate_blocks_report_issues_for_telegram_only(self):
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        rg = _make_rg()
        coverage_result = SimpleNamespace(is_valid=False, missing_requirements=["artifact references"])
        content = "# Final Report\n\n## Findings\nGrounded claim [1]."
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        passed, issues = rg.run_delivery_integrity_gate(
            content=content,
            response_policy=policy,
            coverage_result=coverage_result,
            stream_metadata={"provider": "test"},
            truncation_exhausted=False,
            additional_warnings=["hallucination_verification_skipped"],
            delivery_channel="telegram",
        )

        assert passed is False
        assert "coverage_missing:artifact references" in issues
        assert "missing_references_section" in issues
        assert "hallucination_verification_skipped" not in issues

    def test_delivery_integrity_gate_keeps_same_report_issues_as_warnings_for_web(self):
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        rg = _make_rg()
        coverage_result = SimpleNamespace(is_valid=False, missing_requirements=["artifact references"])
        content = "# Final Report\n\n## Findings\nGrounded claim [1]."
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        passed, issues = rg.run_delivery_integrity_gate(
            content=content,
            response_policy=policy,
            coverage_result=coverage_result,
            stream_metadata={"provider": "test"},
            truncation_exhausted=False,
            additional_warnings=["hallucination_verification_skipped"],
            delivery_channel="web",
        )

        assert passed is True
        assert issues == []


def _make_output_verifier(*, lettuce_enabled: bool = True):
    """Build a minimal OutputVerifier with all dependencies mocked."""
    from app.domain.services.agents.output_verifier import OutputVerifier

    mock_source_tracker = MagicMock()
    mock_source_tracker._collected_sources = []

    return OutputVerifier(
        llm=MagicMock(),
        critic=MagicMock(),
        cove=MagicMock(),
        context_manager=MagicMock(),
        source_tracker=mock_source_tracker,
        metrics=MagicMock(),
        resolve_feature_flags_fn=lambda: {"lettuce_verification": True},
        lettuce_enabled=lettuce_enabled,
        cove_enabled=False,
    )


def _make_lettuce_result(ratio: float, span_count: int = 2, skipped: bool = False):
    result = MagicMock()
    result.hallucination_ratio = ratio
    result.has_hallucinations = ratio > 0
    result.hallucinated_spans = [MagicMock() for _ in range(span_count)]
    result.skipped = skipped
    result.confidence_score = 0.9
    result.get_summary.return_value = f"{ratio * 100:.1f}% hallucination"
    return result


class TestHallucinationDisclaimerNotRedaction:
    """The 5-15% hallucination ratio branch must append a disclaimer
    and must NOT call redact_hallucinations (which produces […] markers)."""

    @pytest.mark.asyncio
    async def test_moderate_ratio_appends_disclaimer(self):
        ov = _make_output_verifier()
        content = "# Research Report\n\nSome findings here with specific facts and numbers."
        lettuce_result = _make_lettuce_result(ratio=0.15, span_count=2)
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = lettuce_result

        with patch(
            "app.domain.services.agents.lettuce_verifier.get_lettuce_verifier",
            return_value=mock_verifier,
        ):
            result = await ov.verify_hallucination(content, "research query")

        assert result is not None
        assert "Reliability Notice" in result.content
        assert "15.0% unverified" in result.content
        assert "hallucination_ratio_moderate" in result.warnings
        assert "[…]" not in result.content
        assert "[...]" not in result.content

    @pytest.mark.asyncio
    async def test_moderate_ratio_does_not_call_redact_hallucinations(self):
        ov = _make_output_verifier()
        content = "# Report\n\nSome findings."
        lettuce_result = _make_lettuce_result(ratio=0.12, span_count=1)
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = lettuce_result
        mock_verifier.redact_hallucinations = MagicMock(return_value="should not be called")

        with patch(
            "app.domain.services.agents.lettuce_verifier.get_lettuce_verifier",
            return_value=mock_verifier,
        ):
            await ov.verify_hallucination(content, "query")

        mock_verifier.redact_hallucinations.assert_not_called()

    @pytest.mark.asyncio
    async def test_ratio_above_block_threshold_uses_critical_path(self):
        """Ratios above the 15% critical threshold must block delivery."""
        ov = _make_output_verifier()
        content = "# Report\n\nContent."
        lettuce_result = _make_lettuce_result(ratio=0.18, span_count=1)
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = lettuce_result

        with patch(
            "app.domain.services.agents.lettuce_verifier.get_lettuce_verifier",
            return_value=mock_verifier,
        ):
            result = await ov.verify_hallucination(content, "query")

        assert "hallucination_ratio_critical" in result.blocking_issues
        assert "could not be fully verified" in result.content

    @pytest.mark.asyncio
    async def test_high_ratio_above_30_uses_critical_path(self):
        """Ratio > 30% triggers blocking — likely genuine hallucination."""
        ov = _make_output_verifier()
        content = "# Report\n\nContent."
        lettuce_result = _make_lettuce_result(ratio=0.35, span_count=5)
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = lettuce_result

        with patch(
            "app.domain.services.agents.lettuce_verifier.get_lettuce_verifier",
            return_value=mock_verifier,
        ):
            result = await ov.verify_hallucination(content, "query")

        assert result.blocking_issues
        assert "hallucination_ratio_critical" in result.blocking_issues


class TestSourceGroundingContext:
    def test_build_source_context_includes_browser_snippets(self):
        ov = _make_output_verifier()
        ov._source_tracker._collected_sources = [
            SimpleNamespace(
                title="Example Project",
                url="https://example.com/project",
                snippet="Browser-fetched body text describing repository behavior and features.",
            )
        ]

        assert ov.build_source_context() == [
            "Example Project — https://example.com/project: Browser-fetched body text describing repository behavior and features."
        ]

    def test_browser_source_tracker_extracts_text_snippet_from_content(self):
        from app.domain.services.agents.source_tracker import SourceTracker

        tracker = SourceTracker()
        event = MagicMock()
        event.function_args = {"url": "https://example.com/project"}
        event.tool_content = SimpleNamespace(
            content=(
                "<html><title>Example Project</title><body>"
                "<h1>Example Project</h1><p>Repository overview with grounded browser text.</p>"
                "</body></html>"
            )
        )

        tracker._extract_browser_source(event, datetime.now(UTC))

        source = tracker.get_collected_sources()[0]
        assert source.title == "Example Project"
        assert source.snippet is not None
        assert "Repository overview with grounded browser text." in source.snippet


class TestTruncationNoticeHeader:
    def test_has_truncation_artifacts_delegate(self):
        """ExecutionAgent._has_truncation_artifacts must delegate to ResponseGenerator."""
        from app.domain.services.agents.execution import ExecutionAgent

        agent = ExecutionAgent.__new__(ExecutionAgent)
        mock_rg = MagicMock()
        mock_rg.has_truncation_artifacts.return_value = True
        agent._response_generator = mock_rg

        result = agent._has_truncation_artifacts("some […] content")

        mock_rg.has_truncation_artifacts.assert_called_once_with("some […] content")
        assert result is True

    def test_has_truncation_artifacts_false_when_clean(self):
        from app.domain.services.agents.execution import ExecutionAgent

        agent = ExecutionAgent.__new__(ExecutionAgent)
        mock_rg = MagicMock()
        mock_rg.has_truncation_artifacts.return_value = False
        agent._response_generator = mock_rg

        result = agent._has_truncation_artifacts("clean content")
        assert result is False


def _make_execution_agent_for_summarize():
    """Build a minimal ExecutionAgent suitable for summarize() unit tests."""
    from app.domain.services.agents.execution import ExecutionAgent

    agent = ExecutionAgent.__new__(ExecutionAgent)
    agent._user_request = "What are the top AI trends?"
    agent._research_depth = "STANDARD"
    agent._pre_trim_report_cache = None
    agent._collected_sources = False
    agent._response_policy = None
    agent._delivery_channel = None
    agent._artifact_references = []

    llm = MagicMock()
    rg = ResponseGenerator(
        llm=llm,
        memory=MagicMock(get_messages=MagicMock(return_value=[])),
        source_tracker=MagicMock(get_collected_sources=MagicMock(return_value=[])),
        metrics=MagicMock(),
        resolve_feature_flags_fn=lambda: {"delivery_integrity_gate": False},
    )
    agent._response_generator = rg
    agent.llm = llm
    agent.memory = MagicMock(get_messages=MagicMock(return_value=[{"role": "user", "content": "query"}]))
    agent._add_to_memory = AsyncMock()
    agent._ensure_within_token_limit = AsyncMock()
    agent._resolve_feature_flags = MagicMock(return_value={"delivery_integrity_gate": False})
    agent._extract_title = MagicMock(return_value="AI Trends")
    agent._extract_fallback_summary = MagicMock(return_value="")
    agent._extract_report_from_file_write_memory = MagicMock(return_value=None)
    agent._ensure_complete_references = MagicMock(side_effect=lambda x: x)
    agent._build_numbered_source_list = MagicMock(return_value="")
    agent._needs_verification = MagicMock(return_value=False)
    agent._verify_hallucination = AsyncMock(return_value=SimpleNamespace(content="", blocking_issues=[], warnings=[]))
    agent._output_coverage_validator = MagicMock(
        validate=MagicMock(return_value=SimpleNamespace(is_valid=True, missing_requirements=[]))
    )
    agent._response_compressor = MagicMock(compress=MagicMock(side_effect=lambda content, **_: content))
    agent._run_delivery_integrity_gate = MagicMock(return_value=(True, []))
    agent._can_auto_repair_delivery_integrity = MagicMock(return_value=False)
    agent._append_delivery_integrity_fallback = MagicMock(side_effect=lambda content, _issues: content)
    agent._generate_follow_up_suggestions = AsyncMock(return_value=[])
    return agent


class TestCancelledErrorPartialReport:
    """When summarize() is cancelled mid-stream, it must emit a partial ReportEvent
    before re-raising CancelledError."""

    @pytest.mark.asyncio
    async def test_cancelled_error_emits_partial_report_then_reraises(self):
        from app.domain.models.event import ReportEvent, StreamEvent

        agent = _make_execution_agent_for_summarize()
        partial_text = "# 🔬 AI Trends\n\n## 📊 Findings\n\nLarge language models are growing rapidly."

        async def _cancelling_iter(*_args, **_kwargs):
            yield StreamEvent(content=partial_text, is_final=False, phase="summarizing")
            raise asyncio.CancelledError

        agent._iter_coalesced_stream_events = _cancelling_iter

        collected_events: list = []
        with pytest.raises(asyncio.CancelledError):
            async for ev in agent.summarize(all_steps_completed=True):
                collected_events.append(ev)  # noqa: PERF401

        report_events = [e for e in collected_events if isinstance(e, ReportEvent)]
        assert len(report_events) == 1, f"Expected 1 partial ReportEvent, got {len(report_events)}: {collected_events}"
        assert "[Partial]" in report_events[0].title
        assert "⚠️" not in report_events[0].content
        assert "🔬" not in report_events[0].content
        assert "📊" not in report_events[0].content
        assert "Partial Report" in report_events[0].content

    @pytest.mark.asyncio
    async def test_cancelled_error_with_no_content_does_not_emit_report(self):
        """If CancelledError fires before content is collected, no partial report is emitted."""
        from app.domain.models.event import ReportEvent

        agent = _make_execution_agent_for_summarize()

        async def _immediately_cancel(*_args, **_kwargs):
            raise asyncio.CancelledError
            yield  # makes this an async generator (unreachable but required)

        agent._iter_coalesced_stream_events = _immediately_cancel

        collected_events: list = []
        with pytest.raises(asyncio.CancelledError):
            async for ev in agent.summarize(all_steps_completed=True):
                collected_events.append(ev)  # noqa: PERF401

        report_events = [e for e in collected_events if isinstance(e, ReportEvent)]
        assert len(report_events) == 0


class TestDirectDeliveryShortCircuit:
    def test_can_deliver_pretrim_report_directly_requires_completed_telegram_report(self):
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        agent = _make_execution_agent_for_summarize()
        agent._pre_trim_report_cache = "# Final Report\n\n" + ("Grounded detail [1]\n" * 120)
        agent._run_delivery_integrity_gate = MagicMock(return_value=(True, []))
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result"],
            allow_compression=False,
        )

        assert (
            agent._can_deliver_pretrim_report_directly(
                response_policy=policy,
                all_steps_completed=False,
                delivery_channel="telegram",
            )
            is False
        )
        assert (
            agent._can_deliver_pretrim_report_directly(
                response_policy=policy,
                all_steps_completed=True,
                delivery_channel="web",
            )
            is False
        )
        assert (
            agent._can_deliver_pretrim_report_directly(
                response_policy=policy,
                all_steps_completed=True,
                delivery_channel="telegram",
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_summarize_skips_llm_when_pretrim_report_is_already_deliverable(self):
        from app.domain.models.event import ReportEvent

        agent = _make_execution_agent_for_summarize()
        grounded_pretrim = (
            "# Final Report\n\n"
            "## Findings\n"
            + ("Grounded detail with source support [1].\n" * 80)
            + "\n## References\n[1] https://example.com/source\n"
        )

        agent._delivery_channel = "telegram"
        agent._resolve_feature_flags = MagicMock(return_value={"delivery_integrity_gate": True})
        agent._extract_report_from_file_write_memory = MagicMock(return_value=grounded_pretrim)
        agent._needs_verification = MagicMock(return_value=False)
        agent._can_deliver_pretrim_report_directly = MagicMock(return_value=True)
        agent._run_delivery_integrity_gate = MagicMock(
            side_effect=lambda *args, **kwargs: (
                (kwargs.get("content", args[0] if args else "") == grounded_pretrim),
                [] if kwargs.get("content", args[0] if args else "") == grounded_pretrim else ["ungrounded"],
            )
        )

        async def should_not_stream(*_args, **_kwargs):
            raise AssertionError("ask_stream should not be called when the pre-trim draft is already deliverable")
            yield  # pragma: no cover

        agent.llm.ask_stream = should_not_stream

        events = [event async for event in agent.summarize(all_steps_completed=True)]

        report = next(event for event in events if isinstance(event, ReportEvent))
        assert report.content == grounded_pretrim
        assert any(
            (kwargs.get("content", args[0] if args else "") == grounded_pretrim)
            for args, kwargs in agent._run_delivery_integrity_gate.call_args_list
        )

    @pytest.mark.asyncio
    async def test_summarize_telegram_auto_repairs_artifact_reference_gap_when_verification_is_skipped(self):
        from app.domain.models.event import ErrorEvent, ReportEvent
        from app.domain.services.agents.execution import ExecutionAgent
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        agent = _make_execution_agent_for_summarize()
        agent._response_generator._resolve_feature_flags_fn = lambda: {"delivery_integrity_gate": True}
        raw_report = (
            "# Final Report\n\n"
            "## Final Result\n"
            "Trending repositories were analyzed and summarized.\n\n"
            "## Findings\n"
            "The report is otherwise ready for delivery.\n"
        )
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        agent._delivery_channel = "telegram"
        agent._resolve_feature_flags = MagicMock(return_value={"delivery_integrity_gate": True})
        agent._needs_verification = MagicMock(return_value=True)
        agent._verify_hallucination = AsyncMock(
            return_value=SimpleNamespace(
                content=raw_report,
                blocking_issues=[],
                warnings=["hallucination_verification_skipped"],
            )
        )
        agent._output_coverage_validator = MagicMock(
            validate=MagicMock(
                side_effect=lambda output, **_: SimpleNamespace(
                    is_valid="## Artifact References" in output,
                    missing_requirements=[] if "## Artifact References" in output else ["artifact references"],
                )
            )
        )
        agent._run_delivery_integrity_gate = ExecutionAgent._run_delivery_integrity_gate.__get__(agent, ExecutionAgent)
        agent._can_auto_repair_delivery_integrity = ExecutionAgent._can_auto_repair_delivery_integrity.__get__(
            agent, ExecutionAgent
        )
        agent._append_delivery_integrity_fallback = ExecutionAgent._append_delivery_integrity_fallback.__get__(
            agent, ExecutionAgent
        )
        agent._set_response_generator_artifact_references = (
            ExecutionAgent._set_response_generator_artifact_references.__get__(agent, ExecutionAgent)
        )

        async def summary_stream(*_args, **_kwargs):
            agent.llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield raw_report

        agent.llm.ask_stream = summary_stream
        agent.llm.ask = AsyncMock(return_value={"content": '["Follow-up question?"]'})

        with patch("app.domain.services.agents.execution.uuid.uuid4", return_value="report-fixed-id"):
            events = [event async for event in agent.summarize(response_policy=policy, all_steps_completed=True)]

        assert not any(isinstance(event, ErrorEvent) for event in events)
        report = next(event for event in events if isinstance(event, ReportEvent))
        assert "## Artifact References" in report.content
        assert "`report-report-fixed-id.md`" in report.content
        assert "No file artifacts were created" not in report.content

    def test_delivery_gate_blocks_false_no_artifacts_when_artifacts_exist(self):
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        rg = _make_rg()
        rg.set_artifact_references(
            [
                {"filename": "report-abc.md", "content_type": "text/markdown"},
            ]
        )
        coverage_result = SimpleNamespace(is_valid=True, missing_requirements=[])
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        passed, issues = rg.run_delivery_integrity_gate(
            content=(
                "# Final Report\n\n"
                "## Final Result\nDone.\n\n"
                "## Artifact References\n"
                "- No file artifacts were created or referenced in this response.\n"
            ),
            response_policy=policy,
            coverage_result=coverage_result,
            stream_metadata={"provider": "test"},
            truncation_exhausted=False,
            delivery_channel="telegram",
        )

        assert passed is False
        assert "coverage_missing:artifact references" in issues

    @pytest.mark.asyncio
    async def test_summarize_telegram_gate_failure_downgrades_when_all_steps_completed(self):
        """Telegram delivery should downgrade (not block) when all steps completed."""
        from app.domain.models.event import ErrorEvent, ReportEvent
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        agent = _make_execution_agent_for_summarize()
        raw_report = (
            "# Final Report\n\n"
            "## Final Result\n"
            "Trending repositories were analyzed and summarized.\n\n"
            "## Findings\n"
            "The report is otherwise ready for delivery.\n"
        )
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        agent._delivery_channel = "telegram"
        agent._run_delivery_integrity_gate = MagicMock(return_value=(False, ["coverage_missing:artifact references"]))
        agent._can_auto_repair_delivery_integrity = MagicMock(return_value=False)

        async def summary_stream(*_args, **_kwargs):
            agent.llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield raw_report

        agent.llm.ask_stream = summary_stream
        agent.llm.ask = AsyncMock(return_value={"content": '["Follow-up question?"]'})

        events = [event async for event in agent.summarize(response_policy=policy, all_steps_completed=True)]

        # With all steps completed, gate downgrades to warning and delivers
        assert any(isinstance(event, ReportEvent) for event in events)
        assert not any(isinstance(event, ErrorEvent) for event in events)

    @pytest.mark.asyncio
    async def test_summarize_telegram_hallucination_ratio_critical_blocks_when_completed(self):
        """Critical hallucination findings must still block completed Telegram delivery."""
        from app.domain.models.event import ErrorEvent, ReportEvent
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        agent = _make_execution_agent_for_summarize()
        raw_report = (
            "# Final Report\n\n"
            "## Final Result\n"
            "Trending repositories were analyzed and summarized.\n\n"
            "## Findings\n"
            "This report contains synthesized claims beyond source snippets.\n"
            "\n> **Note:** Some information in this response "
            "could not be fully verified against available sources."
        )
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        agent._delivery_channel = "telegram"
        agent._run_delivery_integrity_gate = MagicMock(return_value=(False, ["hallucination_ratio_critical"]))
        agent._can_auto_repair_delivery_integrity = MagicMock(return_value=False)

        async def summary_stream(*_args, **_kwargs):
            agent.llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield raw_report

        agent.llm.ask_stream = summary_stream
        agent.llm.ask = AsyncMock(return_value={"content": '["Follow-up question?"]'})

        events = [event async for event in agent.summarize(response_policy=policy, all_steps_completed=True)]

        assert any(isinstance(event, ErrorEvent) for event in events)
        assert not any(isinstance(event, ReportEvent) for event in events)

    @pytest.mark.asyncio
    async def test_summarize_telegram_gate_failure_blocks_when_steps_incomplete(self):
        """Telegram delivery should block when steps did NOT all complete."""
        from app.domain.models.event import ErrorEvent, ReportEvent
        from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

        agent = _make_execution_agent_for_summarize()
        raw_report = (
            "# Final Report\n\n"
            "## Final Result\n"
            "Trending repositories were analyzed and summarized.\n\n"
            "## Findings\n"
            "The report is otherwise ready for delivery.\n"
        )
        policy = ResponsePolicy(
            mode=VerbosityMode.STANDARD,
            min_required_sections=["final result", "artifact references"],
            allow_compression=False,
        )

        agent._delivery_channel = "telegram"
        agent._run_delivery_integrity_gate = MagicMock(return_value=(False, ["coverage_missing:artifact references"]))
        agent._can_auto_repair_delivery_integrity = MagicMock(return_value=False)

        async def summary_stream(*_args, **_kwargs):
            agent.llm.last_stream_metadata = {
                "finish_reason": "stop",
                "truncated": False,
                "provider": "test",
            }
            yield raw_report

        agent.llm.ask_stream = summary_stream
        agent.llm.ask = AsyncMock(return_value={"content": '["Follow-up question?"]'})

        # all_steps_completed=False — should block
        events = [event async for event in agent.summarize(response_policy=policy, all_steps_completed=False)]

        error = next(event for event in events if isinstance(event, ErrorEvent))
        assert error.error == "I couldn't send the final response for this request. Please send it again."
        assert not any(isinstance(event, ReportEvent) for event in events)
