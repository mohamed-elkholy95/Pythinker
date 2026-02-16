"""Tests for sandbox screenshot backend selection logic."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import screenshot as screenshot_module


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(screenshot_module.router, prefix="/api/v1/screenshot", tags=["screenshot"])
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("image_format", ["jpeg", "png"])
def test_screenshot_uses_cdp_backend_when_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    image_format: str,
) -> None:
    async def _fake_cdp_capture(quality: int, requested_format: str) -> bytes:
        assert quality == 75
        assert requested_format == image_format
        return b"cdp-image"

    monkeypatch.setattr(screenshot_module, "_capture_with_cdp", _fake_cdp_capture)
    monkeypatch.setattr(screenshot_module, "_xwd_pipeline_available", lambda: False)

    response = client.get(
        f"/api/v1/screenshot?quality=75&scale=0.5&format={image_format}"
    )

    assert response.status_code == 200
    assert response.headers["x-screenshot-backend"] == "cdp"
    assert response.content == b"cdp-image"


def test_screenshot_falls_back_to_xwd_when_cdp_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_cdp_capture(quality: int, requested_format: str) -> bytes | None:
        assert quality == 80
        assert requested_format == "jpeg"
        return None

    async def _fake_xwd_capture(
        quality: int, scale: float, requested_format: str
    ) -> bytes:
        assert quality == 80
        assert scale == 0.5
        assert requested_format == "jpeg"
        return b"xwd-image"

    monkeypatch.setattr(screenshot_module, "_capture_with_cdp", _fake_cdp_capture)
    monkeypatch.setattr(screenshot_module, "_xwd_pipeline_available", lambda: True)
    monkeypatch.setattr(screenshot_module, "_capture_with_xwd_pipeline", _fake_xwd_capture)

    response = client.get("/api/v1/screenshot?quality=80&scale=0.5&format=jpeg")

    assert response.status_code == 200
    assert response.headers["x-screenshot-backend"] == "xwd"
    assert response.content == b"xwd-image"


def test_screenshot_returns_503_when_no_backend_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that 503 is returned only when all backends fail AND cache is empty."""

    async def _fake_cdp_capture(quality: int, requested_format: str) -> bytes | None:
        assert quality == 75
        assert requested_format == "jpeg"
        return None

    async def _fake_xwd_pillow(
        quality: int, scale: float, requested_format: str
    ) -> bytes | None:
        return None

    # Clear the module-level cache before this test
    screenshot_module._screenshot_cache._entries.clear()

    monkeypatch.setattr(screenshot_module, "_capture_with_cdp", _fake_cdp_capture)
    monkeypatch.setattr(screenshot_module, "_xwd_pipeline_available", lambda: False)
    monkeypatch.setattr(screenshot_module, "_capture_with_xwd_pillow", _fake_xwd_pillow)

    response = client.get("/api/v1/screenshot?quality=75&scale=0.5&format=jpeg")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
