"""Tests for app.domain.models.research_trace — research trace models.

Covers: TraceType, TraceTier, TraceEntry creation and defaults.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.models.research_trace import TraceEntry, TraceTier, TraceType


class TestTraceType:
    def test_all_types(self):
        expected = {"search_query", "url_visited", "search_snippet", "browser_content", "distilled_outcome"}
        actual = {t.value for t in TraceType}
        assert actual == expected


class TestTraceTier:
    def test_tiers(self):
        assert TraceTier.TRANSIENT == "transient"
        assert TraceTier.DURABLE == "durable"


class TestTraceEntry:
    def test_minimal_creation(self):
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.SEARCH_QUERY,
            content="how to use FastAPI",
        )
        assert entry.session_id == "s1"
        assert entry.content == "how to use FastAPI"

    def test_defaults(self):
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.URL_VISITED,
            content="https://example.com",
        )
        assert entry.source_tool == ""
        assert entry.tier == TraceTier.TRANSIENT
        assert entry.metadata == {}
        assert isinstance(entry.created_at, datetime)

    def test_durable_tier(self):
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.DISTILLED_OUTCOME,
            content="Key finding: X is better than Y",
            tier=TraceTier.DURABLE,
        )
        assert entry.tier == TraceTier.DURABLE

    def test_with_metadata(self):
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.SEARCH_SNIPPET,
            content="snippet text",
            metadata={"score": 0.9, "source": "google"},
        )
        assert entry.metadata["score"] == 0.9

    def test_source_tool(self):
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.BROWSER_CONTENT,
            content="page content",
            source_tool="playwright",
        )
        assert entry.source_tool == "playwright"

    def test_serialization(self):
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.SEARCH_QUERY,
            content="test query",
        )
        data = entry.model_dump()
        assert data["session_id"] == "s1"
        assert data["trace_type"] == "search_query"
        assert data["tier"] == "transient"

    def test_each_trace_type(self):
        for tt in TraceType:
            entry = TraceEntry(session_id="s1", trace_type=tt, content="test")
            assert entry.trace_type == tt
