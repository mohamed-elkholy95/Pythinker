"""Regression tests for search_provider_chain in settings schemas."""

from app.core.search_provider_policy import DEFAULT_SEARCH_PROVIDER_CHAIN
from app.interfaces.schemas.settings import UpdateUserSettingsRequest, UserSettingsResponse


def test_user_settings_response_includes_search_provider_chain() -> None:
    response = UserSettingsResponse(
        llm_provider="openai",
        model_name="gpt-4",
        temperature=0.7,
        max_tokens=4000,
        search_provider="duckduckgo",
        search_provider_chain=["tavily", "duckduckgo", "serper"],
        browser_agent_max_steps=25,
        browser_agent_timeout=300,
        browser_agent_use_vision=True,
        response_verbosity_preference="adaptive",
        clarification_policy="auto",
        quality_floor_enforced=True,
        skill_auto_trigger_enabled=False,
    )

    assert response.search_provider_chain == ["tavily", "duckduckgo", "serper"]


def test_update_user_settings_request_accepts_search_provider_chain() -> None:
    request = UpdateUserSettingsRequest(
        search_provider_chain=["duckduckgo", "unknown", "serper"],
    )

    assert request.search_provider_chain == ["duckduckgo", "serper"]


def test_update_user_settings_request_accepts_jina_in_chain() -> None:
    request = UpdateUserSettingsRequest(
        search_provider_chain=["jina", "duckduckgo", "unknown"],
    )

    assert request.search_provider_chain == ["jina", "duckduckgo"]


def test_update_user_settings_request_unknown_only_chain_falls_back_to_default() -> None:
    request = UpdateUserSettingsRequest(
        search_provider_chain=["unknown", "invalid"],
    )

    assert request.search_provider_chain == list(DEFAULT_SEARCH_PROVIDER_CHAIN)
