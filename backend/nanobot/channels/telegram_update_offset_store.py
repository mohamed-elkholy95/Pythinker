"""Persist Telegram polling offsets between restarts."""

from __future__ import annotations

import json
from pathlib import Path

from nanobot.utils.helpers import get_data_path

_STORE_VERSION = 2


def _extract_bot_id(bot_token: str | None) -> str | None:
    token = str(bot_token or "").strip()
    if not token:
        return None
    raw_bot_id = token.split(":", 1)[0]
    return raw_bot_id if raw_bot_id.isdigit() else None


def _offset_store_path(account_id: str = "default") -> Path:
    normalized = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in account_id.strip() or "default")
    return get_data_path() / "telegram" / f"update-offset-{normalized}.json"


def _load_state(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("version") not in {1, _STORE_VERSION}:
        return None
    last_update_id = payload.get("last_update_id")
    if last_update_id is not None and not isinstance(last_update_id, int):
        return None
    bot_id = payload.get("bot_id")
    if bot_id is not None and not isinstance(bot_id, str):
        return None
    return {
        "version": _STORE_VERSION,
        "last_update_id": last_update_id,
        "bot_id": bot_id if payload.get("version") == _STORE_VERSION else None,
    }


async def read_telegram_update_offset(*, account_id: str = "default", bot_token: str | None = None) -> int | None:
    """Load the last safely processed Telegram update id for this bot/account."""
    path = _offset_store_path(account_id)
    state = await __import__("asyncio").to_thread(_load_state, path)
    if state is None:
        return None
    expected_bot_id = _extract_bot_id(bot_token)
    stored_bot_id = state.get("bot_id")
    if expected_bot_id and stored_bot_id and stored_bot_id != expected_bot_id:
        return None
    if expected_bot_id and stored_bot_id is None:
        return None
    last_update_id = state.get("last_update_id")
    return last_update_id if isinstance(last_update_id, int) else None


def _write_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    temp_path.replace(path)


async def write_telegram_update_offset(
    *,
    update_id: int,
    account_id: str = "default",
    bot_token: str | None = None,
) -> None:
    """Persist the last safely processed Telegram update id."""
    payload = {
        "version": _STORE_VERSION,
        "last_update_id": int(update_id),
        "bot_id": _extract_bot_id(bot_token),
    }
    await __import__("asyncio").to_thread(_write_state, _offset_store_path(account_id), payload)


async def delete_telegram_update_offset(*, account_id: str = "default") -> None:
    """Delete the persisted Telegram update offset if it exists."""
    path = _offset_store_path(account_id)

    def _delete(target: Path) -> None:
        try:
            target.unlink()
        except FileNotFoundError:
            return

    await __import__("asyncio").to_thread(_delete, path)
