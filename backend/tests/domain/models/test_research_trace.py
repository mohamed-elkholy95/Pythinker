"""Tests for TraceType, TraceTier, and TraceEntry domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.research_trace import TraceEntry, TraceTier, TraceType


@pytest.mark.unit
class TestTraceTypeEnum:
    def test_all_five_values_exist(self) -> None:
        assert TraceType.SEARCH_QUERY.value == "search_query"
        assert TraceType.URL_VISITED.value == "url_visited"
        assert TraceType.SEARCH_SNIPPET.value == "search_snippet"
        assert TraceType.BROWSER_CONTENT.value == "browser_content"
        assert TraceType.DISTILLED_OUTCOME.value == "distilled_outcome"

    def test_exact_member_count(self) -> None:
        assert len(TraceType) == 5

    def test_is_str_enum(self) -> None:
        assert isinstance(TraceType.SEARCH_QUERY, str)
        assert TraceType.URL_VISITED == "url_visited"

    def test_lookup_by_value(self) -> None:
        assert TraceType("search_query") is TraceType.SEARCH_QUERY
        assert TraceType("distilled_outcome") is TraceType.DISTILLED_OUTCOME

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            TraceType("unknown_type")

    def test_all_values_are_strings(self) -> None:
        for tt in TraceType:
            assert isinstance(tt.value, str)


@pytest.mark.unit
class TestTraceTierEnum:
    def test_both_values_exist(self) -> None:
        assert TraceTier.TRANSIENT.value == "transient"
        assert TraceTier.DURABLE.value == "durable"

    def test_exact_member_count(self) -> None:
        assert len(TraceTier) == 2

    def test_is_str_enum(self) -> None:
        assert isinstance(TraceTier.TRANSIENT, str)
        assert TraceTier.DURABLE == "durable"

    def test_lookup_by_value(self) -> None:
        assert TraceTier("transient") is TraceTier.TRANSIENT
        assert TraceTier("durable") is TraceTier.DURABLE

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            TraceTier("ephemeral")


@pytest.mark.unit
class TestTraceEntryRequiredFields:
    def test_minimal_construction(self) -> None:
        entry = TraceEntry(
            session_id="sess-abc123",
            trace_type=TraceType.SEARCH_QUERY,
            content="python async best practices",
        )
        assert entry.session_id == "sess-abc123"
        assert entry.trace_type is TraceType.SEARCH_QUERY
        assert entry.content == "python async best practices"

    def test_missing_session_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            TraceEntry(  # type: ignore[call-arg]
                trace_type=TraceType.URL_VISITED,
                content="https://example.com",
            )

    def test_missing_trace_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            TraceEntry(  # type: ignore[call-arg]
                session_id="sess-xyz",
                content="some content",
            )

    def test_missing_content_raises(self) -> None:
        with pytest.raises(ValidationError):
            TraceEntry(  # type: ignore[call-arg]
                session_id="sess-xyz",
                trace_type=TraceType.SEARCH_QUERY,
            )


@pytest.mark.unit
class TestTraceEntryDefaults:
    def test_source_tool_default_empty_string(self) -> None:
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.SEARCH_SNIPPET,
            content="snippet text",
        )
        assert entry.source_tool == ""

    def test_tier_default_transient(self) -> None:
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.SEARCH_QUERY,
            content="a query",
        )
        assert entry.tier is TraceTier.TRANSIENT

    def test_created_at_default_utc_aware(self) -> None:
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.BROWSER_CONTENT,
            content="page html",
        )
        assert entry.created_at.tzinfo is not None
        assert entry.created_at.tzinfo == UTC

    def test_metadata_default_empty_dict(self) -> None:
        entry = TraceEntry(
            session_id="s1",
            trace_type=TraceType.URL_VISITED,
            content="https://example.com",
        )
        assert entry.metadata == {}


@pytest.mark.unit
class TestTraceEntryExplicitFields:
    def test_source_tool_set(self) -> None:
        entry = TraceEntry(
            session_id="s2",
            trace_type=TraceType.URL_VISITED,
            content="https://docs.python.org",
            source_tool="browser_navigate",
        )
        assert entry.source_tool == "browser_navigate"

    def test_tier_durable(self) -> None:
        entry = TraceEntry(
            session_id="s2",
            trace_type=TraceType.DISTILLED_OUTCOME,
            content="Python 3.12 adds per-interpreter GIL",
            tier=TraceTier.DURABLE,
        )
        assert entry.tier is TraceTier.DURABLE

    def test_created_at_explicit(self) -> None:
        t = datetime(2026, 2, 10, 8, 30, 0, tzinfo=UTC)
        entry = TraceEntry(
            session_id="s3",
            trace_type=TraceType.SEARCH_QUERY,
            content="query text",
            created_at=t,
        )
        assert entry.created_at == t

    def test_metadata_populated(self) -> None:
        entry = TraceEntry(
            session_id="s3",
            trace_type=TraceType.SEARCH_SNIPPET,
            content="short snippet",
            metadata={"rank": 1, "engine": "serper", "score": 0.92},
        )
        assert entry.metadata["rank"] == 1
        assert entry.metadata["engine"] == "serper"
        assert entry.metadata["score"] == pytest.approx(0.92)

    def test_tier_coercion_from_string(self) -> None:
        entry = TraceEntry(
            session_id="s4",
            trace_type=TraceType.DISTILLED_OUTCOME,
            content="outcome text",
            tier="durable",  # type: ignore[arg-type]
        )
        assert entry.tier is TraceTier.DURABLE

    def test_trace_type_coercion_from_string(self) -> None:
        entry = TraceEntry(
            session_id="s4",
            trace_type="browser_content",  # type: ignore[arg-type]
            content="page content",
        )
        assert entry.trace_type is TraceType.BROWSER_CONTENT


@pytest.mark.unit
class TestTraceEntryAllTypes:
    """Ensure each TraceType and TraceTier combination can be constructed."""

    @pytest.mark.parametrize("trace_type", list(TraceType))
    def test_all_trace_types_constructable(self, trace_type: TraceType) -> None:
        entry = TraceEntry(
            session_id="session-parameterized",
            trace_type=trace_type,
            content=f"content for {trace_type.value}",
        )
        assert entry.trace_type is trace_type

    @pytest.mark.parametrize("tier", list(TraceTier))
    def test_all_tiers_constructable(self, tier: TraceTier) -> None:
        entry = TraceEntry(
            session_id="session-parameterized",
            trace_type=TraceType.SEARCH_QUERY,
            content="some query",
            tier=tier,
        )
        assert entry.tier is tier

    def test_distilled_outcome_typically_durable(self) -> None:
        entry = TraceEntry(
            session_id="s5",
            trace_type=TraceType.DISTILLED_OUTCOME,
            content="Python async I/O summary",
            tier=TraceTier.DURABLE,
        )
        assert entry.trace_type is TraceType.DISTILLED_OUTCOME
        assert entry.tier is TraceTier.DURABLE


@pytest.mark.unit
class TestTraceEntrySerialization:
    def test_roundtrip_model_dump(self) -> None:
        t = datetime(2026, 3, 10, 14, 0, 0, tzinfo=UTC)
        entry = TraceEntry(
            session_id="sess-round",
            trace_type=TraceType.BROWSER_CONTENT,
            content="extracted page text",
            source_tool="browser_navigate",
            tier=TraceTier.TRANSIENT,
            created_at=t,
            metadata={"url": "https://example.com", "depth": 2},
        )
        data = entry.model_dump()
        entry2 = TraceEntry.model_validate(data)
        assert entry2.session_id == entry.session_id
        assert entry2.trace_type is entry.trace_type
        assert entry2.content == entry.content
        assert entry2.source_tool == entry.source_tool
        assert entry2.tier is entry.tier
        assert entry2.metadata == entry.metadata

    def test_metadata_dicts_are_independent(self) -> None:
        e1 = TraceEntry(
            session_id="s1",
            trace_type=TraceType.SEARCH_QUERY,
            content="q1",
        )
        e2 = TraceEntry(
            session_id="s2",
            trace_type=TraceType.SEARCH_QUERY,
            content="q2",
        )
        e1.metadata["key"] = "value"
        assert "key" not in e2.metadata

    def test_json_roundtrip(self) -> None:
        entry = TraceEntry(
            session_id="sess-json",
            trace_type=TraceType.URL_VISITED,
            content="https://python.org",
            source_tool="info_search_web",
        )
        json_str = entry.model_dump_json()
        entry2 = TraceEntry.model_validate_json(json_str)
        assert entry2.session_id == "sess-json"
        assert entry2.trace_type is TraceType.URL_VISITED
        assert entry2.source_tool == "info_search_web"
