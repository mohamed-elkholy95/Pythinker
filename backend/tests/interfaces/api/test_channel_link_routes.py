"""Unit tests for channel link API endpoints.

Tests cover:
    - _generate_link_code format and uniqueness
    - _get_linked_channels repository delegation and response mapping
    - POST /channel-links/generate — Redis storage, response fields
    - GET  /channel-links          — list passthrough
    - DELETE /channel-links/{channel} — valid and invalid channel
"""

from __future__ import annotations

import json
import string
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models.channel import ChannelType
from app.domain.models.user import User
from app.interfaces.api.channel_link_routes import _generate_link_code, _get_linked_channels
from app.interfaces.dependencies import get_current_user
from app.main import app


def _make_user(user_id: str = "user-abc-123") -> User:
    return User(id=user_id, email="user@example.com", fullname="Test User")


def test_generate_link_code_length():
    """Generated code must be exactly 6 characters."""
    code = _generate_link_code()
    assert len(code) == 6


def test_generate_link_code_alphabet():
    """Each character must be an uppercase letter or digit."""
    valid = set(string.ascii_uppercase + string.digits)
    for _ in range(50):
        code = _generate_link_code()
        assert all(ch in valid for ch in code), f"Invalid character in code: {code!r}"


def test_generate_link_code_uniqueness():
    """1000 consecutive codes should not all be identical (probabilistic)."""
    codes = {_generate_link_code() for _ in range(1000)}
    assert len(codes) > 950, "Too many duplicate codes generated"


@pytest.mark.asyncio
async def test_get_linked_channels_maps_fields():
    """_get_linked_channels should map raw MongoDB dicts to LinkedChannelResponse."""
    now = datetime.now(UTC)
    raw_docs = [
        {"channel": "telegram", "sender_id": "tg-user-1", "linked_at": now},
        {"channel": "discord", "sender_id": "dc-user-2", "linked_at": None},
    ]

    mock_repo = AsyncMock()
    mock_repo.get_linked_channels = AsyncMock(return_value=raw_docs)

    mock_db = MagicMock()
    mock_mongodb = MagicMock()
    mock_mongodb.database = mock_db

    with (
        patch(
            "app.interfaces.api.channel_link_routes.MongoUserChannelRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.interfaces.api.channel_link_routes.get_mongodb",
            return_value=mock_mongodb,
        ),
    ):
        result = await _get_linked_channels("user-abc-123")

    assert len(result) == 2
    assert result[0].channel == "telegram"
    assert result[0].sender_id == "tg-user-1"
    assert result[0].linked_at == now
    assert result[1].channel == "discord"
    assert result[1].sender_id == "dc-user-2"
    assert result[1].linked_at is None


@pytest.mark.asyncio
async def test_get_linked_channels_empty():
    """An empty repository result returns an empty list."""
    mock_repo = AsyncMock()
    mock_repo.get_linked_channels = AsyncMock(return_value=[])

    mock_db = MagicMock()
    mock_mongodb = MagicMock()
    mock_mongodb.database = mock_db

    with (
        patch(
            "app.interfaces.api.channel_link_routes.MongoUserChannelRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.interfaces.api.channel_link_routes.get_mongodb",
            return_value=mock_mongodb,
        ),
    ):
        result = await _get_linked_channels("nobody")

    assert result == []


