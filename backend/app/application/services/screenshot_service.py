"""Screenshot capture service for session replay."""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from uuid import uuid4

from app.core.config import get_settings
from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot
from app.domain.repositories.screenshot_repository import ScreenshotRepository
from app.infrastructure.observability.prometheus_metrics import (
    record_screenshot_capture,
    record_screenshot_fetch,
)

logger = logging.getLogger(__name__)


class ScreenshotCircuitState(str, Enum):
    """Screenshot circuit breaker states (Priority 2: prevent cascading failures)."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Skip screenshots after failures
    HALF_OPEN = "half_open"  # Testing recovery


class ScreenshotCircuitBreaker:
    """Circuit breaker for screenshot capture to prevent cascading failures.

    Priority 2: Screenshot Service Reliability
    - Opens circuit after N consecutive failures
    - Tests recovery after timeout
    - Tracks state transitions via metrics
    """

    def __init__(
        self,
        max_consecutive_failures: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self._state = ScreenshotCircuitState.CLOSED
        self._consecutive_failures = 0
        self._max_consecutive_failures = max_consecutive_failures
        self._recovery_timeout = recovery_timeout
        self._opened_at: float | None = None
        self._consecutive_successes = 0

    def is_allowed(self) -> bool:
        """Check if screenshot capture is allowed."""
        if self._state == ScreenshotCircuitState.CLOSED:
            return True

        if self._state == ScreenshotCircuitState.OPEN:
            # Check if enough time has passed for recovery test
            if self._opened_at and (time.time() - self._opened_at) >= self._recovery_timeout:
                self._transition_to(ScreenshotCircuitState.HALF_OPEN)
                logger.info("Screenshot circuit breaker: OPEN -> HALF_OPEN (testing recovery)")
                return True  # Allow one test request
            return False  # Circuit still open

        # HALF_OPEN: allow the request to test recovery
        return True

    def record_success(self) -> None:
        """Record successful screenshot capture."""
        self._consecutive_failures = 0

        if self._state == ScreenshotCircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= 2:  # Require 2 successes to close
                self._transition_to(ScreenshotCircuitState.CLOSED)
                logger.info("Screenshot circuit breaker: HALF_OPEN -> CLOSED (recovery successful)")
                self._consecutive_successes = 0

    def record_failure(self) -> None:
        """Record failed screenshot capture."""
        self._consecutive_failures += 1
        self._consecutive_successes = 0

        if self._state == ScreenshotCircuitState.CLOSED:
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._transition_to(ScreenshotCircuitState.OPEN)
                self._opened_at = time.time()
                logger.warning(
                    f"Screenshot circuit breaker: CLOSED -> OPEN after {self._consecutive_failures} failures"
                )

        elif self._state == ScreenshotCircuitState.HALF_OPEN:
            # Failed during recovery test, go back to OPEN
            self._transition_to(ScreenshotCircuitState.OPEN)
            self._opened_at = time.time()
            logger.warning("Screenshot circuit breaker: HALF_OPEN -> OPEN (recovery failed)")

    def _transition_to(self, new_state: ScreenshotCircuitState) -> None:
        """Transition to new state and record metrics."""
        self._state = new_state

        # Record state to metrics
        from app.infrastructure.observability.prometheus_metrics import screenshot_circuit_state

        state_value = {"closed": 0, "half_open": 1, "open": 2}
        screenshot_circuit_state.set({"state": new_state.value}, state_value[new_state.value])

    @property
    def state(self) -> ScreenshotCircuitState:
        """Get current circuit state."""
        return self._state


@dataclass
class ToolExecutionContext:
    """Context describing the visual tool currently executing."""

    tool_call_id: str | None = None
    tool_name: str | None = None
    function_name: str | None = None
    action_type: str | None = None


class ScreenshotCaptureService:
    """Captures screenshots during session execution for later replay."""
    MAX_PERIODIC_FAILURES = 3

    def __init__(
        self,
        sandbox,
        session_id: str,
        repository: ScreenshotRepository | None = None,
        mongodb=None,
    ):
        self._sandbox = sandbox
        self._session_id = session_id
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._periodic_task: asyncio.Task | None = None
        self._consecutive_failures = 0
        self._max_periodic_failures = self.MAX_PERIODIC_FAILURES
        if repository is None:
            from app.infrastructure.repositories.mongo_screenshot_repository import MongoScreenshotRepository

            repository = MongoScreenshotRepository()
        self._repository = repository
        if mongodb is None:
            from app.infrastructure.storage.mongodb import get_mongodb

            mongodb = get_mongodb()
        self._mongodb = mongodb
        self._settings = get_settings()

        # Priority 2: Initialize circuit breaker
        if self._settings.screenshot_circuit_breaker_enabled:
            self._circuit_breaker = ScreenshotCircuitBreaker(
                max_consecutive_failures=self._settings.screenshot_max_consecutive_failures,
                recovery_timeout=self._settings.screenshot_circuit_recovery_seconds,
            )
        else:
            self._circuit_breaker = None
        self._tool_context: ToolExecutionContext | None = None

    def set_tool_context(
        self,
        *,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        function_name: str | None = None,
        action_type: str | None = None,
    ) -> None:
        """Track active tool metadata for periodic captures."""
        self._tool_context = ToolExecutionContext(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            action_type=action_type,
        )

    def clear_tool_context(self, tool_call_id: str | None = None) -> None:
        """Clear tracked tool metadata.

        If a tool_call_id is provided, only clears when it matches the active context.
        This avoids clearing context from unrelated tool events.
        """
        if self._tool_context is None:
            return

        if (
            tool_call_id
            and self._tool_context.tool_call_id
            and self._tool_context.tool_call_id != tool_call_id
        ):
            return

        self._tool_context = None

    async def capture(
        self,
        trigger: ScreenshotTrigger,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        function_name: str | None = None,
        action_type: str | None = None,
    ) -> SessionScreenshot | None:
        """Capture a screenshot. Never raises -- returns None on failure.

        Priority 2: Circuit breaker prevents cascading failures.
        """
        # Priority 2: Check circuit breaker before attempting capture
        if self._circuit_breaker and not self._circuit_breaker.is_allowed():
            logger.debug(
                f"Screenshot capture skipped for session {self._session_id}: "
                f"circuit breaker {self._circuit_breaker.state.value}"
            )
            return None

        start_time = time.perf_counter()
        status = "error"
        size_bytes = 0

        # Enrich periodic screenshots with the latest visual tool context.
        if trigger == ScreenshotTrigger.PERIODIC and self._tool_context:
            tool_call_id = tool_call_id or self._tool_context.tool_call_id
            tool_name = tool_name or self._tool_context.tool_name
            function_name = function_name or self._tool_context.function_name
            action_type = action_type or self._tool_context.action_type

        try:
            async with self._lock:
                quality = self._settings.screenshot_quality
                scale = self._settings.screenshot_scale

                # Priority 2: Exponential backoff retry
                response = await self._get_screenshot_with_retry(quality, scale)
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
                status = "success"
                size_bytes = screenshot.size_bytes
                self._consecutive_failures = 0

                # Priority 2: Record success in circuit breaker
                if self._circuit_breaker:
                    self._circuit_breaker.record_success()

                logger.debug(
                    "Captured screenshot %s seq=%d trigger=%s size=%d",
                    screenshot_id,
                    screenshot.sequence_number,
                    trigger.value,
                    size_bytes,
                )
                return screenshot

        except Exception as e:
            self._consecutive_failures += 1

            # Priority 2: Record failure in circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()

            logger.debug(
                "Screenshot capture failed for session %s (trigger=%s): %s",
                self._session_id,
                trigger.value,
                str(e),
                exc_info=True,
            )
            if (
                trigger == ScreenshotTrigger.PERIODIC
                and self._periodic_task
                and not self._periodic_task.done()
                and self._consecutive_failures >= self._max_periodic_failures
            ):
                logger.warning(
                    "Stopping periodic screenshot capture for session %s after %d consecutive failures",
                    self._session_id,
                    self._consecutive_failures,
                )
                await self.stop_periodic()
            return None
        finally:
            record_screenshot_capture(
                trigger=trigger.value,
                status=status,
                latency=max(0.0, time.perf_counter() - start_time),
                size_bytes=size_bytes,
            )

    async def _get_screenshot_with_retry(self, quality: int, scale: float):
        """Get screenshot with exponential backoff retry.

        Priority 2: Screenshot Service Reliability - retry logic to handle transient failures.

        Args:
            quality: JPEG quality (1-100)
            scale: Scale factor (0.0-1.0)

        Returns:
            Response with screenshot content

        Raises:
            Exception: If all retries fail
        """
        max_attempts = self._settings.screenshot_http_retry_attempts
        base_delay = self._settings.screenshot_http_retry_delay

        last_exception = None

        for attempt in range(max_attempts):
            try:
                response = await self._sandbox.get_screenshot(quality=quality, scale=scale)
                if response and response.content:
                    if attempt > 0:
                        # Record successful retry
                        from app.infrastructure.observability.prometheus_metrics import (
                            screenshot_retry_attempts_total,
                        )

                        screenshot_retry_attempts_total.inc({})
                        logger.info(f"Screenshot capture succeeded on retry attempt {attempt + 1}/{max_attempts}")
                    return response

            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    delay = base_delay * (2**attempt)
                    logger.debug(
                        f"Screenshot capture attempt {attempt + 1}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        f"Screenshot capture failed after {max_attempts} attempts: {e}",
                        exc_info=True,
                    )

        # All attempts failed
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Screenshot capture failed after {max_attempts} attempts")

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


class ScreenshotQueryService:
    """Read/query screenshot metadata and bytes for replay endpoints."""

    def __init__(self, repository: ScreenshotRepository | None = None, mongodb=None) -> None:
        if repository is None:
            from app.infrastructure.repositories.mongo_screenshot_repository import MongoScreenshotRepository

            repository = MongoScreenshotRepository()
        self._repository = repository
        if mongodb is None:
            from app.infrastructure.storage.mongodb import get_mongodb

            mongodb = get_mongodb()
        self._mongodb = mongodb

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all screenshots for a session."""
        return await self._repository.delete_by_session(session_id)

    async def list_by_session(self, session_id: str, limit: int, offset: int) -> tuple[list[SessionScreenshot], int]:
        """Fetch paginated screenshot metadata plus total count."""
        screenshots = await self._repository.find_by_session(session_id, limit=limit, offset=offset)
        total = await self._repository.count_by_session(session_id)
        return screenshots, total

    async def get_image_bytes(self, session_id: str, screenshot_id: str, thumbnail: bool) -> bytes | None:
        """Fetch screenshot image bytes, or None when not found/mismatched."""
        start_time = time.perf_counter()
        access = "thumbnail" if thumbnail else "full"
        status = "error"
        size_bytes = 0
        try:
            screenshot = await self._repository.find_by_id(screenshot_id)
            if not screenshot or screenshot.session_id != session_id:
                return None

            file_id = (
                screenshot.thumbnail_file_id
                if thumbnail and screenshot.thumbnail_file_id
                else screenshot.gridfs_file_id
            )
            image_data = await self._mongodb.get_screenshot(file_id)
            if image_data:
                status = "success"
                size_bytes = len(image_data)
            return image_data
        finally:
            record_screenshot_fetch(
                access=access,
                status=status,
                latency=max(0.0, time.perf_counter() - start_time),
                size_bytes=size_bytes,
            )


@lru_cache
def get_screenshot_query_service() -> ScreenshotQueryService:
    """Singleton screenshot query service for API dependencies."""
    return ScreenshotQueryService()
