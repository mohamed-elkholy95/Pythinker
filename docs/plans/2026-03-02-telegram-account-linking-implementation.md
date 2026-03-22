# Telegram Account Linking — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow web UI users to link their Telegram account via a 6-digit code, so Telegram bot sessions appear in the web UI under the same user identity.

**Architecture:** Code-based linking. Web UI generates a 6-digit code stored in Redis (15 min TTL). User sends `/link CODE` to @Pythinkbot. MessageRouter validates the code, updates `user_channel_links` to map the Telegram identity to the web user_id. Future sessions use the web user_id.

**Tech Stack:** FastAPI, Redis, MongoDB (Motor), Vue 3 Composition API, Pydantic v2, pytest

---

## Task 1: Add Repository Methods for Channel Linking

**Files:**
- Modify: `backend/app/infrastructure/repositories/user_channel_repository.py:83-105`
- Test: `backend/tests/infrastructure/repositories/test_user_channel_repository.py` (Create)

**Context:** The `MongoUserChannelRepository` already has `create_channel_user()` (line 83) and `get_user_by_channel()` (line 70). We need 3 new methods: `link_channel_to_user()`, `get_linked_channels()`, and `unlink_channel()`. Also need `migrate_sessions()` to re-assign sessions from old channel-user-id to web user_id.

**Step 1: Write the failing tests**

Create `backend/tests/infrastructure/repositories/test_user_channel_repository.py`:

```python
"""Unit tests for MongoUserChannelRepository linking methods."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.channel import ChannelType
from app.infrastructure.repositories.user_channel_repository import (
    MongoUserChannelRepository,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock Motor database with links and sessions collections."""
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda name: {
        "user_channel_links": MagicMock(),
        "channel_sessions": MagicMock(),
    }[name])
    return db


@pytest.fixture
def repo(mock_db: MagicMock) -> MongoUserChannelRepository:
    return MongoUserChannelRepository(mock_db)


class TestLinkChannelToUser:
    """link_channel_to_user() upserts a user_channel_links doc."""

    @pytest.mark.asyncio
    async def test_link_new_channel(self, repo: MongoUserChannelRepository) -> None:
        """Upserting a link for a new (channel, sender_id) sets user_id."""
        repo._links.update_one = AsyncMock()
        await repo.link_channel_to_user(
            channel=ChannelType.TELEGRAM,
            sender_id="5829880422|UNIDM9",
            web_user_id="abc123webuser",
        )
        repo._links.update_one.assert_awaited_once()
        call_args = repo._links.update_one.call_args
        # Filter matches on channel + sender_id
        assert call_args[0][0]["channel"] == "telegram"
        assert call_args[0][0]["sender_id"] == "5829880422|UNIDM9"
        # $set includes user_id and linked_at
        set_fields = call_args[0][1]["$set"]
        assert set_fields["user_id"] == "abc123webuser"
        assert "linked_at" in set_fields

    @pytest.mark.asyncio
    async def test_link_returns_old_user_id(self, repo: MongoUserChannelRepository) -> None:
        """When re-linking, returns the previous user_id for session migration."""
        repo._links.find_one_and_update = AsyncMock(
            return_value={"user_id": "channel-oldid12345"}
        )
        old_id = await repo.link_channel_to_user(
            channel=ChannelType.TELEGRAM,
            sender_id="5829880422|UNIDM9",
            web_user_id="abc123webuser",
        )
        assert old_id == "channel-oldid12345"


class TestGetLinkedChannels:
    """get_linked_channels() returns all channels linked to a user_id."""

    @pytest.mark.asyncio
    async def test_returns_linked_channels(self, repo: MongoUserChannelRepository) -> None:
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {
                "channel": "telegram",
                "sender_id": "5829880422|UNIDM9",
                "linked_at": datetime(2026, 3, 2, tzinfo=UTC),
            }
        ])
        repo._links.find = MagicMock(return_value=mock_cursor)

        result = await repo.get_linked_channels("abc123webuser")
        assert len(result) == 1
        assert result[0]["channel"] == "telegram"

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_links(self, repo: MongoUserChannelRepository) -> None:
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        repo._links.find = MagicMock(return_value=mock_cursor)

        result = await repo.get_linked_channels("no-links-user")
        assert result == []


class TestUnlinkChannel:
    """unlink_channel() removes a channel link document."""

    @pytest.mark.asyncio
    async def test_unlink_deletes_doc(self, repo: MongoUserChannelRepository) -> None:
        repo._links.delete_one = AsyncMock()
        await repo.unlink_channel("abc123webuser", ChannelType.TELEGRAM)
        repo._links.delete_one.assert_awaited_once_with({
            "user_id": "abc123webuser",
            "channel": "telegram",
        })


class TestMigrateSessions:
    """migrate_sessions() re-assigns sessions from old to new user_id."""

    @pytest.mark.asyncio
    async def test_migrate_updates_sessions(self, repo: MongoUserChannelRepository) -> None:
        repo._sessions.update_many = AsyncMock()
        await repo.migrate_sessions(
            old_user_id="channel-oldid12345",
            new_user_id="abc123webuser",
            channel=ChannelType.TELEGRAM,
        )
        repo._sessions.update_many.assert_awaited_once()
        call_args = repo._sessions.update_many.call_args
        assert call_args[0][0]["user_id"] == "channel-oldid12345"
        assert call_args[0][0]["channel"] == "telegram"
        assert call_args[0][1]["$set"]["user_id"] == "abc123webuser"
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/mac/Desktop/Pythinker-main/backend
conda activate pythinker
pytest tests/infrastructure/repositories/test_user_channel_repository.py -v -p no:cov -o addopts=
```

