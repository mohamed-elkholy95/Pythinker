"""Tests for SpeculativeExecutor."""

from datetime import datetime

import pytest

from app.domain.services.agents.speculative.executor import (
    SAFE_SPECULATION_TOOLS,
    SpeculationSafety,
    SpeculativeExecutor,
    SpeculativeResult,
    SpeculativeTask,
    get_speculative_executor,
    reset_speculative_executor,
)

# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------


class TestSpeculationSafety:
    def test_values(self):
        assert SpeculationSafety.SAFE == "safe"
        assert SpeculationSafety.CONDITIONAL == "conditional"
        assert SpeculationSafety.UNSAFE == "unsafe"


class TestSafeTools:
    def test_search_tools_safe(self):
        assert "info_search_web" in SAFE_SPECULATION_TOOLS
        assert "info_search_news" in SAFE_SPECULATION_TOOLS

    def test_file_read_safe(self):
        assert "file_read" in SAFE_SPECULATION_TOOLS
        assert "file_search" in SAFE_SPECULATION_TOOLS

    def test_write_tools_not_safe(self):
        assert "file_write" not in SAFE_SPECULATION_TOOLS
        assert "shell_exec" not in SAFE_SPECULATION_TOOLS


# ---------------------------------------------------------------------------
# SpeculativeTask dataclass
# ---------------------------------------------------------------------------


class TestSpeculativeTask:
    def test_defaults(self):
        t = SpeculativeTask(
            task_id="t1",
            tool_name="file_read",
            tool_args={"path": "/a"},
            prediction_confidence=0.8,
        )
        assert t.depends_on is None
        assert t.result is None
        assert t.error is None
        assert t.was_used is False
        assert isinstance(t.created_at, datetime)

    def test_custom_fields(self):
        t = SpeculativeTask(
            task_id="t2",
            tool_name="info_search_web",
            tool_args={"q": "test"},
            prediction_confidence=0.9,
            depends_on="t1",
        )
        assert t.depends_on == "t1"


# ---------------------------------------------------------------------------
# SpeculativeResult dataclass
# ---------------------------------------------------------------------------


class TestSpeculativeResult:
    def test_defaults(self):
        r = SpeculativeResult(
            task_id="t1",
            tool_name="file_read",
            result="content",
            prediction_confidence=0.8,
            execution_time_ms=50.0,
        )
        assert r.was_accurate is False
        assert r.saved_time_ms == 0.0


# ---------------------------------------------------------------------------
# SpeculativeExecutor
# ---------------------------------------------------------------------------


