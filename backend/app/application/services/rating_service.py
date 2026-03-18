"""Application service for report ratings."""

from functools import lru_cache

from app.infrastructure.models.documents import RatingDocument


class RatingService:
    """Persist rating submissions."""

    async def submit_rating(
        self,
        session_id: str,
        report_id: str,
        user_id: str,
        user_email: str,
        user_name: str,
        rating: int,
        feedback: str | None = None,
    ) -> None:
        doc = RatingDocument(
            session_id=session_id,
            report_id=report_id,
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            rating=rating,
            feedback=feedback,
        )
        await doc.insert()


@lru_cache
def get_rating_service() -> RatingService:
    return RatingService()