Expected: FAIL (methods don't exist yet)

**Step 3: Implement the 4 new methods**

Add to `backend/app/infrastructure/repositories/user_channel_repository.py` after line 105 (after `create_channel_user`):

```python
    async def link_channel_to_user(
        self,
        channel: ChannelType,
        sender_id: str,
        web_user_id: str,
    ) -> str | None:
        """Link an external channel identity to an existing web user account.

        Uses ``find_one_and_update`` to atomically update the link and return
        the previous ``user_id`` (needed for session migration).

        Returns the previous ``user_id`` if the link already existed, or
        ``None`` if this is a brand-new link.
        """
        old_doc = await self._links.find_one_and_update(
            {"channel": str(channel), "sender_id": sender_id},
            {
                "$set": {
                    "user_id": web_user_id,
                    "linked_at": datetime.now(UTC),
                },
                "$setOnInsert": {
                    "channel": str(channel),
                    "sender_id": sender_id,
                    "created_at": datetime.now(UTC),
                },
            },
            upsert=True,
            return_document=False,  # Return the OLD document
        )
        old_user_id = old_doc["user_id"] if old_doc else None
        logger.info(
            "Linked %s/%s → user %s (was %s)",
            channel,
            sender_id,
            web_user_id,
            old_user_id,
        )
        return old_user_id

    async def get_linked_channels(self, user_id: str) -> list[dict]:
        """Return all channel links for a given user_id.

        Each dict contains: ``channel``, ``sender_id``, ``linked_at``.
        """
        cursor = self._links.find(
            {"user_id": user_id, "linked_at": {"$exists": True}},
            {"_id": 0, "channel": 1, "sender_id": 1, "linked_at": 1},
        )
        return await cursor.to_list(length=50)

    async def unlink_channel(self, user_id: str, channel: ChannelType) -> None:
        """Remove a channel link for the given user."""
        await self._links.delete_one({
            "user_id": user_id,
            "channel": str(channel),
        })
        logger.info("Unlinked %s for user %s", channel, user_id)

    async def migrate_sessions(
        self,
        old_user_id: str,
        new_user_id: str,
        channel: ChannelType,
    ) -> None:
        """Re-assign channel_sessions from old_user_id to new_user_id.

        Called after linking so existing sessions become visible under the
        web user account.
        """
        result = await self._sessions.update_many(
            {"user_id": old_user_id, "channel": str(channel)},
            {"$set": {"user_id": new_user_id, "updated_at": datetime.now(UTC)}},
        )
        if result.modified_count:
            logger.info(
                "Migrated %d sessions from %s to %s on %s",
                result.modified_count,
                old_user_id,
                new_user_id,
                channel,
            )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/repositories/test_user_channel_repository.py -v -p no:cov -o addopts=
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/repositories/user_channel_repository.py \
        backend/tests/infrastructure/repositories/test_user_channel_repository.py
git commit -m "feat(channel): add repository methods for account linking

Add link_channel_to_user(), get_linked_channels(), unlink_channel(),
and migrate_sessions() to MongoUserChannelRepository."
```

---

## Task 2: Add `/link` Slash Command to MessageRouter

**Files:**
- Modify: `backend/app/domain/services/channels/message_router.py:27,29-35,194-247`
- Modify: `backend/tests/integration/test_channel_integration.py`

**Context:** MessageRouter handles slash commands at line 194. `SLASH_COMMANDS` is a frozenset at line 27. We add `/link` handling that validates a code from Redis and calls `link_channel_to_user()`. The `UserChannelRepository` Protocol (line 44) needs the new methods added too.

**Step 1: Write the failing tests**

Add to `backend/tests/integration/test_channel_integration.py` after the `TestUnknownSenderCreatesUser` class (after line 294):

```python
# ---------------------------------------------------------------------------
# Test 6: /link command links Telegram to web account
# ---------------------------------------------------------------------------


class TestSlashCommandLinkAccount:
    """/link CODE links a Telegram identity to an existing web user."""

    @pytest.mark.asyncio
    async def test_link_valid_code(self) -> None:
        """/link with a valid code updates the channel link and confirms.

        Verifies:
        - link_channel_to_user is called with the web user_id from the code.
        - migrate_sessions is called to re-assign existing sessions.
        - A confirmation reply is sent to the user.
        - AgentService is NOT invoked.
        """
        repo = _make_repo(user_id="channel-auto123456", session_id=None)
        repo.link_channel_to_user = AsyncMock(return_value="channel-auto123456")
        repo.migrate_sessions = AsyncMock()
        agent_svc = _make_agent_service()

        # Mock Redis to return a valid link code
        mock_redis = AsyncMock()
        mock_redis.call = AsyncMock(side_effect=lambda method, *args, **kwargs: {
            "get": '{"user_id": "webuser-abc123", "channel": "telegram"}',
            "delete": 1,
        }.get(method))

        router = MessageRouter(agent_svc, repo)

        with patch("app.domain.services.channels.message_router.get_redis", return_value=mock_redis):
            inbound = _make_inbound("/link ABC123")
            replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "linked" in replies[0].content.lower()

        # Channel was linked to web user
        repo.link_channel_to_user.assert_awaited_once_with(
            ChannelType.TELEGRAM,
            "tg-user-integration",
            "webuser-abc123",
        )

        # Sessions migrated
        repo.migrate_sessions.assert_awaited_once()

        # AgentService NOT called
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_link_invalid_code(self) -> None:
        """/link with expired/invalid code returns an error message."""
        repo = _make_repo(user_id="channel-auto123456")
        agent_svc = _make_agent_service()

        mock_redis = AsyncMock()
        mock_redis.call = AsyncMock(return_value=None)  # Code not found

        router = MessageRouter(agent_svc, repo)

        with patch("app.domain.services.channels.message_router.get_redis", return_value=mock_redis):
            inbound = _make_inbound("/link BADCODE")
            replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "invalid" in replies[0].content.lower() or "expired" in replies[0].content.lower()

    @pytest.mark.asyncio
    async def test_link_no_code_provided(self) -> None:
        """/link without a code returns usage instructions."""
        repo = _make_repo(user_id="channel-auto123456")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        inbound = _make_inbound("/link")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "usage" in replies[0].content.lower() or "/link" in replies[0].content.lower()
```

Also add `from unittest.mock import patch` to the existing imports at line 17 if not already there.

**Step 2: Run tests to verify they fail**

```bash
pytest tests/integration/test_channel_integration.py::TestSlashCommandLinkAccount -v -p no:cov -o addopts=
```

Expected: FAIL ("/link" not in SLASH_COMMANDS)

**Step 3: Implement `/link` in MessageRouter**

Modify `backend/app/domain/services/channels/message_router.py`:

a) Update `SLASH_COMMANDS` (line 27):
```python
SLASH_COMMANDS = frozenset({"/new", "/stop", "/help", "/status", "/link"})
```

