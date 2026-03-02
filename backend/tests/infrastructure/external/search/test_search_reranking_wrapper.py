"""Tests for infrastructure-level Jina rerank wrapper."""

from unittest.mock import AsyncMock

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.factory import RerankingSearchEngine


def _base_results() -> SearchResults:
    return SearchResults(
        query="test query",
        date_range=None,
        total_results=2,
        results=[
            SearchResultItem(title="Result A", link="https://example.com/a", snippet="a"),
            SearchResultItem(title="Result B", link="https://example.com/b", snippet="b"),
        ],
    )


@pytest.mark.asyncio
async def test_reranking_wrapper_applies_reranked_order() -> None:
    base_engine = AsyncMock()
    base_engine.search = AsyncMock(return_value=ToolResult.ok(data=_base_results(), message="ok"))

    reranker = AsyncMock()
    reranker.rerank = AsyncMock(
        return_value=[
            SearchResultItem(title="Result B", link="https://example.com/b", snippet="b"),
            SearchResultItem(title="Result A", link="https://example.com/a", snippet="a"),
        ]
    )

    wrapper = RerankingSearchEngine(base_engine=base_engine, reranker=reranker, top_n=2)
    result = await wrapper.search("test query")

    assert result.success is True
    assert result.data is not None
    assert [item.link for item in result.data.results] == [
        "https://example.com/b",
        "https://example.com/a",
    ]
    assert "RERANKED: Jina" in (result.message or "")


@pytest.mark.asyncio
async def test_reranking_wrapper_fails_open_on_rerank_error() -> None:
    base = _base_results()
    base_engine = AsyncMock()
    base_engine.search = AsyncMock(return_value=ToolResult.ok(data=base, message="ok"))

    reranker = AsyncMock()
    reranker.rerank = AsyncMock(side_effect=RuntimeError("rerank unavailable"))

    wrapper = RerankingSearchEngine(base_engine=base_engine, reranker=reranker, top_n=2)
    result = await wrapper.search("test query")

    assert result.success is True
    assert result.data is not None
    assert [item.link for item in result.data.results] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
