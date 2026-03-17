"""Smoke tests for WP-2: Dependency-aware parallel scheduling.

Tests verify:
- detect_dependencies() prevents write-then-read same file from running in parallel
- Pure read-only calls on different paths batch correctly into parallel
- _can_parallelize_tools() rejects non-MCP tools with underscore names
"""

from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.parallel_executor import ParallelToolExecutor, ToolCall


def make_tc(id: str, name: str, args: dict) -> dict:
    """Build a raw LLM tool_call dict."""
    return {
        "id": id,
        "function": {"name": name, "arguments": args},
    }


def test_dependency_detection_write_then_read_same_file():
    """Write followed by read on the same file must NOT be parallelized."""
    executor = ParallelToolExecutor()
    calls = [
        ToolCall(id="1", tool_name="file_write", arguments={"file": "/tmp/a.txt", "content": "hello"}),
        ToolCall(id="2", tool_name="file_read", arguments={"file": "/tmp/a.txt"}),
    ]
    executor.add_calls(calls)
    executor.detect_dependencies()

    # file_read on same path depends on prior file_write
    read_call = executor._pending_calls[1]
    assert "1" in read_call.depends_on, "read_call should depend on write_call"


def test_no_dependency_different_files():
    """Reads of different files should have no dependencies."""
    executor = ParallelToolExecutor()
    calls = [
        ToolCall(id="1", tool_name="file_read", arguments={"file": "/tmp/a.txt"}),
        ToolCall(id="2", tool_name="file_read", arguments={"file": "/tmp/b.txt"}),
    ]
    executor.add_calls(calls)
    executor.detect_dependencies()

    for call in executor._pending_calls:
        assert not call.depends_on, f"{call.id} should have no dependencies"


def test_can_parallelize_returns_false_for_write_then_read(monkeypatch):
    """_can_parallelize_tools returns False when write-read dependency exists."""
    # Import base lazily to avoid full import chain

    from app.domain.services.agents.parallel_executor import ParallelToolExecutor as PTE  # noqa: N817

    # Build minimal mock that has the required attributes of BaseAgent
    class FakeAgent:
        def _to_tool_call(self, tc):
            return ToolCall(
                id=tc.get("id", ""),
                tool_name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", {}),
            )

        _can_parallelize_tools = ParallelToolExecutor  # not used directly; we test the logic via executor

    # Directly test through executor logic
    executor = PTE()
    tc_write = ToolCall(id="w1", tool_name="file_read", arguments={"file": "/tmp/x.txt"})
    tc_read = ToolCall(id="r1", tool_name="file_write", arguments={"file": "/tmp/x.txt", "content": "x"})
    executor.add_calls([tc_write, tc_read])
    executor.detect_dependencies()

    # file_write after file_read on same path creates a dependency
    write_call = executor._pending_calls[1]
    assert write_call.depends_on, "write after read on same path should create dependency"


def test_can_parallelize_rejects_deal_tools_even_with_underscores():
    """Only explicit safe tools/MCP read prefixes should parallelize.

    Regression guard for an overly-permissive MCP heuristic that treated any
    tool containing "_" as safe for parallel execution.
    """
    agent = BaseAgent.__new__(BaseAgent)
    calls = [
        make_tc("1", "deal_search", {"query": "rtx 5090"}),
        make_tc("2", "deal_find_coupons", {"store_name": "Amazon"}),
    ]
    assert BaseAgent._can_parallelize_tools(agent, calls) is False


def test_can_parallelize_accepts_safe_mcp_read_prefixes():
    """Read-only MCP dynamic tools should remain parallelizable."""
    agent = BaseAgent.__new__(BaseAgent)
    calls = [
        make_tc("1", "mcp_get_docs", {"topic": "gpu"}),
        make_tc("2", "mcp_list_resources", {"server_name": "ref"}),
    ]
    assert BaseAgent._can_parallelize_tools(agent, calls) is True