b) Update `HELP_TEXT` (lines 29-35):
```python
HELP_TEXT = (
    "Available commands:\n"
    "  /new    \u2014 Start a new conversation\n"
    "  /stop   \u2014 Cancel the current request\n"
    "  /status \u2014 Show active session info\n"
    "  /link   \u2014 Link your Telegram to your web account\n"
    "  /help   \u2014 Show this help message"
)
```

c) Add `link_channel_to_user` and `migrate_sessions` to the `UserChannelRepository` Protocol (after line 73):
```python
    async def link_channel_to_user(self, channel: ChannelType, sender_id: str, web_user_id: str) -> str | None:
        """Link a channel identity to a web user_id. Returns previous user_id."""
        ...

    async def migrate_sessions(self, old_user_id: str, new_user_id: str, channel: ChannelType) -> None:
        """Re-assign sessions from old to new user_id."""
        ...
```

d) Add `/link` handler inside `_handle_slash_command()` (after the `/stop` block, before the unknown-command fallback):
```python
        if command == "/link":
            parts = content.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                yield self._make_reply(
                    message,
                    "Usage: /link CODE\n\nGenerate a link code from the Pythinker web UI "
                    "(Account Settings \u2192 Link Telegram).",
                )
                return

            code = parts[1].strip().upper()
            try:
                from app.infrastructure.storage.redis import get_redis

                redis = get_redis()
                raw = await redis.call("get", f"channel_link:{code}")
                if raw is None:
                    yield self._make_reply(
                        message,
                        "Invalid or expired link code. Please generate a new one from the web UI.",
                    )
                    return

                import json
                link_data = json.loads(raw)
                web_user_id = link_data["user_id"]

                # Link the channel identity to the web user
                old_user_id = await self._user_channel_repo.link_channel_to_user(
                    message.channel,
                    message.sender_id,
                    web_user_id,
                )

                # Migrate existing sessions to the new user_id
                if old_user_id and old_user_id != web_user_id:
                    await self._user_channel_repo.migrate_sessions(
                        old_user_id, web_user_id, message.channel,
                    )

                # Consume the code (single-use)
                await redis.call("delete", f"channel_link:{code}")

                yield self._make_reply(
                    message,
                    "Account linked! Your Telegram sessions will now appear in the web UI.",
                )
            except Exception:
                logger.exception("Failed to process /link command")
                yield self._make_reply(
                    message,
                    "An error occurred while linking your account. Please try again.",
                )
            return
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/integration/test_channel_integration.py -v -p no:cov -o addopts=
```

