"""Tests for CronTool — schedule, list, cancel actions."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.services.tools.cron_tool import CronTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cron_service() -> AsyncMock:
    """Create a mock satisfying CronServiceProtocol."""
    svc = AsyncMock()
    svc.add_job = AsyncMock(return_value="job-abc123")
    svc.list_jobs = AsyncMock(return_value=[])
    svc.remove_job = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def cron_tool(mock_cron_service: AsyncMock) -> CronTool:
    return CronTool(cron_service=mock_cron_service, user_id="user-42")


# ---------------------------------------------------------------------------
# schedule action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_creates_job(cron_tool: CronTool, mock_cron_service: AsyncMock) -> None:
    """Schedule action delegates to cron_service.add_job and returns the job ID."""
    result = await cron_tool.execute(
        action="schedule",
        description="Daily standup reminder",
        cron_expr="0 9 * * *",
        timezone="America/New_York",
    )

    assert result.success is True
    assert "job-abc123" in (result.message or "")
    assert result.data["job_id"] == "job-abc123"
    assert result.data["cron_expr"] == "0 9 * * *"
    assert result.data["timezone"] == "America/New_York"

    mock_cron_service.add_job.assert_awaited_once_with(
        user_id="user-42",
        description="Daily standup reminder",
        cron_expr="0 9 * * *",
        timezone="America/New_York",
    )


@pytest.mark.asyncio
async def test_schedule_defaults_timezone_to_utc(
    cron_tool: CronTool,
    mock_cron_service: AsyncMock,
) -> None:
    """When timezone is omitted, defaults to UTC."""
    result = await cron_tool.execute(
        action="schedule",
        description="Nightly backup",
        cron_expr="0 2 * * *",
    )

    assert result.success is True
    assert result.data["timezone"] == "UTC"
    mock_cron_service.add_job.assert_awaited_once()
    call_kwargs = mock_cron_service.add_job.call_args.kwargs
    assert call_kwargs["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_schedule_without_description_returns_error(cron_tool: CronTool) -> None:
    """Schedule action without description returns a validation error."""
    result = await cron_tool.execute(
        action="schedule",
        cron_expr="0 9 * * *",
    )

    assert result.success is False
    assert "description" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_schedule_without_cron_expr_returns_error(cron_tool: CronTool) -> None:
    """Schedule action without cron_expr returns a validation error."""
    result = await cron_tool.execute(
        action="schedule",
        description="Missing cron",
    )

    assert result.success is False
    assert "cron_expr" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_schedule_handles_service_exception(
    cron_tool: CronTool,
    mock_cron_service: AsyncMock,
) -> None:
    """Schedule action wraps exceptions from the cron service."""
    mock_cron_service.add_job.side_effect = ValueError("bad timezone 'Mars/Olympus'")

    result = await cron_tool.execute(
        action="schedule",
        description="Bad tz",
        cron_expr="0 9 * * *",
        timezone="Mars/Olympus",
    )

    assert result.success is False
    assert "Mars/Olympus" in (result.message or "")


# ---------------------------------------------------------------------------
# list action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_formatted_jobs(
    cron_tool: CronTool,
    mock_cron_service: AsyncMock,
) -> None:
    """List action returns a human-readable list of jobs."""
    mock_cron_service.list_jobs.return_value = [
        {
            "id": "abc1",
            "name": "Morning report",
            "cron_expr": "0 8 * * *",
            "timezone": "UTC",
            "next_run": "2026-03-03 08:00 UTC",
            "enabled": True,
        },
        {
            "id": "def2",
            "name": "Weekly digest",
            "cron_expr": "0 10 * * 1",
            "timezone": "Europe/London",
            "next_run": "2026-03-09 10:00 UTC",
            "enabled": True,
        },
    ]

    result = await cron_tool.execute(action="list")

    assert result.success is True
    assert "abc1" in (result.message or "")
    assert "def2" in (result.message or "")
    assert "Morning report" in (result.message or "")
    assert len(result.data["jobs"]) == 2
    mock_cron_service.list_jobs.assert_awaited_once_with(user_id="user-42")


@pytest.mark.asyncio
async def test_list_empty(cron_tool: CronTool, mock_cron_service: AsyncMock) -> None:
    """List action with no jobs returns a friendly message."""
    mock_cron_service.list_jobs.return_value = []

    result = await cron_tool.execute(action="list")

    assert result.success is True
    assert "no scheduled" in (result.message or "").lower()
    assert result.data["jobs"] == []


# ---------------------------------------------------------------------------
# cancel action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_removes_job(
    cron_tool: CronTool,
    mock_cron_service: AsyncMock,
) -> None:
    """Cancel action delegates to cron_service.remove_job."""
    mock_cron_service.remove_job.return_value = True

    result = await cron_tool.execute(action="cancel", job_id="abc1")

    assert result.success is True
    assert "abc1" in (result.message or "")
    assert result.data["cancelled"] is True
    mock_cron_service.remove_job.assert_awaited_once_with(job_id="abc1")


@pytest.mark.asyncio
async def test_cancel_nonexistent_job(
    cron_tool: CronTool,
    mock_cron_service: AsyncMock,
) -> None:
    """Cancel action for a non-existent job returns an error."""
    mock_cron_service.remove_job.return_value = False

    result = await cron_tool.execute(action="cancel", job_id="ghost")

    assert result.success is False
    assert "not found" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_cancel_without_job_id_returns_error(cron_tool: CronTool) -> None:
    """Cancel action without job_id returns a validation error."""
    result = await cron_tool.execute(action="cancel")

    assert result.success is False
    assert "job_id" in (result.message or "").lower()


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_action_returns_error(cron_tool: CronTool) -> None:
    """An unrecognised action returns an error result."""
    result = await cron_tool.execute(action="purge")

    assert result.success is False
    assert "unknown action" in (result.message or "").lower()


# ---------------------------------------------------------------------------
# Tool schema registration
# ---------------------------------------------------------------------------


def test_tool_schema_registered(cron_tool: CronTool) -> None:
    """CronTool exposes exactly one tool definition with the expected name."""
    tools = cron_tool.get_tools()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "schedule_task"
    assert "action" in tools[0]["function"]["parameters"]["properties"]
