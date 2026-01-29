"""Screenshot capture service for Pythinker desktop preview.

This service provides a unified interface for capturing screenshots of the
Pythinker sandbox desktop (VNC) for thumbnail previews and visual feedback.
"""

import logging
from typing import Optional
from pydantic import BaseModel

from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.file import FileStorage

logger = logging.getLogger(__name__)


class ScreenshotConfig(BaseModel):
    """Configuration for screenshot capture."""
    quality: int = 75  # JPEG quality (1-100)
    scale: float = 0.5  # Scale factor (0.1-1.0, 50% by default)
    format: str = "jpeg"  # Image format (jpeg or png)
    timeout: float = 5.0  # Timeout in seconds


class ScreenshotService:
    """Service for capturing and storing screenshots from Pythinker sandbox.

    This service captures the entire VNC desktop screen, showing whatever
    is currently displayed (browser, terminal, editor, files, etc.).
    """

    def __init__(
        self,
        sandbox: Sandbox,
        browser: Browser,
        file_storage: FileStorage,
        user_id: str,
        config: Optional[ScreenshotConfig] = None
    ):
        """Initialize screenshot service.

        Args:
            sandbox: Sandbox instance for VNC desktop capture
            browser: Browser instance for fallback capture
            file_storage: File storage service for uploading screenshots
            user_id: User ID for file storage
            config: Screenshot configuration (uses defaults if not provided)
        """
        self._sandbox = sandbox
        self._browser = browser
        self._file_storage = file_storage
        self._user_id = user_id
        self._config = config or ScreenshotConfig()

    async def capture_desktop_screenshot(self) -> Optional[str]:
        """Capture VNC desktop screenshot and upload to storage.

        This captures the entire Pythinker PC screen via VNC, showing
        whatever is currently displayed on the desktop.

        Returns:
            File ID of uploaded screenshot, or None if capture fails
        """
        try:
            return await self._capture_vnc_screenshot()
        except Exception as vnc_error:
            logger.warning(
                f"VNC screenshot capture failed: {vnc_error}, "
                "attempting browser fallback"
            )
            try:
                return await self._capture_browser_fallback()
            except Exception as browser_error:
                logger.error(
                    f"Both VNC and browser screenshot capture failed. "
                    f"VNC: {vnc_error}, Browser: {browser_error}"
                )
                return None

    async def _capture_vnc_screenshot(self) -> str:
        """Capture screenshot from VNC desktop.

        Uses the sandbox VNC screenshot API to capture the entire X11 desktop.

        Returns:
            File ID of uploaded screenshot

        Raises:
            Exception: If VNC capture or upload fails
        """
        logger.debug(
            f"Capturing VNC screenshot: quality={self._config.quality}, "
            f"scale={self._config.scale}, format={self._config.format}"
        )

        # Get VNC desktop screenshot from sandbox
        response = await self._sandbox.get_screenshot(
            quality=self._config.quality,
            scale=self._config.scale,
            format=self._config.format
        )

        screenshot_bytes = response.content
        filename = f"screenshot.{self._config.format}"

        # Upload to file storage
        result = await self._file_storage.upload_file(
            screenshot_bytes,
            filename,
            self._user_id
        )

        logger.debug(
            f"VNC screenshot captured and uploaded: "
            f"file_id={result.file_id}, size={len(screenshot_bytes)} bytes"
        )

        return result.file_id

    async def _capture_browser_fallback(self) -> str:
        """Fallback to browser-only screenshot if VNC fails.

        This only captures the browser window, not the entire desktop.
        Used as a fallback when VNC capture is unavailable.

        Returns:
            File ID of uploaded screenshot

        Raises:
            Exception: If browser capture or upload fails
        """
        logger.debug("Using browser fallback for screenshot capture")

        screenshot_bytes = await self._browser.screenshot()

        # Upload to file storage
        result = await self._file_storage.upload_file(
            screenshot_bytes,
            "screenshot.png",
            self._user_id
        )

        logger.debug(
            f"Browser fallback screenshot uploaded: "
            f"file_id={result.file_id}, size={len(screenshot_bytes)} bytes"
        )

        return result.file_id

    def update_config(self, config: ScreenshotConfig) -> None:
        """Update screenshot configuration.

        Args:
            config: New screenshot configuration
        """
        self._config = config
        logger.debug(f"Screenshot config updated: {config}")
