"""Sandbox callback receiver routes.

These endpoints receive events, progress updates, and resource requests
from sandbox containers. Authenticated via X-Sandbox-Callback-Token header.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    PlanningPhase,
    ProgressEvent,
)
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.repositories.mongo_session_repository import (
    MongoSessionRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox/callback", tags=["sandbox-callback"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CallbackEventRequest(BaseModel):
    type: str = Field(..., description="Event type: crash, oom, timeout, ready")
    details: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class CallbackProgressRequest(BaseModel):
    session_id: str
    step: str
    percent: int = Field(ge=0, le=100)
    message: str = ""


class CallbackResourceRequest(BaseModel):
    type: str = Field(..., description="Resource type: upload_url, secret")
    params: dict[str, Any] = Field(default_factory=dict)


class CallbackResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def verify_sandbox_callback_token(
    x_sandbox_callback_token: str = Header(...),
) -> str:
    """Validate the sandbox callback token."""
    settings = get_settings()
    expected = settings.sandbox_callback_token
    if not expected or not secrets.compare_digest(x_sandbox_callback_token, expected):
        raise HTTPException(status_code=401, detail="Invalid sandbox callback token")
    return x_sandbox_callback_token


def _get_session_repository() -> SessionRepository:
    """Provide a session repository for sandbox callback routes."""
    return MongoSessionRepository()


# ---------------------------------------------------------------------------
# Mapping from sandbox event types to domain events
# ---------------------------------------------------------------------------

# Sandbox event types that indicate errors
_ERROR_EVENT_TYPES = frozenset({"crash", "oom", "timeout"})


def _build_domain_event(body: CallbackEventRequest) -> BaseEvent:
    """Convert a sandbox callback event into the appropriate domain event."""
    if body.type in _ERROR_EVENT_TYPES:
        return ErrorEvent(
            error=f"Sandbox {body.type}: {body.details.get('message', body.type)}",
            error_type=f"sandbox_{body.type}",
            recoverable=body.type != "oom",
            error_category="upstream",
            severity="critical" if body.type == "oom" else "error",
            details=body.details or None,
        )

    # Non-error lifecycle events (e.g. "ready") are recorded as progress.
    return ProgressEvent(
        phase=PlanningPhase.HEARTBEAT,
        message=f"Sandbox {body.type}",
        progress_percent=100 if body.type == "ready" else None,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/event", response_model=CallbackResponse)
async def receive_event(
    body: CallbackEventRequest,
    _token: str = Depends(verify_sandbox_callback_token),
    session_repo: SessionRepository = Depends(_get_session_repository),
) -> CallbackResponse:
    """Receive a sandbox event (crash, OOM, timeout, ready).

    Converts the raw callback into a domain event and persists it in the
    session timeline so it is visible via SSE to the frontend.
    """
    logger.info(
        "Sandbox callback event: type=%s session=%s details=%s",
        body.type,
        body.session_id,
        body.details,
    )

    event = _build_domain_event(body)

    if body.session_id:
        try:
            await session_repo.add_event(body.session_id, event)
        except Exception:
            logger.exception(
                "Failed to persist sandbox event for session %s",
                body.session_id,
            )

    return CallbackResponse(message=f"Event '{body.type}' received")


@router.post("/progress", response_model=CallbackResponse)
async def receive_progress(
    body: CallbackProgressRequest,
    _token: str = Depends(verify_sandbox_callback_token),
    session_repo: SessionRepository = Depends(_get_session_repository),
) -> CallbackResponse:
    """Receive a progress update from the sandbox.

    Creates a ``ProgressEvent`` and stores it in the session timeline so
    the frontend can display real-time sandbox progress.
    """
    logger.info(
        "Sandbox callback progress: session=%s step=%s percent=%d",
        body.session_id,
        body.step,
        body.percent,
    )

    event = ProgressEvent(
        phase=PlanningPhase.EXECUTING_SETUP if body.percent < 100 else PlanningPhase.HEARTBEAT,
        message=body.message or f"Sandbox: {body.step}",
        progress_percent=body.percent,
    )

    try:
        await session_repo.add_event(body.session_id, event)
    except Exception:
        logger.exception(
            "Failed to persist sandbox progress for session %s",
            body.session_id,
        )

    return CallbackResponse(message="Progress received")


@router.post("/request", response_model=CallbackResponse)
async def receive_resource_request(
    body: CallbackResourceRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Handle a resource request from the sandbox.

    Resource requests (upload URLs, secrets) require human review.
    The request is logged and returned with a ``pending`` status.
    """
    logger.info(
        "Sandbox callback resource request: type=%s params=%s",
        body.type,
        body.params,
    )
    return CallbackResponse(
        message=f"Resource request '{body.type}' received",
        data={"status": "pending"},
    )
