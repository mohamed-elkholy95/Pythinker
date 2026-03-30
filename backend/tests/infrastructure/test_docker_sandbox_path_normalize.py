"""Tests for sandbox path remapping (LLM /app vs /workspace)."""

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


def test_normalize_maps_app_prefix_to_workspace() -> None:
    out, remapped = DockerSandbox._normalize_sandbox_user_path("/app/report.md")
    assert remapped is True
    assert out == "/workspace/report.md"


def test_normalize_maps_app_root_to_workspace() -> None:
    out, remapped = DockerSandbox._normalize_sandbox_user_path("/app")
    assert remapped is True
    assert out == "/workspace"


def test_normalize_leaves_workspace_unchanged() -> None:
    out, remapped = DockerSandbox._normalize_sandbox_user_path("/workspace/foo.md")
    assert remapped is False
    assert out == "/workspace/foo.md"


def test_normalize_accepts_backslashes() -> None:
    out, remapped = DockerSandbox._normalize_sandbox_user_path("\\app\\a.md")
    assert remapped is True
    assert out == "/workspace/a.md"
