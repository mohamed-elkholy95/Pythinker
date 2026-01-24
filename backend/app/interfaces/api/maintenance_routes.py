"""
API routes for database maintenance operations.

These endpoints allow administrators to:
- Check session data health
- Clean up corrupted attachments
- Perform other maintenance tasks

Note: These endpoints should be protected in production environments.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from app.infrastructure.storage.mongodb import get_mongodb
from app.core.config import get_settings
from app.application.services.maintenance_service import MaintenanceService
import logging

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


class SessionHealthResponse(BaseModel):
    """Response schema for session health check"""
    session_id: str
    found: bool
    status: Optional[str] = None
    total_events: Optional[int] = None
    events_with_attachments: Optional[int] = None
    total_attachments: Optional[int] = None
    valid_attachments: Optional[int] = None
    invalid_attachments: Optional[int] = None
    is_healthy: Optional[bool] = None
    issues: Optional[list] = None
    error: Optional[str] = None


@router.get("/health/session/{session_id}", response_model=SessionHealthResponse)
async def get_session_health(session_id: str):
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup/attachments", response_model=CleanupResponse)
async def cleanup_invalid_attachments(
    session_id: Optional[str] = Query(None, description="Specific session to clean up"),
    dry_run: bool = Query(True, description="If true, only reports what would be cleaned")
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
        result = await service.cleanup_invalid_attachments(
            session_id=session_id,
            dry_run=dry_run
        )
        return CleanupResponse(**result)
    except Exception as e:
        logger.exception(f"Cleanup operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cleanup/attachments/preview", response_model=CleanupResponse)
async def preview_attachment_cleanup(
    session_id: Optional[str] = Query(None, description="Specific session to check")
):
    """
    Preview what would be cleaned without making any changes.

    This is equivalent to calling POST /cleanup/attachments with dry_run=true.
    """
    try:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        service = MaintenanceService(db)
        result = await service.cleanup_invalid_attachments(
            session_id=session_id,
            dry_run=True
        )
        return CleanupResponse(**result)
    except Exception as e:
        logger.exception(f"Preview operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
