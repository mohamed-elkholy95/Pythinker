from types import SimpleNamespace

import pytest

from app.core.prometheus_metrics import (
    reset_all_metrics,
    session_reliability_auto_retries_total,
    session_reliability_duplicate_event_drops_total,
    session_reliability_fallback_polls_total,
    session_reliability_max_queue_depth,
    session_reliability_reports_total,
    session_reliability_stale_detections_total,
)
from app.domain.models.session import AgentMode, Session, SessionStatus
from app.interfaces.api.session_routes import get_session_status
from app.interfaces.api.telemetry_routes import receive_session_reliability_diagnostics
from app.interfaces.schemas.session import SessionReliabilityDiagnosticsRequest


class FakeSessionRepository:
    def __init__(self, session: Session | None) -> None:
        self.session = session
        self.saved_sessions: list[Session] = []

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Session | None:
        if self.session and self.session.id == session_id and self.session.user_id == user_id:
            return self.session
        return None

    async def save(self, session: Session) -> None:
        self.session = session
        self.saved_sessions.append(session)


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_all_metrics()
    yield
    reset_all_metrics()


@pytest.mark.asyncio
async def test_posting_reliability_diagnostics_persists_and_round_trips_via_status() -> None:
    session = Session(
        id="session-1",
        user_id="user-1",
        agent_id="agent-1",
        mode=AgentMode.AGENT,
        status=SessionStatus.RUNNING,
    )
    repo = FakeSessionRepository(session)
    current_user = SimpleNamespace(id="user-1")
    payload = SessionReliabilityDiagnosticsRequest(
        auto_retry_count=2,
        fallback_poll_attempts=3,
        stale_detection_count=1,
        duplicate_event_drops=4,
        max_queue_depth=12,
        average_flush_batch_size=6.5,
        max_chunk_processing_duration_ms=18.2,
    )

    response = await receive_session_reliability_diagnostics(
        session_id=session.id,
        payload=payload,
        current_user=current_user,
        session_repo=repo,
    )

    assert response["status"] == "accepted"
    assert repo.saved_sessions
    assert repo.session is not None
    assert repo.session.reliability is not None
    assert repo.session.reliability.auto_retry_count == 2
    assert repo.session.reliability.max_queue_depth == 12

    status = await get_session_status(
        session_id=session.id,
        current_user=current_user,
        agent_service=SimpleNamespace(get_session=repo.find_by_id_and_user_id),
    )

    assert status.data is not None
    assert status.data.reliability is not None
    assert status.data.reliability.auto_retry_count == 2
    assert status.data.reliability.fallback_poll_attempts == 3
    assert status.data.reliability.duplicate_event_drops == 4


@pytest.mark.asyncio
async def test_posting_reliability_diagnostics_records_scorecard_metrics() -> None:
    session = Session(
        id="session-2",
        user_id="user-2",
        agent_id="agent-1",
        mode=AgentMode.AGENT,
        status=SessionStatus.RUNNING,
    )
    repo = FakeSessionRepository(session)
    current_user = SimpleNamespace(id="user-2")
    payload = SessionReliabilityDiagnosticsRequest(
        auto_retry_count=5,
        fallback_poll_attempts=2,
        stale_detection_count=3,
        duplicate_event_drops=7,
        max_queue_depth=20,
        average_flush_batch_size=8.0,
        max_chunk_processing_duration_ms=24.5,
    )

    await receive_session_reliability_diagnostics(
        session_id=session.id,
        payload=payload,
        current_user=current_user,
        session_repo=repo,
    )

    assert session_reliability_reports_total.get({}) == 1
    assert session_reliability_auto_retries_total.get({}) == 5
    assert session_reliability_fallback_polls_total.get({}) == 2
    assert session_reliability_stale_detections_total.get({}) == 3
    assert session_reliability_duplicate_event_drops_total.get({}) == 7

    queue_depth_entry = session_reliability_max_queue_depth.collect()[0]
    assert queue_depth_entry["count"] == 1
    assert queue_depth_entry["sum"] == pytest.approx(20.0)
