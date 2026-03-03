"""REST endpoints for channel account link management.

Provides:
    POST   /channel-links/generate  — generate a one-time link code
    GET    /channel-links           — list all linked channels for the current user
    DELETE /channel-links/{channel} — unlink a channel from the current user
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import string
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends

from app.application.errors.exceptions import BadRequestError, NotFoundError
from app.core.config import get_settings
from app.domain.models.channel import ChannelType
from app.domain.models.user import User
from app.infrastructure.repositories.user_channel_repository import MongoUserChannelRepository
from app.infrastructure.storage.mongodb import get_mongodb
from app.infrastructure.storage.redis import get_redis
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.channel_link import (
    GenerateLinkCodeRequest,
    GenerateLinkCodeResponse,
    LinkedChannelResponse,
    LinkedChannelsListResponse,
    SaveTelegramTokenRequest,
    TelegramTokenStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel-links", tags=["channel-links"])

# Link code configuration
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 6
_CODE_TTL_SECONDS = 900  # 15 minutes
_REDIS_KEY_PREFIX = "channel_link"
_CHANNEL_SECRET_COLLECTION = "user_channel_secrets"
_TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{20,}$")


def _generate_link_code() -> str:
    """Generate a cryptographically random 6-character alphanumeric code.

    Uses ``secrets.choice`` to draw from uppercase letters and digits,
    producing a code space of 36^6 = 2,176,782,336 possibilities.
    """
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def _build_redis_key(code: str) -> str:
    """Build the Redis key for a link code."""
    return f"{_REDIS_KEY_PREFIX}:{code}"


def _build_fernet() -> Fernet:
    """Build a deterministic Fernet key from configured secret material."""
    settings = get_settings()
    seed = (
        settings.credential_encryption_key
        or settings.jwt_secret_key
        or settings.local_auth_password
        or "pythinker-dev-channel-secret"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _encrypt_secret(value: str) -> str:
    """Encrypt a secret string for at-rest persistence."""
    return _build_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _channel_secret_collection() -> Any:
    """Return MongoDB collection for per-user channel secrets."""
    return get_mongodb().database[_CHANNEL_SECRET_COLLECTION]


def _validate_telegram_bot_token(token: str) -> str:
    """Validate Telegram bot token shape and return normalized value."""
    normalized = token.strip()
    if not _TELEGRAM_BOT_TOKEN_PATTERN.fullmatch(normalized):
        raise BadRequestError(
            "Invalid Telegram bot token format. Expected pattern like '123456789:AA...'."
        )
    return normalized


async def _upsert_encrypted_channel_secret(
    *,
    user_id: str,
    channel: ChannelType,
    secret_value: str,
) -> None:
    """Encrypt and upsert channel secret for a user."""
    now = datetime.now(UTC)
    encrypted = _encrypt_secret(secret_value)
    await _channel_secret_collection().update_one(
        {"user_id": user_id, "channel": channel.value},
        {
            "$set": {"secret_encrypted": encrypted, "updated_at": now},
            "$setOnInsert": {"user_id": user_id, "channel": channel.value, "created_at": now},
        },
        upsert=True,
    )


async def _has_saved_channel_secret(*, user_id: str, channel: ChannelType) -> bool:
    """Check whether a channel secret exists for a user."""
    doc = await _channel_secret_collection().find_one(
        {"user_id": user_id, "channel": channel.value},
        {"_id": 0, "secret_encrypted": 1},
    )
    if not doc:
        return False
    secret = doc.get("secret_encrypted")
    return bool(secret and isinstance(secret, str))


def _channel_instructions(channel: str) -> str:
    """Return human-readable instructions for completing the link flow."""
    channel_lower = channel.lower()
    if channel_lower == "telegram":
        return "Open your Telegram bot and send: /link <CODE> — replace <CODE> with the code above."
    if channel_lower == "discord":
        return "In your Discord server, type: /link <CODE> — replace <CODE> with the code above."
    return f"Send the code above to the {channel} bot to complete account linking."


@router.post("/generate", response_model=APIResponse[GenerateLinkCodeResponse])
async def generate_link_code(
    request: GenerateLinkCodeRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[GenerateLinkCodeResponse]:
    """Generate a short-lived, one-time link code for a channel.

    The code is stored in Redis with a 15-minute TTL.  The external
    channel bot redeems this code to bind its identity to the
    authenticated web account.
    """
    # Validate that the requested channel is a known ChannelType.
    try:
        channel_type = ChannelType(request.channel.lower())
    except ValueError:
        valid = ", ".join(c.value for c in ChannelType)
        raise BadRequestError(f"Unknown channel '{request.channel}'. Valid values: {valid}") from None

    if channel_type == ChannelType.TELEGRAM:
        has_token = await _has_saved_channel_secret(
            user_id=current_user.id,
            channel=ChannelType.TELEGRAM,
        )
        if not has_token:
            raise BadRequestError(
                "Telegram bot token is not configured. Save your token in Settings before linking Telegram."
            )

    code = _generate_link_code()
    redis_key = _build_redis_key(code)
    payload = json.dumps({"user_id": current_user.id, "channel": channel_type.value})

    redis = get_redis()
    await redis.call("setex", redis_key, _CODE_TTL_SECONDS, payload)

    logger.info(
        "Generated link code for user=%s channel=%s ttl=%ss",
        current_user.id,
        channel_type.value,
        _CODE_TTL_SECONDS,
    )

    instructions = _channel_instructions(channel_type.value).replace("<CODE>", code)

    return APIResponse.success(
        GenerateLinkCodeResponse(
            code=code,
            channel=channel_type.value,
            expires_in_seconds=_CODE_TTL_SECONDS,
            instructions=instructions,
        )
    )


@router.post("/telegram-token", response_model=APIResponse[TelegramTokenStatusResponse])
async def save_telegram_token(
    request: SaveTelegramTokenRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[TelegramTokenStatusResponse]:
    """Validate and securely store the current user's Telegram bot token."""
    token = _validate_telegram_bot_token(request.token)
    await _upsert_encrypted_channel_secret(
        user_id=current_user.id,
        channel=ChannelType.TELEGRAM,
        secret_value=token,
    )
    logger.info("Saved Telegram token for user=%s", current_user.id)
    return APIResponse.success(TelegramTokenStatusResponse(configured=True))