Expected: ALL PASS (all 8 tests including 3 new ones)

**Step 5: Commit**

```bash
git add backend/app/domain/services/channels/message_router.py \
        backend/tests/integration/test_channel_integration.py
git commit -m "feat(channel): add /link slash command for account linking

Users can send '/link CODE' to the Telegram bot to link their
channel identity to their web UI account. Validates code from
Redis, updates user_channel_links, migrates existing sessions."
```

---

## Task 3: Add Backend API Endpoints for Link Code Generation

**Files:**
- Create: `backend/app/interfaces/api/channel_link_routes.py`
- Create: `backend/app/interfaces/schemas/channel_link.py`
- Modify: `backend/app/interfaces/api/routes.py:3-21,29-47`
- Test: `backend/tests/interfaces/api/test_channel_link_routes.py` (Create)

**Context:** We need 3 REST endpoints: generate code, list links, unlink. Follow the pattern from `auth_routes.py`: FastAPI `APIRouter` with `prefix="/channel-links"`, `Depends(get_current_user)` for auth, `APIResponse` wrapper. Redis stores codes as `channel_link:{CODE}` with 15 min TTL.

**Step 1: Write the failing tests**

Create `backend/tests/interfaces/api/test_channel_link_routes.py`:

```python
"""Tests for channel link API endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.channel import ChannelType


@pytest.fixture
def mock_redis():
    """Mock Redis client for link code storage."""
    redis = AsyncMock()
    redis.call = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def mock_repo():
    """Mock MongoUserChannelRepository."""
    repo = AsyncMock()
    repo.get_linked_channels = AsyncMock(return_value=[])
    repo.unlink_channel = AsyncMock()
    return repo


class TestGenerateLinkCode:
    """POST /api/v1/channel-links/generate"""

    @pytest.mark.asyncio
    async def test_generate_returns_code(self, mock_redis: AsyncMock) -> None:
        """Generates a 6-char alphanumeric code and stores in Redis."""
        from app.interfaces.api.channel_link_routes import _generate_link_code

        with patch("app.interfaces.api.channel_link_routes.get_redis", return_value=mock_redis):
            code = await _generate_link_code(user_id="webuser-abc", channel="telegram")

        # Code is 6 alphanumeric uppercase characters
        assert len(code) == 6
        assert code.isalnum()
        assert code == code.upper()

        # Redis setex was called with correct key and 900s TTL
        mock_redis.call.assert_awaited_once()
        call_args = mock_redis.call.call_args
        assert call_args[0][0] == "setex"
        assert call_args[0][1] == f"channel_link:{code}"
        assert call_args[0][2] == 900  # 15 minutes
        stored = json.loads(call_args[0][3])
        assert stored["user_id"] == "webuser-abc"
        assert stored["channel"] == "telegram"


class TestListLinkedChannels:
    """GET /api/v1/channel-links"""

    @pytest.mark.asyncio
    async def test_returns_linked_channels(self, mock_repo: AsyncMock) -> None:
        """Returns list of channels linked to the authenticated user."""
        from datetime import UTC, datetime

        mock_repo.get_linked_channels = AsyncMock(return_value=[
            {"channel": "telegram", "sender_id": "5829880422|UNIDM9", "linked_at": datetime(2026, 3, 2, tzinfo=UTC)},
        ])

        from app.interfaces.api.channel_link_routes import _get_linked_channels

        result = await _get_linked_channels(user_id="webuser-abc", repo=mock_repo)
        assert len(result) == 1
        assert result[0]["channel"] == "telegram"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/interfaces/api/test_channel_link_routes.py -v -p no:cov -o addopts=
```

