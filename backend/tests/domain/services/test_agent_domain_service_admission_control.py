import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.session import AgentMode, ResearchMode, Session, SessionWorkloadClass
from app.domain.services.agent_domain_service import AgentDomainService


def _build_service() -> AgentDomainService:
    return AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=AsyncMock(),
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=AsyncMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


def test_classify_workload_marks_discuss_and_fast_search_as_interactive() -> None:
    service = _build_service()
    discuss_session = Session(
        id="session-discuss",
        user_id="user-1",
        agent_id="agent-1",
        mode=AgentMode.DISCUSS,
        research_mode=ResearchMode.FAST_SEARCH,
    )
    deep_research_session = Session(
        id="session-heavy",
        user_id="user-1",
        agent_id="agent-1",
        mode=AgentMode.AGENT,
        research_mode=ResearchMode.DEEP_RESEARCH,
    )

    assert service._classify_workload_class(discuss_session) == SessionWorkloadClass.INTERACTIVE
    assert service._classify_workload_class(deep_research_session) == SessionWorkloadClass.HEAVY


def test_select_next_execution_workload_breaks_interactive_burst_when_heavy_waits() -> None:
    service = _build_service()
    service._last_execution_slot_class = SessionWorkloadClass.INTERACTIVE
    service._consecutive_execution_slot_grants = service.MAX_INTERACTIVE_EXECUTION_BURST

    selected = service._select_next_execution_workload_class(interactive_waiting=2, heavy_waiting=1)

    assert selected == SessionWorkloadClass.HEAVY

    service._record_execution_slot_grant(selected)

    assert service._last_execution_slot_class == SessionWorkloadClass.HEAVY
    assert service._consecutive_execution_slot_grants == 1


async def test_acquire_execution_slot_cleans_up_waiter_on_timeout_cancellation() -> None:
    service = _build_service()
    service._max_execution_slots = 0
    service._agent_execution_semaphore = asyncio.Semaphore(0)
    session = Session(
        id="session-timeout",
        user_id="user-1",
        agent_id="agent-1",
        mode=AgentMode.DISCUSS,
        research_mode=ResearchMode.FAST_SEARCH,
    )

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(service._acquire_execution_slot(session), timeout=0.01)

    assert service._waiting_execution_slots[SessionWorkloadClass.INTERACTIVE] == 0
    assert service._execution_slots_in_use == 0
