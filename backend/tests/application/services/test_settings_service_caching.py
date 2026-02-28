import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.settings_service import SettingsService
from app.core.search_provider_policy import DEFAULT_SEARCH_PROVIDER_CHAIN


def test_get_default_settings_surfaces_normalized_search_provider_chain():
    config = SimpleNamespace(
        llm_provider="openai",
        model_name="gpt-4",
        temperature=0.7,
        max_tokens=4000,
        search_provider="duckduckgo",
        search_provider_chain='["duckduckgo", "serper"]',
        browser_agent_max_steps=25,
        browser_agent_timeout=300,
        browser_agent_use_vision=True,
        skill_auto_trigger_enabled=False,
    )

    with patch("app.application.services.settings_service.get_settings", return_value=config):
        result = SettingsService.get_default_settings()

    assert result["search_provider_chain"] == ["duckduckgo", "serper"]


@pytest.mark.parametrize(
    "raw_chain",
    [
        '{"primary": "duckduckgo"}',
        '"duckduckgo"',
        "42",
        "true",
        "null",
        "[duckduckgo, serper]",
    ],
)
def test_normalize_search_provider_chain_rejects_json_like_non_list(raw_chain: str):
    assert SettingsService._normalize_search_provider_chain(raw_chain) == list(DEFAULT_SEARCH_PROVIDER_CHAIN)


def test_normalize_search_provider_chain_filters_unknown_providers():
    assert SettingsService._normalize_search_provider_chain("tavily,unknown,serper") == ["tavily", "serper"]
    assert SettingsService._normalize_search_provider_chain("unknown,another") == list(DEFAULT_SEARCH_PROVIDER_CHAIN)


@pytest.mark.asyncio
async def test_get_user_settings_surfaces_normalized_search_provider_chain():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(
        return_value={
            "user_id": "user-1",
            "search_provider_chain": "serper, tavily, serper",
            "skill_auto_trigger_enabled": True,
        }
    )
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]

    with patch(
        "app.application.services.settings_service.get_settings",
        return_value=SimpleNamespace(
            search_provider_chain="tavily,duckduckgo,serper",
            skill_auto_trigger_enabled=False,
        ),
    ):
        result = await service.get_user_settings("user-1")

    assert result["search_provider_chain"] == ["serper", "tavily"]


@pytest.mark.asyncio
async def test_get_user_settings_falls_back_to_env_chain_when_document_missing_value():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(
        return_value={
            "user_id": "user-1",
            "skill_auto_trigger_enabled": False,
        }
    )
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]

    with patch(
        "app.application.services.settings_service.get_settings",
        return_value=SimpleNamespace(
            search_provider_chain='["duckduckgo", "serper"]',
            skill_auto_trigger_enabled=False,
        ),
    ):
        result = await service.get_user_settings("user-1")

    assert result["search_provider_chain"] == ["duckduckgo", "serper"]


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


@pytest.mark.asyncio
async def test_update_user_settings_normalizes_search_provider_chain_before_persist():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(
        return_value={
            "user_id": "user-1",
            "skill_auto_trigger_enabled": False,
        }
    )
    collection.update_one = AsyncMock()
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]
    service.get_user_settings = AsyncMock(return_value={"skill_auto_trigger_enabled": False})  # type: ignore[method-assign]

    await service.update_user_settings(
        "user-1",
        {
            "search_provider_chain": "Serper, tavily, serper, unknown",
        },
    )

    persisted_doc = collection.update_one.await_args.args[1]["$set"]
    assert persisted_doc["search_provider_chain"] == ["serper", "tavily"]


@pytest.mark.asyncio
async def test_update_user_settings_falls_back_to_default_chain_when_all_providers_unknown():
    service = SettingsService()
    collection = AsyncMock()
    collection.find_one = AsyncMock(
        return_value={
            "user_id": "user-1",
            "skill_auto_trigger_enabled": False,
        }
    )
    collection.update_one = AsyncMock()
    service._get_settings_collection = lambda: collection  # type: ignore[method-assign]
    service.get_user_settings = AsyncMock(return_value={"skill_auto_trigger_enabled": False})  # type: ignore[method-assign]

    await service.update_user_settings(
        "user-1",
        {
            "search_provider_chain": "unknown,another",
        },
    )

    persisted_doc = collection.update_one.await_args.args[1]["$set"]
    assert persisted_doc["search_provider_chain"] == list(DEFAULT_SEARCH_PROVIDER_CHAIN)