@router.get("/telegram-token/status", response_model=APIResponse[TelegramTokenStatusResponse])
async def telegram_token_status(
    current_user: User = Depends(get_current_user),
) -> APIResponse[TelegramTokenStatusResponse]:
    """Return whether the current user has a saved Telegram bot token."""
    configured = await _has_saved_channel_secret(
        user_id=current_user.id,
        channel=ChannelType.TELEGRAM,
    )
    return APIResponse.success(TelegramTokenStatusResponse(configured=configured))


async def _get_linked_channels(user_id: str) -> list[LinkedChannelResponse]:
    """Retrieve all channel identities linked to *user_id* from MongoDB."""
    db = get_mongodb().database
    repo = MongoUserChannelRepository(db)
    raw_docs = await repo.get_linked_channels(user_id)
    return [
        LinkedChannelResponse(
            channel=doc["channel"],
            sender_id=doc["sender_id"],
            linked_at=doc.get("linked_at"),
        )
        for doc in raw_docs
    ]


@router.get("", response_model=APIResponse[LinkedChannelsListResponse])
async def list_linked_channels(
    current_user: User = Depends(get_current_user),
) -> APIResponse[LinkedChannelsListResponse]:
    """Return all channels currently linked to the authenticated user."""
    channels = await _get_linked_channels(current_user.id)
    return APIResponse.success(LinkedChannelsListResponse(channels=channels))


@router.delete("/{channel}", response_model=APIResponse[dict])
async def unlink_channel(
    channel: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[dict]:
    """Remove the link between the authenticated user and *channel*.

    Raises 404 if the channel value is not a recognised ChannelType.
    """
    try:
        channel_type = ChannelType(channel.lower())
    except ValueError:
        raise NotFoundError(f"Channel '{channel}' not found or not supported") from None

    db = get_mongodb().database
    repo = MongoUserChannelRepository(db)
    await repo.unlink_channel(current_user.id, channel_type)

    logger.info(
        "Unlinked channel %s from user=%s",
        channel_type.value,
        current_user.id,
    )

    return APIResponse.success(msg=f"Channel '{channel_type.value}' unlinked successfully")
