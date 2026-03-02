"""Channel gateway domain models.

Defines the core types for multi-channel messaging: inbound/outbound messages,
channel types, media attachments, and user-channel linking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ChannelType(StrEnum):
    """Supported messaging channels."""

    WEB = "web"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CRON = "cron"
    API = "api"


class MediaAttachment(BaseModel):
    """File or media attached to a message."""

    url: str
    mime_type: str = ""
    filename: str = ""
    size_bytes: int = 0


class InboundMessage(BaseModel):
    """Message received from an external channel.

    Attributes:
        id: Unique message identifier (auto-generated hex).
        channel: Source channel type.
        sender_id: Platform-specific sender identifier.
        chat_id: Platform-specific chat/conversation identifier.
        content: Message text body.
        timestamp: When the message was sent.
        media: Attached files or images.
        metadata: Channel-specific extra data (e.g. message_thread_id).
        session_key_override: Optional explicit session key to route into.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    channel: ChannelType
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    media: list[MediaAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_key_override: str | None = None


class OutboundMessage(BaseModel):
    """Message to be sent to an external channel.

    Attributes:
        channel: Target channel type.
        chat_id: Platform-specific chat/conversation identifier.
        content: Message text body.
        reply_to: Optional message ID to reply to.
        media: Attached files or images.
        metadata: Channel-specific extra data.
    """

    channel: ChannelType
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[MediaAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserChannelLink(BaseModel):
    """Links a Pythinker user account to an external channel identity.

    Attributes:
        user_id: Internal Pythinker user ID.
        channel: Channel type.
        sender_id: Platform-specific sender identifier.
        chat_id: Platform-specific chat/conversation identifier.
        display_name: Human-readable name for the linked identity.
        linked_at: When the link was established.
    """

    user_id: str
    channel: ChannelType
    sender_id: str
    chat_id: str
    display_name: str | None = None
    linked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
