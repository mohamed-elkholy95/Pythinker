"""Rating API endpoints.

Ratings are persisted to MongoDB and optionally sent via email notification.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.application.services.email_service import EmailService
from app.application.services.rating_service import RatingService
from app.domain.models.user import User
from app.infrastructure.repositories.mongo_session_repository import MongoSessionRepository
from app.interfaces.dependencies import (
    get_current_user,
    get_email_service,
    get_rating_service,
    get_session_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ratings", tags=["ratings"])


class RatingRequest(BaseModel):
    """Request body for submitting a rating."""

    session_id: str
    report_id: str
    rating: int = Field(ge=1, le=5, description="Rating from 1 to 5")
    feedback: str | None = None


class RatingResponse(BaseModel):
    """Response for rating submission."""

    status: str
    message: str


@router.post("", response_model=RatingResponse, status_code=201)
async def submit_rating(
    request: RatingRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    email_service: EmailService = Depends(get_email_service),
    rating_service: RatingService = Depends(get_rating_service),
    session_repository: MongoSessionRepository = Depends(get_session_repository),
) -> RatingResponse:
    """Submit a rating for a report. Saves to DB and sends email notification.

    Priority 6: Session ownership validation - prevents unauthorized users from rating
    other users' sessions.
    """
    user_name = current_user.fullname or current_user.email

    logger.info(
        "Rating received: %s/5 from %s for session %s",
        request.rating,
        user_name,
        request.session_id,
    )

    # Priority 6: Validate session ownership
    try:
        session = await session_repository.get_by_id(request.session_id)
        if not session:
            logger.warning(
                f"Rating attempt for non-existent session {request.session_id} by user {current_user.id}"
            )
            from app.infrastructure.observability.prometheus_metrics import (
                rating_unauthorized_attempts_total,
            )

            rating_unauthorized_attempts_total.inc({})
            raise HTTPException(
                status_code=404,
                detail=f"Session {request.session_id} not found",
            )

        # Verify user owns the session
        if session.user_id != current_user.id:
            logger.warning(
                f"Unauthorized rating attempt: user {current_user.id} tried to rate "
                f"session {request.session_id} owned by user {session.user_id}"
            )
            from app.infrastructure.observability.prometheus_metrics import (
                rating_unauthorized_attempts_total,
            )

            rating_unauthorized_attempts_total.inc({})
            raise HTTPException(
                status_code=403,
                detail="You can only rate your own sessions",
            )

        logger.info(f"Session ownership validated for user {current_user.id}")

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Session validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to validate session ownership",
        ) from e

    await rating_service.submit_rating(
        session_id=request.session_id,
        report_id=request.report_id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_name=user_name,
        rating=request.rating,
        feedback=request.feedback,
    )

    # Send email notification in background
    background_tasks.add_task(
        email_service.send_rating_email,
        user_email=current_user.email,
        user_name=user_name,
        session_id=request.session_id,
        report_id=request.report_id,
        rating=request.rating,
        feedback=request.feedback,
    )

    return RatingResponse(
        status="accepted",
        message=f"Rating of {request.rating}/5 recorded",
    )
