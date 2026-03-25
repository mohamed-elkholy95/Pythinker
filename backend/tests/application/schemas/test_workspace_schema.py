"""Tests for workspace application schemas."""

from __future__ import annotations

from app.application.schemas.workspace import (
    GitRemoteSpec,
    WorkspaceManifest,
    WorkspaceManifestResponse,
    WorkspaceWriteError,
)


class TestGitRemoteSpec:
    def test_all_optional(self) -> None:
        spec = GitRemoteSpec()
        assert spec.repo_url is None
        assert spec.remote_name is None
        assert spec.branch is None
        assert spec.credentials is None

    def test_with_values(self) -> None:
        spec = GitRemoteSpec(
            repo_url="https://github.com/user/repo.git",
            remote_name="origin",
            branch="main",
        )
        assert spec.repo_url == "https://github.com/user/repo.git"
        assert spec.branch == "main"


class TestWorkspaceManifest:
    def test_defaults(self) -> None:
        m = WorkspaceManifest()
        assert m.name is None
        assert m.capabilities == []
        assert m.env_vars == {}
        assert m.secrets == {}
        assert m.files == {}
        assert m.git_remote is None

    def test_with_all_fields(self) -> None:
        m = WorkspaceManifest(
            name="my-project",
            path="/workspace/my-project",
            template_id="python-fastapi",
            capabilities=["terminal", "browser"],
            dev_command="uvicorn main:app",
            build_command="pip install .",
            test_command="pytest",
            port=8000,
            env_vars={"DEBUG": "1"},
            secrets={"API_KEY": "xxx"},
            files={"main.py": "print('hi')"},
            git_remote=GitRemoteSpec(repo_url="https://github.com/u/r.git"),
        )
        assert m.name == "my-project"
        assert len(m.capabilities) == 2
        assert m.port == 8000
        assert m.git_remote is not None


class TestWorkspaceWriteError:
    def test_construction(self) -> None:
        err = WorkspaceWriteError(path="/app/file.py", message="Permission denied")
        assert err.path == "/app/file.py"
        assert "Permission denied" in err.message


class TestWorkspaceManifestResponse:
    def test_minimal(self) -> None:
        r = WorkspaceManifestResponse(
            session_id="s1",
            workspace_root="/workspace",
            project_root="/workspace/proj",
            project_name="proj",
        )
        assert r.files_written == 0
        assert r.files_failed == 0
        assert r.write_errors == []
        assert r.capabilities == []
        assert r.git_clone_success is None

    def test_with_errors(self) -> None:
        r = WorkspaceManifestResponse(
            session_id="s1",
            workspace_root="/ws",
            project_root="/ws/p",
            project_name="p",
            files_written=5,
            files_failed=2,
            write_errors=[
                WorkspaceWriteError(path="/a.py", message="err1"),
                WorkspaceWriteError(path="/b.py", message="err2"),
            ],
        )
        assert r.files_failed == 2
        assert len(r.write_errors) == 2

    def test_with_git_clone(self) -> None:
        r = WorkspaceManifestResponse(
            session_id="s1",
            workspace_root="/ws",
            project_root="/ws/p",
            project_name="p",
            git_remote=GitRemoteSpec(repo_url="https://github.com/u/r.git"),
            git_clone_success=True,
            git_clone_message="Cloned successfully",
        )
        assert r.git_clone_success is True
