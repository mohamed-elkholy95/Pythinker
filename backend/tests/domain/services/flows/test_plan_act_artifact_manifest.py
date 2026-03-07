"""Tests for artifact manifest injection into summarization context.

Covers PlanActFlow._build_artifact_manifest() — the pure static method
that converts a list of attachment dicts into a deliverables prompt section.
The wiring (population of _report_attachments and injection into
executor.system_prompt) is integration-level and covered by the surrounding
summarization tests.
"""

from __future__ import annotations


class TestBuildArtifactManifest:
    """_build_artifact_manifest returns a formatted deliverables section."""

    def test_with_multiple_files(self):
        from app.domain.services.flows.plan_act import PlanActFlow

        attachments = [
            {"filename": "report.md", "storage_key": "user/abc_report.md"},
            {"filename": "chart.png", "storage_key": "user/def_chart.png"},
        ]
        manifest = PlanActFlow._build_artifact_manifest(attachments)
        assert "report.md" in manifest
        assert "chart.png" in manifest
        assert "Deliverables" in manifest
        assert "Reference these files" in manifest

    def test_empty_list_returns_empty_string(self):
        from app.domain.services.flows.plan_act import PlanActFlow

        manifest = PlanActFlow._build_artifact_manifest([])
        assert manifest == ""

    def test_none_returns_empty_string(self):
        from app.domain.services.flows.plan_act import PlanActFlow

        manifest = PlanActFlow._build_artifact_manifest(None)
        assert manifest == ""

    def test_missing_filename_falls_back_to_unknown(self):
        from app.domain.services.flows.plan_act import PlanActFlow

        attachments = [{"storage_key": "user/abc_report.md"}]
        manifest = PlanActFlow._build_artifact_manifest(attachments)
        assert "unknown" in manifest

    def test_single_file_has_one_bullet(self):
        from app.domain.services.flows.plan_act import PlanActFlow

        attachments = [{"filename": "analysis.pdf"}]
        manifest = PlanActFlow._build_artifact_manifest(attachments)
        assert "analysis.pdf" in manifest
        assert manifest.count("- ") == 1

    def test_result_starts_with_double_newline(self):
        """Ensures safe concatenation with an existing system prompt."""
        from app.domain.services.flows.plan_act import PlanActFlow

        attachments = [{"filename": "out.csv"}]
        manifest = PlanActFlow._build_artifact_manifest(attachments)
        assert manifest.startswith("\n\n")

    def test_all_filenames_appear_as_bullets(self):
        from app.domain.services.flows.plan_act import PlanActFlow

        names = ["a.txt", "b.json", "c.png", "d.pdf"]
        attachments = [{"filename": n} for n in names]
        manifest = PlanActFlow._build_artifact_manifest(attachments)
        for name in names:
            assert f"- {name}" in manifest

    def test_scope_filtered_manifest_excludes_stale_files(self):
        from app.domain.models.file import FileInfo
        from app.domain.services.flows.plan_act import PlanActFlow

        files = [
            FileInfo(
                filename="old-report.md",
                file_path="/workspace/s1/runs/run-1/reports/old-report.md",
                metadata={"delivery_scope": "run-1"},
            ),
            FileInfo(
                filename="current-report.md",
                file_path="/workspace/s1/runs/run-2/reports/current-report.md",
                metadata={"delivery_scope": "run-2"},
            ),
        ]

        filtered = PlanActFlow._filter_files_for_delivery_scope(
            files,
            "run-2",
            "/workspace/s1/runs/run-2",
        )
        manifest = PlanActFlow._build_artifact_manifest([{"filename": file_info.filename} for file_info in filtered])

        assert "current-report.md" in manifest
        assert "old-report.md" not in manifest

    def test_report_attachments_instance_variable_initialized(self):
        """_report_attachments must be initialized as an empty list in __init__."""
        # Import only the class — do not instantiate (requires heavy deps).
        # Inspect the source to confirm the attribute is set in __init__.
        import inspect

        from app.domain.services.flows.plan_act import PlanActFlow

        source = inspect.getsource(PlanActFlow.__init__)
        assert "_report_attachments" in source
        assert "list[dict[str, str]]" in source
