"""Tests for task_state_manager — TaskState, TaskStateManager, singleton helpers.

Covers:
  - TaskState: add_step, mark_step_completed, mark_step_in_progress,
    mark_remaining_completed, record_url, record_query, _normalize_search_query,
    get_visited_summary, add_finding, get_current_step, to_markdown,
    to_context_signal
  - TaskStateManager: initialize_from_plan, update_step_status, add_finding,
    record_url, record_query, get_visited_urls, get_searched_queries,
    get_context_signal, get_markdown, reset, recreate_from_comprehension,
    should_trigger_comprehension, record_action, record_step_complete,
    record_no_progress, get_recent_actions, get_last_error
  - Singleton: get_task_state_manager, set_task_state_manager
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from app.domain.services.agents.task_state_manager import (
    STEP_STATUS_ICONS,
    TaskState,
    TaskStateManager,
    get_task_state_manager,
    set_task_state_manager,
)

# ---------------------------------------------------------------------------
# TaskState dataclass
# ---------------------------------------------------------------------------


class TestTaskState:
    """TaskState data manipulation."""

    def test_add_step(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("Do thing A")
        assert len(ts.steps) == 1
        assert ts.steps[0]["description"] == "Do thing A"
        assert ts.steps[0]["status"] == "pending"
        assert ts.steps[0]["id"] == "1"

    def test_add_step_custom_id(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("Do X", step_id="alpha")
        assert ts.steps[0]["id"] == "alpha"

    def test_mark_step_completed(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("A", step_id="1")
        assert ts.mark_step_completed("1", result="done") is True
        assert ts.steps[0]["status"] == "completed"
        assert ts.steps[0]["result"] == "done"

    def test_mark_step_completed_not_found(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("A", step_id="1")
        assert ts.mark_step_completed("99") is False

    def test_mark_step_completed_no_result(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("A", step_id="1")
        ts.mark_step_completed("1")
        assert "result" not in ts.steps[0]

    def test_mark_step_in_progress(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("A", step_id="1")
        assert ts.mark_step_in_progress("1") is True
        assert ts.steps[0]["status"] == "in_progress"

    def test_mark_step_in_progress_not_found(self) -> None:
        ts = TaskState(objective="test")
        assert ts.mark_step_in_progress("1") is False

    def test_mark_remaining_completed(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("A", step_id="1", status="completed")
        ts.add_step("B", step_id="2", status="in_progress")
        ts.add_step("C", step_id="3", status="pending")
        ts.add_step("D", step_id="4", status="failed")
        count = ts.mark_remaining_completed()
        assert count == 2
        assert ts.steps[0]["status"] == "completed"
        assert ts.steps[1]["status"] == "completed"
        assert ts.steps[2]["status"] == "completed"
        assert ts.steps[3]["status"] == "failed"

    def test_mark_remaining_completed_none_to_promote(self) -> None:
        ts = TaskState(objective="test")
        ts.add_step("A", step_id="1", status="completed")
        count = ts.mark_remaining_completed()
        assert count == 0


class TestTaskStateUrls:
    """TaskState URL and query tracking."""

    def test_record_url_new(self) -> None:
        ts = TaskState()
        assert ts.record_url("https://example.com") is True
        assert any(urlparse(url).netloc == "example.com" for url in ts.visited_urls)

    def test_record_url_duplicate(self) -> None:
        ts = TaskState()
        ts.record_url("https://example.com")
        assert ts.record_url("https://example.com") is False

    def test_record_url_normalizes_trailing_slash(self) -> None:
        ts = TaskState()
        ts.record_url("https://example.com/page/")
        assert ts.record_url("https://example.com/page") is False

    def test_record_url_normalizes_fragment(self) -> None:
        ts = TaskState()
        ts.record_url("https://example.com/page#section")
        assert ts.record_url("https://example.com/page") is False

    def test_record_url_empty(self) -> None:
        ts = TaskState()
        assert ts.record_url("") is False

    def test_record_query_new(self) -> None:
        ts = TaskState()
        assert ts.record_query("python async patterns") is True

    def test_record_query_duplicate(self) -> None:
        ts = TaskState()
        ts.record_query("python async patterns")
        assert ts.record_query("python async patterns") is False

    def test_record_query_empty(self) -> None:
        ts = TaskState()
        assert ts.record_query("") is False


class TestNormalizeSearchQuery:
    """TaskState._normalize_search_query deduplication logic."""

    def test_order_independent(self) -> None:
        assert TaskState._normalize_search_query("alpha beta") == TaskState._normalize_search_query("beta alpha")

    def test_strips_temporal_suffix_latest(self) -> None:
        q1 = TaskState._normalize_search_query("fastapi latest 2026")
        q2 = TaskState._normalize_search_query("fastapi")
        assert q1 == q2

    def test_strips_temporal_suffix_month_year(self) -> None:
        q1 = TaskState._normalize_search_query("react february 2026")
        q2 = TaskState._normalize_search_query("react")
        assert q1 == q2

    def test_strips_trailing_year(self) -> None:
        q1 = TaskState._normalize_search_query("rust web frameworks 2026")
        q2 = TaskState._normalize_search_query("rust web frameworks")
        assert q1 == q2

    def test_case_insensitive(self) -> None:
        q1 = TaskState._normalize_search_query("Python Async")
        q2 = TaskState._normalize_search_query("python async")
        assert q1 == q2


class TestTaskStateVisitedSummary:
    """TaskState.get_visited_summary output."""

    def test_empty_no_output(self) -> None:
        ts = TaskState()
        assert ts.get_visited_summary() == ""

    def test_includes_urls(self) -> None:
        ts = TaskState()
        ts.record_url("https://example.com")
        summary = ts.get_visited_summary()
        assert any(urlparse(token.strip("()[]<>,.;!?")).netloc == "example.com" for token in summary.split())
        assert "URLS ALREADY VISITED" in summary

    def test_includes_queries(self) -> None:
        ts = TaskState()
        ts.record_query("python asyncio")
        summary = ts.get_visited_summary()
        assert "SEARCHES ALREADY PERFORMED" in summary

    def test_truncates_large_url_set(self) -> None:
        ts = TaskState()
        for i in range(25):
            ts.record_url(f"https://example.com/page{i}")
        summary = ts.get_visited_summary()
        assert "and 5 more" in summary


class TestTaskStateFindings:
    """TaskState.add_finding and key_findings."""

    def test_add_finding(self) -> None:
        ts = TaskState()
        ts.add_finding("Important discovery")
        assert "Important discovery" in ts.key_findings

    def test_add_finding_dedup(self) -> None:
        ts = TaskState()
        ts.add_finding("A")
        ts.add_finding("A")
        assert len(ts.key_findings) == 1

    def test_add_finding_empty_ignored(self) -> None:
        ts = TaskState()
        ts.add_finding("")
        assert len(ts.key_findings) == 0

    def test_findings_capped_at_10(self) -> None:
        ts = TaskState()
        for i in range(15):
            ts.add_finding(f"finding-{i}")
        assert len(ts.key_findings) == 10


class TestTaskStateCurrentStep:
    """TaskState.get_current_step priority logic."""

    def test_returns_in_progress_first(self) -> None:
        ts = TaskState()
        ts.add_step("A", step_id="1", status="pending")
        ts.add_step("B", step_id="2", status="in_progress")
        current = ts.get_current_step()
        assert current is not None
        assert current["id"] == "2"

    def test_falls_back_to_pending(self) -> None:
        ts = TaskState()
        ts.add_step("A", step_id="1", status="completed")
        ts.add_step("B", step_id="2", status="pending")
        current = ts.get_current_step()
        assert current is not None
        assert current["id"] == "2"

    def test_none_when_all_completed(self) -> None:
        ts = TaskState()
        ts.add_step("A", step_id="1", status="completed")
        assert ts.get_current_step() is None

    def test_none_when_empty(self) -> None:
        ts = TaskState()
        assert ts.get_current_step() is None


class TestTaskStateMarkdown:
    """TaskState.to_markdown output."""

    def test_includes_objective(self) -> None:
        ts = TaskState(objective="Build a widget")
        md = ts.to_markdown()
        assert "Build a widget" in md

    def test_includes_steps(self) -> None:
        ts = TaskState(objective="X")
        ts.add_step("Step A", step_id="1", status="completed")
        ts.add_step("Step B", step_id="2", status="pending")
        md = ts.to_markdown()
        assert "[x]" in md
        assert "[ ]" in md
        assert "Step A" in md
        assert "Step B" in md

    def test_includes_findings(self) -> None:
        ts = TaskState(objective="X")
        ts.add_finding("key result")
        md = ts.to_markdown()
        assert "key result" in md

    def test_no_steps(self) -> None:
        ts = TaskState(objective="X")
        md = ts.to_markdown()
        assert "No steps defined" in md


class TestTaskStateContextSignal:
    """TaskState.to_context_signal compact output."""

    def test_includes_objective(self) -> None:
        ts = TaskState(objective="Build widget")
        ts.add_step("A", step_id="1", status="completed")
        signal = ts.to_context_signal()
        assert "OBJECTIVE:" in signal
        assert "Build widget" in signal

    def test_includes_progress(self) -> None:
        ts = TaskState(objective="X")
        ts.add_step("A", step_id="1", status="completed")
        ts.add_step("B", step_id="2", status="pending")
        signal = ts.to_context_signal()
        assert "1/2 completed" in signal

    def test_truncates_long_objective(self) -> None:
        ts = TaskState(objective="A" * 200)
        signal = ts.to_context_signal()
        assert "..." in signal

    def test_shows_running_steps(self) -> None:
        ts = TaskState(objective="X")
        ts.add_step("A", step_id="1", status="in_progress")
        signal = ts.to_context_signal()
        assert "1 running" in signal

    def test_shows_failed_steps(self) -> None:
        ts = TaskState(objective="X")
        ts.add_step("A", step_id="1", status="failed")
        signal = ts.to_context_signal()
        assert "1 failed" in signal


# ---------------------------------------------------------------------------
# TaskStateManager
# ---------------------------------------------------------------------------


class TestTaskStateManagerInit:
    """TaskStateManager.initialize_from_plan."""

    def test_creates_state(self) -> None:
        mgr = TaskStateManager()
        state = mgr.initialize_from_plan("Do X", [{"id": "1", "description": "Step A"}])
        assert state.objective == "Do X"
        assert len(state.steps) == 1

    def test_initializes_progress_metrics(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("Do X", [{"id": "1", "description": "A"}, {"id": "2", "description": "B"}])
        metrics = mgr.get_progress_metrics()
        assert metrics is not None
        assert metrics.total_steps == 2
        assert metrics.steps_completed == 0
        assert metrics.steps_remaining == 2

    def test_clears_recent_actions(self) -> None:
        mgr = TaskStateManager()
        mgr._recent_actions = [{"x": 1}]
        mgr.initialize_from_plan("Do X", [])
        assert mgr.get_recent_actions() == []


class TestTaskStateManagerUpdateStep:
    """TaskStateManager.update_step_status."""

    @pytest.fixture()
    def mgr(self) -> TaskStateManager:
        m = TaskStateManager()
        m.initialize_from_plan(
            "Obj",
            [
                {"id": "1", "description": "A"},
                {"id": "2", "description": "B"},
            ],
        )
        return m

    async def test_complete_step(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "completed", result="done")
        assert mgr._state.steps[0]["status"] == "completed"
        assert mgr._state.steps[0]["result"] == "done"

    async def test_in_progress(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "in_progress")
        assert mgr._state.steps[0]["status"] == "in_progress"

    async def test_failed_status(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "failed", result="error msg")
        assert mgr._state.steps[0]["status"] == "failed"
        assert mgr._state.steps[0]["result"] == "error msg"

    async def test_blocked_status(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "blocked")
        assert mgr._state.steps[0]["status"] == "blocked"

    async def test_skipped_status(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "skipped")
        assert mgr._state.steps[0]["status"] == "skipped"

    async def test_unmapped_status_terminated(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "terminated")
        assert mgr._state.steps[0]["status"] == "failed"

    async def test_not_found_step(self, mgr: TaskStateManager) -> None:
        # Should not raise
        await mgr.update_step_status("99", "completed")

    async def test_with_findings(self, mgr: TaskStateManager) -> None:
        await mgr.update_step_status("1", "completed", findings=["found X"])
        assert "found X" in mgr._state.key_findings

    async def test_no_state_warning(self) -> None:
        mgr = TaskStateManager()
        # Should not raise
        await mgr.update_step_status("1", "completed")


class TestTaskStateManagerRecording:
    """TaskStateManager URL/query/finding recording."""

    def test_record_url_without_state(self) -> None:
        mgr = TaskStateManager()
        assert mgr.record_url("https://x.com") is False

    def test_record_url_with_state(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [])
        assert mgr.record_url("https://x.com") is True

    def test_record_query_without_state(self) -> None:
        mgr = TaskStateManager()
        assert mgr.record_query("test") is False

    def test_record_query_with_state(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [])
        assert mgr.record_query("test") is True

    def test_get_visited_urls_empty(self) -> None:
        mgr = TaskStateManager()
        assert mgr.get_visited_urls() == set()

    def test_get_searched_queries_empty(self) -> None:
        mgr = TaskStateManager()
        assert mgr.get_searched_queries() == set()

    async def test_add_finding(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [])
        await mgr.add_finding("important")
        assert "important" in mgr._state.key_findings


class TestTaskStateManagerContextSignal:
    """TaskStateManager context signal and markdown."""

    def test_context_signal_none_when_no_state(self) -> None:
        mgr = TaskStateManager()
        assert mgr.get_context_signal() is None

    def test_context_signal_with_state(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("Test", [{"id": "1", "description": "A"}])
        signal = mgr.get_context_signal()
        assert signal is not None
        assert "Test" in signal

    def test_markdown_none_when_no_state(self) -> None:
        mgr = TaskStateManager()
        assert mgr.get_markdown() is None

    def test_markdown_with_state(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("Test", [{"id": "1", "description": "A"}])
        md = mgr.get_markdown()
        assert md is not None
        assert "Test" in md


class TestTaskStateManagerReset:
    """TaskStateManager.reset."""

    def test_reset_clears_state(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [{"id": "1", "description": "A"}])
        mgr.reset()
        assert mgr._state is None
        assert mgr._progress_metrics is None
        assert mgr._recent_actions == []


class TestTaskStateManagerComprehension:
    """TaskStateManager.recreate_from_comprehension and should_trigger_comprehension."""

    def test_recreate_preserves_findings(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("Old", [{"id": "1", "description": "A"}])
        mgr._state.add_finding("kept")
        state = mgr.recreate_from_comprehension(
            "New objective", "Summarized understanding", [{"id": "1", "description": "B"}]
        )
        assert "kept" in state.key_findings
        assert "Understood as:" in state.objective

    def test_recreate_without_findings(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("Old", [])
        state = mgr.recreate_from_comprehension(
            "New", "Summary", [{"id": "1", "description": "B"}], preserve_findings=False
        )
        assert state.key_findings == []

    def test_recreate_no_comprehension_summary(self) -> None:
        mgr = TaskStateManager()
        state = mgr.recreate_from_comprehension("Obj", "", [{"id": "1", "description": "X"}])
        assert state.objective == "Obj"

    def test_should_trigger_short_message(self) -> None:
        mgr = TaskStateManager()
        assert mgr.should_trigger_comprehension("hello") is False

    def test_should_trigger_long_unstructured(self) -> None:
        mgr = TaskStateManager()
        assert mgr.should_trigger_comprehension("a " * 600) is True

    def test_should_trigger_many_bullets(self) -> None:
        mgr = TaskStateManager()
        msg = "Requirements:\n" + "\n".join(f"- item {i}" for i in range(10))
        assert mgr.should_trigger_comprehension(msg, threshold_chars=50) is True

    def test_should_trigger_many_numbered(self) -> None:
        mgr = TaskStateManager()
        msg = "Steps:\n" + "\n".join(f"{i}. step {i}" for i in range(1, 10))
        assert mgr.should_trigger_comprehension(msg, threshold_chars=50) is True

    def test_should_trigger_many_sections(self) -> None:
        mgr = TaskStateManager()
        msg = "\n".join(f"# Section {i}\nContent here." for i in range(5))
        assert mgr.should_trigger_comprehension(msg, threshold_chars=50) is True


class TestTaskStateManagerProgressActions:
    """TaskStateManager progress tracking and recent actions."""

    async def test_record_action_success(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [{"id": "1", "description": "A"}])
        await mgr.record_action("search", success=True, result="found it")
        actions = mgr.get_recent_actions()
        assert len(actions) == 1
        assert actions[0]["function_name"] == "search"
        assert actions[0]["success"] is True

    async def test_record_action_failure(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [{"id": "1", "description": "A"}])
        await mgr.record_action("search", success=False, error="timeout")
        last_err = mgr.get_last_error()
        assert last_err == "timeout"

    async def test_record_action_capped(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [])
        for i in range(15):
            await mgr.record_action(f"tool_{i}", success=True)
        assert len(mgr.get_recent_actions()) == 10

    async def test_record_action_no_metrics(self) -> None:
        mgr = TaskStateManager()
        # No init — should not raise
        await mgr.record_action("search", success=True)

    async def test_record_step_complete(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [{"id": "1", "description": "A"}])
        await mgr.record_step_complete("1", success=True)
        assert mgr._state.steps[0]["status"] == "completed"

    def test_record_no_progress(self) -> None:
        mgr = TaskStateManager()
        mgr.initialize_from_plan("X", [{"id": "1", "description": "A"}])
        mgr.record_no_progress()
        assert mgr._progress_metrics.actions_since_progress == 1

    def test_get_last_error_none(self) -> None:
        mgr = TaskStateManager()
        assert mgr.get_last_error() is None


class TestStepStatusIcons:
    """STEP_STATUS_ICONS constant coverage."""

    def test_all_icons_present(self) -> None:
        assert "completed" in STEP_STATUS_ICONS
        assert "in_progress" in STEP_STATUS_ICONS
        assert "pending" in STEP_STATUS_ICONS
        assert "failed" in STEP_STATUS_ICONS


class TestSingleton:
    """get_task_state_manager and set_task_state_manager."""

    def test_set_and_get(self) -> None:
        mgr = TaskStateManager()
        set_task_state_manager(mgr)
        assert get_task_state_manager() is mgr
        # Cleanup
        set_task_state_manager(TaskStateManager())
