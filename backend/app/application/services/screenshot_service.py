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
from app.core.prometheus_metrics import (
    record_screenshot_capture,
    record_screenshot_fetch,
)
from app.core.retry import RetryConfig, calculate_delay
from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot
from app.domain.repositories.screenshot_repository import ScreenshotRepository
from app.domain.repositories.screenshot_storage import ScreenshotStorage
from app.domain.services.stream_guard import has_active_stream

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
        max_consecutive_failures: int = 3,  # P1.4: Reduced from 5 - enter protection sooner
        recovery_timeout: float = 120.0,  # P1.4: Increased from 60s - more time to stabilize
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
            if self._consecutive_successes >= 1:  # P1.4: Reduced from 2 - faster recovery
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
        from app.core.prometheus_metrics import screenshot_circuit_state

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
    """Captures screenshots during session execution for later replay.

    Uses MinIO S3 for binary storage and MongoDB for metadata.
    """

    MAX_PERIODIC_FAILURES = 3

    def __init__(
        self,
        sandbox,
        session_id: str,
        repository: ScreenshotRepository | None = None,
        minio_storage: ScreenshotStorage | None = None,
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
        if minio_storage is None:
            from app.infrastructure.storage.minio_storage import get_minio_storage

            minio_storage = get_minio_storage()
        self._minio = minio_storage
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

        # Startup readiness gate: prevents ConnectError when the sandbox
        # screenshot handler hasn't fully initialized after ensure_sandbox().
        # _ready is set once and never cleared — all subsequent captures skip the gate.
        self._ready = asyncio.Event()
        self._startup_lock = asyncio.Lock()

        # Initialize deduplication service
        self._dedup = None
        if self._settings.screenshot_dedup_enabled:
            from app.application.services.screenshot_dedup_service import ScreenshotDedupService

            self._dedup = ScreenshotDedupService()

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

        if tool_call_id and self._tool_context.tool_call_id and self._tool_context.tool_call_id != tool_call_id:
            return

        self._tool_context = None

    async def _ensure_endpoint_ready(self) -> None:
        """One-time readiness gate for the screenshot endpoint.

        Prevents ConnectError at session startup when the sandbox's screenshot
        handler hasn't fully initialized after ensure_sandbox() returns.

        Design: Uses asyncio.Lock to ensure exactly one coroutine runs the probe
        sequence.  All other concurrent callers wait on the asyncio.Event.
        Once set, the Event stays set forever — zero overhead on subsequent calls.
        """
        if self._ready.is_set():
            return

        async with self._startup_lock:
            # Double-check after acquiring the lock (another coroutine may have finished)
            if self._ready.is_set():
                return

            settings = self._settings
            grace = settings.screenshot_startup_grace_seconds
            max_probes = settings.screenshot_startup_max_probes
            probe_timeout = settings.screenshot_startup_probe_timeout

            # Grace period — let the sandbox connection pool and screenshot handler stabilize
            if grace > 0:
                logger.debug(
                    "Screenshot startup grace: %.1fs before probing (session=%s)",
                    grace,
                    self._session_id,
                )
                await asyncio.sleep(grace)

            start = time.monotonic()
            delay = 1.0

            for attempt in range(max_probes):
                # Hard timeout guard
                if (time.monotonic() - start) >= probe_timeout:
                    break

                try:
                    # Lightweight probe — minimal quality/scale to keep payload small
                    response = await self._sandbox.get_screenshot(quality=10, scale=0.1)
                    if response and getattr(response, "content", None):
                        elapsed = time.monotonic() - start + grace
                        logger.info(
                            "Screenshot endpoint ready after %d probe(s) (%.1fs incl. grace, session=%s)",
                            attempt + 1,
                            elapsed,
                            self._session_id,
                        )
                        self._ready.set()
                        return
                except Exception as e:
                    logger.debug(
                        "Screenshot probe %d/%d failed (session=%s): %s",
                        attempt + 1,
                        max_probes,
                        self._session_id,
                        e,
                    )

                if attempt < max_probes - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 1.5, 5.0)  # Backoff: 1.0 → 1.5 → 2.25 → 3.375 → 5.0

            # Probes exhausted — set ready anyway so captures aren't blocked forever.
            # The capture method's own retry logic will handle any remaining transient issues.
            total_elapsed = time.monotonic() - start + grace
            logger.warning(
                "Screenshot endpoint readiness not confirmed after %d probes (%.1fs). "
                "Proceeding — capture retries will handle remaining instability (session=%s)",
                max_probes,
                total_elapsed,
                self._session_id,
            )
            self._ready.set()

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
        # Startup readiness gate — blocks only until the first successful probe,
        # then becomes a no-op (asyncio.Event.is_set() is O(1)).
        try:
            await asyncio.wait_for(self._ensure_endpoint_ready(), timeout=35.0)
        except TimeoutError:
            logger.warning(
                "Screenshot readiness gate timed out (session=%s), attempting capture anyway",
                self._session_id,
            )
            self._ready.set()  # Unblock any other waiters

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

        # Suppress periodic captures while screencast is actively streaming to
        # avoid duplicate saves from concurrent periodic + tool-triggered shots.
        if (
            trigger == ScreenshotTrigger.PERIODIC
            and getattr(self._settings, "feature_sweep_dedup_enabled", True)
            and await has_active_stream(self._session_id, endpoint="screencast")
        ):
            logger.debug(
                "Skipping periodic screenshot for session %s while screencast stream is active",
                self._session_id,
            )
            return None

        try:
            async with self._lock:
                quality = self._settings.screenshot_quality
                scale = self._settings.screenshot_scale

                # Priority 2: Exponential backoff retry
                response = await self._get_screenshot_with_retry(quality, scale)
                image_data = response.content
                if not image_data:
                    return None

                # Detect stale screenshots from sandbox cache tier
                is_stale_response = response.headers.get("X-Screenshot-Stale") == "true"

                size_bytes = len(image_data)
                screenshot_id = uuid4().hex[:16]

                # Deduplication: compute hash and check for duplicates
                perceptual_hash: str | None = None
                is_duplicate = False
                original_storage_key: str | None = None

                if self._dedup:
                    perceptual_hash = self._dedup.compute_hash(image_data)
                    is_duplicate = self._dedup.is_duplicate(self._session_id, perceptual_hash, trigger)

                # Store full-res in MinIO (key: {session_id}/{sequence}_{trigger}.jpg)
                storage_key = f"{self._session_id}/{self._sequence:04d}_{trigger.value}.jpg"

                if is_duplicate:
                    # Find original's storage key to reference
                    recent = await self._repository.find_by_session(self._session_id, limit=5, offset=0)
                    original_storage_key = (
                        self._dedup.find_original_key(self._session_id, recent) if self._dedup else None
                    )
                    # Point storage_key to original (no new S3 upload)
                    if original_storage_key:
                        storage_key = original_storage_key
                        # Record dedup metrics
                        from app.core.prometheus_metrics import (
                            screenshot_dedup_saved_bytes,
                            screenshot_dedup_total,
                        )

                        screenshot_dedup_total.inc({"trigger": trigger.value})
                        screenshot_dedup_saved_bytes.inc({"trigger": trigger.value}, len(image_data))

                        # Periodic captures of an idle browser produce no new visual data.
                        # Skip the MongoDB write entirely — dedup metrics already count it.
                        # Tool-triggered and session-start captures always write to preserve
                        # replay fidelity for user-initiated actions.
                        if trigger == ScreenshotTrigger.PERIODIC:
                            return None
                    else:
                        # Fallback: store anyway if we can't find original
                        is_duplicate = False
                        await self._minio.store_screenshot(image_data, storage_key)
                else:
                    await self._minio.store_screenshot(image_data, storage_key)

                # Store thumbnail in MinIO (skip for duplicates and stale responses)
                thumbnail_storage_key: str | None = None
                if not is_duplicate and not is_stale_response:
                    try:
                        thumb_response = await self._sandbox.get_screenshot(
                            quality=self._settings.screenshot_thumbnail_quality,
                            scale=self._settings.screenshot_thumbnail_scale,
                        )
                        if thumb_response.content:
                            thumb_data = thumb_response.content
                            thumb_content_type = "image/jpeg"
                            thumb_ext = "jpg"

                            # WebP conversion if enabled
                            if self._settings.screenshot_thumbnail_webp_enabled:
                                try:
                                    from io import BytesIO

                                    from PIL import Image

                                    img = Image.open(BytesIO(thumb_response.content))
                                    webp_buf = BytesIO()
                                    img.save(
                                        webp_buf,
                                        format="WEBP",
                                        quality=self._settings.screenshot_thumbnail_webp_quality,
                                    )
                                    thumb_data = webp_buf.getvalue()
                                    thumb_content_type = "image/webp"
                                    thumb_ext = "webp"
                                except Exception:
                                    logger.debug("WebP conversion failed, using JPEG thumbnail")

                            thumb_key = f"{self._session_id}/thumb_{self._sequence:04d}.{thumb_ext}"
                            await self._minio.store_thumbnail(thumb_data, thumb_key, content_type=thumb_content_type)
                            thumbnail_storage_key = thumb_key
                    except Exception:
                        logger.debug("Thumbnail capture failed, continuing without")

                screenshot = SessionScreenshot(
                    id=screenshot_id,
                    session_id=self._session_id,
                    sequence_number=self._sequence,
                    storage_key=storage_key,
                    thumbnail_storage_key=thumbnail_storage_key,
                    trigger=trigger,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    function_name=function_name,
                    action_type=action_type,
                    size_bytes=size_bytes,
                    perceptual_hash=perceptual_hash,
                    is_duplicate=is_duplicate,
                    original_storage_key=original_storage_key,
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

        The sandbox endpoint now supports multi-tier fallback with an in-memory cache,
        so 503 errors are rare. When the sandbox returns a stale cached screenshot,
        the response includes ``X-Screenshot-Stale: true`` - we still accept the image
        but mark the response for downstream handling (e.g., skip thumbnail re-capture).

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
                        from app.core.prometheus_metrics import (
                            screenshot_retry_attempts_total,
                        )

                        screenshot_retry_attempts_total.inc({})
                        logger.info("Screenshot capture succeeded on retry attempt %d/%d", attempt + 1, max_attempts)

                    # Check if the sandbox returned a stale cached screenshot
                    is_stale = response.headers.get("X-Screenshot-Stale") == "true"
                    if is_stale:
                        stale_age = response.headers.get("X-Screenshot-Stale-Age-Ms", "?")
                        backend = response.headers.get("X-Screenshot-Backend", "unknown")
                        logger.debug(
                            "Screenshot from stale cache (age=%sms, backend=%s) for session %s",
                            stale_age,
                            backend,
                            self._session_id,
                        )

                    return response

            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    # Use centralized exponential backoff
                    retry_config = RetryConfig(
                        base_delay=base_delay,
                        exponential_base=2.0,
                        max_delay=16.0,  # Cap at 16s
                        jitter=True,
                    )
                    delay = calculate_delay(attempt + 1, retry_config)
                    logger.debug(
                        "Screenshot capture attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt + 1,
                        max_attempts,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "Screenshot capture failed after %d attempts: %s",
                        max_attempts,
                        e,
                        exc_info=True,
                    )

        # All attempts failed
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Screenshot capture returned empty content after {max_attempts} attempts")

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

    def __init__(
        self, repository: ScreenshotRepository | None = None, minio_storage: ScreenshotStorage | None = None
    ) -> None:
        if repository is None:
            from app.infrastructure.repositories.mongo_screenshot_repository import MongoScreenshotRepository

            repository = MongoScreenshotRepository()
        self._repository = repository
        if minio_storage is None:
            from app.infrastructure.storage.minio_storage import get_minio_storage

            minio_storage = get_minio_storage()
        self._minio = minio_storage

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all screenshots for a session (metadata + S3 objects)."""
        # Delete S3 objects first
        try:
            await self._minio.delete_screenshots_by_session(session_id)
        except Exception as e:
            logger.warning("Failed to delete S3 screenshot objects for session %s: %s", session_id, e)
        # Delete metadata
        return await self._repository.delete_by_session(session_id)

    async def list_by_session(self, session_id: str, limit: int, offset: int) -> tuple[list[SessionScreenshot], int]:
        """Fetch paginated screenshot metadata plus total count."""
        screenshots = await self._repository.find_by_session(session_id, limit=limit, offset=offset)
        total = await self._repository.count_by_session(session_id)
        return screenshots, total

    async def get_image_bytes(self, session_id: str, screenshot_id: str, thumbnail: bool) -> tuple[bytes | None, str]:
        """Fetch screenshot image bytes and content type, or (None, '') when not found."""
        start_time = time.perf_counter()
        access = "thumbnail" if thumbnail else "full"
        status = "error"
        size_bytes = 0
        try:
            screenshot = await self._repository.find_by_id(screenshot_id)
            if not screenshot or screenshot.session_id != session_id:
                return None, ""

            if thumbnail and screenshot.thumbnail_storage_key:
                data = await self._minio.get_thumbnail(screenshot.thumbnail_storage_key)
                content_type = "image/webp" if screenshot.thumbnail_storage_key.endswith(".webp") else "image/jpeg"
            else:
                # For duplicates, fetch from original storage key
                key = (
                    (screenshot.original_storage_key or screenshot.storage_key)
                    if screenshot.is_duplicate
                    else screenshot.storage_key
                )
                data = await self._minio.get_screenshot(key)
                content_type = "image/jpeg"

            if data:
                status = "success"
                size_bytes = len(data)
            return data, content_type
        except Exception as e:
            logger.warning("Failed to fetch screenshot %s: %s", screenshot_id, e)
            return None, ""
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
