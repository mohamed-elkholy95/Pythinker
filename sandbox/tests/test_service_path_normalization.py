"""Tests for path normalization and path-traversal prevention in FileService."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import BadRequestException
from app.services.file import FileService, safe_resolve
from app.services.shell import ShellService


# ---------------------------------------------------------------------------
# safe_resolve – unit tests (use explicit base_dir, unaffected by conftest)
# ---------------------------------------------------------------------------


class TestSafeResolve:
    """Verify the standalone safe_resolve function blocks traversals."""

    _ALLOWED = [Path("/home/ubuntu")]

    def _resolved_base(self) -> str:
        return str(self._ALLOWED[0].resolve())

    def test_path_within_base_is_allowed(self) -> None:
        result = safe_resolve(
            "/home/ubuntu/project/file.py", allowed_dirs=self._ALLOWED
        )
        assert result.startswith(self._resolved_base())

    def test_base_dir_itself_is_allowed(self) -> None:
        result = safe_resolve("/home/ubuntu", allowed_dirs=self._ALLOWED)
        assert result == self._resolved_base()

    def test_dot_dot_traversal_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/home/ubuntu/../../etc/passwd", allowed_dirs=self._ALLOWED)

    def test_absolute_path_outside_base_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/etc/passwd", allowed_dirs=self._ALLOWED)

    def test_root_path_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/", allowed_dirs=self._ALLOWED)

    def test_tmp_path_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/tmp/evil.sh", allowed_dirs=self._ALLOWED)

    def test_var_path_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/var/log/syslog", allowed_dirs=self._ALLOWED)

    def test_proc_path_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/proc/self/environ", allowed_dirs=self._ALLOWED)

    def test_deeply_nested_traversal_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve(
                "/home/ubuntu/a/b/c/../../../../etc/shadow", allowed_dirs=self._ALLOWED
            )

    def test_dot_dot_at_start_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/../../../etc/passwd", allowed_dirs=self._ALLOWED)

    def test_home_other_user_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/home/root/.ssh/authorized_keys", allowed_dirs=self._ALLOWED)

    def test_subdirectory_is_allowed(self) -> None:
        result = safe_resolve(
            "/home/ubuntu/workspace/project/src/main.py", allowed_dirs=self._ALLOWED
        )
        assert result.startswith(self._resolved_base())

    def test_multiple_allowed_dirs(self) -> None:
        dirs = [Path("/home/ubuntu"), Path("/workspace")]
        result = safe_resolve("/workspace/session/file.txt", allowed_dirs=dirs)
        assert result.startswith(str(Path("/workspace").resolve()))

    def test_multiple_allowed_dirs_traversal_blocked(self) -> None:
        dirs = [Path("/home/ubuntu"), Path("/workspace")]
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/etc/passwd", allowed_dirs=dirs)

    def test_custom_allowed_dir(self) -> None:
        custom = [Path("/opt/sandbox")]
        result = safe_resolve("/opt/sandbox/data/file.txt", allowed_dirs=custom)
        assert result.startswith(str(Path("/opt/sandbox").resolve()))

    def test_custom_allowed_dir_traversal_blocked(self) -> None:
        custom = [Path("/opt/sandbox")]
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            safe_resolve("/opt/other/data.txt", allowed_dirs=custom)


# ---------------------------------------------------------------------------
# FileService._normalize_path – uses the monkeypatched SANDBOX_ALLOWED_DIRS
# from conftest, so we test with tmp_path as the allowed base.
# ---------------------------------------------------------------------------


class TestFileServiceNormalizePath:
    """Verify _normalize_path chains alias resolution with traversal checks.

    NOTE: The conftest autouse fixture sets SANDBOX_ALLOWED_DIRS to [tmp_path].
    These tests therefore validate that paths outside tmp_path are rejected.
    """

    def setup_method(self) -> None:
        self.service = FileService()

    def test_path_outside_sandbox_base_is_blocked(self) -> None:
        """Any path that resolves outside the (monkeypatched) base is rejected."""
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            self.service._normalize_path("/etc/shadow")

    def test_dot_dot_escape_is_blocked(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            self.service._normalize_path("/home/ubuntu/../root/.bashrc")


# ---------------------------------------------------------------------------
# FileService methods – traversal blocked at entry point
# ---------------------------------------------------------------------------


class TestFileServiceMethodTraversal:
    """Verify every public method rejects paths outside the sandbox.

    The conftest monkeypatches SANDBOX_ALLOWED_DIRS to [tmp_path], so /etc, /tmp
    etc. are all outside the allowed directories and must be rejected.
    """

    def setup_method(self) -> None:
        self.service = FileService()

    @pytest.mark.asyncio
    async def test_read_file_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.read_file(file="/etc/passwd")

    @pytest.mark.asyncio
    async def test_write_file_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.write_file(file="/etc/crontab", content="* * * * * evil")

    @pytest.mark.asyncio
    async def test_str_replace_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.str_replace(
                file="/etc/hosts", old_str="localhost", new_str="evil"
            )

    @pytest.mark.asyncio
    async def test_find_in_content_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.find_in_content(file="/etc/passwd", regex="root")

    @pytest.mark.asyncio
    async def test_find_by_name_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.find_by_name(path="/etc", glob_pattern="*.conf")

    @pytest.mark.asyncio
    async def test_upload_file_blocks_traversal(self) -> None:
        fake_upload = AsyncMock()
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.upload_file(
                path="/tmp/evil.bin", file_stream=fake_upload
            )

    @pytest.mark.asyncio
    async def test_delete_file_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.delete_file(path="/etc/passwd")

    @pytest.mark.asyncio
    async def test_list_dir_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            await self.service.list_dir(path="/etc")

    def test_ensure_file_blocks_traversal(self) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            self.service.ensure_file(path="/root/.ssh/id_rsa")


# ---------------------------------------------------------------------------
# ShellService – existing tests preserved
# ---------------------------------------------------------------------------


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
