"""
API routes for database maintenance operations.

These endpoints allow administrators to:
- Check session data health
- Clean up corrupted attachments
- Perform other maintenance tasks

Note: These endpoints should be protected in production environments.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.application.services.maintenance_service import MaintenanceService
from app.core.config import get_settings
from app.domain.models.user import User
from app.infrastructure.storage.mongodb import get_mongodb
from app.interfaces.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CleanupResponse(BaseModel):
    """Response schema for cleanup operations"""

    dry_run: bool
    sessions_scanned: int
    sessions_affected: int
    events_cleaned: int
    attachments_removed: int
    affected_sessions: list
    errors: list
    timestamp: str


class StaleSessionCleanupResponse(BaseModel):
    """Response schema for stale session cleanup operations"""

    dry_run: bool
    stale_threshold_minutes: int
    sessions_cleaned: int
    sessions_marked_failed: list
    errors: list
    timestamp: str


class SessionHealthResponse(BaseModel):
    """Response schema for session health check"""

    session_id: str
    found: bool
    status: str | None = None
    total_events: int | None = None
    events_with_attachments: int | None = None
    total_attachments: int | None = None
    valid_attachments: int | None = None
    invalid_attachments: int | None = None
    is_healthy: bool | None = None
    issues: list | None = None
    error: str | None = None


@router.get("/health/session/{session_id}", response_model=SessionHealthResponse)
async def get_session_health(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Check the data health of a specific session.

    Returns information about:
    - Total events and attachments
    - Valid vs invalid attachments
    - Specific issues found (null file_id, missing filename, etc.)
    """
    try:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        service = MaintenanceService(db)
        result = await service.get_session_health(session_id)
        return SessionHealthResponse(**result)
    except Exception as e:
        logger.exception(f"Failed to check session health: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/cleanup/attachments", response_model=CleanupResponse)
async def cleanup_invalid_attachments(
    session_id: str | None = Query(None, description="Specific session to clean up"),
    dry_run: bool = Query(True, description="If true, only reports what would be cleaned"),
    current_user: User = Depends(get_current_user),
):
    """
    Clean up events with invalid attachments (null file_id or filename).

    This fixes issues where event attachments were not properly synced to storage,
    resulting in errors when fetching session data.

    **Important:** Set `dry_run=false` to actually perform the cleanup.
    Default is dry_run=true for safety.

    Args:
        session_id: Optional specific session ID to clean up. If not provided, scans all sessions.
        dry_run: If true (default), only reports what would be cleaned without making changes.

    Returns:
        Statistics about the cleanup operation including affected sessions and attachments.
    """
    try:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        service = MaintenanceService(db)
        result = await service.cleanup_invalid_attachments(session_id=session_id, dry_run=dry_run)
        return CleanupResponse(**result)
    except Exception as e:
        logger.exception(f"Cleanup operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/cleanup/attachments/preview", response_model=CleanupResponse)
async def preview_attachment_cleanup(
    session_id: str | None = Query(None, description="Specific session to check"),
    current_user: User = Depends(get_current_user),
):
    """
    Preview what would be cleaned without making any changes.

    This is equivalent to calling POST /cleanup/attachments with dry_run=true.
    """
    try:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        service = MaintenanceService(db)
        result = await service.cleanup_invalid_attachments(session_id=session_id, dry_run=True)
        return CleanupResponse(**result)
    except Exception as e:
        logger.exception(f"Preview operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/cleanup/stale-sessions", response_model=StaleSessionCleanupResponse)
async def cleanup_stale_running_sessions(
    stale_threshold_minutes: int = Query(30, description="Sessions running longer than this are considered stale"),
    dry_run: bool = Query(True, description="If true, only reports what would be cleaned"),
    current_user: User = Depends(get_current_user),
):
    """
    Clean up sessions stuck in "running" or "initializing" status.

    Sessions can become stuck if the backend crashes or restarts during processing.
    This marks them as failed so users can start new sessions.

    **Important:** Set `dry_run=false` to actually perform the cleanup.
    Default is dry_run=true for safety.

    Args:
        stale_threshold_minutes: Sessions running longer than this are considered stale (default: 30).
        dry_run: If true (default), only reports what would be cleaned without making changes.

    Returns:
        Statistics about the cleanup operation including affected sessions.
    """
    try:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        service = MaintenanceService(db)
        result = await service.cleanup_stale_running_sessions(
            stale_threshold_minutes=stale_threshold_minutes,
            dry_run=dry_run,
        )
        return StaleSessionCleanupResponse(**result)
    except Exception as e:
        logger.exception(f"Stale session cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/cleanup/stale-sessions/preview", response_model=StaleSessionCleanupResponse)
async def preview_stale_session_cleanup(
    stale_threshold_minutes: int = Query(30, description="Sessions running longer than this are considered stale"),
    current_user: User = Depends(get_current_user),
):
    """
    Preview stale sessions that would be cleaned without making changes.
    """
    try:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        service = MaintenanceService(db)
        result = await service.cleanup_stale_running_sessions(
            stale_threshold_minutes=stale_threshold_minutes,
            dry_run=True,
        )
        return StaleSessionCleanupResponse(**result)
    except Exception as e:
        logger.exception(f"Preview operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
