"""Tests for full-report recovery and attachment ordering in AgentTaskRunner."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ReportEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner

FULL_REPORT_CONTENT = """\
# Comprehensive Research Report

## Introduction

This is the full research report with detailed analysis spanning multiple sections.

## Key Findings

1. Finding one with detailed explanation and supporting evidence.
2. Finding two with metrics and data points.
3. Finding three with comparative analysis.

## Methodology

The research was conducted using multiple search queries and browser-based verification.

## Conclusion

A thorough summary of all findings above.
"""

SUMMARY_CONTENT = """\
## Key Findings

1. Finding one.
2. Finding two.
3. Finding three.
"""


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear settings cache before each test to prevent state contamination."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
    sandbox.file_delete = AsyncMock(return_value=MagicMock(success=True))
    sandbox.exec_command = AsyncMock(return_value=MagicMock(success=True, data="", message=""))
    return sandbox


@pytest.fixture
def runner(mock_sandbox) -> AgentTaskRunner:
    with patch("app.domain.services.agent_task_runner.PlanActFlow"):
        return AgentTaskRunner(
            session_id="test-session",
            agent_id="test-agent",
            user_id="test-user",
            llm=MagicMock(),
            sandbox=mock_sandbox,
            browser=AsyncMock(),
            agent_repository=AsyncMock(),
            session_repository=AsyncMock(),
            json_parser=MagicMock(),
            file_storage=AsyncMock(
                upload_file=AsyncMock(return_value=MagicMock(filename="report.pdf", file_url="http://test/report.pdf")),
            ),
            mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
            search_engine=AsyncMock(),
            mode=AgentMode.AGENT,
        )


def _set_flow(runner: AgentTaskRunner, mock_flow: MagicMock | None) -> None:
    """Set the flow on the runner by writing the underlying _plan_act_flow attribute.

    The runner's ``_flow`` is a read-only property that returns ``_plan_act_flow``
    when mode is AGENT, so we must set the backing attribute directly.
    """
    runner._plan_act_flow = mock_flow


class TestGetPreTrimReportContentFallback:
    """Tests for _get_pre_trim_report_content fallback to file_write memory."""

    def test_returns_cached_content_when_available(self, runner):
        """Primary path: returns _pre_trim_report_cache when it has content."""
        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = FULL_REPORT_CONTENT
        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        result = runner._get_pre_trim_report_content()

        assert result == FULL_REPORT_CONTENT

    def test_falls_back_to_file_write_memory_when_cache_is_none(self, runner):
        """When _pre_trim_report_cache is None, recover from file_write memory."""
        mock_rg = MagicMock()
        mock_rg.extract_report_from_file_write_memory.return_value = FULL_REPORT_CONTENT

        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = None
        mock_executor._response_generator = mock_rg

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        result = runner._get_pre_trim_report_content()

        assert result == FULL_REPORT_CONTENT
        mock_rg.extract_report_from_file_write_memory.assert_called_once()

    def test_falls_back_to_file_write_memory_when_cache_is_empty_string(self, runner):
        """When _pre_trim_report_cache is an empty string, recover from file_write memory."""
        mock_rg = MagicMock()
        mock_rg.extract_report_from_file_write_memory.return_value = FULL_REPORT_CONTENT

        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = "   "
        mock_executor._response_generator = mock_rg

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        result = runner._get_pre_trim_report_content()

        assert result == FULL_REPORT_CONTENT
        mock_rg.extract_report_from_file_write_memory.assert_called_once()

    def test_returns_none_when_both_cache_and_fallback_empty(self, runner):
        """When both cache and file_write memory return nothing, return None."""
        mock_rg = MagicMock()
        mock_rg.extract_report_from_file_write_memory.return_value = None

        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = None
        mock_executor._response_generator = mock_rg

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        result = runner._get_pre_trim_report_content()

        assert result is None

    def test_fallback_exception_is_caught_and_returns_none(self, runner):
        """When file_write memory extraction raises, catch and return None."""
        mock_rg = MagicMock()
        mock_rg.extract_report_from_file_write_memory.side_effect = RuntimeError("memory corrupted")

        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = None
        mock_executor._response_generator = mock_rg

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        result = runner._get_pre_trim_report_content()

        assert result is None

    def test_returns_none_when_no_flow(self, runner):
        """When _flow is None, return None gracefully."""
        _set_flow(runner, None)

        result = runner._get_pre_trim_report_content()

        assert result is None

    def test_returns_none_when_executor_has_no_response_generator(self, runner):
        """When executor lacks _response_generator, skip fallback gracefully."""
        mock_executor = MagicMock(spec=[])  # no attributes at all
        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        result = runner._get_pre_trim_report_content()

        assert result is None


class TestFullReportAttachmentOrder:
    """Tests that the full-report file is the primary (first) attachment."""

    @pytest.mark.asyncio
    async def test_full_report_is_first_attachment(self, runner, mock_sandbox):
        """When full report content exists, its FileInfo is at index 0."""
        mock_rg = MagicMock()
        mock_rg.extract_report_from_file_write_memory.return_value = FULL_REPORT_CONTENT

        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = None
        mock_executor._response_generator = mock_rg

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        event = ReportEvent(
            id="report-order-1",
            title="Test Report",
            content=SUMMARY_CONTENT,
            attachments=None,
        )

        await runner._ensure_report_file(event)

        assert event.attachments is not None
        assert len(event.attachments) >= 1
        # Full report must be first
        assert event.attachments[0].filename == "full-report-report-order-1.md"
        assert event.attachments[0].metadata is not None
        assert event.attachments[0].metadata.get("is_full_report") is True

    @pytest.mark.asyncio
    async def test_full_report_not_created_when_content_matches_summary(self, runner, mock_sandbox):
        """When full report content equals the summary, no separate full-report attachment."""
        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = SUMMARY_CONTENT

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        event = ReportEvent(
            id="report-same-1",
            title="Test Report",
            content=SUMMARY_CONTENT,
            attachments=None,
        )

        await runner._ensure_report_file(event)

        assert event.attachments is not None
        full_reports = [a for a in event.attachments if a.filename.startswith("full-report-")]
        assert len(full_reports) == 0

    @pytest.mark.asyncio
    async def test_full_report_first_with_preexisting_attachments(self, runner, mock_sandbox):
        """Full report is inserted before any pre-existing attachments."""
        mock_executor = MagicMock()
        mock_executor._pre_trim_report_cache = FULL_REPORT_CONTENT

        mock_flow = MagicMock()
        mock_flow.executor = mock_executor
        _set_flow(runner, mock_flow)

        existing_attachment = FileInfo(
            filename="data.csv",
            file_path="/workspace/test-session/data.csv",
            content_type="text/csv",
            size=100,
        )
        event = ReportEvent(
            id="report-existing-1",
            title="Test Report",
            content=SUMMARY_CONTENT,
            attachments=[existing_attachment],
        )

        await runner._ensure_report_file(event)

        assert event.attachments is not None
        assert len(event.attachments) >= 2
        # Full report must be first, before the pre-existing attachment
        assert event.attachments[0].filename == "full-report-report-existing-1.md"
        assert event.attachments[0].metadata is not None
        assert event.attachments[0].metadata.get("is_full_report") is True
        # The pre-existing data.csv must come after
        data_idx = next(i for i, a in enumerate(event.attachments) if a.filename == "data.csv")
        assert data_idx > 0