Expected: FAIL (module not found)

**Step 3: Create the schemas**

Create `backend/app/interfaces/schemas/channel_link.py`:

```python
"""Request/response schemas for channel link endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GenerateLinkCodeRequest(BaseModel):
    """Request to generate a channel link code."""

    channel: str = "telegram"


class GenerateLinkCodeResponse(BaseModel):
    """Response with the generated link code."""

    code: str
    channel: str
    expires_in_seconds: int = 900
    instructions: str = ""


class LinkedChannelResponse(BaseModel):
    """A single linked channel entry."""

    channel: str
    sender_id: str
    linked_at: datetime | None = None


class LinkedChannelsListResponse(BaseModel):
    """List of all linked channels for a user."""

    channels: list[LinkedChannelResponse]
```

**Step 4: Create the route module**

Create `backend/app/interfaces/api/channel_link_routes.py`:

```python
"""API endpoints for channel account linking.

Allows authenticated web users to generate link codes and manage
their linked channel identities (Telegram, Discord, etc.).
"""

from __future__ import annotations

import json
import logging
import secrets
import string

from fastapi import APIRouter, Depends

from app.domain.models.user import User
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

_CODE_LENGTH = 6
_CODE_TTL_SECONDS = 900  # 15 minutes
_CODE_ALPHABET = string.ascii_uppercase + string.digits


async def _generate_link_code(user_id: str, channel: str) -> str:
    """Generate a random link code and store in Redis."""
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    redis = get_redis()
    payload = json.dumps({"user_id": user_id, "channel": channel})
    await redis.call("setex", f"channel_link:{code}", _CODE_TTL_SECONDS, payload)
    return code


async def _get_linked_channels(user_id: str, repo: object) -> list[dict]:
    """Fetch linked channels from the repository."""
    return await repo.get_linked_channels(user_id)  # type: ignore[union-attr]


@router.post("/generate", response_model=APIResponse[GenerateLinkCodeResponse])
async def generate_link_code(
    request: GenerateLinkCodeRequest = GenerateLinkCodeRequest(),
    current_user: User = Depends(get_current_user),
) -> APIResponse[GenerateLinkCodeResponse]:
    """Generate a 6-digit link code for connecting a channel account.

    The code is valid for 15 minutes and single-use.
    User sends ``/link CODE`` to the bot to complete linking.
    """
    code = await _generate_link_code(current_user.id, request.channel)
    bot_name = "Pythinkbot"  # TODO: make configurable if needed
    return APIResponse.success(
        GenerateLinkCodeResponse(
            code=code,
            channel=request.channel,
            expires_in_seconds=_CODE_TTL_SECONDS,
            instructions=f"Send /link {code} to @{bot_name} on Telegram within 15 minutes.",
        )
    )


@router.get("", response_model=APIResponse[LinkedChannelsListResponse])
async def list_linked_channels(
    current_user: User = Depends(get_current_user),
) -> APIResponse[LinkedChannelsListResponse]:
    """List all channels linked to the authenticated user."""
    from app.infrastructure.storage.mongodb import get_mongodb

    from app.infrastructure.repositories.user_channel_repository import (
        MongoUserChannelRepository,
    )

    db = get_mongodb().database
    repo = MongoUserChannelRepository(db)
    raw = await _get_linked_channels(current_user.id, repo)
    channels = [
        LinkedChannelResponse(
            channel=doc["channel"],
            sender_id=doc["sender_id"],
            linked_at=doc.get("linked_at"),
        )
        for doc in raw
    ]
    return APIResponse.success(LinkedChannelsListResponse(channels=channels))


@router.delete("/{channel}", response_model=APIResponse)
async def unlink_channel(
    channel: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse:
    """Unlink a channel from the authenticated user's account."""
    from app.infrastructure.storage.mongodb import get_mongodb

    from app.infrastructure.repositories.user_channel_repository import (
        MongoUserChannelRepository,
    )
    from app.domain.models.channel import ChannelType

    db = get_mongodb().database
    repo = MongoUserChannelRepository(db)
    await repo.unlink_channel(current_user.id, ChannelType(channel))
    return APIResponse.success(msg=f"{channel} channel unlinked successfully")
```

