"""Tests for search domain models: SearchResultItem, SearchResultMeta, SearchResults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.search import SearchResultItem, SearchResultMeta, SearchResults


# ===========================================================================
# SearchResultItem
# ===========================================================================

class TestSearchResultItem:
    # --- Required fields ---

    def test_required_title_and_link(self):
        item = SearchResultItem(title="Python 3.12", link="https://python.org")
        assert item.title == "Python 3.12"
        assert item.link == "https://python.org"

    def test_missing_title_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            SearchResultItem(link="https://example.com")  # type: ignore[call-arg]
        field_names = [e["loc"][0] for e in exc_info.value.errors()]
        assert "title" in field_names

    def test_missing_link_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            SearchResultItem(title="No link")  # type: ignore[call-arg]
        field_names = [e["loc"][0] for e in exc_info.value.errors()]
        assert "link" in field_names

    def test_missing_both_required_fields_raises(self):
        with pytest.raises(ValidationError):
            SearchResultItem()  # type: ignore[call-arg]

    # --- Snippet default ---

    def test_snippet_defaults_to_empty_string(self):
        item = SearchResultItem(title="T", link="https://x.com")
        assert item.snippet == ""

    def test_snippet_can_be_set(self):
        item = SearchResultItem(
            title="FastAPI Docs",
            link="https://fastapi.tiangolo.com",
            snippet="FastAPI is a modern web framework for building APIs.",
        )
        assert "FastAPI" in item.snippet

    def test_snippet_can_be_empty_string_explicitly(self):
        item = SearchResultItem(title="T", link="https://x.com", snippet="")
        assert item.snippet == ""

    # --- Serialization ---

    def test_model_dump_minimal(self):
        item = SearchResultItem(title="T", link="https://x.com")
        data = item.model_dump()
        assert data["title"] == "T"
        assert data["link"] == "https://x.com"
        assert data["snippet"] == ""

    def test_model_dump_with_snippet(self):
        item = SearchResultItem(title="T", link="https://x.com", snippet="A snippet")
        data = item.model_dump()
        assert data["snippet"] == "A snippet"

    def test_round_trip_from_dict(self):
        original = SearchResultItem(
            title="Ruff Linter", link="https://docs.astral.sh/ruff", snippet="Fast Python linter"
        )
        data = original.model_dump()
        restored = SearchResultItem.model_validate(data)
        assert restored.title == original.title
        assert restored.link == original.link
        assert restored.snippet == original.snippet

    def test_round_trip_via_json(self):
        item = SearchResultItem(title="JSON RT", link="https://example.com", snippet="snippet")
        restored = SearchResultItem.model_validate_json(item.model_dump_json())
        assert restored.title == "JSON RT"
        assert restored.snippet == "snippet"


# ===========================================================================
# SearchResultMeta
# ===========================================================================

class TestSearchResultMeta:
    # --- Required field ---

    def test_required_provider(self):
        meta = SearchResultMeta(provider="serper")
        assert meta.provider == "serper"

    def test_missing_provider_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            SearchResultMeta()  # type: ignore[call-arg]
        field_names = [e["loc"][0] for e in exc_info.value.errors()]
        assert "provider" in field_names

    # --- Defaults ---

    def test_default_latency_ms_is_zero(self):
        meta = SearchResultMeta(provider="tavily")
        assert meta.latency_ms == 0.0

    def test_default_provider_request_id_is_none(self):
        meta = SearchResultMeta(provider="brave")
        assert meta.provider_request_id is None

    def test_default_estimated_credits_is_one(self):
        meta = SearchResultMeta(provider="serper")
        assert meta.estimated_credits == 1.0

    def test_default_cached_is_false(self):
        meta = SearchResultMeta(provider="serper")
        assert meta.cached is False

    def test_default_canonical_query_is_empty_string(self):
        meta = SearchResultMeta(provider="serper")
        assert meta.canonical_query == ""

    # --- Explicit values ---

    def test_latency_ms_set(self):
        meta = SearchResultMeta(provider="tavily", latency_ms=123.45)
        assert meta.latency_ms == 123.45

    def test_provider_request_id_set(self):
        meta = SearchResultMeta(provider="serper", provider_request_id="req-xyz")
        assert meta.provider_request_id == "req-xyz"

    def test_estimated_credits_advanced(self):
        meta = SearchResultMeta(provider="tavily", estimated_credits=2.0)
        assert meta.estimated_credits == 2.0

    def test_cached_true(self):
        meta = SearchResultMeta(provider="serper", cached=True)
        assert meta.cached is True

    def test_canonical_query_set(self):
        meta = SearchResultMeta(provider="serper", canonical_query="python async tutorial")
        assert meta.canonical_query == "python async tutorial"

    # --- Full construction ---

    def test_full_construction(self):
        meta = SearchResultMeta(
            provider="brave",
            latency_ms=88.5,
            provider_request_id="cf-ray-abc",
            estimated_credits=1.0,
            cached=False,
            canonical_query="brave search python",
        )
        assert meta.provider == "brave"
        assert meta.latency_ms == 88.5
        assert meta.provider_request_id == "cf-ray-abc"
        assert meta.canonical_query == "brave search python"

    # --- Serialization ---

    def test_model_dump_defaults(self):
        meta = SearchResultMeta(provider="serper")
        data = meta.model_dump()
        assert data["provider"] == "serper"
        assert data["latency_ms"] == 0.0
        assert data["provider_request_id"] is None
        assert data["estimated_credits"] == 1.0
        assert data["cached"] is False
        assert data["canonical_query"] == ""

    def test_round_trip_from_dict(self):
        original = SearchResultMeta(
            provider="tavily",
            latency_ms=200.0,
            provider_request_id="trace-001",
            estimated_credits=2.0,
            cached=True,
            canonical_query="site:example.com",
        )
        data = original.model_dump()
        restored = SearchResultMeta.model_validate(data)
        assert restored.provider == original.provider
        assert restored.latency_ms == original.latency_ms
        assert restored.cached == original.cached
        assert restored.canonical_query == original.canonical_query

    def test_round_trip_via_json(self):
        meta = SearchResultMeta(provider="brave", latency_ms=55.5)
        restored = SearchResultMeta.model_validate_json(meta.model_dump_json())
        assert restored.provider == "brave"
        assert restored.latency_ms == 55.5


# ===========================================================================
# SearchResults
# ===========================================================================

class TestSearchResults:
    # --- Required field ---

    def test_required_query(self):
        sr = SearchResults(query="python async")
        assert sr.query == "python async"

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            SearchResults()  # type: ignore[call-arg]
        field_names = [e["loc"][0] for e in exc_info.value.errors()]
        assert "query" in field_names

    # --- Defaults ---

    def test_default_date_range_is_none(self):
        sr = SearchResults(query="q")
        assert sr.date_range is None

    def test_default_total_results_is_zero(self):
        sr = SearchResults(query="q")
        assert sr.total_results == 0

    def test_default_results_is_empty_list(self):
        sr = SearchResults(query="q")
        assert sr.results == []

    def test_default_meta_is_none(self):
        sr = SearchResults(query="q")
        assert sr.meta is None

    def test_results_lists_are_independent_between_instances(self):
        sr_a = SearchResults(query="a")
        sr_b = SearchResults(query="b")
        sr_a.results.append(SearchResultItem(title="T", link="https://x.com"))
        assert sr_b.results == []

    # --- Explicit values ---

    def test_date_range_set(self):
        sr = SearchResults(query="news", date_range="2026-01-01..2026-03-25")
        assert sr.date_range == "2026-01-01..2026-03-25"

    def test_total_results_set(self):
        sr = SearchResults(query="q", total_results=1_000_000)
        assert sr.total_results == 1_000_000

    def test_with_single_result_item(self):
        item = SearchResultItem(title="A", link="https://a.com", snippet="snippet a")
        sr = SearchResults(query="test", total_results=1, results=[item])
        assert len(sr.results) == 1
        assert sr.results[0].title == "A"

    def test_with_multiple_result_items(self):
        items = [
            SearchResultItem(title=f"Result {i}", link=f"https://r{i}.com")
            for i in range(5)
        ]
        sr = SearchResults(query="multi", total_results=5, results=items)
        assert len(sr.results) == 5
        assert sr.results[2].title == "Result 2"

    def test_with_meta(self):
        meta = SearchResultMeta(provider="serper", latency_ms=120.0)
        sr = SearchResults(query="q with meta", meta=meta)
        assert sr.meta is not None
        assert sr.meta.provider == "serper"
        assert sr.meta.latency_ms == 120.0

    # --- Full construction ---

    def test_full_construction(self):
        items = [
            SearchResultItem(title="Doc 1", link="https://d1.com", snippet="Snippet one"),
            SearchResultItem(title="Doc 2", link="https://d2.com", snippet="Snippet two"),
        ]
        meta = SearchResultMeta(
            provider="tavily",
            latency_ms=95.0,
            estimated_credits=2.0,
            cached=False,
            canonical_query="full test",
        )
        sr = SearchResults(
            query="full construction test",
            date_range="2026-01..2026-03",
            total_results=2,
            results=items,
            meta=meta,
        )
        assert sr.query == "full construction test"
        assert sr.date_range == "2026-01..2026-03"
        assert sr.total_results == 2
        assert len(sr.results) == 2
        assert sr.results[0].title == "Doc 1"
        assert sr.meta is not None
        assert sr.meta.provider == "tavily"

    # --- Serialization ---

    def test_model_dump_empty_results(self):
        sr = SearchResults(query="empty")
        data = sr.model_dump()
        assert data["query"] == "empty"
        assert data["date_range"] is None
        assert data["total_results"] == 0
        assert data["results"] == []
        assert data["meta"] is None

    def test_model_dump_with_nested_meta(self):
        meta = SearchResultMeta(provider="brave")
        sr = SearchResults(query="q", meta=meta)
        data = sr.model_dump()
        assert isinstance(data["meta"], dict)
        assert data["meta"]["provider"] == "brave"

    def test_model_dump_with_results_list(self):
        items = [SearchResultItem(title="T", link="https://x.com", snippet="s")]
        sr = SearchResults(query="q", results=items)
        data = sr.model_dump()
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "T"

    def test_round_trip_from_dict(self):
        items = [SearchResultItem(title="RT", link="https://rt.com")]
        meta = SearchResultMeta(provider="serper", latency_ms=50.0)
        original = SearchResults(
            query="round trip",
            date_range="2026-03",
            total_results=1,
            results=items,
            meta=meta,
        )
        data = original.model_dump()
        restored = SearchResults.model_validate(data)
        assert restored.query == original.query
        assert restored.total_results == original.total_results
        assert len(restored.results) == 1
        assert restored.results[0].title == "RT"
        assert restored.meta is not None
        assert restored.meta.provider == "serper"

    def test_round_trip_via_json(self):
        items = [SearchResultItem(title="JSON", link="https://json.com", snippet="test")]
        meta = SearchResultMeta(provider="tavily", cached=True)
        sr = SearchResults(query="json rt", total_results=1, results=items, meta=meta)
        json_str = sr.model_dump_json()
        restored = SearchResults.model_validate_json(json_str)
        assert restored.query == "json rt"
        assert len(restored.results) == 1
        assert restored.results[0].title == "JSON"
        assert restored.meta is not None
        assert restored.meta.cached is True

    def test_results_items_are_searchresultitem_instances(self):
        items = [SearchResultItem(title="T", link="https://x.com")]
        sr = SearchResults(query="q", results=items)
        assert isinstance(sr.results[0], SearchResultItem)

    def test_meta_is_searchresultmeta_instance(self):
        meta = SearchResultMeta(provider="serper")
        sr = SearchResults(query="q", meta=meta)
        assert isinstance(sr.meta, SearchResultMeta)
