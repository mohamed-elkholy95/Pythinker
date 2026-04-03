"""Diagnostics endpoints (opt-in, development-oriented)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.diagnostics import tail_container_logs_preview
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.diagnostics import ContainerLogsPreviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _sync_container_logs() -> ContainerLogsPreviewResponse:
    settings = get_settings()
    if not settings.container_log_preview_enabled:
        return ContainerLogsPreviewResponse(
            enabled=False,
            message="Set CONTAINER_LOG_PREVIEW_ENABLED=true to enable (requires Docker socket).",
        )
    try:
        raw, docker_hint = tail_container_logs_preview()
    except Exception as e:
        logger.warning("container log tail failed: %s: %r", type(e).__name__, e)
        return ContainerLogsPreviewResponse(
            enabled=True,
            message=f"Could not read container logs: {type(e).__name__}",
        )
    return ContainerLogsPreviewResponse(
        enabled=True,
        backend=raw.get("backend", []),
        sandbox=raw.get("sandbox", []),
        message=docker_hint,
    )


@router.get("/container-logs", response_model=APIResponse[ContainerLogsPreviewResponse])
async def get_container_logs_preview(
    _current_user: User = Depends(get_current_user),
) -> APIResponse[ContainerLogsPreviewResponse]:
    """Return recent log lines from running backend and sandbox containers.

    Disabled by default. Enable ``CONTAINER_LOG_PREVIEW_ENABLED`` only in trusted
    environments — log lines may contain sensitive data.
    """
    payload = await asyncio.to_thread(_sync_container_logs)
    return APIResponse.success(payload)
