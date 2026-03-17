"""Tests for DelegateTool — unified delegation with typed roles and concurrency cap."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.models.delegation import (
    DelegateRequest,
    DelegateRole,
    DelegateStatus,
)
from app.domain.services.tools.delegate_tool import DelegateTool

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_manager(running_count: int = 0) -> AsyncMock:
    """Return an AsyncMock that satisfies the subagent manager duck-type."""
    manager = AsyncMock()
    manager.get_running_count = AsyncMock(return_value=running_count)
    manager.spawn = AsyncMock(return_value="subagent-started")
    return manager


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_empty_task() -> None:
    """An empty task string must be rejected before touching the manager."""
    manager = _make_manager(running_count=0)
    tool = DelegateTool(subagent_manager=manager, max_concurrent=3)

    request = DelegateRequest(task="", role=DelegateRole.EXECUTOR)
    result = await tool.execute(request)

    assert result.status is DelegateStatus.REJECTED
    assert result.error is not None
    assert "empty" in result.error.lower()
    # Manager must not have been called at all.
    manager.get_running_count.assert_not_called()
    manager.spawn.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_over_concurrency_cap() -> None:
    """When running count equals the cap the request must be rejected."""
    manager = _make_manager(running_count=2)
    tool = DelegateTool(subagent_manager=manager, max_concurrent=2)

    request = DelegateRequest(task="Analyse data", role=DelegateRole.ANALYST)
    result = await tool.execute(request)

    assert result.status is DelegateStatus.REJECTED
    assert result.error is not None
    assert "2/2" in result.error
    manager.spawn.assert_not_called()


@pytest.mark.asyncio
async def test_researcher_role_routes_to_research_flow() -> None:
    """RESEARCHER role with a factory must call the factory, not the spawn method."""

    async def _fake_flow(task: str):  # type: ignore[return]
        yield "Research chunk 1"
        yield "Research chunk 2"

    manager = _make_manager(running_count=0)
    factory_calls: list[str] = []

    def _factory(task: str):
        factory_calls.append(task)
        return _fake_flow(task)

    tool = DelegateTool(
        subagent_manager=manager,
        research_flow_factory=_factory,
        max_concurrent=3,
    )

    request = DelegateRequest(task="Research Python 3.12 features", role=DelegateRole.RESEARCHER)
    result = await tool.execute(request)

    # Factory must have been called exactly once with the task text.
    assert factory_calls == ["Research Python 3.12 features"]
    # Result must be COMPLETED (not STARTED — that is the subagent path).
    assert result.status is DelegateStatus.COMPLETED
    # Subagent spawn must NOT have been called.
    manager.spawn.assert_not_called()


def test_all_roles_defined() -> None:
    """DelegateRole must expose exactly the 6 specified members."""
    expected = {"researcher", "executor", "coder", "browser", "analyst", "writer"}
    actual = {role.value for role in DelegateRole}
    assert actual == expected


def test_delegate_request_has_timeout() -> None:
    """DelegateRequest default timeout must be 900 seconds."""
    request = DelegateRequest(task="Write a summary", role=DelegateRole.WRITER)
    assert request.timeout_seconds == 900
