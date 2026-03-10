"""Tests for artifact manifest injection into summarization context.

Verifies that _merge_session_files_into_attachments() correctly merges
session files into _report_attachments with dedup, instead of the old
guard that skipped session_files when _report_attachments was already
partially populated.
"""

from __future__ import annotations

from types import SimpleNamespace


class TestArtifactManifestInjection:
    """Verify artifact references are always available to the summarizer."""

    def test_session_files_populate_empty_report_attachments(self):
        """When _report_attachments is empty, session_files should populate it."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = []

        session_files = [
            SimpleNamespace(
                filename="report.md",
                storage_key="minio://reports/report.md",
                file_path="/workspace/output/report.md",
            ),
            SimpleNamespace(
                filename="chart.html",
                storage_key="minio://reports/chart.html",
                file_path="/workspace/output/chart.html",
            ),
        ]

        flow._merge_session_files_into_attachments(session_files)

        assert len(flow._report_attachments) == 2
        assert flow._report_attachments[0]["filename"] == "report.md"
        assert flow._report_attachments[1]["filename"] == "chart.html"

    def test_report_attachments_merged_not_overwritten(self):
        """Session files should be merged into _report_attachments, not replace them."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = [
            {"filename": "existing.pdf", "storage_key": "s3://bucket/existing.pdf"},
        ]

        session_files = [
            SimpleNamespace(
                filename="new.md",
                storage_key="minio://reports/new.md",
                file_path="/workspace/output/new.md",
            ),
        ]

        flow._merge_session_files_into_attachments(session_files)

        assert len(flow._report_attachments) == 2
        filenames = [a["filename"] for a in flow._report_attachments]
        assert "existing.pdf" in filenames
        assert "new.md" in filenames

    def test_duplicate_filenames_not_added(self):
        """Duplicate filenames should be skipped during merge."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = [
            {"filename": "report.md", "storage_key": "s3://bucket/report.md"},
        ]

        session_files = [
            SimpleNamespace(
                filename="report.md",
                storage_key="minio://reports/report.md",
                file_path="/workspace/output/report.md",
            ),
            SimpleNamespace(
                filename="chart.html",
                storage_key="minio://reports/chart.html",
                file_path="/workspace/output/chart.html",
            ),
        ]

        flow._merge_session_files_into_attachments(session_files)

        assert len(flow._report_attachments) == 2
        filenames = [a["filename"] for a in flow._report_attachments]
        assert filenames.count("report.md") == 1
        assert "chart.html" in filenames

    def test_empty_session_files_is_noop(self):
        """Empty session_files should not modify _report_attachments."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = [{"filename": "existing.pdf", "storage_key": "key"}]

        flow._merge_session_files_into_attachments([])

        assert len(flow._report_attachments) == 1

    def test_storage_key_falls_back_to_file_path(self):
        """When storage_key is missing/empty, file_path should be used."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = []

        session_files = [
            SimpleNamespace(
                filename="local.txt",
                file_path="/workspace/output/local.txt",
            ),
        ]

        flow._merge_session_files_into_attachments(session_files)

        assert len(flow._report_attachments) == 1
        assert flow._report_attachments[0]["storage_key"] == "/workspace/output/local.txt"

    def test_preserves_insertion_order(self):
        """Existing attachments should come first, new ones appended."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._report_attachments = [
            {"filename": "first.pdf", "storage_key": "key1"},
        ]

        session_files = [
            SimpleNamespace(
                filename="second.md",
                storage_key="key2",
                file_path="/workspace/output/second.md",
            ),
            SimpleNamespace(
                filename="third.html",
                storage_key="key3",
                file_path="/workspace/output/third.html",
            ),
        ]

        flow._merge_session_files_into_attachments(session_files)

        filenames = [a["filename"] for a in flow._report_attachments]
        assert filenames == ["first.pdf", "second.md", "third.html"]
