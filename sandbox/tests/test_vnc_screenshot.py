"""Tests for sandbox VNC screenshot backend selection logic."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import vnc as vnc_module


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(vnc_module.router, prefix="/api/v1/vnc", tags=["vnc"])
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

    monkeypatch.setattr(vnc_module, "_capture_with_cdp", _fake_cdp_capture)
    monkeypatch.setattr(vnc_module, "_xwd_pipeline_available", lambda: False)

    response = client.get(f"/api/v1/vnc/screenshot?quality=75&scale=0.5&format={image_format}")

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

    async def _fake_xwd_capture(quality: int, scale: float, requested_format: str) -> bytes:
        assert quality == 80
        assert scale == 0.5
        assert requested_format == "jpeg"
        return b"xwd-image"

    monkeypatch.setattr(vnc_module, "_capture_with_cdp", _fake_cdp_capture)
    monkeypatch.setattr(vnc_module, "_xwd_pipeline_available", lambda: True)
    monkeypatch.setattr(vnc_module, "_capture_with_xwd_pipeline", _fake_xwd_capture)

    response = client.get("/api/v1/vnc/screenshot?quality=80&scale=0.5&format=jpeg")

    assert response.status_code == 200
    assert response.headers["x-screenshot-backend"] == "xwd"
    assert response.content == b"xwd-image"


def test_screenshot_returns_503_when_no_backend_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_cdp_capture(quality: int, requested_format: str) -> bytes | None:
        assert quality == 75
        assert requested_format == "jpeg"
        return None

    monkeypatch.setattr(vnc_module, "_capture_with_cdp", _fake_cdp_capture)
    monkeypatch.setattr(vnc_module, "_xwd_pipeline_available", lambda: False)

    response = client.get("/api/v1/vnc/screenshot?quality=75&scale=0.5&format=jpeg")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
