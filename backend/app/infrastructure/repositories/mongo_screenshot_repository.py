"""MongoDB implementation of screenshot repository."""

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
