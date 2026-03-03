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
