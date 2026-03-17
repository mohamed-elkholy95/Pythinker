from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_create_uses_docker_container_creation_when_static_addresses_disabled() -> None:
    expected = DockerSandbox(ip="127.0.0.1", container_name="sandbox-ephemeral")
    to_thread = AsyncMock(return_value=expected)

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.get_settings",
            return_value=SimpleNamespace(
                uses_static_sandbox_addresses=False,
                sandbox_address="sandbox,sandbox2",
            ),
        ),
        patch("app.infrastructure.external.sandbox.docker_sandbox.asyncio.to_thread", to_thread),
    ):
        sandbox = await DockerSandbox.create()

    to_thread.assert_awaited_once_with(DockerSandbox._create_task)
    assert sandbox.id == "sandbox-ephemeral"


@pytest.mark.asyncio
async def test_destroy_skips_container_remove_for_static_sandbox_identifier() -> None:
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="dev-sandbox-sandbox")

    class _Pool:
        async def force_release_all(self, _cdp_url: str) -> int:
            return 0

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.get_settings",
            return_value=SimpleNamespace(uses_static_sandbox_addresses=True),
        ),
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.BrowserConnectionPool.get_instance",
            return_value=_Pool(),
        ),
        patch("app.infrastructure.external.sandbox.docker_sandbox.docker.from_env") as docker_env,
    ):
        result = await sandbox.destroy()

    assert result is True
    docker_env.assert_not_called()


@pytest.mark.asyncio
async def test_destroy_removes_container_for_ephemeral_identifier() -> None:
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="sandbox-123")

    class _Pool:
        async def force_release_all(self, _cdp_url: str) -> int:
            return 0

    docker_client = MagicMock()
    docker_container = MagicMock()
    docker_client.containers.get.return_value = docker_container

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.get_settings",
            return_value=SimpleNamespace(uses_static_sandbox_addresses=True),
        ),
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.BrowserConnectionPool.get_instance",
            return_value=_Pool(),
        ),
        patch("app.infrastructure.external.sandbox.docker_sandbox.docker.from_env", return_value=docker_client),
    ):
        result = await sandbox.destroy()

    assert result is True
    docker_client.containers.get.assert_called_once_with("sandbox-123")
    docker_container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_ensure_sandbox_fails_fast_when_container_missing_on_connect_error() -> None:
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="sandbox-missing")
    request = httpx.Request("GET", "http://127.0.0.1:8080/api/v1/supervisor/status")
    sandbox.get_client = AsyncMock(side_effect=httpx.ConnectError("connection refused", request=request))

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.get_settings",
            return_value=SimpleNamespace(
                sandbox_warmup_grace_period=0.0,
                sandbox_warmup_initial_retry_delay=0.01,
                sandbox_warmup_max_retry_delay=0.01,
                sandbox_warmup_backoff_multiplier=1.0,
                sandbox_warmup_connection_failure_threshold=12,
                sandbox_warmup_wall_clock_timeout=0.0,
            ),
        ),
        patch.object(sandbox, "_container_exists_and_running", return_value=False),
        pytest.raises(RuntimeError, match="no longer running"),
    ):
        await sandbox.ensure_sandbox()
