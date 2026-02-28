"""Tests for search factory chain-policy resolution."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.infrastructure.external.search.factory import (
    DEFAULT_PROVIDER_CHAIN,
    FallbackSearchEngine,
    get_search_engine_from_factory,
)


class _DummyEngine:
    async def search(self, query: str, date_range: str | None = None):  # pragma: no cover - not exercised in this unit test
        raise NotImplementedError


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


def test_default_chain_prioritizes_tavily_then_duckduckgo_then_serper() -> None:
    available = {
        "tavily": _DummyEngine(),
        "duckduckgo": _DummyEngine(),
        "serper": _DummyEngine(),
    }

    engine, attempts = _build_engine_and_attempts(
        search_provider="duckduckgo",
        search_provider_chain=None,
        available=available,
    )

    assert isinstance(engine, FallbackSearchEngine)
    assert [name for name, _ in engine._providers] == ["tavily", "duckduckgo", "serper"]
    assert attempts[:3] == ["tavily", "duckduckgo", "serper"]


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