class TestSpeculativeExecutor:
    def test_init_defaults(self):
        ex = SpeculativeExecutor()
        assert ex._max_concurrent == 3
        assert ex._min_confidence == 0.6

    def test_init_custom(self):
        ex = SpeculativeExecutor(max_concurrent=5, min_confidence=0.8)
        assert ex._max_concurrent == 5
        assert ex._min_confidence == 0.8

    def test_can_speculate_safe_tool(self):
        ex = SpeculativeExecutor()
        assert ex.can_speculate("file_read") is True

    def test_can_speculate_unsafe_tool(self):
        ex = SpeculativeExecutor()
        assert ex.can_speculate("shell_exec") is False
        assert ex.can_speculate("file_write") is False

    def test_queue_speculation_safe(self):
        ex = SpeculativeExecutor()
        task = ex.queue_speculation("file_read", {"path": "/a"}, 0.9)
        assert task is not None
        assert task.tool_name == "file_read"
        assert len(ex._queue) == 1

    def test_queue_speculation_unsafe_rejected(self):
        ex = SpeculativeExecutor()
        task = ex.queue_speculation("shell_exec", {"cmd": "ls"}, 0.9)
        assert task is None
        assert len(ex._queue) == 0

    def test_queue_speculation_low_confidence_rejected(self):
        ex = SpeculativeExecutor()
        task = ex.queue_speculation("file_read", {"path": "/a"}, 0.3)
        assert task is None

    def test_queue_speculation_full_queue_rejected(self):
        ex = SpeculativeExecutor()
        for i in range(ex.MAX_QUEUE_SIZE):
            ex.queue_speculation("file_read", {"path": f"/{i}"}, 0.9)
        task = ex.queue_speculation("file_read", {"path": "/overflow"}, 0.9)
        assert task is None

    def test_queue_speculation_increments_stats(self):
        ex = SpeculativeExecutor()
        ex.queue_speculation("file_read", {"path": "/a"}, 0.9)
        assert ex._stats["total_speculated"] == 1

    @pytest.mark.asyncio
    async def test_execute_speculations_runs_tasks(self):
        ex = SpeculativeExecutor()
        ex.queue_speculation("file_read", {"path": "/a"}, 0.9)

        async def mock_executor(tool_name, tool_args):
            return f"result for {tool_args['path']}"

        results = await ex.execute_speculations(mock_executor)
        assert len(results) == 1
        assert results[0].tool_name == "file_read"
        assert results[0].result == "result for /a"

    @pytest.mark.asyncio
    async def test_execute_speculations_empty_queue(self):
        ex = SpeculativeExecutor()
        results = await ex.execute_speculations(lambda t, a: None)
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_speculations_handles_errors(self):
        ex = SpeculativeExecutor()
        ex.queue_speculation("file_read", {"path": "/fail"}, 0.9)

        async def failing_executor(tool_name, tool_args):
            raise RuntimeError("boom")

        results = await ex.execute_speculations(failing_executor)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_execute_speculations_respects_max_concurrent(self):
        ex = SpeculativeExecutor(max_concurrent=2)
        for i in range(5):
            ex.queue_speculation("file_read", {"path": f"/{i}"}, 0.9)

        call_count = 0

        async def counting_executor(tool_name, tool_args):
            nonlocal call_count
            call_count += 1
            return "ok"

        await ex.execute_speculations(counting_executor)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_speculations_sorts_by_confidence(self):
        ex = SpeculativeExecutor(max_concurrent=1)
        ex.queue_speculation("file_read", {"path": "/low"}, 0.7)
        ex.queue_speculation("file_read", {"path": "/high"}, 0.95)

        executed_paths = []

        async def tracking_executor(tool_name, tool_args):
            executed_paths.append(tool_args["path"])
            return "ok"

        await ex.execute_speculations(tracking_executor)
        assert executed_paths[0] == "/high"

    def test_mark_result_used(self):
        ex = SpeculativeExecutor()
        result = SpeculativeResult(
            task_id="t1",
            tool_name="file_read",
            result="data",
            prediction_confidence=0.9,
            execution_time_ms=50.0,
        )
        ex.mark_result_used(result, actual_execution_time_ms=200.0)
        assert result.was_accurate is True
        assert result.saved_time_ms == 150.0
        assert ex._stats["time_saved_ms"] == 150.0

    def test_mark_result_used_no_savings(self):
        ex = SpeculativeExecutor()
        result = SpeculativeResult(
            task_id="t1",
            tool_name="file_read",
            result="data",
            prediction_confidence=0.9,
            execution_time_ms=300.0,
        )
        ex.mark_result_used(result, actual_execution_time_ms=100.0)
        assert result.saved_time_ms == 0.0

    def test_clear_speculation_all(self):
        ex = SpeculativeExecutor()
        ex.queue_speculation("file_read", {"path": "/a"}, 0.9)
        ex._completed["t1"] = SpeculativeResult(
            task_id="t1",
            tool_name="file_read",
            result="r",
            prediction_confidence=0.9,
            execution_time_ms=50.0,
        )
        ex.clear_speculation()
        assert len(ex._queue) == 0
        assert len(ex._completed) == 0

    def test_clear_speculation_specific(self):
        ex = SpeculativeExecutor()
        t = ex.queue_speculation("file_read", {"path": "/a"}, 0.9)
        ex.queue_speculation("file_read", {"path": "/b"}, 0.9)
        ex.clear_speculation(t.task_id)
        assert len(ex._queue) == 1

    def test_get_statistics(self):
        ex = SpeculativeExecutor()
        ex.queue_speculation("file_read", {"path": "/a"}, 0.9)
        stats = ex.get_statistics()
        assert stats["total_speculated"] == 1
        assert stats["queue_size"] == 1
        assert stats["cached_results"] == 0
        assert stats["hit_rate"] == 0

    def test_args_match_equal(self):
        ex = SpeculativeExecutor()
        assert ex._args_match({"a": 1, "b": 2}, {"a": 1, "b": 2}) is True

    def test_args_match_different_values(self):
        ex = SpeculativeExecutor()
        assert ex._args_match({"a": 1}, {"a": 2}) is False

    def test_args_match_different_keys(self):
        ex = SpeculativeExecutor()
        assert ex._args_match({"a": 1}, {"b": 1}) is False


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        reset_speculative_executor()

    def teardown_method(self):
        reset_speculative_executor()

    def test_get_returns_same_instance(self):
        e1 = get_speculative_executor()
        e2 = get_speculative_executor()
        assert e1 is e2

    def test_reset_creates_new(self):
        e1 = get_speculative_executor()
        reset_speculative_executor()
        e2 = get_speculative_executor()
        assert e1 is not e2
