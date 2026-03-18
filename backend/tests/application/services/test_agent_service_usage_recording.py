from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.agent_service import AgentService


async def test_record_usage_start_run_requires_user_and_session() -> None:
    service = object.__new__(AgentService)

    with (
        patch("app.application.services.agent_service.get_usage_service", return_value=AsyncMock()),
        pytest.raises(ValueError, match="start_run requires user_id and session_id"),
    ):
        await AgentService._record_usage(service, action="start_run", session_id="session-1")


async def test_record_usage_finish_run_rejects_invalid_status() -> None:
    service = object.__new__(AgentService)

    with (
        patch("app.application.services.agent_service.get_usage_service", return_value=AsyncMock()),
        pytest.raises(ValueError, match="Invalid agent run status"),
    ):
        await AgentService._record_usage(
            service,
            action="finish_run",
            run_id="run-1",
            status="not-a-status",
        )


async def test_record_usage_tool_call_requires_user_and_session() -> None:
    service = object.__new__(AgentService)

    with (
        patch("app.application.services.agent_service.get_usage_service", return_value=AsyncMock()),
        pytest.raises(ValueError, match="record_tool_call requires user_id and session_id"),
    ):
        await AgentService._record_usage(service, action="record_tool_call", tool_name="search_query")