**Step 5: Register the router**

Modify `backend/app/interfaces/api/routes.py`:

Add import (after line 4):
```python
    channel_link_routes,
```

Add router inclusion (after line 44, before the prompt_optimization line):
```python
    api_router.include_router(channel_link_routes.router)
```

**Step 6: Run tests to verify they pass**

```bash
pytest tests/interfaces/api/test_channel_link_routes.py -v -p no:cov -o addopts=
```

Expected: ALL PASS

**Step 7: Commit**

```bash
git add backend/app/interfaces/api/channel_link_routes.py \
        backend/app/interfaces/schemas/channel_link.py \
        backend/app/interfaces/api/routes.py \
        backend/tests/interfaces/api/test_channel_link_routes.py
git commit -m "feat(api): add channel link API endpoints

POST /channel-links/generate — generate 6-digit link code (Redis, 15min TTL)
GET /channel-links — list linked channels for authenticated user
DELETE /channel-links/{channel} — unlink a channel"
```

---

## Task 4: Add Frontend UI for Account Linking

**Files:**
- Create: `frontend/src/api/channelLinks.ts`
- Modify: `frontend/src/components/settings/AccountSettings.vue`

**Context:** The `AccountSettings.vue` component (339 lines) has a profile card and quick stats. We add a "Linked Channels" section below the quick stats. The frontend API client pattern uses `apiClient` from `client.ts` with `ApiResponse<T>` unwrapping.

**Step 1: Create the API functions**

Create `frontend/src/api/channelLinks.ts`:

```typescript
import apiClient from './client'
import type { ApiResponse } from './client'

export interface GenerateLinkCodeResponse {
  code: string
  channel: string
  expires_in_seconds: number
  instructions: string
}

export interface LinkedChannel {
  channel: string
  sender_id: string
  linked_at: string | null
}

export interface LinkedChannelsListResponse {
  channels: LinkedChannel[]
}

export async function generateLinkCode(
  channel: string = 'telegram',
): Promise<GenerateLinkCodeResponse> {
  const response = await apiClient.post<ApiResponse<GenerateLinkCodeResponse>>(
    '/channel-links/generate',
    { channel },
  )
  return response.data.data!
}

export async function getLinkedChannels(): Promise<LinkedChannel[]> {
  const response = await apiClient.get<ApiResponse<LinkedChannelsListResponse>>(
    '/channel-links',
  )
  return response.data.data?.channels ?? []
}

export async function unlinkChannel(channel: string): Promise<void> {
  await apiClient.delete(`/channel-links/${channel}`)
}
```

**Step 2: Update AccountSettings.vue**

Replace the entire `frontend/src/components/settings/AccountSettings.vue` file. The key changes:
- Add "Linked Channels" section after quick stats
- Add state management for link code generation, countdown timer, and linked channels list
- Add "Link Telegram" button, code display with copy, and unlink functionality

