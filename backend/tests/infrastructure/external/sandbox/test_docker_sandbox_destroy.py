"""Tests for DockerSandbox destroy idempotency."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import NotFound as DockerNotFound

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_destroy_returns_true_when_container_already_removed():
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="missing-container")
    mock_client = SimpleNamespace(is_closed=False)

    async def _aclose() -> None:
        return None

    mock_client.aclose = _aclose
    sandbox.client = mock_client

    class _Pool:
        async def force_release_all(self, _cdp_url: str) -> int:
            return 0

    pool = _Pool()

    docker_client = MagicMock()
    docker_client.containers.get.side_effect = DockerNotFound("not found")

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.BrowserConnectionPool.get_instance",
            return_value=pool,
        ),
        patch("app.infrastructure.external.sandbox.docker_sandbox.docker.from_env", return_value=docker_client),
    ):
        result = await sandbox.destroy()

    assert result is True


@pytest.mark.asyncio
async def test_destroy_returns_false_on_unexpected_container_error():
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="bad-container")
    mock_client = SimpleNamespace(is_closed=False)

    async def _aclose() -> None:
        return None

    mock_client.aclose = _aclose
    sandbox.client = mock_client

    class _Pool:
        async def force_release_all(self, _cdp_url: str) -> int:
            return 0

    pool = _Pool()

    docker_client = MagicMock()
    docker_client.containers.get.side_effect = RuntimeError("docker unavailable")

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.BrowserConnectionPool.get_instance",
            return_value=pool,
        ),
        patch("app.infrastructure.external.sandbox.docker_sandbox.docker.from_env", return_value=docker_client),
    ):
        result = await sandbox.destroy()

    assert result is False
