"""Tests for DockerSandbox browser pool policy in static sandbox mode."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_get_browser_bypasses_pool_when_static_sandbox_address_configured():
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")
    pooled = AsyncMock()
    sandbox._get_pooled_browser = pooled  # type: ignore[attr-defined]

    browser_instance = MagicMock()
    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.get_settings",
            return_value=SimpleNamespace(sandbox_address="sandbox,sandbox2", browser_pool_enabled=True),
        ),
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.PlaywrightBrowser",
            return_value=browser_instance,
        ),
    ):
        browser = await sandbox.get_browser(verify_connection=False, use_pool=True)

    pooled.assert_not_awaited()
    assert browser is browser_instance


@pytest.mark.asyncio
async def test_get_browser_uses_pool_when_no_static_sandbox_address():
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")
    pooled_browser = MagicMock()
    pooled = AsyncMock(return_value=pooled_browser)
    sandbox._get_pooled_browser = pooled  # type: ignore[attr-defined]

    with (
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.get_settings",
            return_value=SimpleNamespace(sandbox_address=None, browser_pool_enabled=True),
        ),
        patch("app.infrastructure.external.sandbox.docker_sandbox.PlaywrightBrowser") as playwright_cls,
    ):
        browser = await sandbox.get_browser(verify_connection=False, use_pool=True)

    pooled.assert_awaited_once()
    playwright_cls.assert_not_called()
    assert browser is pooled_browser