**Template additions** (add after the `</div>` closing the `quick-stats` div, before the closing `</div>` of `account-settings`):

```html
    <!-- Linked Channels -->
    <div class="linked-channels-section">
      <h4 class="section-title">
        <Link2 class="w-4 h-4" />
        <span>Linked Channels</span>
      </h4>

      <!-- Linked Telegram -->
      <div v-if="telegramLinked" class="channel-item channel-linked">
        <div class="channel-icon telegram-icon">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
          </svg>
        </div>
        <div class="channel-info">
          <span class="channel-name">Telegram</span>
          <span class="channel-detail">{{ telegramSenderId }}</span>
        </div>
        <button class="unlink-btn" @click="handleUnlink('telegram')">
          Unlink
        </button>
      </div>

      <!-- Link Code Display -->
      <div v-else-if="linkCode" class="link-code-display">
        <div class="code-header">
          <span class="code-label">Your link code:</span>
          <span v-if="codeCountdown > 0" class="code-timer">{{ formatCountdown(codeCountdown) }}</span>
          <span v-else class="code-expired">Expired</span>
        </div>
        <div class="code-value" @click="copyCode">
          <span class="code-text">{{ linkCode }}</span>
          <Copy class="w-4 h-4 code-copy-icon" />
        </div>
        <p class="code-instructions">
          Send <code>/link {{ linkCode }}</code> to <strong>@Pythinkbot</strong> on Telegram
        </p>
        <button class="action-btn action-btn-secondary" @click="linkCode = null">
          Cancel
        </button>
      </div>

      <!-- Generate Link Button -->
      <div v-else class="channel-item channel-unlinked">
        <div class="channel-icon telegram-icon">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
          </svg>
        </div>
        <div class="channel-info">
          <span class="channel-name">Telegram</span>
          <span class="channel-detail">Not linked</span>
        </div>
        <button
          class="link-btn"
          :disabled="isGenerating"
          @click="handleGenerateCode"
        >
          {{ isGenerating ? 'Generating...' : 'Link' }}
        </button>
      </div>
    </div>
```

**Script additions** (add to `<script setup>`):

Add imports:
```typescript
import { Link2, Copy } from 'lucide-vue-next'
import { generateLinkCode, getLinkedChannels, unlinkChannel } from '../../api/channelLinks'
```

Add state and functions:
```typescript
// Channel linking state
const linkCode = ref<string | null>(null)
const codeCountdown = ref(0)
const isGenerating = ref(false)
const linkedChannels = ref<Array<{ channel: string; sender_id: string; linked_at: string | null }>>([])
let countdownInterval: ReturnType<typeof setInterval> | null = null

const telegramLinked = computed(() =>
  linkedChannels.value.some((c) => c.channel === 'telegram'),
)
const telegramSenderId = computed(() => {
  const tg = linkedChannels.value.find((c) => c.channel === 'telegram')
  if (!tg) return ''
  // sender_id format: "user_id|username" — show username part
  const parts = tg.sender_id.split('|')
  return parts.length > 1 ? `@${parts[1]}` : tg.sender_id
})

const formatCountdown = (seconds: number) => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

const handleGenerateCode = async () => {
  isGenerating.value = true
  try {
    const result = await generateLinkCode('telegram')
    linkCode.value = result.code
    codeCountdown.value = result.expires_in_seconds

    // Start countdown
    if (countdownInterval) clearInterval(countdownInterval)
    countdownInterval = setInterval(() => {
      codeCountdown.value--
      if (codeCountdown.value <= 0) {
        if (countdownInterval) clearInterval(countdownInterval)
        linkCode.value = null
      }
    }, 1000)
  } catch {
    // Generation failed
  } finally {
    isGenerating.value = false
  }
}

const copyCode = async () => {
  if (linkCode.value) {
    await navigator.clipboard.writeText(`/link ${linkCode.value}`)
  }
}

const handleUnlink = async (channel: string) => {
  try {
    await unlinkChannel(channel)
    linkedChannels.value = linkedChannels.value.filter((c) => c.channel !== channel)
  } catch {
    // Unlink failed
  }
}

const loadLinkedChannels = async () => {
  try {
    linkedChannels.value = await getLinkedChannels()
  } catch {
    // Failed to load — will show as unlinked
  }
}
```

