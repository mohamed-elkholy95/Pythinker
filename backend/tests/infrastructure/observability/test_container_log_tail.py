"""Tests for container_log_tail."""

from unittest.mock import MagicMock, patch

from app.infrastructure.observability.container_log_tail import tail_running_container_logs


def test_returns_empty_when_docker_unavailable() -> None:
    with patch("app.infrastructure.observability.container_log_tail.docker", None):
        out, hint = tail_running_container_logs()
    assert out == {"backend": [], "sandbox": []}
    assert hint is not None


def test_tails_matching_containers() -> None:
    mock_backend = MagicMock()
    mock_backend.name = "proj-backend-1"
    mock_backend.logs.return_value = b"line1\nline2\n"

    mock_sandbox = MagicMock()
    mock_sandbox.name = "proj-sandbox-1"
    mock_sandbox.logs.return_value = b"sandbox-a\n"

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_backend, mock_sandbox]

    with patch("app.infrastructure.observability.container_log_tail.docker") as mock_docker:
        mock_docker.from_env.return_value = mock_client
        out, hint = tail_running_container_logs()

    assert out["backend"] == ["line1", "line2"]
    assert out["sandbox"] == ["sandbox-a"]
    assert hint is None
