"""Tests that sudo file operations use shlex.quote() to prevent shell injection."""

import shlex
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.file import FileService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DANGEROUS_FILENAME = "file'; rm -rf /; echo '"
SAFE_QUOTED = shlex.quote(DANGEROUS_FILENAME)


def _make_subprocess_mock(
    returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
):
    """Return a mock that looks like an asyncio.subprocess.Process."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def service() -> FileService:
    return FileService()


@pytest.fixture()
def allowed_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch SANDBOX_ALLOWED_DIRS to point at tmp_path so _normalize_path passes."""
    monkeypatch.setattr("app.services.file.SANDBOX_ALLOWED_DIRS", [tmp_path])
    return tmp_path


# ---------------------------------------------------------------------------
# read_file sudo — SEC-003
# ---------------------------------------------------------------------------


class TestReadFileSudoInjection:
    """shlex.quote must appear in the sudo cat command for read_file."""

    @pytest.mark.asyncio
    async def test_safe_filename_uses_shlex_quote(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        target = allowed_workspace / "safe.txt"
        target.touch()

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock(stdout=b"hello")

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.read_file(str(target), sudo=True)

        assert len(captured) == 1
        assert shlex.quote(str(target)) in captured[0]

    @pytest.mark.asyncio
    async def test_dangerous_filename_is_quoted_in_read_command(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        # Build the target path without creating it on disk; the dangerous
        # filename contains characters (/ and ;) that the macOS FS rejects.
        target = allowed_workspace / DANGEROUS_FILENAME

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock(stdout=b"data")

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
            # Bypass the os.path.exists guard in read_file (sudo path skips it anyway)
            patch("os.path.exists", return_value=True),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.read_file(str(target), sudo=True)

        assert len(captured) == 1
        cmd = captured[0]
        assert shlex.quote(str(allowed_workspace / DANGEROUS_FILENAME)) in cmd
        # The raw unquoted dangerous string must NOT appear verbatim
        assert DANGEROUS_FILENAME not in cmd


# ---------------------------------------------------------------------------
# write_file sudo — mkdir + cat (SEC-003)
# ---------------------------------------------------------------------------


class TestWriteFileSudoInjection:
    """shlex.quote must appear in both mkdir and cat commands for write_file."""

    @pytest.mark.asyncio
    async def test_write_file_mkdir_uses_shlex_quote(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        # Place target in a non-existent sub-directory so mkdir is triggered
        target = allowed_workspace / "newdir" / "safe.txt"

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock()

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.write_file(str(target), "content", sudo=True)

        # First call should be the mkdir, second the cat
        assert len(captured) == 2
        mkdir_cmd = captured[0]
        assert shlex.quote(str(target.parent)) in mkdir_cmd

    @pytest.mark.asyncio
    async def test_write_file_cat_uses_shlex_quote(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        target = allowed_workspace / "output.txt"
        # Parent already exists — no mkdir call
        target.parent.mkdir(parents=True, exist_ok=True)

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock()

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.write_file(str(target), "content", sudo=True)

        assert len(captured) == 1
        cat_cmd = captured[0]
        assert shlex.quote(str(target)) in cat_cmd

    @pytest.mark.asyncio
    async def test_dangerous_filename_quoted_in_write_command(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        target = allowed_workspace / DANGEROUS_FILENAME
        # Parent exists
        target.parent.mkdir(parents=True, exist_ok=True)

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock()

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.write_file(str(target), "data", sudo=True)

        # cat command
        assert len(captured) == 1
        cmd = captured[0]
        assert shlex.quote(str(allowed_workspace / DANGEROUS_FILENAME)) in cmd
        assert DANGEROUS_FILENAME not in cmd


# ---------------------------------------------------------------------------
# delete_file sudo — SEC-003
# ---------------------------------------------------------------------------


class TestDeleteFileSudoInjection:
    """shlex.quote must appear in the sudo rm command for delete_file."""

    @pytest.mark.asyncio
    async def test_safe_path_uses_shlex_quote(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        target = allowed_workspace / "todelete.txt"
        target.touch()

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock()

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.delete_file(str(target), sudo=True)

        assert len(captured) == 1
        assert shlex.quote(str(target)) in captured[0]

    @pytest.mark.asyncio
    async def test_dangerous_filename_quoted_in_delete_command(
        self, service: FileService, allowed_workspace: Path
    ) -> None:
        # Don't create the file on disk — the dangerous name contains FS-illegal
        # characters on macOS.  Mock os.path.exists so delete_file proceeds.
        target = allowed_workspace / DANGEROUS_FILENAME

        captured: list[str] = []

        async def fake_create_subprocess_shell(cmd, **kwargs):
            captured.append(cmd)
            return _make_subprocess_mock()

        with (
            patch("app.services.file.settings") as mock_settings,
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=fake_create_subprocess_shell,
            ),
            patch("os.path.exists", return_value=True),
        ):
            mock_settings.ALLOW_SUDO = True
            await service.delete_file(str(target), sudo=True)

        assert len(captured) == 1
        cmd = captured[0]
        assert shlex.quote(str(allowed_workspace / DANGEROUS_FILENAME)) in cmd
        assert DANGEROUS_FILENAME not in cmd
