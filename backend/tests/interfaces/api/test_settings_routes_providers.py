"""Tests for settings providers catalog exposure."""

from app.interfaces.api.settings_routes import SEARCH_PROVIDERS


def test_search_providers_include_jina() -> None:
    provider_ids = {provider["id"] for provider in SEARCH_PROVIDERS}
    assert "jina" in provider_ids
