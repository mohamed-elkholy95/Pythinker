"""Request/response schemas for channel link endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GenerateLinkCodeRequest(BaseModel):
    channel: str = "telegram"


class GenerateLinkCodeResponse(BaseModel):
    code: str
    channel: str
    expires_in_seconds: int = 1800
    instructions: str = ""
    bind_command: str = ""
    bot_url: str = ""
    deep_link_url: str = ""


class LinkedChannelResponse(BaseModel):
    channel: str
    sender_id: str
    linked_at: datetime | None = None


class LinkedChannelsListResponse(BaseModel):
    channels: list[LinkedChannelResponse]
