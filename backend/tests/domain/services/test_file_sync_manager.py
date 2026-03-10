"""Unit tests for FileSyncManager sandbox -> storage sync behavior."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest

from app.domain.exceptions.base import SessionNotFoundException
from app.domain.models.file import FileInfo
from app.domain.services.file_sync_manager import FileSyncManager


@pytest.fixture
def manager() -> tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock]:
    sandbox = AsyncMock()
    file_storage = AsyncMock()
    session_repository = AsyncMock()
    sync_manager = FileSyncManager(
        agent_id="agent-1",
        session_id="session-1",
        user_id="user-1",
        sandbox=sandbox,
        file_storage=file_storage,
        session_repository=session_repository,
    )
    return sync_manager, sandbox, file_storage, session_repository


@pytest.mark.asyncio
async def test_sync_file_to_storage_rejects_zero_byte_files(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    sync_manager, sandbox, file_storage, session_repository = manager
    session_repository.get_file_by_path.return_value = None
    sandbox.file_download.return_value = io.BytesIO(b"")

    result = await sync_manager.sync_file_to_storage("/workspace/session-1/empty.md")

    assert result is None
    file_storage.upload_file.assert_not_awaited()
    session_repository.add_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_file_to_storage_uploads_non_empty_files(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    sync_manager, sandbox, file_storage, session_repository = manager
    session_repository.get_file_by_path.return_value = None
    sandbox.file_download.return_value = io.BytesIO(b"# report")
    file_storage.upload_file.return_value = FileInfo(file_id="file-123", filename="report.md")

    result = await sync_manager.sync_file_to_storage("/workspace/session-1/report.md")

    assert result is not None
    assert result.file_id == "file-123"
    file_storage.upload_file.assert_awaited_once()
    session_repository.add_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_file_to_storage_skips_when_session_missing_before_upload(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    sync_manager, sandbox, file_storage, session_repository = manager
    sandbox.file_download.return_value = io.BytesIO(b"# report")
    session_repository.get_file_by_path.side_effect = SessionNotFoundException("session-1")

    result = await sync_manager.sync_file_to_storage("/workspace/session-1/report.md")

    assert result is None
    file_storage.upload_file.assert_not_awaited()
    session_repository.add_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_file_to_storage_deletes_orphan_upload_when_session_disappears(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    sync_manager, sandbox, file_storage, session_repository = manager
    sandbox.file_download.return_value = io.BytesIO(b"# report")
    session_repository.get_file_by_path.return_value = None
    file_storage.upload_file.return_value = FileInfo(file_id="file-123", filename="report.md")
    session_repository.add_file.side_effect = SessionNotFoundException("session-1")

    result = await sync_manager.sync_file_to_storage("/workspace/session-1/report.md")

    assert result is None
    file_storage.upload_file.assert_awaited_once()
    file_storage.delete_file.assert_awaited_once_with("file-123", "user-1")


@pytest.mark.asyncio
async def test_sync_file_to_storage_uses_filename_override(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """When filename_override is provided, upload uses it instead of basename from file_path.

    This is critical for chart images: the markdown references
    'comparison-chart-{event_id}.png' but the sandbox file is at
    '/workspace/{slugified_title}.png'. Without the override the synced
    FileInfo gets the wrong filename and _rewrite_chart_image_urls
    cannot match the markdown reference → broken image.
    """
    sync_manager, sandbox, file_storage, session_repository = manager
    session_repository.get_file_by_path.return_value = None
    sandbox.file_download.return_value = io.BytesIO(b"\x89PNG_data")
    file_storage.upload_file.return_value = FileInfo(
        file_id="png-file-id",
        filename="comparison-chart-abc123.png",
    )

    result = await sync_manager.sync_file_to_storage(
        "/workspace/best_smartphones_2026.png",
        content_type="image/png",
        filename_override="comparison-chart-abc123.png",
    )

    assert result is not None
    assert result.file_id == "png-file-id"
    # The upload must use the override name, not "best_smartphones_2026.png"
    call_args = file_storage.upload_file.call_args
    assert call_args[0][1] == "comparison-chart-abc123.png"


@pytest.mark.asyncio
async def test_sync_file_to_storage_falls_back_to_basename_without_override(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """Without filename_override, the basename of file_path is used (existing behaviour)."""
    sync_manager, sandbox, file_storage, session_repository = manager
    session_repository.get_file_by_path.return_value = None
    sandbox.file_download.return_value = io.BytesIO(b"# report content")
    file_storage.upload_file.return_value = FileInfo(file_id="file-456", filename="report.md")

    result = await sync_manager.sync_file_to_storage("/workspace/session-1/report.md")

    assert result is not None
    call_args = file_storage.upload_file.call_args
    assert call_args[0][1] == "report.md"


@pytest.mark.asyncio
async def test_sync_event_attachments_passes_filename_override(
    manager: tuple[FileSyncManager, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """sync_event_attachments_to_storage passes attachment.filename as override."""
    from unittest.mock import patch

    from app.domain.models.event import ReportEvent

    sync_manager, _sandbox, _file_storage, _session_repository = manager

    event = ReportEvent(
        id="evt-1",
        title="Test Report",
        content="![Chart](comparison-chart-evt-1.png)",
        attachments=[
            FileInfo(
                filename="comparison-chart-evt-1.png",
                file_path="/workspace/slug_name.png",
                content_type="image/png",
            ),
        ],
    )

    synced_fi = FileInfo(
        file_id="synced-id",
        filename="comparison-chart-evt-1.png",
        content_type="image/png",
    )

    with patch.object(sync_manager, "sync_file_to_storage", new_callable=AsyncMock, return_value=synced_fi) as mock_sync:
        await sync_manager.sync_event_attachments_to_storage(event)

        mock_sync.assert_awaited_once_with(
            "/workspace/slug_name.png",
            content_type="image/png",
            metadata=None,
            filename_override="comparison-chart-evt-1.png",
        )
