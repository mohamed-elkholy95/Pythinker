from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models.agent_usage import AgentRun, AgentRunStatus
from app.infrastructure.models.documents import AgentRunDocument
from app.infrastructure.repositories.mongo_usage_repository import MongoUsageRepository

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_insert_agent_run_returns_none_when_insert_fails() -> None:
    from types import SimpleNamespace

    repository = MongoUsageRepository()
    run = AgentRun(
        run_id="run-1",
        user_id="user-1",
        session_id="session-1",
        status=AgentRunStatus.RUNNING,
        started_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
    )
    fake_doc = SimpleNamespace(insert=AsyncMock(side_effect=RuntimeError("insert failed")))

    with patch.object(AgentRunDocument, "from_domain", return_value=fake_doc):
        stored = await repository.insert_agent_run(run)

    assert stored is None


@pytest.mark.asyncio
async def test_list_agent_runs_skips_invalid_documents() -> None:
    repository = MongoUsageRepository()
    valid_run = AgentRun(
        run_id="run-1",
        user_id="user-1",
        session_id="session-1",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
    )
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=[valid_run, {"run_id": "broken"}])

    with patch.object(AgentRunDocument, "find", return_value=cursor):
        runs = await repository.list_agent_runs("user-1", datetime(2026, 3, 1, tzinfo=UTC))

    assert runs == [valid_run]
