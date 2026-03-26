"""Tests for app.core.search_provider_policy and underlying _normalize_provider_chain_value.

Covers: parse_search_provider_chain, normalize_search_provider_chain, constants,
and edge cases of the provider chain normalization logic.
"""

from __future__ import annotations

import json

from app.core.search_provider_policy import (
    ALLOWED_SEARCH_PROVIDERS,
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    normalize_search_provider_chain,
    parse_search_provider_chain,
)
from app.domain.models.user_settings import _normalize_provider_chain_value


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestConstants:
    def test_allowed_providers_is_frozenset(self):
        assert isinstance(ALLOWED_SEARCH_PROVIDERS, frozenset)

    def test_allowed_providers_includes_expected(self):
        for provider in ("bing", "google", "duckduckgo", "brave", "tavily", "serper", "exa", "jina"):
            assert provider in ALLOWED_SEARCH_PROVIDERS

    def test_default_chain_is_tuple(self):
        assert isinstance(DEFAULT_SEARCH_PROVIDER_CHAIN, tuple)

    def test_default_chain_length(self):
        assert len(DEFAULT_SEARCH_PROVIDER_CHAIN) == 4


# ---------------------------------------------------------------------------
# _normalize_provider_chain_value
# ---------------------------------------------------------------------------
class TestNormalizeProviderChainValue:
    """Test the core normalization function from user_settings."""

    def test_list_input(self):
        result = _normalize_provider_chain_value(["brave", "tavily"])
        assert result == ["brave", "tavily"]

    def test_list_lowercases(self):
        result = _normalize_provider_chain_value(["BRAVE", "Tavily"])
        assert result == ["brave", "tavily"]

    def test_list_deduplicates(self):
        result = _normalize_provider_chain_value(["brave", "brave", "tavily"])
        assert result == ["brave", "tavily"]

    def test_list_filters_invalid_providers(self):
        result = _normalize_provider_chain_value(["brave", "invalid_provider", "google"])
        assert result == ["brave", "google"]

    def test_list_all_invalid_returns_default(self):
        result = _normalize_provider_chain_value(["invalid1", "invalid2"])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_empty_list_returns_default(self):
        result = _normalize_provider_chain_value([])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_json_string_input(self):
        result = _normalize_provider_chain_value('["brave", "google"]')
        assert result == ["brave", "google"]

    def test_comma_separated_string(self):
        result = _normalize_provider_chain_value("brave,google,tavily")
        assert result == ["brave", "google", "tavily"]

    def test_comma_separated_with_spaces(self):
        result = _normalize_provider_chain_value("brave , google , tavily")
        assert result == ["brave", "google", "tavily"]

    def test_empty_string_returns_default(self):
        result = _normalize_provider_chain_value("")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_whitespace_string_returns_default(self):
        result = _normalize_provider_chain_value("   ")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_invalid_json_with_bracket_returns_default(self):
        result = _normalize_provider_chain_value("[invalid json")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_json_object_returns_default(self):
        result = _normalize_provider_chain_value('{"key": "value"}')
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_json_string_scalar_returns_default(self):
        result = _normalize_provider_chain_value('"just a string"')
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_none_returns_default(self):
        result = _normalize_provider_chain_value(None)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_integer_returns_default(self):
        result = _normalize_provider_chain_value(42)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_preserves_order(self):
        result = _normalize_provider_chain_value(["jina", "exa", "brave"])
        assert result == ["jina", "exa", "brave"]

    def test_strips_whitespace_in_items(self):
        result = _normalize_provider_chain_value(["  brave  ", "  google  "])
        assert result == ["brave", "google"]

    def test_json_array_with_invalid_entries(self):
        result = _normalize_provider_chain_value(json.dumps(["brave", "nonexistent", "exa"]))
        assert result == ["brave", "exa"]


# ---------------------------------------------------------------------------
# parse_search_provider_chain
# ---------------------------------------------------------------------------
class TestParseSearchProviderChain:
    """Test the parse function (re-export wrapper)."""

    def test_valid_list(self):
        result = parse_search_provider_chain(["brave", "tavily"])
        assert result == ["brave", "tavily"]

    def test_valid_string(self):
        result = parse_search_provider_chain("brave,google")
        assert result == ["brave", "google"]

    def test_none_returns_empty(self):
        result = parse_search_provider_chain(None)
        assert result == []

    def test_empty_string_returns_empty(self):
        result = parse_search_provider_chain("")
        assert result == []

    def test_integer_returns_empty(self):
        result = parse_search_provider_chain(42)
        assert result == []


# ---------------------------------------------------------------------------
# normalize_search_provider_chain
# ---------------------------------------------------------------------------
class TestNormalizeSearchProviderChain:
    """Test the normalize function (always returns valid chain or default)."""

    def test_valid_input(self):
        result = normalize_search_provider_chain(["brave"])
        assert result == ["brave"]

    def test_none_returns_default(self):
        result = normalize_search_provider_chain(None)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_empty_returns_default(self):
        result = normalize_search_provider_chain([])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_invalid_returns_default(self):
        result = normalize_search_provider_chain(["fake_provider"])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)