Add to `onMounted`:
```typescript
onMounted(async () => {
  authProvider.value = await getCachedAuthProvider()
  await loadLinkedChannels()
})
```

**Style additions** (add to `<style scoped>`):

```css
/* Linked Channels */
.linked-channels-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.channel-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.channel-item:hover {
  border-color: var(--border-main);
}

.channel-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  flex-shrink: 0;
}

.telegram-icon {
  background: rgba(0, 136, 204, 0.1);
  color: #0088cc;
}

.channel-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.channel-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.channel-detail {
  font-size: 12px;
  color: var(--text-tertiary);
}

.link-btn,
.unlink-btn {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.link-btn {
  background: var(--fill-blue);
  color: #fff;
  border: none;
}

.link-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.link-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.unlink-btn {
  background: var(--function-error-tsp);
  color: var(--function-error);
  border: 1px solid transparent;
}

.unlink-btn:hover {
  background: rgba(239, 68, 68, 0.15);
}

/* Link Code Display */
.link-code-display {
  padding: 20px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  text-align: center;
}

.code-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 12px;
}

.code-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.code-timer {
  font-size: 12px;
  font-weight: 600;
  color: var(--function-success);
  background: rgba(34, 197, 94, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.code-expired {
  font-size: 12px;
  font-weight: 600;
  color: var(--function-error);
}

.code-value {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: var(--fill-tsp-white-dark);
  border: 2px dashed var(--border-main);
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 12px;
  transition: all 0.2s ease;
}

.code-value:hover {
  border-color: var(--text-brand);
}

.code-text {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: var(--text-primary);
  font-family: monospace;
}

.code-copy-icon {
  color: var(--icon-secondary);
}

.code-instructions {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.code-instructions code {
  font-weight: 600;
  color: var(--text-primary);
  background: var(--fill-tsp-white-dark);
  padding: 2px 6px;
  border-radius: 4px;
}

.action-btn-secondary {
  background: var(--fill-tsp-white-dark);
  color: var(--text-secondary);
  border: 1px solid var(--border-main);
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
}

.action-btn-secondary:hover {
  background: var(--fill-tsp-white-main);
  color: var(--text-primary);
}
```

**Step 3: Run frontend lint and type-check**

```bash
cd /home/mac/Desktop/Pythinker-main/frontend
bun run lint
bun run type-check
```

Expected: PASS (no errors)

**Step 4: Commit**

```bash
git add frontend/src/api/channelLinks.ts \
        frontend/src/components/settings/AccountSettings.vue
git commit -m "feat(ui): add Telegram account linking to AccountSettings

Adds 'Linked Channels' section with code generation, countdown timer,
copy-to-clipboard, and unlink functionality."
```

---

## Task 5: Run Full Test Suite and Lint

**Files:** None (verification only)

**Step 1: Run backend tests**

```bash
cd /home/mac/Desktop/Pythinker-main/backend
conda activate pythinker
pytest tests/ -v -p no:cov -o addopts= --timeout=30 -x -q 2>&1 | tail -20
```

Expected: ALL PASS

**Step 2: Run backend lint**

```bash
ruff check . && ruff format --check .
```

Expected: PASS

**Step 3: Run frontend checks**

```bash
cd /home/mac/Desktop/Pythinker-main/frontend
bun run lint && bun run type-check
```

Expected: PASS

**Step 4: Commit any lint fixes if needed**

```bash
git add -A
git commit -m "fix: lint and format fixes for channel linking"
```

---

## Task 6: Rebuild and Deploy Gateway

**Files:** None (deployment only)

**Step 1: Rebuild gateway image**

```bash
cd /home/mac/Desktop/Pythinker-main
docker compose --profile gateway build gateway
```

**Step 2: Restart gateway**

```bash
docker compose --profile gateway up -d gateway
```

**Step 3: Verify gateway logs**

```bash
docker compose --profile gateway logs gateway --tail 20
```

Expected: "Telegram bot @Pythinkbot connected" in logs

**Step 4: Manual test**

1. Open web UI → Account Settings → Click "Link Telegram"
2. Copy the 6-digit code
3. Send `/link CODE` to @Pythinkbot on Telegram
4. Verify confirmation message
5. Send a message to @Pythinkbot
6. Check web UI — session should appear in session list
