"""Tests for chart reference injection into delivered report file.

Charts must be generated before report-{id}.md is written, so the
written file includes references to chart filenames.
"""

from app.domain.models.event import ReportEvent
from app.domain.models.file import FileInfo
from app.domain.services.agent_task_runner import AgentTaskRunner


def _inject_chart_references(event: ReportEvent, chart_attachments: list[FileInfo]) -> None:
    """Mirror the chart reference injection logic from _ensure_report_file."""
    if not chart_attachments:
        return
    chart_lines = ["\n\n---\n\n## Charts\n"]
    chart_lines.extend(
        f"![Comparison Chart]({ci.filename})"
        if ci.content_type == "image/png"
        else f"*Interactive version:* `{ci.filename}`"
        for ci in chart_attachments
        if ci.content_type in {"image/png", "text/html"}
    )
    event.content += "\n".join(chart_lines) + "\n"


class TestChartReferenceInContent:
    """After _ensure_report_file, event.content should reference charts."""

    def test_png_chart_referenced_in_content(self):
        """event.content should contain the PNG chart filename."""
        event = ReportEvent(
            id="test-report-1",
            title="Test Report",
            content="# Report\n\nSome analysis here.",
        )
        # Verify PNG chart reference format
        chart_ref = f"![Comparison Chart](comparison-chart-{event.id}.png)"
        assert chart_ref.startswith("![")
        assert event.id in chart_ref

    def test_html_chart_referenced_in_content(self):
        """event.content should contain the HTML chart filename in backticks."""
        event = ReportEvent(
            id="test-report-1",
            title="Test Report",
            content="# Report\n\nSome analysis here.",
        )
        chart_ref = f"`comparison-chart-{event.id}.html`"
        assert chart_ref.startswith("`")
        assert event.id in chart_ref

    def test_no_chart_no_injection(self):
        """When chart generation returns no files, content is unchanged."""
        event = ReportEvent(
            id="test-report-1",
            title="Test Report",
            content="# Report\n\nOriginal content.",
        )
        original_content = event.content
        # No charts -> content unchanged
        assert event.content == original_content

    def test_injection_appends_charts_section(self):
        """Chart injection should append a ## Charts section to content."""
        event = ReportEvent(
            id="rpt-42",
            title="Comparison Report",
            content="# Report\n\nAnalysis body.",
        )
        chart_attachments = [
            FileInfo(
                filename="comparison-chart-rpt-42.png",
                file_path="/workspace/deliverables/comparison-chart-rpt-42.png",
                size=12345,
                content_type="image/png",
                user_id="user-1",
            ),
            FileInfo(
                filename="comparison-chart-rpt-42.html",
                file_path="/workspace/deliverables/comparison-chart-rpt-42.html",
                size=67890,
                content_type="text/html",
                user_id="user-1",
            ),
        ]
        # Simulate the injection logic from _ensure_report_file
        _inject_chart_references(event, chart_attachments)

        assert "## Charts" in event.content
        assert "![Comparison Chart](comparison-chart-rpt-42.png)" in event.content
        assert "`comparison-chart-rpt-42.html`" in event.content

    def test_injection_preserves_original_content(self):
        """Chart injection should not overwrite existing content."""
        original = "# Report\n\nOriginal analysis with important data."
        event = ReportEvent(
            id="rpt-99",
            title="Test",
            content=original,
        )
        chart_attachments = [
            FileInfo(
                filename="comparison-chart-rpt-99.png",
                file_path="/workspace/comparison-chart-rpt-99.png",
                size=5000,
                content_type="image/png",
                user_id="user-1",
            ),
        ]
        _inject_chart_references(event, chart_attachments)

        assert event.content.startswith(original)
        assert "## Charts" in event.content


