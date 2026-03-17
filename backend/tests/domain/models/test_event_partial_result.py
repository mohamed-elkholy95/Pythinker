"""Tests for PartialResultEvent model."""

from app.domain.models.event import PartialResultEvent


def test_partial_result_event_construction() -> None:
    event = PartialResultEvent(
        step_index=0,
        step_title="Search for renewable energy",
        headline="Found 12 results about renewable energy trends",
        sources_count=12,
    )
    assert event.type == "partial_result"
    assert event.step_index == 0
    assert event.sources_count == 12


def test_partial_result_event_serialization() -> None:
    event = PartialResultEvent(
        step_index=1,
        step_title="Read article",
        headline="Visited: Understanding AI Agents",
    )
    data = event.model_dump()
    assert data["type"] == "partial_result"
    assert data["sources_count"] == 0  # default
    assert data["headline"] == "Visited: Understanding AI Agents"
