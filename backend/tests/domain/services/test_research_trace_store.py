"""Tests for ResearchTraceStore — RESEARCH_TRACE memory tier."""

import asyncio
from datetime import datetime

import pytest

from app.domain.models.research_trace import TraceEntry, TraceTier, TraceType
from app.domain.services.research_trace_store import ResearchTraceStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    session_id: str = "sess-1",
    trace_type: TraceType = TraceType.SEARCH_QUERY,
    content: str = "python async patterns",
    tier: TraceTier = TraceTier.TRANSIENT,
    created_at: datetime | None = None,
) -> TraceEntry:
    kwargs: dict = {
        "session_id": session_id,
        "trace_type": trace_type,
        "content": content,
        "tier": tier,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return TraceEntry(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_and_retrieve_trace() -> None:
    """Adding a SEARCH_QUERY entry and retrieving it should return the same entry."""
    store = ResearchTraceStore()
    entry = _make_entry(trace_type=TraceType.SEARCH_QUERY, content="asyncio tutorial")

    await store.add(entry)
    results = await store.get_session_traces("sess-1")

    assert len(results) == 1
    assert results[0].trace_type is TraceType.SEARCH_QUERY
    assert results[0].content == "asyncio tutorial"


@pytest.mark.asyncio
async def test_expired_traces_excluded() -> None:
    """Transient entries should be excluded once they exceed the TTL."""
    store = ResearchTraceStore(ttl_seconds=0)
    entry = _make_entry()

    await store.add(entry)
    # Wait just long enough for created_at to be strictly less than cutoff
    await asyncio.sleep(0.01)

    results = await store.get_session_traces("sess-1")
    assert results == []


@pytest.mark.asyncio
async def test_distill_returns_only_outcomes() -> None:
    """get_distilled_outcomes must return only DISTILLED_OUTCOME entries."""
    store = ResearchTraceStore()

    transient_snippet = _make_entry(
        trace_type=TraceType.SEARCH_SNIPPET,
        content="some snippet",
        tier=TraceTier.TRANSIENT,
    )
    durable_outcome = _make_entry(
        trace_type=TraceType.DISTILLED_OUTCOME,
        content="Key finding: Python 3.12 is faster",
        tier=TraceTier.DURABLE,
    )
    url_entry = _make_entry(
        trace_type=TraceType.URL_VISITED,
        content="https://docs.python.org",
        tier=TraceTier.TRANSIENT,
    )

    await store.add(transient_snippet)
    await store.add(durable_outcome)
    await store.add(url_entry)

    outcomes = await store.get_distilled_outcomes("sess-1")

    assert len(outcomes) == 1
    assert outcomes[0].trace_type is TraceType.DISTILLED_OUTCOME
    assert outcomes[0].content == "Key finding: Python 3.12 is faster"


@pytest.mark.asyncio
async def test_trace_types_cover_source_tracker_events() -> None:
    """All 5 TraceType values must exist (contract with source tracker layer)."""
    expected = {
        "search_query",
        "url_visited",
        "search_snippet",
        "browser_content",
        "distilled_outcome",
    }
    actual = {t.value for t in TraceType}
    assert actual == expected


@pytest.mark.asyncio
async def test_clear_session_traces() -> None:
    """clear_session should remove all entries for the given session."""
    store = ResearchTraceStore()

    await store.add(_make_entry(session_id="sess-a", content="query 1"))
    await store.add(_make_entry(session_id="sess-a", content="query 2"))
    await store.add(_make_entry(session_id="sess-b", content="other session"))

    await store.clear_session("sess-a")

    assert await store.get_session_traces("sess-a") == []
    # Other session must be unaffected
    assert len(await store.get_session_traces("sess-b")) == 1