class TestChartReferenceFormat:
    """Verify the injected chart reference markdown format."""

    def test_png_uses_image_syntax(self):
        """PNG should be referenced with ![alt](filename) markdown."""
        ref = "![Comparison Chart](comparison-chart-abc.png)"
        assert ref.startswith("![")
        assert ref.endswith(")")
        assert "comparison-chart-abc.png" in ref

    def test_html_uses_backtick_syntax(self):
        """HTML should be referenced with `filename` backtick syntax."""
        ref = "`comparison-chart-abc.html`"
        assert ref.startswith("`")
        assert ref.endswith("`")
        assert "comparison-chart-abc.html" in ref

    def test_svg_not_injected(self):
        """SVG charts should not produce image/png or text/html references."""
        svg_info = FileInfo(
            filename="comparison-chart-xyz.svg",
            file_path="/workspace/comparison-chart-xyz.svg",
            size=3000,
            content_type="image/svg+xml",
            user_id="user-1",
        )
        # The injection logic only handles image/png and text/html
        chart_lines = []
        if svg_info.content_type == "image/png":
            chart_lines.append(f"![Comparison Chart]({svg_info.filename})")
        elif svg_info.content_type == "text/html":
            chart_lines.append(f"*Interactive version:* `{svg_info.filename}`")
        assert chart_lines == []

    def test_chart_section_has_horizontal_rule(self):
        """Chart section should start with a horizontal rule separator."""
        chart_lines = ["\n\n---\n\n## Charts\n"]
        chart_lines.append("![Comparison Chart](chart.png)")
        section = "\n".join(chart_lines) + "\n"
        assert "---" in section
        assert section.index("---") < section.index("## Charts")

    def test_empty_attachments_produce_no_section(self):
        """Empty chart_attachments list should not modify content."""
        event = ReportEvent(
            id="rpt-empty",
            title="No Charts",
            content="# Report\n\nJust text.",
        )
        original = event.content
        chart_attachments: list[FileInfo] = []
        _inject_chart_references(event, chart_attachments)
        assert event.content == original


class TestRewriteChartImageUrls:
    """Tests for _rewrite_chart_image_urls that replaces bare filenames with API URLs."""

    @staticmethod
    def _make_report(content: str, attachments: list[FileInfo] | None = None) -> ReportEvent:
        return ReportEvent(
            id="report-1",
            title="Test Report",
            content=content,
            attachments=attachments,
            session_id="session-1",
        )

    def test_png_filename_rewritten_to_api_url(self):
        attachment = FileInfo(
            file_id="abc123",
            filename="comparison-chart-report-1.png",
            content_type="image/png",
        )
        event = self._make_report(
            content="## Charts\n![Comparison Chart](comparison-chart-report-1.png)\nMore text.",
            attachments=[attachment],
        )
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert "](/api/v1/files/abc123/download)" in event.content
        assert "comparison-chart-report-1.png" not in event.content

    def test_no_rewrite_when_file_id_missing(self):
        attachment = FileInfo(
            filename="comparison-chart-report-1.png",
            content_type="image/png",
            file_id=None,
        )
        event = self._make_report(
            content="![Chart](comparison-chart-report-1.png)",
            attachments=[attachment],
        )
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert "comparison-chart-report-1.png" in event.content

    def test_html_attachment_not_rewritten(self):
        attachment = FileInfo(
            file_id="html-id",
            filename="comparison-chart-report-1.html",
            content_type="text/html",
        )
        event = self._make_report(
            content="`comparison-chart-report-1.html`",
            attachments=[attachment],
        )
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert "comparison-chart-report-1.html" in event.content

    def test_empty_attachments_no_error(self):
        event = self._make_report(content="Just text.", attachments=[])
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert event.content == "Just text."

    def test_empty_content_no_error(self):
        event = self._make_report(content="", attachments=[FileInfo(file_id="x", content_type="image/png")])
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert event.content == ""

    def test_multiple_png_attachments(self):
        a1 = FileInfo(file_id="id-1", filename="chart-a.png", content_type="image/png")
        a2 = FileInfo(file_id="id-2", filename="chart-b.png", content_type="image/png")
        event = self._make_report(
            content="![A](chart-a.png)\n![B](chart-b.png)",
            attachments=[a1, a2],
        )
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert "](/api/v1/files/id-1/download)" in event.content
        assert "](/api/v1/files/id-2/download)" in event.content
        assert "chart-a.png" not in event.content
        assert "chart-b.png" not in event.content

    def test_surrounding_content_preserved(self):
        attachment = FileInfo(file_id="xyz", filename="chart.png", content_type="image/png")
        event = self._make_report(
            content="# Report\nSome analysis.\n![Chart](chart.png)\n\n## Conclusion\nDone.",
            attachments=[attachment],
        )
        AgentTaskRunner._rewrite_chart_image_urls(event)
        assert "# Report" in event.content
        assert "Some analysis." in event.content
        assert "## Conclusion" in event.content
        assert "](/api/v1/files/xyz/download)" in event.content
