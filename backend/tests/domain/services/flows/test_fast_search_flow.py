from __future__ import annotations

from typing import Any

import pytest

from app.domain.models.event import (
    DoneEvent,
    MessageEvent,
    ResearchModeEvent,
    StreamEvent,
    SuggestionEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.message import Message
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.fast_search import FastSearchFlow, _build_tool_call_id


class _StubSearchEngine:
    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        del date_range
        return ToolResult.ok(
            message=f"Found results for {query}",
            data=SearchResults(
                query=query,
                total_results=1,
                results=[
                    SearchResultItem(
                        title=f"Result for {query}",
                        link="https://example.com/result",
                        snippet="Helpful snippet",
                    )
                ],
            ),
        )


class _StubLLM:
    async def ask(self, messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        assert messages
        return {"content": "Synthesized answer"}


@pytest.mark.asyncio
async def test_fast_search_emits_valid_tool_events_with_structured_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.domain.services.flows.fast_search.QueryExpander.expand",
        lambda *_args, **_kwargs: ["vector database comparison"],
    )

    flow = FastSearchFlow(
        session_id="session-fast-search",
        llm=_StubLLM(),
        search_engine=_StubSearchEngine(),
    )

    events = [event async for event in flow.run(Message(message="Compare vector databases"))]

    assert isinstance(events[0], ResearchModeEvent)

    calling_event = next(
        event for event in events if isinstance(event, ToolEvent) and event.status == ToolStatus.CALLING
    )
    assert calling_event.tool_name == "info_search_web"
    assert calling_event.function_name == "info_search_web"
    assert calling_event.function_args == {"query": "vector database comparison"}

    called_event = next(event for event in events if isinstance(event, ToolEvent) and event.status == ToolStatus.CALLED)
    assert called_event.tool_name == "info_search_web"
    assert called_event.function_args == {"query": "vector database comparison"}
    assert isinstance(called_event.function_result, ToolResult)
    assert called_event.function_result.success is True
    assert called_event.function_result.data is not None
    assert called_event.function_result.data.query == "vector database comparison"
    assert called_event.command_category == "search"

    assert any(isinstance(event, StreamEvent) and event.phase == "synthesizing" for event in events)
    assert any(isinstance(event, MessageEvent) and event.message == "Synthesized answer" for event in events)
    assert any(isinstance(event, SuggestionEvent) for event in events)
    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_fast_search_uses_unique_tool_call_ids_for_each_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.domain.services.flows.fast_search.QueryExpander.expand",
        lambda *_args, **_kwargs: ["duplicate query", "duplicate query"],
    )

    flow = FastSearchFlow(
        session_id="session-fast-search-ids",
        llm=_StubLLM(),
        search_engine=_StubSearchEngine(),
    )

    events = [event async for event in flow.run(Message(message="Compare vector databases"))]

    calling_ids = [
        event.tool_call_id for event in events if isinstance(event, ToolEvent) and event.status == ToolStatus.CALLING
    ]
    called_ids = [
        event.tool_call_id for event in events if isinstance(event, ToolEvent) and event.status == ToolStatus.CALLED
    ]

    expected_ids = [
        _build_tool_call_id(0, "duplicate query"),
        _build_tool_call_id(1, "duplicate query"),
    ]
    assert calling_ids == expected_ids
    assert called_ids == expected_ids
