"""Tests for phased research flow."""

from unittest.mock import AsyncMock

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.phased_research import PhasedResearchFlow


@pytest.fixture
def mock_search_engine():
    engine = AsyncMock()
    engine.search = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=SearchResults(
                query="test",
                results=[
                    SearchResultItem(title="T1", link="https://example.com/1", snippet="S1"),
                    SearchResultItem(title="T2", link="https://example.com/2", snippet="S2"),
                ],
            ),
        )
    )
    return engine


@pytest.mark.asyncio
async def test_run_emits_phase_transition_checkpoints_and_report(mock_search_engine):
    flow = PhasedResearchFlow(search_engine=mock_search_engine, session_id="session-1")

    events = [event async for event in flow.run("python async testing")]

    event_types = [event.type for event in events]
    assert event_types.count("phase_transition") >= 4
    assert event_types.count("checkpoint_saved") == 3
    assert "report" in event_types
    assert event_types[-1] == "phase_transition"


@pytest.mark.asyncio
async def test_run_builds_report_from_checkpoints(mock_search_engine):
    flow = PhasedResearchFlow(search_engine=mock_search_engine, session_id="session-2")

    events = [event async for event in flow.run("agent architecture")]
    report = next(event for event in events if event.type == "report")

    assert "# Research Report: agent architecture" in report.content
    assert "## phase_1" in report.content
    assert "https://example.com/1" in report.content
