"""Tests for auto-saving report events as files."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ReportEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner

COMPARISON_MARKDOWN = """# LLM Comparison

## Comparison Table
| Model | Score | Cost |
|-------|-------|------|
| Alpha | 92 | 0.50 |
| Beta | 88 | 0.30 |
| Gamma | 85 | 0.20 |
"""


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
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
            file_storage=AsyncMock(),
            mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
            search_engine=AsyncMock(),
            mode=AgentMode.AGENT,
        )


class TestReportFileAttachment:
    @pytest.mark.asyncio
    async def test_report_event_is_written_and_attached(self, runner, mock_sandbox):
        event = ReportEvent(
            id="report-1",
            title="Test Report",
            content="# Hello\n\nReport body.",
            attachments=None,
        )

        await runner._ensure_report_file(event)

        mock_sandbox.file_write.assert_called_once()
        assert event.attachments is not None
        assert len(event.attachments) == 1
        assert event.attachments[0].file_path == "/home/ubuntu/report-report-1.md"

    @pytest.mark.asyncio
    async def test_comparison_report_generates_chart_attachment(self, runner, mock_sandbox):
        event = ReportEvent(
            id="report-chart-1",
            title="Model Comparison",
            content=COMPARISON_MARKDOWN,
            attachments=None,
        )

        await runner._ensure_report_file(event)

        assert mock_sandbox.file_write.call_count == 2
        assert event.attachments is not None
        assert len(event.attachments) == 2

        report_attachment = next(a for a in event.attachments if a.filename == "report-report-chart-1.md")
        assert report_attachment.content_type == "text/markdown"

        chart_attachment = next(a for a in event.attachments if a.filename == "comparison-chart-report-chart-1.svg")
        assert chart_attachment.content_type == "image/svg+xml"
        assert chart_attachment.file_path == "/home/ubuntu/comparison-chart-report-chart-1.svg"
        assert chart_attachment.metadata is not None
        assert chart_attachment.metadata.get("is_comparison_chart") is True
        assert chart_attachment.metadata.get("chart_format") == "svg"
        assert chart_attachment.metadata.get("source_report_id") == "report-chart-1"
        assert chart_attachment.metadata.get("chart_width") is not None
        assert chart_attachment.metadata.get("chart_height") is not None

        chart_write_call = mock_sandbox.file_write.call_args_list[1]
        assert chart_write_call.kwargs["file"] == "/home/ubuntu/comparison-chart-report-chart-1.svg"
        assert "<svg" in chart_write_call.kwargs["content"]

    @pytest.mark.asyncio
    async def test_chart_generation_can_be_skipped_with_user_flag(self, runner, mock_sandbox):
        runner.current_task = "Create comparison report on model latency [chart=skip]"
        event = ReportEvent(
            id="report-skip-1",
            title="Latency Comparison",
            content=COMPARISON_MARKDOWN,
            attachments=None,
        )

        await runner._ensure_report_file(event)

        assert mock_sandbox.file_write.call_count == 1
        assert event.attachments is not None
        assert len(event.attachments) == 1
        assert event.attachments[0].filename == "report-report-skip-1.md"

    @pytest.mark.asyncio
    async def test_chart_generation_can_be_forced_with_user_flag(self, runner, mock_sandbox):
        runner.current_task = "Summarize benchmark table [chart=force]"
        event = ReportEvent(
            id="report-force-1",
            title="Benchmark Summary",
            content="""# Benchmarks

| Engine | Throughput | Notes |
|--------|------------|-------|
| A | 1200 | Stable |
| B | 900 | Balanced |
""",
            attachments=None,
        )

        await runner._ensure_report_file(event)

        assert mock_sandbox.file_write.call_count == 2
        assert event.attachments is not None
        assert any(a.filename == "comparison-chart-report-force-1.svg" for a in event.attachments)

    @pytest.mark.asyncio
    async def test_chart_regeneration_replaces_existing_chart(self, runner, mock_sandbox):
        runner.current_task = "Update report with latest data [chart=regenerate]"
        event = ReportEvent(
            id="report-regen-1",
            title="Updated Comparison",
            content=COMPARISON_MARKDOWN,
            attachments=[
                FileInfo(
                    filename="report-report-regen-1.md",
                    file_path="/home/ubuntu/report-report-regen-1.md",
                    content_type="text/markdown",
                    size=20,
                ),
                FileInfo(
                    filename="comparison-chart-report-regen-1.svg",
                    file_path="/home/ubuntu/comparison-chart-report-regen-1.svg",
                    content_type="image/svg+xml",
                    size=10,
                    metadata={"is_comparison_chart": True, "source_report_id": "report-regen-1"},
                ),
            ],
        )

        await runner._ensure_report_file(event)

        assert mock_sandbox.file_write.call_count == 1
        assert event.attachments is not None
        assert len(event.attachments) == 2
        chart_attachments = [a for a in event.attachments if a.filename == "comparison-chart-report-regen-1.svg"]
        assert len(chart_attachments) == 1
        assert chart_attachments[0].metadata is not None
        assert chart_attachments[0].metadata.get("generation_mode") == "regenerate"
