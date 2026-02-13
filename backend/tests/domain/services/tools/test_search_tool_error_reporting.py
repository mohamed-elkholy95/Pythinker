"""Regression tests for SearchTool variant error reporting."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.search import SearchTool, SearchType


@pytest.mark.asyncio
async def test_expanded_search_returns_failure_when_all_variants_fail() -> None:
    tool = SearchTool(search_engine=MagicMock())
    tool._execute_typed_search = AsyncMock(side_effect=RuntimeError("search backend unavailable"))

    result = await tool.expanded_search("python async patterns", max_variants=1)

    assert result.success is False
    assert result.data is not None
    assert result.data.total_results == 0
    assert "All variants failed" in (result.message or "")


@pytest.mark.asyncio
async def test_expanded_search_surfaces_partial_variant_failures() -> None:
    tool = SearchTool(search_engine=MagicMock())
    good_data = SearchResults(
        query="python api",
        date_range=None,
        total_results=1,
        results=[
            SearchResultItem(
                title="Python API Docs",
                link="https://docs.python.org/3/",
                snippet="Official Python documentation.",
            )
        ],
    )
    tool._execute_typed_search = AsyncMock(
        side_effect=[
            ToolResult(success=False, message="timeout"),
            ToolResult(success=True, data=good_data, message="ok"),
        ]
    )

    result = await tool.expanded_search("python api", search_type=SearchType.API, max_variants=2)

    assert result.success is True
    assert result.data is not None
    assert result.data.total_results == 1
    assert "VARIANT ERRORS" in (result.message or "")
