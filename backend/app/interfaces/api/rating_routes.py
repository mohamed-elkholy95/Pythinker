"""Rating API endpoints.

This module provides endpoints for submitting ratings on reports.
Currently, ratings are logged for metrics collection.
In the future, this could persist to a database for analytics.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user

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
    request: RatingRequest, current_user: User = Depends(get_current_user)
) -> RatingResponse:
    """Submit a rating for a report.

    Args:
        request: The rating request containing session_id, report_id,
                 rating (1-5), and optional feedback.
        current_user: The authenticated user submitting the rating.

    Returns:
        RatingResponse indicating the rating was accepted.
    """
    logger.info(
        "Rating received",
        extra={
            "session_id": request.session_id,
            "report_id": request.report_id,
            "rating": request.rating,
            "feedback": request.feedback,
        },
    )
    return RatingResponse(
        status="accepted",
        message=f"Rating of {request.rating}/5 recorded",
    )
