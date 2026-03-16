from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.file import FileInfo
from app.domain.services.agents.agent_task_factory import AgentTaskFactory


def _make_factory() -> AgentTaskFactory:
    file_storage = MagicMock()
    file_storage.get_file_info = AsyncMock(return_value=None)
    return AgentTaskFactory(
        agent_repository=MagicMock(),
        session_repository=MagicMock(),
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=file_storage,
        mcp_repository=MagicMock(),
    )


@pytest.mark.asyncio
async def test_resolve_user_attachments_preserves_local_file_path_metadata() -> None:
    factory = _make_factory()

    resolved = await factory.resolve_user_attachments(
        [
            {
                "file_path": "/tmp/sticker.webp",
                "filename": "sticker.webp",
                "content_type": "image/webp",
                "size": 321,
                "type": "sticker",
                "metadata": {
                    "telegram": {
                        "file_id": "sticker-file-id",
                        "file_unique_id": "sticker-unique-id",
                    }
                },
            }
        ],
        user_id="user-1",
    )

    assert resolved == [
        FileInfo(
            file_id=None,
            filename="sticker.webp",
            file_path="/tmp/sticker.webp",
            content_type="image/webp",
            size=321,
            metadata={
                "type": "sticker",
                "telegram": {
                    "file_id": "sticker-file-id",
                    "file_unique_id": "sticker-unique-id",
                },
            },
            user_id="user-1",
        )
    ]
