import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_skill_auto_trigger_policy_is_cached_between_calls():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(return_value={"skill_auto_trigger_enabled": True})
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]

    first = await service.get_skill_auto_trigger_enabled("user-1")
    second = await service.get_skill_auto_trigger_enabled("user-1")

    assert first is True
    assert second is True
    assert collection.find_one.await_count == 1


@pytest.mark.asyncio
async def test_skill_auto_trigger_policy_falls_back_to_environment_default():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(return_value=None)
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]

    with patch(
        "app.application.services.settings_service.get_settings",
        return_value=SimpleNamespace(skill_auto_trigger_enabled=True),
    ):
        value = await service.get_skill_auto_trigger_enabled("user-1")

    assert value is True


@pytest.mark.asyncio
async def test_skill_auto_trigger_policy_cache_expires():
    service = SettingsService()
    service.SKILL_POLICY_CACHE_TTL_SECONDS = 0.01
    collection = AsyncMock()
    collection.find_one = AsyncMock(
        side_effect=[
            {"skill_auto_trigger_enabled": False},
            {"skill_auto_trigger_enabled": True},
        ]
    )
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]

    first = await service.get_skill_auto_trigger_enabled("user-1")
    await asyncio.sleep(0.02)
    second = await service.get_skill_auto_trigger_enabled("user-1")

    assert first is False
    assert second is True
    assert collection.find_one.await_count == 2


@pytest.mark.asyncio
async def test_update_user_settings_refreshes_skill_policy_cache():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(
        side_effect=[
            {"user_id": "user-1", "skill_auto_trigger_enabled": False},
            {"user_id": "user-1", "skill_auto_trigger_enabled": True},
        ]
    )
    collection.update_one = AsyncMock()
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]

    await service.update_user_settings("user-1", {"skill_auto_trigger_enabled": True})

    collection.find_one.side_effect = AssertionError("Cache should satisfy this lookup")
    cached_value = await service.get_skill_auto_trigger_enabled("user-1")

    assert cached_value is True
    collection.update_one.assert_awaited_once()
