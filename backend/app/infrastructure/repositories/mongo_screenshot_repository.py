"""MongoDB implementation of screenshot repository."""

from datetime import datetime

from beanie.operators import In

from app.domain.models.screenshot import SessionScreenshot
from app.infrastructure.models.documents import ScreenshotDocument


class MongoScreenshotRepository:
    """MongoDB implementation of ScreenshotRepository."""

    async def save(self, screenshot: SessionScreenshot) -> None:
        document = ScreenshotDocument.from_domain(screenshot)
        await document.save()

    async def find_by_session(self, session_id: str, limit: int = 500, offset: int = 0) -> list[SessionScreenshot]:
        documents = (
            await ScreenshotDocument.find(ScreenshotDocument.session_id == session_id)
            .sort("+sequence_number")
            .skip(offset)
            .limit(limit)
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    async def find_by_id(self, screenshot_id: str) -> SessionScreenshot | None:
        document = await ScreenshotDocument.find_one(ScreenshotDocument.screenshot_id == screenshot_id)
        return document.to_domain() if document else None

    async def count_by_session(self, session_id: str) -> int:
        return await ScreenshotDocument.find(ScreenshotDocument.session_id == session_id).count()

    async def delete_by_session(self, session_id: str) -> int:
        result = await ScreenshotDocument.find(ScreenshotDocument.session_id == session_id).delete()
        return result.deleted_count if result else 0

    async def find_expired_screenshots(self, before_date: datetime) -> list[SessionScreenshot]:
        """Return all screenshot records older than the cutoff (record-level precision)."""
        docs = await ScreenshotDocument.find(ScreenshotDocument.timestamp < before_date).to_list()
        return [doc.to_domain() for doc in docs]

    async def delete_by_ids(self, screenshot_ids: list[str]) -> int:
        """Delete screenshot documents by their screenshot_id values."""
        if not screenshot_ids:
            return 0
        result = await ScreenshotDocument.find(In(ScreenshotDocument.screenshot_id, screenshot_ids)).delete()
        return result.deleted_count if result else 0
