"""Tests for MongoUserChannelRepository.

Uses AsyncMock for MongoDB collections so no live database is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo import ReturnDocument

from app.domain.models.channel import ChannelType
from app.infrastructure.repositories.user_channel_repository import (
    MongoUserChannelRepository,
)


@pytest.fixture()
def mock_db() -> MagicMock:
    """Return a mock Motor database with two mock collections."""
    links_col = MagicMock()
    sessions_col = MagicMock()
    session_docs_col = MagicMock()
    db = MagicMock()
    db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "user_channel_links": links_col,
            "channel_sessions": sessions_col,
            "sessions": session_docs_col,
        }[name]
    )
    return db


@pytest.fixture()
def repo(mock_db: MagicMock) -> MongoUserChannelRepository:
    """Construct a repository backed by mock collections."""
    return MongoUserChannelRepository(mock_db)


# ------------------------------------------------------------------
# get_user_by_channel
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_by_channel_returns_none_for_unknown(
    repo: MongoUserChannelRepository,
) -> None:
    """get_user_by_channel returns None when no link document exists."""
    repo._links.find_one = AsyncMock(return_value=None)

    result = await repo.get_user_by_channel(ChannelType.TELEGRAM, "tg-user-123")

    assert result is None
    repo._links.find_one.assert_awaited_once()
    call_args = repo._links.find_one.call_args
    assert call_args[0][0]["channel"] == "telegram"
    assert call_args[0][0]["sender_id"] == "tg-user-123"


@pytest.mark.asyncio
async def test_get_user_by_channel_returns_user_id(
    repo: MongoUserChannelRepository,
) -> None:
    """get_user_by_channel returns the stored user_id when a link exists."""
    repo._links.find_one = AsyncMock(return_value={"user_id": "channel-abc123def456"})

    result = await repo.get_user_by_channel(ChannelType.DISCORD, "discord-42")

    assert result == "channel-abc123def456"


@pytest.mark.asyncio
async def test_get_user_by_channel_telegram_falls_back_to_stable_sender_prefix(
    repo: MongoUserChannelRepository,
) -> None:
    """Telegram lookup retries using numeric sender prefix when username variant misses."""
    repo._links.find_one = AsyncMock(side_effect=[None, {"user_id": "web-user-abc"}])

    result = await repo.get_user_by_channel(ChannelType.TELEGRAM, "5829880422|new_username")

    assert result == "web-user-abc"
    assert repo._links.find_one.await_count == 2

    first_filter = repo._links.find_one.await_args_list[0].args[0]
    assert first_filter == {"channel": "telegram", "sender_id": "5829880422|new_username"}

    second_filter = repo._links.find_one.await_args_list[1].args[0]
    assert second_filter["channel"] == "telegram"
    assert second_filter["$or"][0]["sender_id"] == "5829880422"
    assert second_filter["$or"][1]["sender_id"]["$regex"] == r"^5829880422\|"


# ------------------------------------------------------------------
# create_channel_user
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_channel_user_returns_user_id(
    repo: MongoUserChannelRepository,
) -> None:
    """create_channel_user generates a user_id and inserts a link document."""
    repo._links.insert_one = AsyncMock()

    user_id = await repo.create_channel_user(ChannelType.TELEGRAM, "tg-sender-1", "tg-chat-1")

    assert user_id.startswith("channel-")
    assert len(user_id) == len("channel-") + 12  # 12 hex chars
    repo._links.insert_one.assert_awaited_once()

    inserted_doc = repo._links.insert_one.call_args[0][0]
    assert inserted_doc["user_id"] == user_id
    assert inserted_doc["channel"] == "telegram"
    assert inserted_doc["sender_id"] == "tg-sender-1"
    assert inserted_doc["chat_id"] == "tg-chat-1"
    assert "created_at" in inserted_doc


@pytest.mark.asyncio
async def test_create_channel_user_generates_unique_ids(
    repo: MongoUserChannelRepository,
) -> None:
    """Two calls to create_channel_user produce different user IDs."""
    repo._links.insert_one = AsyncMock()

    id1 = await repo.create_channel_user(ChannelType.SLACK, "s1", "c1")
    id2 = await repo.create_channel_user(ChannelType.SLACK, "s2", "c2")

    assert id1 != id2


# ------------------------------------------------------------------
# get_session_key
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_key_returns_none_when_no_session(
    repo: MongoUserChannelRepository,
) -> None:
    """get_session_key returns None when no session document exists."""
    repo._sessions.find_one = AsyncMock(return_value=None)

    result = await repo.get_session_key("channel-abc", ChannelType.TELEGRAM, "chat-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_session_key_returns_none_when_cleared(
    repo: MongoUserChannelRepository,
) -> None:
    """get_session_key returns None when session_id has been cleared (set to None)."""
    repo._sessions.find_one = AsyncMock(return_value={"session_id": None})

    result = await repo.get_session_key("channel-abc", ChannelType.TELEGRAM, "chat-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_session_key_returns_session_id(
    repo: MongoUserChannelRepository,
) -> None:
    """get_session_key returns the stored session_id."""
    repo._sessions.find_one = AsyncMock(return_value={"session_id": "sess-xyz-789"})

    result = await repo.get_session_key("channel-abc", ChannelType.DISCORD, "chat-99")

    assert result == "sess-xyz-789"


# ------------------------------------------------------------------
# set_session_key + get_session_key round-trip
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_session_key_upserts(
    repo: MongoUserChannelRepository,
) -> None:
    """set_session_key performs an upsert with the correct filter and update."""
    repo._sessions.update_one = AsyncMock()

    await repo.set_session_key("channel-abc", ChannelType.TELEGRAM, "chat-1", "session-new")

    repo._sessions.update_one.assert_awaited_once()
    call_args = repo._sessions.update_one.call_args

    # Filter
    filt = call_args[0][0]
    assert filt["user_id"] == "channel-abc"
    assert filt["channel"] == "telegram"
    assert filt["chat_id"] == "chat-1"

    # Update
    update = call_args[0][1]
    assert update["$set"]["session_id"] == "session-new"
    assert "updated_at" in update["$set"]
    assert "$setOnInsert" in update

    # Upsert flag
    assert call_args[1]["upsert"] is True


# ------------------------------------------------------------------
# clear_session_key
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_session_key_sets_none(
    repo: MongoUserChannelRepository,
) -> None:
    """clear_session_key sets session_id to None in the document."""
    repo._sessions.update_one = AsyncMock()

    await repo.clear_session_key("channel-abc", ChannelType.TELEGRAM, "chat-1")

    repo._sessions.update_one.assert_awaited_once()
    call_args = repo._sessions.update_one.call_args

    filt = call_args[0][0]
    assert filt["user_id"] == "channel-abc"
    assert filt["channel"] == "telegram"
    assert filt["chat_id"] == "chat-1"

    update = call_args[0][1]
    assert update["$set"]["session_id"] is None


# ------------------------------------------------------------------
# ensure_indexes
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_indexes_creates_both(
    repo: MongoUserChannelRepository,
) -> None:
    """ensure_indexes creates indexes on both collections."""
    repo._links.create_index = AsyncMock()
    repo._sessions.create_index = AsyncMock()

    await repo.ensure_indexes()

    repo._links.create_index.assert_awaited_once()
    repo._sessions.create_index.assert_awaited_once()

    # Verify link index is unique on (channel, sender_id)
    link_call = repo._links.create_index.call_args
    assert link_call[0][0] == [("channel", 1), ("sender_id", 1)]
    assert link_call[1]["unique"] is True

    # Verify session index is unique on (user_id, channel, chat_id)
    session_call = repo._sessions.create_index.call_args
    assert session_call[0][0] == [("user_id", 1), ("channel", 1), ("chat_id", 1)]
    assert session_call[1]["unique"] is True


# ------------------------------------------------------------------
# link_channel_to_user
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_channel_to_user_upserts_with_correct_filter(
    repo: MongoUserChannelRepository,
) -> None:
    """link_channel_to_user calls find_one_and_update with the expected filter and update."""
    repo._links.find_one_and_update = AsyncMock(return_value=None)

    result = await repo.link_channel_to_user(ChannelType.TELEGRAM, "tg-999", "web-user-abc")

    repo._links.find_one_and_update.assert_awaited_once()
    call_args = repo._links.find_one_and_update.call_args

    # Positional filter
    filt = call_args[0][0]
    assert filt["channel"] == "telegram"
    assert filt["sender_id"] == "tg-999"

    # Update doc must contain $set with user_id and linked_at
    update = call_args[0][1]
    assert update["$set"]["user_id"] == "web-user-abc"
    assert "linked_at" in update["$set"]

    # $setOnInsert must contain channel and sender_id for upsert path
    assert "$setOnInsert" in update
    assert update["$setOnInsert"]["channel"] == "telegram"
    assert update["$setOnInsert"]["sender_id"] == "tg-999"
    assert "created_at" in update["$setOnInsert"]

    # Upsert flag and return_document=BEFORE (must return OLD doc, not new)
    assert call_args[1]["upsert"] is True
    assert call_args[1]["return_document"] == ReturnDocument.BEFORE

    # No previous document → returns None
    assert result is None


@pytest.mark.asyncio
async def test_link_channel_to_user_returns_old_user_id(
    repo: MongoUserChannelRepository,
) -> None:
    """link_channel_to_user returns the old user_id from the previous document."""
    old_doc = {"user_id": "channel-old-abc123"}
    repo._links.find_one_and_update = AsyncMock(return_value=old_doc)

    result = await repo.link_channel_to_user(ChannelType.TELEGRAM, "tg-999", "web-user-abc")

    assert result == "channel-old-abc123"


@pytest.mark.asyncio
async def test_link_channel_to_user_returns_none_when_no_previous_doc(
    repo: MongoUserChannelRepository,
) -> None:
    """link_channel_to_user returns None when there was no previous document (new insert)."""
    repo._links.find_one_and_update = AsyncMock(return_value=None)

    result = await repo.link_channel_to_user(ChannelType.DISCORD, "discord-42", "web-user-xyz")

    assert result is None


@pytest.mark.asyncio
async def test_link_channel_to_user_telegram_sender_with_username_uses_prefix_matching(
    repo: MongoUserChannelRepository,
) -> None:
    """Telegram link uses both full and prefix sender IDs to prevent username-rotation splits."""
    repo._links.find_one_and_update = AsyncMock(return_value={"user_id": "channel-old-telegram"})

    await repo.link_channel_to_user(
        ChannelType.TELEGRAM,
        "5829880422|new_username",
        "web-user-xyz",
    )

    call_args = repo._links.find_one_and_update.call_args
    filt = call_args[0][0]
    assert filt["channel"] == "telegram"
    assert filt["$or"][0]["sender_id"] == "5829880422|new_username"
    assert filt["$or"][1]["sender_id"] == "5829880422"
    assert filt["$or"][2]["sender_id"]["$regex"] == r"^5829880422\|"

    update = call_args[0][1]
    assert update["$setOnInsert"]["sender_id"] == "5829880422"


# ------------------------------------------------------------------
# get_linked_channels
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_linked_channels_returns_list(
    repo: MongoUserChannelRepository,
) -> None:
    """get_linked_channels returns all linked channels for a user."""
    expected = [
        {"channel": "telegram", "sender_id": "tg-123", "linked_at": "2026-01-01T00:00:00"},
        {"channel": "discord", "sender_id": "dc-456", "linked_at": "2026-01-02T00:00:00"},
    ]

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=expected)
    repo._links.find = MagicMock(return_value=mock_cursor)

    result = await repo.get_linked_channels("web-user-abc")

    assert result == expected

    # Verify the query filter
    call_args = repo._links.find.call_args
    filt = call_args[0][0]
    assert filt["user_id"] == "web-user-abc"
    assert "$exists" in filt["linked_at"]
    assert filt["linked_at"]["$exists"] is True

    # Verify to_list was called with a length limit
    mock_cursor.to_list.assert_awaited_once_with(length=50)


@pytest.mark.asyncio
async def test_get_linked_channels_returns_empty_list(
    repo: MongoUserChannelRepository,
) -> None:
    """get_linked_channels returns an empty list when the user has no linked channels."""
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    repo._links.find = MagicMock(return_value=mock_cursor)

    result = await repo.get_linked_channels("web-user-no-links")

    assert result == []


# ------------------------------------------------------------------
# unlink_channel
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_channel_calls_delete_one(
    repo: MongoUserChannelRepository,
) -> None:
    """unlink_channel calls delete_one with the correct filter."""
    mock_result = MagicMock()
    mock_result.deleted_count = 1
    sess_result = MagicMock()
    sess_result.deleted_count = 0
    repo._links.delete_one = AsyncMock(return_value=mock_result)
    repo._sessions.delete_many = AsyncMock(return_value=sess_result)

    await repo.unlink_channel("web-user-abc", ChannelType.TELEGRAM)

    repo._links.delete_one.assert_awaited_once()
    call_args = repo._links.delete_one.call_args
    filt = call_args[0][0]
    assert filt["user_id"] == "web-user-abc"
    assert filt["channel"] == "telegram"


@pytest.mark.asyncio
async def test_unlink_channel_uses_string_channel(
    repo: MongoUserChannelRepository,
) -> None:
    """unlink_channel converts ChannelType to string for the MongoDB filter."""
    mock_result = MagicMock()
    mock_result.deleted_count = 1
    sess_result = MagicMock()
    sess_result.deleted_count = 0
    repo._links.delete_one = AsyncMock(return_value=mock_result)
    repo._sessions.delete_many = AsyncMock(return_value=sess_result)

    await repo.unlink_channel("web-user-xyz", ChannelType.DISCORD)

    filt = repo._links.delete_one.call_args[0][0]
    assert filt["channel"] == "discord"


# ------------------------------------------------------------------
# migrate_sessions
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_sessions_calls_update_many(
    repo: MongoUserChannelRepository,
) -> None:
    """migrate_sessions calls update_many with the correct filter and $set."""
    repo._sessions.update_many = AsyncMock()

    await repo.migrate_sessions("channel-old-abc", "web-user-new", ChannelType.TELEGRAM)

    repo._sessions.update_many.assert_awaited_once()
    call_args = repo._sessions.update_many.call_args

    filt = call_args[0][0]
    assert filt["user_id"] == "channel-old-abc"
    assert filt["channel"] == "telegram"

    update = call_args[0][1]
    assert update["$set"]["user_id"] == "web-user-new"
    assert "updated_at" in update["$set"]


@pytest.mark.asyncio
async def test_migrate_sessions_uses_string_channel(
    repo: MongoUserChannelRepository,
) -> None:
    """migrate_sessions converts ChannelType to string for the MongoDB filter."""
    repo._sessions.update_many = AsyncMock()

    await repo.migrate_sessions("old-id", "new-id", ChannelType.SLACK)

    filt = repo._sessions.update_many.call_args[0][0]
    assert filt["channel"] == "slack"


# ------------------------------------------------------------------
# migrate_session_ownership
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_session_ownership_calls_update_many(
    repo: MongoUserChannelRepository,
) -> None:
    """migrate_session_ownership updates session owner IDs in sessions collection."""
    repo._session_docs.update_many = AsyncMock()

    await repo.migrate_session_ownership("channel-old-abc", "web-user-new")

    repo._session_docs.update_many.assert_awaited_once()
    call_args = repo._session_docs.update_many.call_args

    filt = call_args[0][0]
    assert filt["user_id"] == "channel-old-abc"

    update = call_args[0][1]
    assert update["$set"]["user_id"] == "web-user-new"
    assert "updated_at" in update["$set"]


# ------------------------------------------------------------------
# activity + context metadata
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_touch_last_inbound_at_upserts_activity_fields(
    repo: MongoUserChannelRepository,
) -> None:
    """touch_last_inbound_at updates inbound activity with upsert semantics."""
    repo._sessions.update_one = AsyncMock()

    await repo.touch_last_inbound_at("user-1", ChannelType.TELEGRAM, "chat-1")

    repo._sessions.update_one.assert_awaited_once()
    call_args = repo._sessions.update_one.call_args
    filt = call_args[0][0]
    assert filt == {"user_id": "user-1", "channel": "telegram", "chat_id": "chat-1"}

    update = call_args[0][1]
    assert "last_inbound_at" in update["$set"]
    assert "updated_at" in update["$set"]
    assert update["$setOnInsert"]["context_turn_count"] == 0
    assert call_args[1]["upsert"] is True


@pytest.mark.asyncio
async def test_touch_last_outbound_at_upserts_activity_fields(
    repo: MongoUserChannelRepository,
) -> None:
    """touch_last_outbound_at updates outbound activity with upsert semantics."""
    repo._sessions.update_one = AsyncMock()

    await repo.touch_last_outbound_at("user-2", ChannelType.DISCORD, "chat-2")

    repo._sessions.update_one.assert_awaited_once()
    call_args = repo._sessions.update_one.call_args
    filt = call_args[0][0]
    assert filt == {"user_id": "user-2", "channel": "discord", "chat_id": "chat-2"}

    update = call_args[0][1]
    assert "last_outbound_at" in update["$set"]
    assert "updated_at" in update["$set"]
    assert update["$setOnInsert"]["context_summary"] is None
    assert call_args[1]["upsert"] is True


@pytest.mark.asyncio
async def test_get_session_activity_returns_projection(
    repo: MongoUserChannelRepository,
) -> None:
    """get_session_activity requests only activity/context fields."""
    repo._sessions.find_one = AsyncMock(return_value={"last_inbound_at": "x"})

    result = await repo.get_session_activity("user-3", ChannelType.SLACK, "chat-3")

    assert result == {"last_inbound_at": "x"}
    repo._sessions.find_one.assert_awaited_once()
    filt, projection = repo._sessions.find_one.call_args[0]
    assert filt == {"user_id": "user-3", "channel": "slack", "chat_id": "chat-3"}
    assert projection["context_turn_count"] == 1
    assert projection["context_summary_updated_at"] == 1


@pytest.mark.asyncio
async def test_set_session_context_summary_persists_context_fields(
    repo: MongoUserChannelRepository,
) -> None:
    """set_session_context_summary stores turn count and summary metadata."""
    repo._sessions.update_one = AsyncMock()

    await repo.set_session_context_summary(
        user_id="user-4",
        channel=ChannelType.TELEGRAM,
        chat_id="chat-4",
        context_turn_count=51,
        context_summary="Conversation summary",
    )

    repo._sessions.update_one.assert_awaited_once()
    call_args = repo._sessions.update_one.call_args
    update = call_args[0][1]
    assert update["$set"]["context_turn_count"] == 51
    assert update["$set"]["context_summary"] == "Conversation summary"
    assert "context_summary_updated_at" in update["$set"]
    assert call_args[1]["upsert"] is True
