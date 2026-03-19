"""Sandbox callback receiver routes.

These endpoints receive events, progress updates, and resource requests
from sandbox containers. Authenticated via X-Sandbox-Callback-Token header.

Rate-limited per session to prevent a compromised sandbox from flooding
the backend with callback events.
"""

from __future__ import annotations

import logging
import secrets
import time
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


# ---------------------------------------------------------------------------
# Per-session callback rate limiter (in-memory, lightweight)
# ---------------------------------------------------------------------------

# Max callback events per session per window (covers event + progress + request)
_CALLBACK_MAX_PER_WINDOW = 300  # generous but bounded
_CALLBACK_WINDOW_SECONDS = 60

_callback_counters: dict[str, tuple[int, float]] = {}


def _check_callback_rate_limit(identifier: str) -> None:
    """Raise 429 if this identifier exceeds the callback rate limit."""
    now = time.monotonic()
    entry = _callback_counters.get(identifier)
    if entry is not None:
        count, window_start = entry
        if now - window_start < _CALLBACK_WINDOW_SECONDS:
            if count >= _CALLBACK_MAX_PER_WINDOW:
                logger.warning(
                    "Sandbox callback rate limit exceeded for %s (%d/%d in %ds)",
                    identifier,
                    count,
                    _CALLBACK_MAX_PER_WINDOW,
                    _CALLBACK_WINDOW_SECONDS,
                )
                raise HTTPException(
                    status_code=429,
                    detail="Callback rate limit exceeded",
                )
            _callback_counters[identifier] = (count + 1, window_start)
            return
    # New window
    _callback_counters[identifier] = (1, now)

    # Periodic cleanup: remove expired entries every ~100 new windows
    if len(_callback_counters) > 200:
        expired = [k for k, (_, ws) in _callback_counters.items() if now - ws > _CALLBACK_WINDOW_SECONDS]
        for k in expired:
            del _callback_counters[k]


def _get_session_repository() -> SessionRepository:
    """Provide a session repository for sandbox callback routes."""
    from app.interfaces.dependencies import get_session_repository

    return get_session_repository()


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
    _check_callback_rate_limit(body.session_id or "global")

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
    _check_callback_rate_limit(body.session_id)

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
    _check_callback_rate_limit("resource-request")

    logger.info(
        "Sandbox callback resource request: type=%s params=%s",
        body.type,
        body.params,
    )
    return CallbackResponse(
        message=f"Resource request '{body.type}' received",
        data={"status": "pending"},
    )
