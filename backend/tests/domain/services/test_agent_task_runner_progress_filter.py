"""Tests for AgentTaskRunner._should_persist_tool_progress_event.

This static method gates which ToolProgressEvent instances are persisted
to MongoDB session history vs. streamed SSE-only.  Only checkpoints that
carry meaningful keys (url, action, coordinates, query, etc.) should be
stored — noisy ticks without replay value are dropped.
"""

import pytest

from app.domain.models.event import ToolProgressEvent
from app.domain.services.agent_task_runner import AgentTaskRunner


def _make_progress(checkpoint_data: dict | None = None) -> ToolProgressEvent:
    return ToolProgressEvent(
        tool_call_id="call-1",
        tool_name="search",
        function_name="info_search_web",
        progress_percent=50,
        current_step="Processing...",
        steps_completed=1,
        steps_total=3,
        elapsed_ms=1200,
        checkpoint_data=checkpoint_data,
    )


class TestShouldPersistToolProgressEvent:
    """Unit tests for the MongoDB persistence filter."""

    def test_persists_checkpoint_with_url(self) -> None:
        event = _make_progress({"url": "https://example.com", "action": "navigate"})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_checkpoint_with_action_only(self) -> None:
        event = _make_progress({"action": "search"})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_checkpoint_with_query(self) -> None:
        event = _make_progress({"query": "best headphones 2026"})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_checkpoint_with_coordinates(self) -> None:
        event = _make_progress({"coordinate_x": 120, "coordinate_y": 340})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_checkpoint_with_index(self) -> None:
        event = _make_progress({"index": 2})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_checkpoint_with_store_statuses(self) -> None:
        """Deal scraper progress with partial store info should persist."""
        event = _make_progress({"store_statuses": [{"store": "Amazon", "count": 5}]})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_checkpoint_with_partial_deals(self) -> None:
        event = _make_progress({"partial_deals": [{"title": "20% off"}]})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_skips_none_checkpoint(self) -> None:
        event = _make_progress(None)
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is False

    def test_skips_empty_dict_checkpoint(self) -> None:
        event = _make_progress({})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is False

    def test_skips_irrelevant_keys_only(self) -> None:
        """Checkpoint with only non-meaningful keys (e.g. heartbeat notes)."""
        event = _make_progress({"note": "background update", "timestamp": 123456})
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is False

    def test_skips_non_dict_checkpoint(self) -> None:
        """Checkpoint data that is not a dict (e.g. a string or list)."""
        event = _make_progress(None)
        # Simulate non-dict by forcing the field after construction
        object.__setattr__(event, "checkpoint_data", "not-a-dict")
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is False

    def test_persists_full_search_navigate_checkpoint(self) -> None:
        """Real-world checkpoint from _browse_top_results."""
        event = _make_progress({
            "action": "navigate",
            "action_function": "browser_navigate",
            "url": "https://example.com/deals/headphones",
            "index": 1,
            "query": "headphones",
            "step": 2,
        })
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True

    def test_persists_browser_agent_action_checkpoint(self) -> None:
        """Real-world checkpoint from BrowserAgentTool."""
        event = _make_progress({
            "action": "click_element",
            "action_function": "browser_agent_run",
            "step": 3,
            "url": "https://example.com",
            "index": 5,
            "coordinate_x": 200,
            "coordinate_y": 450,
        })
        assert AgentTaskRunner._should_persist_tool_progress_event(event) is True