@pytest.fixture()
def _override_user():
    """Override get_current_user for the duration of the test."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_generate_link_code_stores_in_redis():
    """POST /generate stores the correct JSON payload in Redis and returns code."""
    mock_redis = AsyncMock()
    mock_redis.call = AsyncMock(return_value="OK")

    with patch("app.interfaces.api.channel_link_routes.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/channel-links/generate",
                json={"channel": "telegram"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0  # APIResponse success code
    data = body["data"]
    assert data["channel"] == "telegram"
    assert data["expires_in_seconds"] == 900
    assert len(data["code"]) == 6
    assert data["instructions"] != ""
    # Regression: <CODE> placeholder must be substituted with the actual code
    assert "<CODE>" not in data["instructions"], "Placeholder <CODE> was not substituted"
    assert data["code"] in data["instructions"], "Generated code missing from instructions"

    mock_redis.call.assert_awaited_once()
    call_args = mock_redis.call.call_args
    method, redis_key, ttl, payload_str = call_args.args
    assert method == "setex"
    assert redis_key.startswith("channel_link:")
    assert ttl == 900
    stored = json.loads(payload_str)
    assert stored["user_id"] == "user-abc-123"
    assert stored["channel"] == "telegram"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_generate_link_code_invalid_channel():
    """POST /generate with an unknown channel returns 400."""
    mock_redis = AsyncMock()
    mock_redis.call = AsyncMock(return_value="OK")

    with patch("app.interfaces.api.channel_link_routes.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/channel-links/generate",
                json={"channel": "carrier_pigeon"},
            )

    assert response.status_code == 400
    mock_redis.call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_generate_link_code_defaults_to_telegram():
    """POST /generate with no body defaults channel to 'telegram'."""
    mock_redis = AsyncMock()
    mock_redis.call = AsyncMock(return_value="OK")

    with patch("app.interfaces.api.channel_link_routes.get_redis", return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/channel-links/generate", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["channel"] == "telegram"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_list_linked_channels_returns_channels():
    """GET /channel-links returns all linked channels for the authenticated user."""
    now = datetime.now(UTC)
    raw_docs = [{"channel": "telegram", "sender_id": "tg-999", "linked_at": now}]

    mock_repo = AsyncMock()
    mock_repo.get_linked_channels = AsyncMock(return_value=raw_docs)
    mock_db = MagicMock()
    mock_mongodb = MagicMock()
    mock_mongodb.database = mock_db

    with (
        patch(
            "app.interfaces.api.channel_link_routes.MongoUserChannelRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.interfaces.api.channel_link_routes.get_mongodb",
            return_value=mock_mongodb,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/channel-links")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    channels = body["data"]["channels"]
    assert len(channels) == 1
    assert channels[0]["channel"] == "telegram"
    assert channels[0]["sender_id"] == "tg-999"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_list_linked_channels_empty():
    """GET /channel-links returns empty list when no channels are linked."""
    mock_repo = AsyncMock()
    mock_repo.get_linked_channels = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_mongodb = MagicMock()
    mock_mongodb.database = mock_db

    with (
        patch(
            "app.interfaces.api.channel_link_routes.MongoUserChannelRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.interfaces.api.channel_link_routes.get_mongodb",
            return_value=mock_mongodb,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/channel-links")

    assert response.status_code == 200
    assert response.json()["data"]["channels"] == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_unlink_channel_success():
    """DELETE /channel-links/telegram calls repo.unlink_channel and returns success."""
    mock_repo = AsyncMock()
    mock_repo.unlink_channel = AsyncMock(return_value=None)
    mock_db = MagicMock()
    mock_mongodb = MagicMock()
    mock_mongodb.database = mock_db

    with (
        patch(
            "app.interfaces.api.channel_link_routes.MongoUserChannelRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.interfaces.api.channel_link_routes.get_mongodb",
            return_value=mock_mongodb,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/api/v1/channel-links/telegram")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert "telegram" in body["msg"]
    mock_repo.unlink_channel.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_unlink_channel_invalid_channel():
    """DELETE /channel-links/unknown_channel returns 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/channel-links/fax_machine")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_unlink_channel_case_insensitive():
    """DELETE /channel-links/TELEGRAM normalises the channel name to lowercase."""
    mock_repo = AsyncMock()
    mock_repo.unlink_channel = AsyncMock(return_value=None)
    mock_db = MagicMock()
    mock_mongodb = MagicMock()
    mock_mongodb.database = mock_db

    with (
        patch(
            "app.interfaces.api.channel_link_routes.MongoUserChannelRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.interfaces.api.channel_link_routes.get_mongodb",
            return_value=mock_mongodb,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/api/v1/channel-links/TELEGRAM")

    assert response.status_code == 200
    mock_repo.unlink_channel.assert_awaited_once_with("user-abc-123", ChannelType.TELEGRAM)
