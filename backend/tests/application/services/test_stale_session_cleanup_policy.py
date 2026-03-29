import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.services.stale_session_cleanup_policy import StaleSessionCleanupPolicy
from app.domain.models.session import AgentMode, Session, SessionStatus


class FakeSessionRepository:
    def __init__(self, sessions: list[Session]) -> None:
        self._sessions = sessions

    async def find_by_user_id(self, user_id: str) -> list[Session]:
        return [session for session in self._sessions if session.user_id == user_id]


def _build_session(
    session_id: str,
    *,
    status: SessionStatus = SessionStatus.RUNNING,
    updated_at: datetime | None = None,
    sandbox_id: str | None = None,
) -> Session:
    session = Session(
        id=session_id,
        user_id="user-1",
        agent_id="agent-1",
        mode=AgentMode.AGENT,
        status=status,
        sandbox_id=sandbox_id,
    )
    session.updated_at = updated_at or (datetime.now(UTC) - timedelta(minutes=5))
    return session


def _settings(min_age_seconds: float = 30.0) -> SimpleNamespace:
    return SimpleNamespace(stale_session_autostop_min_age_seconds=min_age_seconds)


@pytest.mark.asyncio
async def test_cleanup_only_stops_stale_sessions_without_active_streams(monkeypatch) -> None:
    stale = _build_session("stale-session", sandbox_id="sandbox-stale")
    recent = _build_session("recent-session", updated_at=datetime.now(UTC))
    active_stream = _build_session("streaming-session", sandbox_id="sandbox-streaming")
    completed = _build_session("completed-session", status=SessionStatus.COMPLETED)

    stop_session = AsyncMock()
    close_browser = AsyncMock()

    async def fake_has_active_stream(session_id: str) -> bool:
        return session_id == active_stream.id

    monkeypatch.setattr("app.application.services.stale_session_cleanup_policy.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.application.services.stale_session_cleanup_policy._has_active_chat_stream",
        fake_has_active_stream,
    )

    policy = StaleSessionCleanupPolicy(
        session_repository=FakeSessionRepository([stale, recent, active_stream, completed]),
        stop_session=stop_session,
        close_browser_for_sandbox=close_browser,
    )

    await policy.cleanup_for_user("user-1")

    stop_session.assert_awaited_once_with(stale.id)
    close_browser.assert_awaited_once_with("sandbox-stale")


@pytest.mark.asyncio
async def test_cleanup_caps_each_stale_session_individually(monkeypatch) -> None:
    slow = _build_session("slow-session")
    fast = _build_session("fast-session")
    completed: list[str] = []

    async def stop_session(session_id: str) -> None:
        if session_id == slow.id:
            await asyncio.sleep(0.01)
        completed.append(session_id)

    monkeypatch.setattr("app.application.services.stale_session_cleanup_policy.get_settings", lambda: _settings(0.0))
    monkeypatch.setattr(
        "app.application.services.stale_session_cleanup_policy._has_active_chat_stream",
        AsyncMock(return_value=False),
    )

    policy = StaleSessionCleanupPolicy(
        session_repository=FakeSessionRepository([slow, fast]),
        stop_session=stop_session,
        close_browser_for_sandbox=AsyncMock(),
        per_session_timeout_seconds=0.001,
        total_timeout_seconds=1.0,
    )

    await policy.cleanup_for_user("user-1")

    assert fast.id in completed
    assert slow.id not in completed


@pytest.mark.asyncio
async def test_cleanup_applies_a_total_timeout_cap(monkeypatch) -> None:
    first = _build_session("slow-session-1")
    second = _build_session("slow-session-2")
    started: list[str] = []
    completed: list[str] = []

    async def stop_session(session_id: str) -> None:
        started.append(session_id)
        await asyncio.sleep(0.01)
        completed.append(session_id)

    monkeypatch.setattr("app.application.services.stale_session_cleanup_policy.get_settings", lambda: _settings(0.0))
    monkeypatch.setattr(
        "app.application.services.stale_session_cleanup_policy._has_active_chat_stream",
        AsyncMock(return_value=False),
    )

    policy = StaleSessionCleanupPolicy(
        session_repository=FakeSessionRepository([first, second]),
        stop_session=stop_session,
        close_browser_for_sandbox=AsyncMock(),
        per_session_timeout_seconds=1.0,
        total_timeout_seconds=0.001,
    )

    await policy.cleanup_for_user("user-1")

    assert started
    assert completed == []
