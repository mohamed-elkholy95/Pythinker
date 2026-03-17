"""Abstract protocol for screenshot binary storage."""

from typing import Protocol


class ScreenshotStorage(Protocol):
    """Protocol for screenshot binary storage (MinIO, S3, etc.).

    Application/domain layers depend on this protocol; infrastructure
    provides the concrete implementation.
    """

    async def store_screenshot(self, image_data: bytes, object_key: str, content_type: str = "image/jpeg") -> str: ...

    async def store_thumbnail(self, image_data: bytes, object_key: str, content_type: str = "image/webp") -> str: ...

    async def get_screenshot(self, object_key: str) -> bytes: ...

    async def get_thumbnail(self, object_key: str) -> bytes: ...

    async def delete_screenshots_by_session(self, session_id: str) -> int: ...
