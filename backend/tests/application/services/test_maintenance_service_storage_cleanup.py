"""Tests for screenshot and snapshot TTL cleanup in MaintenanceService.

Verifies record-level precision: expired screenshots are deleted while
fresh screenshots in the same session are preserved.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.maintenance_service import MaintenanceService
from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot


def _make_screenshot(
    screenshot_id: str,
    session_id: str,
    timestamp: datetime,
    storage_key: str,
    thumbnail_key: str | None = None,
) -> SessionScreenshot:
    return SessionScreenshot(
        id=screenshot_id,
        session_id=session_id,
        sequence_number=1,
        timestamp=timestamp,
        storage_key=storage_key,
        thumbnail_storage_key=thumbnail_key,
        trigger=ScreenshotTrigger.PERIODIC,
    )


@pytest.mark.asyncio
async def test_cleanup_old_screenshots_mixed_age_preserves_fresh() -> None:
    """A session with both expired and fresh screenshots: only expired are deleted."""
    now = datetime.now(UTC)
    expired_time = now - timedelta(days=45)
    fresh_time = now - timedelta(hours=2)

    expired_screenshot = _make_screenshot(
        screenshot_id="expired-1",
        session_id="session-mixed",
        timestamp=expired_time,
        storage_key="session-mixed/0001_periodic.jpg",
        thumbnail_key="session-mixed/thumb_0001.webp",
    )
    # This fresh screenshot exists in the same session but should NOT be returned
    # by find_expired_screenshots — it's newer than the cutoff
    _make_screenshot(
        screenshot_id="fresh-1",
        session_id="session-mixed",
        timestamp=fresh_time,
        storage_key="session-mixed/0002_periodic.jpg",
        thumbnail_key="session-mixed/thumb_0002.webp",
    )

    mock_repo = AsyncMock()
    # Only the expired screenshot is returned
    mock_repo.find_expired_screenshots.return_value = [expired_screenshot]
    mock_repo.delete_by_ids.return_value = 1

    mock_minio = AsyncMock()
    mock_minio.delete_screenshot_objects.return_value = 2  # 1 full + 1 thumb

    db = SimpleNamespace(sessions=SimpleNamespace())
    service = MaintenanceService(db)

    with (
        patch(
            "app.infrastructure.repositories.mongo_screenshot_repository.MongoScreenshotRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.infrastructure.storage.minio_storage.get_minio_storage",
            return_value=mock_minio,
        ),
    ):
        result = await service.cleanup_old_screenshots(ttl_days=30)

    # Verify only expired object keys were targeted
    mock_minio.delete_screenshot_objects.assert_awaited_once_with(
        ["session-mixed/0001_periodic.jpg"],
        ["session-mixed/thumb_0001.webp"],
    )

    # Verify only expired document was deleted
    mock_repo.delete_by_ids.assert_awaited_once_with(["expired-1"])

    # Fresh screenshot was never touched
    assert result["documents_deleted"] == 1
    assert result["objects_deleted"] == 2
    assert not result["errors"]


@pytest.mark.asyncio
async def test_cleanup_old_screenshots_no_expired() -> None:
    """No expired screenshots: nothing is deleted."""
    mock_repo = AsyncMock()
    mock_repo.find_expired_screenshots.return_value = []

    db = SimpleNamespace(sessions=SimpleNamespace())
    service = MaintenanceService(db)

    with patch(
        "app.infrastructure.repositories.mongo_screenshot_repository.MongoScreenshotRepository",
        return_value=mock_repo,
    ):
        result = await service.cleanup_old_screenshots(ttl_days=30)

    assert result["documents_deleted"] == 0
    assert result["objects_deleted"] == 0


@pytest.mark.asyncio
async def test_cleanup_old_screenshots_minio_failure_still_deletes_docs() -> None:
    """MinIO failure doesn't prevent Mongo document cleanup."""
    now = datetime.now(UTC)
    expired = _make_screenshot(
        screenshot_id="exp-1",
        session_id="s1",
        timestamp=now - timedelta(days=60),
        storage_key="s1/0001.jpg",
    )

    mock_repo = AsyncMock()
    mock_repo.find_expired_screenshots.return_value = [expired]
    mock_repo.delete_by_ids.return_value = 1

    mock_minio = AsyncMock()
    mock_minio.delete_screenshot_objects.side_effect = RuntimeError("connection refused")

    db = SimpleNamespace(sessions=SimpleNamespace())
    service = MaintenanceService(db)

    with (
        patch(
            "app.infrastructure.repositories.mongo_screenshot_repository.MongoScreenshotRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.infrastructure.storage.minio_storage.get_minio_storage",
            return_value=mock_minio,
        ),
    ):
        result = await service.cleanup_old_screenshots(ttl_days=30)

    # Mongo docs still deleted despite MinIO failure
    mock_repo.delete_by_ids.assert_awaited_once_with(["exp-1"])
    assert result["documents_deleted"] == 1
    assert len(result["errors"]) == 1


@pytest.mark.asyncio
async def test_cleanup_old_screenshots_deduplicates_keys() -> None:
    """Screenshots with duplicate storage keys are all passed to MinIO layer."""
    now = datetime.now(UTC)
    old = now - timedelta(days=45)

    # Two expired screenshots pointing to the same original (dedup scenario)
    s1 = _make_screenshot("dup-1", "s1", old, "s1/0001.jpg", "s1/thumb_0001.webp")
    s2 = _make_screenshot("dup-2", "s1", old, "s1/0001.jpg", "s1/thumb_0001.webp")

    mock_repo = AsyncMock()
    mock_repo.find_expired_screenshots.return_value = [s1, s2]
    mock_repo.delete_by_ids.return_value = 2

    mock_minio = AsyncMock()
    mock_minio.delete_screenshot_objects.return_value = 2

    db = SimpleNamespace(sessions=SimpleNamespace())
    service = MaintenanceService(db)

    with (
        patch(
            "app.infrastructure.repositories.mongo_screenshot_repository.MongoScreenshotRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.infrastructure.storage.minio_storage.get_minio_storage",
            return_value=mock_minio,
        ),
    ):
        result = await service.cleanup_old_screenshots(ttl_days=30)

    # Both keys are passed (dedup happens in MinIO layer)
    call_args = mock_minio.delete_screenshot_objects.call_args
    assert call_args[0][0] == ["s1/0001.jpg", "s1/0001.jpg"]
    mock_repo.delete_by_ids.assert_awaited_once_with(["dup-1", "dup-2"])
    assert result["documents_deleted"] == 2


@pytest.mark.asyncio
async def test_cleanup_old_snapshots() -> None:
    """Snapshot cleanup deletes documents older than TTL."""
    mock_repo = AsyncMock()
    mock_repo.delete_all_older_than.return_value = 5

    db = SimpleNamespace(sessions=SimpleNamespace())
    service = MaintenanceService(db)

    with patch(
        "app.infrastructure.repositories.mongo_snapshot_repository.MongoSnapshotRepository",
        return_value=mock_repo,
    ):
        result = await service.cleanup_old_snapshots(ttl_days=7)

    assert result["documents_deleted"] == 5
    assert not result["errors"]
    mock_repo.delete_all_older_than.assert_awaited_once()
    # Verify cutoff is approximately 7 days ago
    cutoff = mock_repo.delete_all_older_than.call_args[0][0]
    assert (datetime.now(UTC) - cutoff).days == 7
