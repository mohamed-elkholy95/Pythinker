"""Tests for auto-saving report events as files."""

import json
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

    tmp_specs: dict[str, dict] = {}

    async def file_write_side_effect(*, file: str, content: str):
        if "plotly_input_" in file:
            tmp_specs[file] = json.loads(content)
        return MagicMock(success=True)

    async def exec_command_side_effect(*, session_id: str, exec_dir: str, command: str):
        _ = session_id, exec_dir
        tmp_input = command.split("<")[-1].strip()
        spec = tmp_specs.get(tmp_input, {})
        output = {
            "success": True,
            "html_path": spec.get("output_html", "/workspace/test-session/comparison-chart-fallback.html"),
            "png_path": spec.get("output_png", "/workspace/test-session/comparison-chart-fallback.png"),
            "html_size": 2048,
            "png_size": 1024,
            "data_points": len(spec.get("points", [])),
        }
        return MagicMock(success=True, data=json.dumps(output), message="")

    sandbox.file_write = AsyncMock(side_effect=file_write_side_effect)
    sandbox.exec_command = AsyncMock(side_effect=exec_command_side_effect)
    sandbox.file_delete = AsyncMock(return_value=MagicMock(success=True))
    return sandbox


@pytest.fixture
def mock_llm_for_chart() -> AsyncMock:
    """AsyncMock LLM that returns chart analysis for comparison reports."""
    from app.domain.services.plotly_chart_orchestrator import ChartAnalysisResult

    llm = AsyncMock()
    llm.model_name = "test-model"

    async def _chart_analysis(messages, response_model, **kwargs):
        # Extract report content from user message
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        content_lower = user_msg.lower()
        is_forced = "user has explicitly requested" in sys_msg.lower()
        if "comparison" in content_lower or "score" in content_lower or is_forced:
            return ChartAnalysisResult(
                should_generate=True,
                chart_type="bar",
                title="Comparison Chart",
                metric_name="Score",
                lower_is_better=False,
                points=[
                    {"label": "Alpha", "value": 92.0, "display_value": "92"},
                    {"label": "Beta", "value": 88.0, "display_value": "88"},
                    {"label": "Gamma", "value": 85.0, "display_value": "85"},
                ],
                reason="Compares values.",
            )
        return ChartAnalysisResult(should_generate=False, reason="Not a comparison.")

    llm.ask_structured = AsyncMock(side_effect=_chart_analysis)
    return llm


