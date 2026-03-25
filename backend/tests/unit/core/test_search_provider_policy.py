"""Tests for search provider policy normalization."""

import pytest

from app.core.search_provider_policy import (
    ALLOWED_SEARCH_PROVIDERS,
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    normalize_search_provider_chain,
    parse_search_provider_chain,
)


@pytest.mark.unit
class TestSearchProviderConstants:
    """Tests for search provider constants."""

    def test_allowed_providers_contains_known(self) -> None:
        for provider in ("bing", "google", "duckduckgo", "brave", "tavily", "serper", "exa", "jina"):
            assert provider in ALLOWED_SEARCH_PROVIDERS

    def test_allowed_providers_is_frozenset(self) -> None:
        assert isinstance(ALLOWED_SEARCH_PROVIDERS, frozenset)

    def test_default_chain_is_tuple(self) -> None:
        assert isinstance(DEFAULT_SEARCH_PROVIDER_CHAIN, tuple)

    def test_default_chain_all_allowed(self) -> None:
        for provider in DEFAULT_SEARCH_PROVIDER_CHAIN:
            assert provider in ALLOWED_SEARCH_PROVIDERS


@pytest.mark.unit
class TestParseSearchProviderChain:
    """Tests for parse_search_provider_chain function."""

    def test_valid_list(self) -> None:
        result = parse_search_provider_chain(["brave", "google"])
        assert result == ["brave", "google"]

    def test_valid_string(self) -> None:
        result = parse_search_provider_chain("brave,google")
        assert "brave" in result
        assert "google" in result

    def test_filters_unknown_providers(self) -> None:
        result = parse_search_provider_chain(["brave", "unknown_provider"])
        assert "brave" in result
        assert "unknown_provider" not in result

    def test_deduplicates(self) -> None:
        result = parse_search_provider_chain(["brave", "brave", "google"])
        assert result.count("brave") == 1

    def test_empty_input_returns_empty(self) -> None:
        result = parse_search_provider_chain(None)
        assert result == []

    def test_none_returns_empty(self) -> None:
        result = parse_search_provider_chain(None)
        assert result == []

    def test_lowercases_input(self) -> None:
        result = parse_search_provider_chain(["BRAVE", "Google"])
        assert "brave" in result


@pytest.mark.unit
class TestNormalizeSearchProviderChain:
    """Tests for normalize_search_provider_chain function."""

    def test_valid_list(self) -> None:
        result = normalize_search_provider_chain(["brave", "google"])
        assert result == ["brave", "google"]

    def test_falls_back_to_default_on_empty(self) -> None:
        result = normalize_search_provider_chain([])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_falls_back_to_default_on_none(self) -> None:
        result = normalize_search_provider_chain(None)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_falls_back_to_default_on_invalid(self) -> None:
        result = normalize_search_provider_chain(42)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_filters_and_falls_back_if_all_invalid(self) -> None:
        result = normalize_search_provider_chain(["fake1", "fake2"])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)
