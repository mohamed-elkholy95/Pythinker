from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.framework.db import get_session
from app.framework.models import AgentSession
from app.framework.schemas import AgentSessionResponse, BootstrapRequest

router = APIRouter(prefix="/api/v1/framework", tags=["framework"])


@router.get("/health")
async def framework_health() -> dict:
    return {"status": "ok", "service": "sandbox-framework"}


@router.post("/bootstrap", response_model=AgentSessionResponse)
async def bootstrap_agent_session(
    payload: BootstrapRequest,
    session: AsyncSession = Depends(get_session),
) -> AgentSessionResponse:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(AgentSession).where(AgentSession.session_id == payload.session_id)
    )
    record = result.scalar_one_or_none()

    if record:
        record.status = payload.status
        record.last_seen_at = now
    else:
        record = AgentSession(
            session_id=payload.session_id,
            status=payload.status,
            created_at=now,
            last_seen_at=now,
        )
        session.add(record)

    await session.commit()
    await session.refresh(record)

    return AgentSessionResponse(
        session_id=record.session_id,
        status=record.status,
        created_at=record.created_at,
        last_seen_at=record.last_seen_at,
    )


@router.get("/sessions/{session_id}", response_model=AgentSessionResponse)
async def get_agent_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> AgentSessionResponse:
    result = await session.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Session not found")

    return AgentSessionResponse(
        session_id=record.session_id,
        status=record.status,
        created_at=record.created_at,
        last_seen_at=record.last_seen_at,
    )
