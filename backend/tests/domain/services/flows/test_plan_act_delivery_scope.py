"""Tests for delivery-scope filtering in PlanActFlow."""

from __future__ import annotations

from app.domain.models.file import FileInfo


def test_filter_session_files_for_active_delivery_scope_prefers_metadata() -> None:
    """Only files tagged to the active scope should be eligible for delivery."""
    from app.domain.services.flows.plan_act import PlanActFlow

    active_scope = "run-2"
    scope_root = "/workspace/s1/runs/run-2"
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

    result = PlanActFlow._filter_files_for_delivery_scope(files, active_scope, scope_root)

    assert [file_info.filename for file_info in result] == ["current-report.md"]


def test_filter_session_files_for_delivery_scope_passthrough_when_scope_disabled() -> None:
    """Legacy behavior should remain unchanged when scope isolation is off."""
    from app.domain.services.flows.plan_act import PlanActFlow

    files = [
        FileInfo(filename="report-1.md", file_path="/workspace/s1/report-1.md"),
        FileInfo(filename="report-2.md", file_path="/workspace/s1/report-2.md"),
    ]

    result = PlanActFlow._filter_files_for_delivery_scope(files, None, None)

    assert result == files
