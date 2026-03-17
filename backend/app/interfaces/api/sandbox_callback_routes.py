"""Sandbox callback receiver routes.

These endpoints receive events, progress updates, and resource requests
from sandbox containers. Authenticated via X-Sandbox-Callback-Token header.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox/callback", tags=["sandbox-callback"])


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


async def verify_sandbox_callback_token(
    x_sandbox_callback_token: str = Header(...),
) -> str:
    """Validate the sandbox callback token."""
    settings = get_settings()
    expected = settings.sandbox_callback_token
    if not expected or x_sandbox_callback_token != expected:
        raise HTTPException(status_code=401, detail="Invalid sandbox callback token")
    return x_sandbox_callback_token


@router.post("/event", response_model=CallbackResponse)
async def receive_event(
    body: CallbackEventRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Receive a sandbox event (crash, OOM, timeout, ready)."""
    logger.info(
        "Sandbox callback event: type=%s session=%s details=%s",
        body.type,
        body.session_id,
        body.details,
    )
    return CallbackResponse(message=f"Event '{body.type}' received")


@router.post("/progress", response_model=CallbackResponse)
async def receive_progress(
    body: CallbackProgressRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Receive a progress update from the sandbox."""
    logger.info(
        "Sandbox callback progress: session=%s step=%s percent=%d",
        body.session_id,
        body.step,
        body.percent,
    )
    return CallbackResponse(message="Progress received")


@router.post("/request", response_model=CallbackResponse)
async def receive_resource_request(
    body: CallbackResourceRequest,
    _token: str = Depends(verify_sandbox_callback_token),
) -> CallbackResponse:
    """Handle a resource request from the sandbox."""
    logger.info(
        "Sandbox callback resource request: type=%s params=%s",
        body.type,
        body.params,
    )
    return CallbackResponse(
        message=f"Resource request '{body.type}' received",
        data={"status": "pending"},
    )
