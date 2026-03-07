"""Tests for delivery-scope filtering in PlanActFlow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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


@pytest.mark.asyncio
async def test_load_scoped_session_files_for_summary_sets_delivery_channel_and_filters_files() -> None:
    from app.domain.services.flows.plan_act import PlanActFlow

    flow = PlanActFlow.__new__(PlanActFlow)
    flow.executor = MagicMock()
    flow._delivery_scope_id = "run-2"
    flow._delivery_scope_root = "/workspace/s1/runs/run-2"
    flow._session_id = "session-1"
    flow._session_repository = MagicMock(
        find_by_id=AsyncMock(
            return_value=SimpleNamespace(
                source="telegram",
                files=[
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
                ],
            )
        )
    )

    result = await flow._load_scoped_session_files_for_summary()

    flow.executor.set_delivery_channel.assert_called_once_with("telegram")
    assert [file_info.filename for file_info in result] == ["current-report.md"]


@pytest.mark.asyncio
async def test_load_scoped_session_files_for_summary_clears_stale_delivery_channel_on_lookup_error() -> None:
    from app.domain.services.flows.plan_act import PlanActFlow

    flow = PlanActFlow.__new__(PlanActFlow)
    flow.executor = MagicMock()
    flow._delivery_scope_id = "run-2"
    flow._delivery_scope_root = "/workspace/s1/runs/run-2"
    flow._session_id = "session-1"
    flow._session_repository = MagicMock(find_by_id=AsyncMock(side_effect=RuntimeError("session lookup failed")))

    result = await flow._load_scoped_session_files_for_summary()

    flow.executor.set_delivery_channel.assert_called_once_with(None)
    assert result == []
