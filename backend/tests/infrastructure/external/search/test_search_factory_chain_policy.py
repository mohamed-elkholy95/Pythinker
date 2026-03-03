"""Tests for search factory chain-policy resolution."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.infrastructure.external.search import factory as search_factory
from app.infrastructure.external.search.factory import (
    DEFAULT_PROVIDER_CHAIN,
    FallbackSearchEngine,
    get_search_engine_from_factory,
)


class _DummyEngine:
    async def search(
        self, query: str, date_range: str | None = None
    ):  # pragma: no cover - not exercised in this unit test
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _reset_missing_config_warning_cache() -> None:
    search_factory._missing_config_warned.clear()
    yield
    search_factory._missing_config_warned.clear()


def _build_engine_and_attempts(
    *,
    search_provider: str | None,
    search_provider_chain: str | list[str] | None,
    available: dict[str, object],
) -> tuple[object | None, list[str]]:
    attempts: list[str] = []

    def fake_create_provider_engine(provider: str, redis_client=None):
        attempts.append(provider)
        return available.get(provider)

    settings = SimpleNamespace(
        search_provider=search_provider,
        search_provider_chain=search_provider_chain,
    )

    with (
        patch("app.infrastructure.external.search.factory.get_settings", return_value=settings),
        patch(
            "app.infrastructure.external.search.factory._create_provider_engine",
            side_effect=fake_create_provider_engine,
        ),
    ):
        engine = get_search_engine_from_factory()

    return engine, attempts


def test_default_chain_prioritizes_api_providers_serper_brave_tavily_exa() -> None:
    """Fix 1: Default chain now uses API-only providers (no scrapers that share IP)."""
    available = {
        "serper": _DummyEngine(),
        "brave": _DummyEngine(),
        "tavily": _DummyEngine(),
        "exa": _DummyEngine(),
    }

    engine, attempts = _build_engine_and_attempts(
        search_provider=None,
        search_provider_chain=None,
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == ["serper", "brave", "tavily", "exa"]
    assert attempts[:4] == ["serper", "brave", "tavily", "exa"]


@pytest.mark.parametrize(
    "configured_chain",
    [
        '["duckduckgo", "serper"]',
        "duckduckgo, serper",
    ],
)
def test_explicit_chain_string_parsing_appends_configured_provider_once(configured_chain: str) -> None:
    available = {
        "duckduckgo": _DummyEngine(),
        "serper": _DummyEngine(),
        "tavily": _DummyEngine(),
    }

    engine, attempts = _build_engine_and_attempts(
        search_provider="tavily",
        search_provider_chain=configured_chain,
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == ["duckduckgo", "serper", "tavily"]
    assert attempts[:3] == ["duckduckgo", "serper", "tavily"]
    assert attempts.count("tavily") == 1


def test_unknown_provider_is_ignored_and_unconfigured_engines_are_skipped() -> None:
    available = {
        "tavily": _DummyEngine(),
    }

    engine, attempts = _build_engine_and_attempts(
        search_provider="unknown-provider",
        search_provider_chain="tavily, duckduckgo, tavily",
        available=available,
    )

    assert engine is available["tavily"]
    assert attempts == ["tavily", "duckduckgo"]


def test_blank_search_provider_still_uses_default_chain() -> None:
    available = {provider: _DummyEngine() for provider in DEFAULT_PROVIDER_CHAIN}

    engine, attempts = _build_engine_and_attempts(
        search_provider="",
        search_provider_chain=None,
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == DEFAULT_PROVIDER_CHAIN
    assert attempts[: len(DEFAULT_PROVIDER_CHAIN)] == DEFAULT_PROVIDER_CHAIN


@pytest.mark.parametrize(
    "configured_chain",
    [
        '{"primary": "duckduckgo"}',
        '"duckduckgo"',
        "42",
        "true",
        "null",
        "[duckduckgo, serper]",
    ],
)
def test_json_like_non_list_chain_falls_back_to_defaults(configured_chain: str) -> None:
    available = {provider: _DummyEngine() for provider in DEFAULT_PROVIDER_CHAIN}

    engine, attempts = _build_engine_and_attempts(
        search_provider="tavily",
        search_provider_chain=configured_chain,
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == DEFAULT_PROVIDER_CHAIN
    assert attempts[: len(DEFAULT_PROVIDER_CHAIN)] == DEFAULT_PROVIDER_CHAIN


def test_unknown_chain_entries_fall_back_to_defaults() -> None:
    available = {provider: _DummyEngine() for provider in DEFAULT_PROVIDER_CHAIN}

    engine, attempts = _build_engine_and_attempts(
        search_provider=None,
        search_provider_chain="unknown, still-unknown",
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == DEFAULT_PROVIDER_CHAIN
    assert attempts[: len(DEFAULT_PROVIDER_CHAIN)] == DEFAULT_PROVIDER_CHAIN


def test_explicit_chain_supports_jina_provider() -> None:
    available = {
        "jina": _DummyEngine(),
        "duckduckgo": _DummyEngine(),
    }

    engine, attempts = _build_engine_and_attempts(
        search_provider="jina",
        search_provider_chain="jina,duckduckgo",
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == ["jina", "duckduckgo"]
    assert attempts[:2] == ["jina", "duckduckgo"]


def test_missing_provider_configuration_warning_emitted_once_per_provider_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SimpleNamespace(
        brave_search_api_key=None,
        brave_search_api_key_2=None,
        brave_search_api_key_3=None,
    )

    with (
        patch("app.infrastructure.external.search.factory.get_settings", return_value=settings),
        caplog.at_level("WARNING", logger="app.infrastructure.external.search.factory"),
    ):
        assert search_factory._provider_kwargs("brave") is None
        assert search_factory._provider_kwargs("brave") is None
        assert search_factory._provider_kwargs("brave") is None

    warnings = [
        record.getMessage() for record in caplog.records if "Brave Search not configured" in record.getMessage()
    ]
    assert len(warnings) == 1


def test_provider_kwargs_apply_search_profile_settings() -> None:
    settings = SimpleNamespace(
        search_max_results=13,
        tavily_search_depth="advanced",
        exa_search_type="neural",
        serper_quota_cooldown_seconds=900,
        brave_search_api_key="brave-key",
        brave_search_api_key_2=None,
        brave_search_api_key_3=None,
        tavily_api_key="tavily-key",
        tavily_api_key_2=None,
        tavily_api_key_3=None,
        tavily_api_key_4=None,
        tavily_api_key_5=None,
        tavily_api_key_6=None,
        tavily_api_key_7=None,
        tavily_api_key_8=None,
        tavily_api_key_9=None,
        serper_api_key="serper-key",
        serper_api_key_2=None,
        serper_api_key_3=None,
        serper_api_key_4=None,
        serper_api_key_5=None,
        serper_api_key_6=None,
        serper_api_key_7=None,
        serper_api_key_8=None,
        serper_api_key_9=None,
        exa_api_key="exa-key",
        exa_api_key_2=None,
        exa_api_key_3=None,
        exa_api_key_4=None,
        exa_api_key_5=None,
    )

    with patch("app.infrastructure.external.search.factory.get_settings", return_value=settings):
        brave_kwargs = search_factory._provider_kwargs("brave")
        tavily_kwargs = search_factory._provider_kwargs("tavily")
        serper_kwargs = search_factory._provider_kwargs("serper")
        exa_kwargs = search_factory._provider_kwargs("exa")

    assert brave_kwargs is not None
    assert tavily_kwargs is not None
    assert serper_kwargs is not None
    assert exa_kwargs is not None

    assert brave_kwargs["max_results"] == 13
    assert tavily_kwargs["max_results"] == 13
    assert tavily_kwargs["search_depth"] == "advanced"
    assert serper_kwargs["max_results"] == 13
    assert serper_kwargs["quota_cooldown_seconds"] == 900
    assert exa_kwargs["max_results"] == 13
    assert exa_kwargs["search_type"] == "neural"


def test_provider_kwargs_fallback_to_safe_defaults_for_invalid_profile_values() -> None:
    settings = SimpleNamespace(
        search_max_results=0,
        tavily_search_depth="invalid-depth",
        exa_search_type="invalid-type",
        serper_quota_cooldown_seconds=1800,
        brave_search_api_key="brave-key",
        brave_search_api_key_2=None,
        brave_search_api_key_3=None,
        tavily_api_key="tavily-key",
        tavily_api_key_2=None,
        tavily_api_key_3=None,
        tavily_api_key_4=None,
        tavily_api_key_5=None,
        tavily_api_key_6=None,
        tavily_api_key_7=None,
        tavily_api_key_8=None,
        tavily_api_key_9=None,
        exa_api_key="exa-key",
        exa_api_key_2=None,
        exa_api_key_3=None,
        exa_api_key_4=None,
        exa_api_key_5=None,
    )

    with patch("app.infrastructure.external.search.factory.get_settings", return_value=settings):
        brave_kwargs = search_factory._provider_kwargs("brave")
        tavily_kwargs = search_factory._provider_kwargs("tavily")
        exa_kwargs = search_factory._provider_kwargs("exa")

    assert brave_kwargs is not None
    assert tavily_kwargs is not None
    assert exa_kwargs is not None

    assert brave_kwargs["max_results"] == 8
    assert tavily_kwargs["max_results"] == 8
    assert tavily_kwargs["search_depth"] == "basic"
    assert exa_kwargs["max_results"] == 8
    assert exa_kwargs["search_type"] == "auto"