@pytest.fixture
def runner(mock_sandbox, mock_llm_for_chart) -> AgentTaskRunner:
    with patch("app.domain.services.agent_task_runner.PlanActFlow"):
        return AgentTaskRunner(
            session_id="test-session",
            agent_id="test-agent",
            user_id="test-user",
            llm=mock_llm_for_chart,
            sandbox=mock_sandbox,
            browser=AsyncMock(),
            agent_repository=AsyncMock(),
            session_repository=AsyncMock(),
            json_parser=MagicMock(),
            file_storage=AsyncMock(upload_file=AsyncMock(return_value=None)),
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
        assert event.attachments[0].file_path == "/workspace/test-session/report-report-1.md"

    @pytest.mark.asyncio
    async def test_report_event_is_written_under_active_delivery_scope(self, runner, mock_sandbox):
        event = ReportEvent(
            id="report-scoped-1",
            title="Scoped Report",
            content="# Hello\n\nScoped body.",
            attachments=None,
        )
        runner._delivery_scope_id = "run-2"
        runner._delivery_scope_root = "/workspace/test-session/runs/run-2"

        await runner._ensure_report_file(event)

        mock_sandbox.file_write.assert_called_once()
        assert event.attachments is not None
        assert len(event.attachments) == 1
        assert event.attachments[0].file_path == "/workspace/test-session/runs/run-2/report-report-scoped-1.md"
        assert event.attachments[0].metadata is not None
        assert event.attachments[0].metadata.get("delivery_scope") == "run-2"

    @pytest.mark.asyncio
    async def test_report_event_prefers_session_output_workspace(self, runner, mock_sandbox):
        runner._session_repository.find_by_id = AsyncMock(
            return_value=MagicMock(
                workspace_structure={
                    "_output_path": "/workspace/test-session/output",
                    "reports": "Markdown reports",
                }
            )
        )
        event = ReportEvent(
            id="report-output-1",
            title="Workspace Report",
            content="# Hello\n\nWorkspace body.",
            attachments=None,
        )

        await runner._ensure_report_file(event)

        mock_sandbox.file_write.assert_called_once()
        assert event.attachments is not None
        assert event.attachments[0].file_path == "/workspace/test-session/output/reports/report-report-output-1.md"

    @pytest.mark.asyncio
    async def test_existing_human_named_report_attachment_skips_canonical_rewrite(self, runner, mock_sandbox):
        runner._generate_report_pdf = AsyncMock(return_value=None)
        event = ReportEvent(
            id="report-existing-1",
            title="Existing Report",
            content="# Hello\n\nExisting body.",
            attachments=[
                FileInfo(
                    filename="dgx-spark-vs-m3-ultra-96-report.md",
                    file_path="/workspace/test-session/output/reports/dgx-spark-vs-m3-ultra-96-report.md",
                    content_type="text/markdown",
                    size=100,
                )
            ],
        )

        await runner._ensure_report_file(event)

        mock_sandbox.file_write.assert_not_called()
        assert event.attachments is not None
        assert len(event.attachments) == 1
        assert event.attachments[0].filename == "dgx-spark-vs-m3-ultra-96-report.md"

    @pytest.mark.asyncio
    async def test_repeated_calls_do_not_write_file_when_attachment_already_tracked(self, runner, mock_sandbox):
        """Simulates a verification retry loop: calling _ensure_report_file multiple times
        when the human-named attachment is already present must never trigger additional
        file_write calls — i.e. the runner-side guard is idempotent and loop-resistant.
        """
        runner._generate_report_pdf = AsyncMock(return_value=None)
        existing_attachment = FileInfo(
            filename="my-deep-research-report.md",
            file_path="/workspace/test-session/output/reports/my-deep-research-report.md",
            content_type="text/markdown",
            size=200,
        )
        event = ReportEvent(
            id="report-loop-guard-1",
            title="Loop Guard Test",
            content="# Loop Guard\n\nContent.",
            attachments=[existing_attachment],
        )

        # First call: no write expected
        await runner._ensure_report_file(event)
        mock_sandbox.file_write.assert_not_called()

        # Second call (simulates retry after failed verification): still no write
        await runner._ensure_report_file(event)
        mock_sandbox.file_write.assert_not_called()

        # Attachment list is stable — no duplicates added
        assert event.attachments is not None
        assert len(event.attachments) == 1
        assert event.attachments[0].filename == "my-deep-research-report.md"

    @pytest.mark.asyncio
    async def test_resolve_workspace_deliverables_root_avoids_shared_deliverables_directory(self, runner):
        runner._session_repository.find_by_id = AsyncMock(
            return_value=MagicMock(workspace_structure={"deliverables": "Final outputs"})
        )

        result = await runner._resolve_workspace_deliverables_root()

        assert result == "/workspace/test-session/deliverables"

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
        assert len(event.attachments) == 3

        report_attachment = next(a for a in event.attachments if a.filename == "report-report-chart-1.md")
        assert report_attachment.content_type == "text/markdown"

        html_attachment = next(a for a in event.attachments if a.filename == "comparison-chart-report-chart-1.html")
        assert html_attachment.content_type == "text/html"
        assert html_attachment.file_path == "/workspace/model_comparison.html"
        assert html_attachment.metadata is not None
        assert html_attachment.metadata.get("is_comparison_chart") is True
        assert html_attachment.metadata.get("chart_format") == "plotly_html_png"
        assert html_attachment.metadata.get("chart_engine") == "plotly"
        assert html_attachment.metadata.get("source_report_id") == "report-chart-1"
        assert html_attachment.metadata.get("data_points") == 3

        png_attachment = next(a for a in event.attachments if a.filename == "comparison-chart-report-chart-1.png")
        assert png_attachment.content_type == "image/png"
        assert png_attachment.file_path == "/workspace/model_comparison.png"
        assert png_attachment.metadata is not None
        assert png_attachment.metadata.get("is_comparison_chart") is True
        assert png_attachment.metadata.get("chart_format") == "plotly_html_png"
        assert png_attachment.metadata.get("chart_engine") == "plotly"
        assert png_attachment.metadata.get("source_report_id") == "report-chart-1"

        # After reorder, chart input is written before the report file
        chart_input_write_call = mock_sandbox.file_write.call_args_list[0]
        assert "plotly_input_" in chart_input_write_call.kwargs["file"]
        assert '"output_html": "/workspace/model_comparison.html"' in chart_input_write_call.kwargs["content"]

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
        assert any(a.filename == "comparison-chart-report-force-1.html" for a in event.attachments)
        assert any(a.filename == "comparison-chart-report-force-1.png" for a in event.attachments)

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
                    file_path="/workspace/test-session/report-report-regen-1.md",
                    content_type="text/markdown",
                    size=20,
                ),
                FileInfo(
                    filename="comparison-chart-report-regen-1.html",
                    file_path="/workspace/test-session/comparison-chart-report-regen-1.html",
                    content_type="text/html",
                    size=10,
                    metadata={
                        "is_comparison_chart": True,
                        "source_report_id": "report-regen-1",
                        "chart_engine": "plotly",
                    },
                ),
                FileInfo(
                    filename="comparison-chart-report-regen-1.png",
                    file_path="/workspace/test-session/comparison-chart-report-regen-1.png",
                    content_type="image/png",
                    size=10,
                    metadata={
                        "is_comparison_chart": True,
                        "source_report_id": "report-regen-1",
                        "chart_engine": "plotly",
                    },
                ),
            ],
        )

        await runner._ensure_report_file(event)

        assert mock_sandbox.file_write.call_count == 1
        assert event.attachments is not None
        assert len(event.attachments) == 3
        html_attachments = [a for a in event.attachments if a.filename == "comparison-chart-report-regen-1.html"]
        png_attachments = [a for a in event.attachments if a.filename == "comparison-chart-report-regen-1.png"]
        assert len(html_attachments) == 1
        assert len(png_attachments) == 1
        assert html_attachments[0].metadata is not None
        assert png_attachments[0].metadata is not None
        assert html_attachments[0].metadata.get("generation_mode") == "regenerate"
        assert png_attachments[0].metadata.get("generation_mode") == "regenerate"
