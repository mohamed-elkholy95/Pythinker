"""Rating API endpoints.

Ratings are persisted to MongoDB and optionally sent via email notification.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.application.services.email_service import EmailService
from app.application.services.rating_service import RatingService
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user, get_email_service, get_rating_service

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
) -> RatingResponse:
    """Submit a rating for a report. Saves to DB and sends email notification."""
    user_name = current_user.fullname or current_user.email

    logger.info(
        "Rating received: %s/5 from %s for session %s",
        request.rating,
        user_name,
        request.session_id,
    )

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
