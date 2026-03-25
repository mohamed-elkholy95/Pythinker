"""Tests for the search provider policy module.

Covers ALLOWED_SEARCH_PROVIDERS, DEFAULT_SEARCH_PROVIDER_CHAIN,
normalize_search_provider_chain, and parse_search_provider_chain.
"""

from __future__ import annotations

import json

from app.core.search_provider_policy import (
    ALLOWED_SEARCH_PROVIDERS,
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    normalize_search_provider_chain,
    parse_search_provider_chain,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify public constants are exported and have expected values."""

    def test_allowed_providers_is_frozenset(self) -> None:
        assert isinstance(ALLOWED_SEARCH_PROVIDERS, frozenset)

    def test_allowed_providers_contains_canonical_engines(self) -> None:
        expected = {"bing", "google", "duckduckgo", "brave", "tavily", "serper", "exa", "jina"}
        assert expected == ALLOWED_SEARCH_PROVIDERS

    def test_default_chain_is_tuple(self) -> None:
        assert isinstance(DEFAULT_SEARCH_PROVIDER_CHAIN, tuple)

    def test_default_chain_not_empty(self) -> None:
        assert len(DEFAULT_SEARCH_PROVIDER_CHAIN) > 0

    def test_default_chain_values_are_allowed(self) -> None:
        for provider in DEFAULT_SEARCH_PROVIDER_CHAIN:
            assert provider in ALLOWED_SEARCH_PROVIDERS

    def test_default_chain_no_duplicates(self) -> None:
        assert len(DEFAULT_SEARCH_PROVIDER_CHAIN) == len(set(DEFAULT_SEARCH_PROVIDER_CHAIN))

    def test_default_chain_canonical_providers(self) -> None:
        # Canonical defaults established in domain model
        chain = set(DEFAULT_SEARCH_PROVIDER_CHAIN)
        assert "tavily" in chain
        assert "brave" in chain


# ---------------------------------------------------------------------------
# normalize_search_provider_chain — always returns a non-empty list
# ---------------------------------------------------------------------------


class TestNormalizeSearchProviderChain:
    """normalize_search_provider_chain must never return an empty list."""

    # --- list inputs ---

    def test_valid_list_passthrough(self) -> None:
        result = normalize_search_provider_chain(["tavily", "brave"])
        assert result == ["tavily", "brave"]

    def test_list_deduplicates_providers(self) -> None:
        result = normalize_search_provider_chain(["tavily", "tavily", "brave"])
        assert result == ["tavily", "brave"]

    def test_list_filters_unknown_providers(self) -> None:
        result = normalize_search_provider_chain(["tavily", "unknown_engine"])
        assert result == ["tavily"]

    def test_list_lowercases_providers(self) -> None:
        result = normalize_search_provider_chain(["TAVILY", "Brave"])
        assert result == ["tavily", "brave"]

    def test_list_strips_whitespace(self) -> None:
        result = normalize_search_provider_chain(["  tavily  ", " brave "])
        assert result == ["tavily", "brave"]

    def test_all_allowed_providers_accepted_in_list(self) -> None:
        providers = list(ALLOWED_SEARCH_PROVIDERS)
        result = normalize_search_provider_chain(providers)
        assert set(result) == ALLOWED_SEARCH_PROVIDERS

    def test_empty_list_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain([])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_list_of_only_unknown_providers_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain(["nonexistent", "fake_engine"])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_list_preserves_insertion_order(self) -> None:
        result = normalize_search_provider_chain(["exa", "serper", "tavily"])
        assert result == ["exa", "serper", "tavily"]

    # --- string inputs ---

    def test_comma_separated_string(self) -> None:
        result = normalize_search_provider_chain("tavily,brave")
        assert result == ["tavily", "brave"]

    def test_comma_separated_string_with_spaces(self) -> None:
        result = normalize_search_provider_chain("tavily, brave, exa")
        assert result == ["tavily", "brave", "exa"]

    def test_comma_separated_uppercase(self) -> None:
        result = normalize_search_provider_chain("TAVILY,BRAVE")
        assert result == ["tavily", "brave"]

    def test_single_provider_string(self) -> None:
        result = normalize_search_provider_chain("serper")
        assert result == ["serper"]

    def test_json_array_string(self) -> None:
        raw = json.dumps(["tavily", "brave"])
        result = normalize_search_provider_chain(raw)
        assert result == ["tavily", "brave"]

    def test_json_array_string_with_uppercase(self) -> None:
        raw = json.dumps(["TAVILY", "Brave"])
        result = normalize_search_provider_chain(raw)
        assert result == ["tavily", "brave"]

    def test_empty_string_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain("")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_whitespace_only_string_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain("   ")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_invalid_json_array_prefix_falls_back_to_defaults(self) -> None:
        # Starts with '[' but is malformed JSON — treated as invalid
        result = normalize_search_provider_chain("[tavily,brave")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_json_non_array_falls_back_to_defaults(self) -> None:
        # Valid JSON but not an array
        result = normalize_search_provider_chain(json.dumps({"provider": "tavily"}))
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_comma_separated_all_unknown_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain("fake,bogus")
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    # --- None / falsy scalar inputs ---

    def test_none_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain(None)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_zero_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain(0)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_false_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain(False)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_dict_input_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain({"provider": "tavily"})
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_integer_input_falls_back_to_defaults(self) -> None:
        result = normalize_search_provider_chain(42)
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_result_is_always_list(self) -> None:
        for raw in [None, "", [], "unknown", 0, False]:
            result = normalize_search_provider_chain(raw)
            assert isinstance(result, list), f"Expected list for raw={raw!r}, got {type(result)}"

    def test_result_is_always_non_empty(self) -> None:
        for raw in [None, "", [], "unknown", 0, False]:
            result = normalize_search_provider_chain(raw)
            assert len(result) > 0, f"Expected non-empty list for raw={raw!r}"

    def test_result_providers_are_all_allowed(self) -> None:
        for raw in [["tavily"], "brave,exa", json.dumps(["serper"]), None, ""]:
            result = normalize_search_provider_chain(raw)
            for p in result:
                assert p in ALLOWED_SEARCH_PROVIDERS, f"Provider {p!r} not in allow-list"


# ---------------------------------------------------------------------------
# parse_search_provider_chain — returns [] for falsy / empty input
# ---------------------------------------------------------------------------


class TestParseSearchProviderChain:
    """parse_search_provider_chain returns [] when input is falsy or empty."""

    # --- truthy list inputs ---

    def test_valid_list_returns_filtered_chain(self) -> None:
        result = parse_search_provider_chain(["tavily", "brave"])
        assert result == ["tavily", "brave"]

    def test_list_deduplicates(self) -> None:
        result = parse_search_provider_chain(["exa", "exa", "serper"])
        assert result == ["exa", "serper"]

    def test_list_filters_unknown_providers(self) -> None:
        result = parse_search_provider_chain(["tavily", "bogus"])
        assert result == ["tavily"]

    def test_list_lowercases_providers(self) -> None:
        result = parse_search_provider_chain(["EXA", "Serper"])
        assert result == ["exa", "serper"]

    def test_list_preserves_order(self) -> None:
        result = parse_search_provider_chain(["jina", "bing", "google"])
        assert result == ["jina", "bing", "google"]

    def test_list_strips_whitespace(self) -> None:
        result = parse_search_provider_chain([" tavily ", " brave "])
        assert result == ["tavily", "brave"]

    # --- truthy string inputs ---

    def test_comma_separated_string(self) -> None:
        result = parse_search_provider_chain("tavily,brave")
        assert result == ["tavily", "brave"]

    def test_comma_separated_string_with_spaces(self) -> None:
        result = parse_search_provider_chain("serper, exa")
        assert result == ["serper", "exa"]

    def test_single_provider_string(self) -> None:
        result = parse_search_provider_chain("duckduckgo")
        assert result == ["duckduckgo"]

    def test_json_array_string(self) -> None:
        raw = json.dumps(["bing", "google"])
        result = parse_search_provider_chain(raw)
        assert result == ["bing", "google"]

    # --- empty / falsy inputs must return [] ---

    def test_none_returns_empty_list(self) -> None:
        result = parse_search_provider_chain(None)
        assert result == []

    def test_empty_list_returns_empty_list(self) -> None:
        result = parse_search_provider_chain([])
        assert result == []

    def test_empty_string_returns_empty_list(self) -> None:
        result = parse_search_provider_chain("")
        assert result == []

    def test_zero_returns_empty_list(self) -> None:
        result = parse_search_provider_chain(0)
        assert result == []

    def test_false_returns_empty_list(self) -> None:
        result = parse_search_provider_chain(False)
        assert result == []

    def test_dict_returns_empty_list(self) -> None:
        result = parse_search_provider_chain({"provider": "tavily"})
        assert result == []

    def test_integer_returns_empty_list(self) -> None:
        result = parse_search_provider_chain(99)
        assert result == []

    # --- list of only unknowns: truthy input, all filtered out ---

    def test_list_of_only_unknown_providers_returns_defaults(self) -> None:
        # Non-empty list is truthy input, so parse delegates fully to normalize;
        # normalize falls back to defaults when nothing passes the allow-list.
        result = parse_search_provider_chain(["fake", "bogus"])
        assert result == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    # --- return type ---

    def test_always_returns_list(self) -> None:
        for raw in [["tavily"], "brave", None, "", 0, False, {}]:
            result = parse_search_provider_chain(raw)
            assert isinstance(result, list), f"Expected list for raw={raw!r}"

    # --- behavioural difference from normalize ---

    def test_parse_returns_empty_for_none_while_normalize_returns_defaults(self) -> None:
        assert parse_search_provider_chain(None) == []
        assert normalize_search_provider_chain(None) == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_parse_returns_empty_for_empty_list_while_normalize_returns_defaults(self) -> None:
        assert parse_search_provider_chain([]) == []
        assert normalize_search_provider_chain([]) == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_parse_returns_empty_for_zero_while_normalize_returns_defaults(self) -> None:
        assert parse_search_provider_chain(0) == []
        assert normalize_search_provider_chain(0) == list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    def test_parse_and_normalize_agree_on_valid_list(self) -> None:
        raw = ["tavily", "brave"]
        assert parse_search_provider_chain(raw) == normalize_search_provider_chain(raw)

    def test_parse_and_normalize_agree_on_valid_string(self) -> None:
        raw = "serper,exa"
        assert parse_search_provider_chain(raw) == normalize_search_provider_chain(raw)


# ---------------------------------------------------------------------------
# Integration: __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify __all__ lists exactly what is documented in the module."""

    def test_all_exports_importable(self) -> None:
        import app.core.search_provider_policy as mod

        for name in mod.__all__:
            assert hasattr(mod, name), f"{name!r} listed in __all__ but not importable"

    def test_all_contains_expected_names(self) -> None:
        import app.core.search_provider_policy as mod

        expected = {
            "ALLOWED_SEARCH_PROVIDERS",
            "DEFAULT_SEARCH_PROVIDER_CHAIN",
            "normalize_search_provider_chain",
            "parse_search_provider_chain",
        }
        assert expected == set(mod.__all__)
