"""REST endpoints for channel account link management.

Provides:
    POST   /channel-links/generate  — generate a one-time link code
    GET    /channel-links           — list all linked channels for the current user
    DELETE /channel-links/{channel} — unlink a channel from the current user
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import string

from fastapi import APIRouter, Depends

from app.application.errors.exceptions import BadRequestError, NotFoundError
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
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel-links", tags=["channel-links"])

# Link code configuration
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 22
_CODE_TTL_SECONDS = 1800  # 30 minutes
_REDIS_KEY_PREFIX = "channel_link"
_DEFAULT_TELEGRAM_BOT_USERNAME = "pythinker_bot"


def _generate_link_code() -> str:
    """Generate a cryptographically random alphanumeric link code."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def _build_redis_key(code: str) -> str:
    """Build the Redis key for a link code."""
    return f"{_REDIS_KEY_PREFIX}:{code}"


def _telegram_bot_username() -> str:
    """Resolve Telegram bot username from env with a stable fallback."""
    raw = os.getenv("TELEGRAM_BOT_USERNAME", _DEFAULT_TELEGRAM_BOT_USERNAME)
    username = raw.strip().lstrip("@")
    return username or _DEFAULT_TELEGRAM_BOT_USERNAME


def _telegram_bot_url() -> str:
    """Get canonical Telegram bot URL."""
    return f"https://t.me/{_telegram_bot_username()}"


def _telegram_deep_link(code: str) -> str:
    """Build a Telegram ``?start=`` deep link that triggers ``/start bind_<code>``.

    When the user clicks the link, Telegram opens the bot and sends
    ``/start bind_<code>`` automatically.  The gateway's
    ``MessageRouter._normalize_command_alias`` converts this into
    ``/link <code>`` for code redemption.
    """
    return f"{_telegram_bot_url()}?start=bind_{code}"


def _bind_command(channel: str, code: str) -> str:
    """Return channel-specific bind command shown to users."""
    if channel.lower() == "telegram":
        return f":bind {code}"
    return f"/link {code}"


def _channel_instructions(channel: str, code: str) -> str:
    """Return human-readable instructions for completing the link flow."""
    channel_lower = channel.lower()
    bind_cmd = _bind_command(channel_lower, code)
    if channel_lower == "telegram":
        return (
            "Click Link Account to open the Pythinker Telegram bot, then send "
            f"`{bind_cmd}` in chat to link your account."
        )
    if channel_lower == "discord":
        return f"In your Discord server, type `{bind_cmd}` to complete account linking."
    return f"Send `{bind_cmd}` to the {channel} bot to complete account linking."


@router.post("/generate", response_model=APIResponse[GenerateLinkCodeResponse])
async def generate_link_code(
    request: GenerateLinkCodeRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[GenerateLinkCodeResponse]:
    """Generate a short-lived, one-time link code for a channel.

    The code is stored in Redis with a 30-minute TTL.  The external
    channel bot redeems this code to bind its identity to the
    authenticated web account.
    """
    try:
        channel_type = ChannelType(request.channel.lower())
    except ValueError:
        valid = ", ".join(c.value for c in ChannelType)
        raise BadRequestError(f"Unknown channel '{request.channel}'. Valid values: {valid}") from None

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

    bind_command = _bind_command(channel_type.value, code)
    bot_url = _telegram_bot_url() if channel_type == ChannelType.TELEGRAM else ""
    deep_link_url = _telegram_deep_link(code) if channel_type == ChannelType.TELEGRAM else ""

    return APIResponse.success(
        GenerateLinkCodeResponse(
            code=code,
            channel=channel_type.value,
            expires_in_seconds=_CODE_TTL_SECONDS,
            instructions=_channel_instructions(channel_type.value, code),
            bind_command=bind_command,
            bot_url=bot_url,
            deep_link_url=deep_link_url,
        )
    )


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
