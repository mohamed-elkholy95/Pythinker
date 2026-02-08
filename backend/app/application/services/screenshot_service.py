"""Screenshot capture service for session replay."""

import asyncio
import contextlib
import logging
from uuid import uuid4

from app.core.config import get_settings
from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot
from app.infrastructure.repositories.mongo_screenshot_repository import MongoScreenshotRepository
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class ScreenshotCaptureService:
    """Captures screenshots during session execution for later replay."""

    def __init__(self, sandbox, session_id: str):
        self._sandbox = sandbox
        self._session_id = session_id
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._periodic_task: asyncio.Task | None = None
        self._repository = MongoScreenshotRepository()
        self._mongodb = get_mongodb()
        self._settings = get_settings()

    async def capture(
        self,
        trigger: ScreenshotTrigger,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        function_name: str | None = None,
        action_type: str | None = None,
    ) -> SessionScreenshot | None:
        """Capture a screenshot. Never raises -- returns None on failure."""
        try:
            async with self._lock:
                quality = self._settings.screenshot_quality
                scale = self._settings.screenshot_scale

                response = await self._sandbox.get_screenshot(
                    quality=quality, scale=scale
                )
                image_data = response.content
                if not image_data:
                    return None

                size_bytes = len(image_data)
                screenshot_id = uuid4().hex[:16]
                filename = f"{self._session_id}_{self._sequence:04d}_{trigger.value}.jpg"

                # Store full-res in GridFS
                gridfs_file_id = await self._mongodb.store_screenshot(
                    image_data,
                    filename,
                    {
                        "session_id": self._session_id,
                        "sequence": self._sequence,
                        "trigger": trigger.value,
                    },
                )

                # Store thumbnail
                thumbnail_file_id: str | None = None
                try:
                    thumb_response = await self._sandbox.get_screenshot(
                        quality=self._settings.screenshot_thumbnail_quality,
                        scale=self._settings.screenshot_thumbnail_scale,
                    )
                    if thumb_response.content:
                        thumbnail_file_id = await self._mongodb.store_screenshot(
                            thumb_response.content,
                            f"thumb_{filename}",
                            {
                                "session_id": self._session_id,
                                "sequence": self._sequence,
                                "is_thumbnail": True,
                            },
                        )
                except Exception:
                    logger.debug("Thumbnail capture failed, continuing without")

                screenshot = SessionScreenshot(
                    id=screenshot_id,
                    session_id=self._session_id,
                    sequence_number=self._sequence,
                    gridfs_file_id=gridfs_file_id,
                    thumbnail_file_id=thumbnail_file_id,
                    trigger=trigger,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    function_name=function_name,
                    action_type=action_type,
                    size_bytes=size_bytes,
                )

                await self._repository.save(screenshot)
                self._sequence += 1

                logger.debug(
                    "Captured screenshot %s seq=%d trigger=%s size=%d",
                    screenshot_id,
                    screenshot.sequence_number,
                    trigger.value,
                    size_bytes,
                )
                return screenshot

        except Exception:
            logger.debug(
                "Screenshot capture failed for session %s (trigger=%s)",
                self._session_id,
                trigger.value,
                exc_info=True,
            )
            return None

    async def start_periodic(self, interval: float | None = None) -> None:
        """Start background periodic capture."""
        if self._periodic_task and not self._periodic_task.done():
            return

        capture_interval = interval or self._settings.screenshot_periodic_interval

        async def _periodic_loop() -> None:
            while True:
                await asyncio.sleep(capture_interval)
                await self.capture(ScreenshotTrigger.PERIODIC)

        self._periodic_task = asyncio.create_task(_periodic_loop())
        logger.debug(
            "Started periodic screenshot capture for session %s (interval=%.1fs)",
            self._session_id,
            capture_interval,
        )

    async def stop_periodic(self) -> None:
        """Cancel the periodic capture task."""
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._periodic_task
            self._periodic_task = None
            logger.debug(
                "Stopped periodic screenshot capture for session %s",
                self._session_id,
            )
