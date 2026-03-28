"""Tests for shell exec_dir path traversal prevention (CodeQL #337)."""

from pathlib import Path

import pytest

from app.core.exceptions import BadRequestException
from app.services.shell import ShellService


@pytest.fixture()
def service() -> ShellService:
    return ShellService()


class TestExecDirPathValidation:
    """_validate_exec_dir must reject paths outside allowed roots."""

    def test_allows_home_directory(self, service: ShellService) -> None:
        result = service._validate_exec_dir("/home/ubuntu")
        # macOS resolves /home → /System/Volumes/Data/home
        assert result.endswith("/home/ubuntu")

    def test_allows_home_subdirectory(self, service: ShellService) -> None:
        result = service._validate_exec_dir("/home/ubuntu/projects")
        assert result.endswith("/home/ubuntu/projects")

    def test_allows_workspace(self, service: ShellService) -> None:
        result = service._validate_exec_dir("/workspace")
        assert result.endswith("/workspace")

    def test_allows_workspace_subdirectory(self, service: ShellService) -> None:
        result = service._validate_exec_dir("/workspace/src")
        assert result.endswith("/workspace/src")

    def test_allows_tmp(self, service: ShellService) -> None:
        result = service._validate_exec_dir("/tmp")
        # macOS resolves /tmp → /private/tmp
        assert Path(result).resolve() == Path("/tmp").resolve()

    def test_rejects_path_traversal(self, service: ShellService) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            service._validate_exec_dir("/home/ubuntu/../../etc/passwd")

    def test_rejects_absolute_escape(self, service: ShellService) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            service._validate_exec_dir("/etc/shadow")

    def test_rejects_root(self, service: ShellService) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            service._validate_exec_dir("/")

    def test_rejects_usr_bin(self, service: ShellService) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            service._validate_exec_dir("/usr/bin")

    def test_resolves_symlinks_before_check(self, service: ShellService) -> None:
        """Even resolved paths must stay within allowed roots."""
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            service._validate_exec_dir("/tmp/../../etc/passwd")

    def test_rejects_opt_directory(self, service: ShellService) -> None:
        with pytest.raises(BadRequestException, match="Path traversal denied"):
            service._validate_exec_dir("/opt/base-python-venv")
