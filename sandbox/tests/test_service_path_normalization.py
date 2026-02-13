from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import BadRequestException
from app.services.file import FileService
from app.services.shell import ShellService


@pytest.mark.asyncio
async def test_file_service_normalizes_legacy_home_alias() -> None:
    service = FileService()

    assert service._normalize_path("/home/user/report.md") == "/home/ubuntu/report.md"


@pytest.mark.asyncio
async def test_shell_service_normalizes_legacy_home_alias() -> None:
    service = ShellService()

    assert service._resolve_home_alias("/home/user/project") == "/home/ubuntu/project"


@pytest.mark.asyncio
async def test_shell_exec_auto_creates_missing_workspace_dir() -> None:
    service = ShellService()
    service.active_shells.clear()

    fake_process = AsyncMock()
    fake_process.returncode = None
    fake_process.stdout = None

    service._create_process = AsyncMock(return_value=fake_process)
    service.wait_for_process = AsyncMock(
        side_effect=BadRequestException("process still running")
    )

    exec_dir = "/workspace/test-session"

    with (
        patch("app.services.shell.os.path.exists", return_value=False),
        patch("app.services.shell.os.makedirs") as makedirs,
    ):
        result = await service.exec_command("shell-session", exec_dir, "echo hi")

    makedirs.assert_called_once_with(exec_dir, exist_ok=True)
    assert result.status == "running"
