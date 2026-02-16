import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.screenshot_service import ScreenshotCaptureService, ScreenshotQueryService
from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot
from app.infrastructure.observability.prometheus_metrics import (
    reset_all_metrics,
    screenshot_capture_size_bytes,
    screenshot_captures_total,
    screenshot_fetch_size_bytes,
    screenshot_fetch_total,
)


@pytest.fixture(autouse=True)
def reset_metrics_fixture():
    reset_all_metrics()
    yield
    reset_all_metrics()


class FakeSandbox:
    def __init__(self, content: bytes):
        self._content = content

    async def get_screenshot(self, quality: int, scale: float):
        return SimpleNamespace(
            content=self._content,
            quality=quality,
            scale=scale,
            headers={},
        )


class FailingSandbox:
    async def get_screenshot(self, quality: int, scale: float):
        raise RuntimeError("sandbox unavailable")


def _make_minio_mock():
    """Create a mock MinIO storage with async screenshot methods."""
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.get_screenshot = AsyncMock(return_value=b"served-bytes")
    minio.get_thumbnail = AsyncMock(return_value=b"thumb-bytes")
    minio.delete_screenshots_by_session = AsyncMock(return_value=0)
    return minio


@pytest.mark.asyncio
async def test_capture_records_success_metrics():
    sandbox = FakeSandbox(b"image-bytes")
    repository = SimpleNamespace(save=AsyncMock())
    minio = _make_minio_mock()

    service = ScreenshotCaptureService(
        sandbox=sandbox,
        session_id="session-metrics-1",
        repository=repository,
        minio_storage=minio,
    )

    screenshot = await service.capture(ScreenshotTrigger.TOOL_AFTER)

    assert screenshot is not None
    assert screenshot.size_bytes == len(b"image-bytes")
    assert screenshot_captures_total.get({"trigger": "tool_after", "status": "success"}) == 1.0
    assert screenshot_capture_size_bytes.get({"trigger": "tool_after"}) == float(len(b"image-bytes"))


@pytest.mark.asyncio
async def test_capture_records_error_metrics_when_image_is_empty():
    sandbox = FakeSandbox(b"")
    repository = SimpleNamespace(save=AsyncMock())
    minio = _make_minio_mock()

    service = ScreenshotCaptureService(
        sandbox=sandbox,
        session_id="session-metrics-2",
        repository=repository,
        minio_storage=minio,
    )

    screenshot = await service.capture(ScreenshotTrigger.PERIODIC)

    assert screenshot is None
    assert screenshot_captures_total.get({"trigger": "periodic", "status": "error"}) == 1.0
    assert screenshot_capture_size_bytes.get({"trigger": "periodic"}) == 0.0


@pytest.mark.asyncio
async def test_query_service_records_fetch_success_metrics():
    screenshot = SessionScreenshot(
        id="screenshot-1",
        session_id="session-metrics-3",
        sequence_number=0,
        storage_key="session-metrics-3/0000_session_start.jpg",
        trigger=ScreenshotTrigger.SESSION_START,
    )
    repository = SimpleNamespace(find_by_id=AsyncMock(return_value=screenshot))
    minio = _make_minio_mock()
    service = ScreenshotQueryService(repository=repository, minio_storage=minio)

    image_data, content_type = await service.get_image_bytes(
        session_id="session-metrics-3",
        screenshot_id="screenshot-1",
        thumbnail=False,
    )

    assert image_data == b"served-bytes"
    assert content_type == "image/jpeg"
    assert screenshot_fetch_total.get({"access": "full", "status": "success"}) == 1.0
    assert screenshot_fetch_size_bytes.get({"access": "full"}) == float(len(b"served-bytes"))


@pytest.mark.asyncio
async def test_query_service_records_fetch_error_metrics_for_missing_screenshot():
    repository = SimpleNamespace(find_by_id=AsyncMock(return_value=None))
    minio = _make_minio_mock()
    service = ScreenshotQueryService(repository=repository, minio_storage=minio)

    image_data, _content_type = await service.get_image_bytes(
        session_id="session-metrics-4",
        screenshot_id="missing-shot",
        thumbnail=True,
    )

    assert image_data is None
    assert screenshot_fetch_total.get({"access": "thumbnail", "status": "error"}) == 1.0
    assert screenshot_fetch_size_bytes.get({"access": "thumbnail"}) == 0.0


@pytest.mark.asyncio
async def test_periodic_capture_stops_after_repeated_failures():
    sandbox = FailingSandbox()
    repository = SimpleNamespace(save=AsyncMock())
    minio = _make_minio_mock()

    service = ScreenshotCaptureService(
        sandbox=sandbox,
        session_id="session-metrics-5",
        repository=repository,
        minio_storage=minio,
    )
    service._max_periodic_failures = 2

    service._periodic_task = asyncio.create_task(asyncio.sleep(60))
    await service.capture(ScreenshotTrigger.PERIODIC)
    await service.capture(ScreenshotTrigger.PERIODIC)

    assert service._periodic_task is None


@pytest.mark.asyncio
async def test_periodic_capture_uses_tool_context_metadata():
    sandbox = FakeSandbox(b"image-bytes")
    repository = SimpleNamespace(save=AsyncMock())
    minio = _make_minio_mock()

    service = ScreenshotCaptureService(
        sandbox=sandbox,
        session_id="session-metrics-6",
        repository=repository,
        minio_storage=minio,
    )
    service.set_tool_context(
        tool_call_id="call-123",
        tool_name="browser",
        function_name="browser_navigate",
        action_type="navigate",
    )

    await service.capture(ScreenshotTrigger.PERIODIC)

    saved_screenshot = repository.save.await_args.args[0]
    assert saved_screenshot.tool_call_id == "call-123"
    assert saved_screenshot.tool_name == "browser"
    assert saved_screenshot.function_name == "browser_navigate"
    assert saved_screenshot.action_type == "navigate"


def test_clear_tool_context_is_scoped_by_tool_call_id():
    service = ScreenshotCaptureService(
        sandbox=FakeSandbox(b"image-bytes"),
        session_id="session-metrics-7",
        repository=SimpleNamespace(save=AsyncMock()),
        minio_storage=_make_minio_mock(),
    )
    service.set_tool_context(tool_call_id="call-123", tool_name="browser")

    service.clear_tool_context(tool_call_id="call-999")
    assert service._tool_context is not None

    service.clear_tool_context(tool_call_id="call-123")
    assert service._tool_context is None
