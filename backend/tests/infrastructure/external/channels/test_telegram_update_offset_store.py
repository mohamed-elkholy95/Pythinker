"""Tests for Telegram update offset persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from nanobot.channels.telegram_update_offset_store import (
    delete_telegram_update_offset,
    read_telegram_update_offset,
    write_telegram_update_offset,
)


@pytest.mark.asyncio
async def test_missing_offset_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nanobot.channels.telegram_update_offset_store.get_data_path", lambda: tmp_path)

    assert await read_telegram_update_offset(bot_token="123:fake") is None


@pytest.mark.asyncio
async def test_write_then_read_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nanobot.channels.telegram_update_offset_store.get_data_path", lambda: tmp_path)

    await write_telegram_update_offset(update_id=77, bot_token="123:fake")

    assert await read_telegram_update_offset(bot_token="123:fake") == 77


@pytest.mark.asyncio
async def test_read_returns_none_when_bot_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nanobot.channels.telegram_update_offset_store.get_data_path", lambda: tmp_path)

    await write_telegram_update_offset(update_id=77, bot_token="123:fake")

    assert await read_telegram_update_offset(bot_token="999:other") is None


@pytest.mark.asyncio
async def test_delete_removes_offset_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nanobot.channels.telegram_update_offset_store.get_data_path", lambda: tmp_path)

    await write_telegram_update_offset(update_id=77, bot_token="123:fake")
    await delete_telegram_update_offset()

    assert await read_telegram_update_offset(bot_token="123:fake") is None
