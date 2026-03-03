"""Tests for graduated compaction — 3-tier decay replacing destructive smart_compact."""

import pytest

from app.domain.models.memory import Memory, MemoryConfig
from app.domain.models.tool_result import ToolResult


def _make_tool_message(function_name: str, content: str, tool_call_id: str = "tc-1") -> dict:
    """Helper to create a tool message dict."""
    return {
        "role": "tool",
        "function_name": function_name,
        "tool_call_id": tool_call_id,
        "content": content,
    }


def _make_result_content(success: bool = True, data: str = "some data", size: int = 0) -> str:
    """Helper to create ToolResult JSON content of a specific size."""
    result = ToolResult(success=success, message="Result message", data=data)
    content = result.model_dump_json()
    if size > len(content):
        # Pad with extra data to reach desired size
        padding = "x" * (size - len(content))
        result = ToolResult(success=success, message="Result message", data=data + padding)
        content = result.model_dump_json()
    return content


class TestGraduatedCompactTierAssignment:
    """Verify correct tier assignment: full, summary, one-liner."""

    def test_recent_tool_results_kept_full(self):
        """Tier 1: Last N tool results should be untouched."""
        config = MemoryConfig(
            graduated_full_window=3,
            graduated_summary_window=2,
            use_graduated_compaction=True,
            preserve_recent=0,  # No extra preserve window
        )
        memory = Memory(config=config)

        # Add 5 tool messages
        original_contents = []
        for i in range(5):
            content = _make_result_content(data=f"tool result {i}")
            original_contents.append(content)
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        memory.graduated_compact()

        # Last 3 (indices 2, 3, 4) should be untouched (Tier 1: full)
        assert memory.messages[2]["content"] == original_contents[2]
        assert memory.messages[3]["content"] == original_contents[3]
        assert memory.messages[4]["content"] == original_contents[4]

    def test_middle_tool_results_get_summary(self):
        """Tier 2: Results 6-15 should get 200-char summary."""
        config = MemoryConfig(
            graduated_full_window=2,
            graduated_summary_window=2,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        # Add 5 tool messages (enough for all 3 tiers)
        for i in range(5):
            content = _make_result_content(data=f"detailed result number {i} with lots of content " * 10)
            memory.messages.append(_make_tool_message("file_read", content, f"tc-{i}"))

        memory.graduated_compact()

        # Messages at rank 2 and 3 from newest → Tier 2 (summary)
        # rank 0,1 = full (indices 3,4), rank 2,3 = summary (indices 1,2), rank 4 = one-liner (index 0)
        assert "graduated-compacted" in memory.messages[1]["content"]
        assert "graduated-compacted" in memory.messages[2]["content"]
        # Summary should contain the first ~200 chars of the original
        assert "detailed result" in memory.messages[1]["content"]

    def test_oldest_tool_results_get_oneliner(self):
        """Tier 3: Results beyond full+summary window get one-liner stub."""
        config = MemoryConfig(
            graduated_full_window=1,
            graduated_summary_window=1,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        for i in range(4):
            content = _make_result_content(data=f"result {i} " * 50)
            memory.messages.append(_make_tool_message("browser_view", content, f"tc-{i}"))

        memory.graduated_compact()

        # rank 0 = full (idx 3), rank 1 = summary (idx 2), rank 2,3 = one-liner (idx 0,1)
        oneliner_0 = memory.messages[0]["content"]
        oneliner_1 = memory.messages[1]["content"]

        assert "graduated-compacted" in oneliner_0
        assert "graduated-compacted" in oneliner_1
        # One-liners should NOT contain the original data
        assert "result 0" not in oneliner_0.split("]", 1)[1] if "]" in oneliner_0 else True
        # But should contain the function name and size
        assert "[browser_view]" in oneliner_0


class TestGraduatedCompactWindowSizes:
    """Configurable window sizes."""

    def test_custom_window_sizes(self):
        config = MemoryConfig(
            graduated_full_window=2,
            graduated_summary_window=3,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        for i in range(8):
            content = _make_result_content(data=f"result {i} " * 50)
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        compacted_count = memory.graduated_compact()

        # 8 messages: rank 0,1 = full (2), rank 2,3,4 = summary (3), rank 5,6,7 = oneliner (3)
        assert compacted_count == 6  # 3 summary + 3 one-liner

    def test_zero_full_window_compacts_everything(self):
        config = MemoryConfig(
            graduated_full_window=0,
            graduated_summary_window=2,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        for i in range(3):
            content = _make_result_content(data=f"result {i}")
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        compacted_count = memory.graduated_compact()
        assert compacted_count == 3  # All get at least summary


class TestGraduatedCompactSkipsCompacted:
    """Already-compacted messages should be skipped."""

    def test_skips_already_compacted(self):
        config = MemoryConfig(
            graduated_full_window=0,
            graduated_summary_window=0,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        # Add a pre-compacted message
        memory.messages.append(_make_tool_message("shell_exec", "(compacted)", "tc-1"))
        # Add a normally compacted one
        memory.messages.append(_make_tool_message("file_read", "(removed)", "tc-2"))
        # Add a graduated-compacted one
        memory.messages.append(
            _make_tool_message(
                "browser_view",
                "[browser_view] (OK, graduated-compacted, 5000 chars)",
                "tc-3",
            )
        )
        # Add an externally stored one
        memory.messages.append(
            _make_tool_message(
                "shell_exec",
                '{"_stored_externally": true, "_result_ref": "trs-123"}',
                "tc-4",
            )
        )

        compacted_count = memory.graduated_compact()
        assert compacted_count == 0  # All already compacted


class TestGraduatedCompactPreserveRecent:
    """preserve_recent parameter should protect the last N messages."""

    def test_preserve_recent_skips_recent(self):
        config = MemoryConfig(
            graduated_full_window=0,
            graduated_summary_window=0,
            use_graduated_compaction=True,
            preserve_recent=3,
        )
        memory = Memory(config=config)

        original_contents = []
        for i in range(5):
            content = _make_result_content(data=f"result {i} " * 20)
            original_contents.append(content)
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        memory.graduated_compact()

        # Last 3 messages (indices 2,3,4) should be untouched due to preserve_recent
        assert memory.messages[2]["content"] == original_contents[2]
        assert memory.messages[3]["content"] == original_contents[3]
        assert memory.messages[4]["content"] == original_contents[4]


class TestGraduatedCompactTokenReduction:
    """Verify that graduated compaction actually reduces token count."""

    def test_reduces_estimated_tokens(self):
        config = MemoryConfig(
            graduated_full_window=2,
            graduated_summary_window=2,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        for i in range(10):
            content = _make_result_content(data="x" * 5000)
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        tokens_before = memory.estimate_tokens()
        memory.graduated_compact()
        tokens_after = memory.estimate_tokens()

        assert tokens_after < tokens_before
        # Should reduce significantly (at least 30%)
        reduction_pct = (tokens_before - tokens_after) / tokens_before
        assert reduction_pct > 0.3, f"Expected >30% reduction, got {reduction_pct:.1%}"


class TestGraduatedCompactReturnValue:
    """Return value should indicate number of compacted messages."""

    def test_returns_zero_for_empty(self):
        memory = Memory(config=MemoryConfig(use_graduated_compaction=True, preserve_recent=0))
        assert memory.graduated_compact() == 0

    def test_returns_zero_for_non_tool(self):
        memory = Memory(config=MemoryConfig(use_graduated_compaction=True, preserve_recent=0))
        memory.messages.append({"role": "user", "content": "hello"})
        memory.messages.append({"role": "assistant", "content": "hi"})
        assert memory.graduated_compact() == 0

    def test_returns_correct_count(self):
        config = MemoryConfig(
            graduated_full_window=1,
            graduated_summary_window=1,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        for i in range(4):
            content = _make_result_content(data=f"result {i}")
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        # rank 0 = full, rank 1 = summary, rank 2,3 = one-liner → 3 compacted
        assert memory.graduated_compact() == 3


class TestGraduatedCompactMixedMessages:
    """Non-tool messages should be preserved and not counted."""

    def test_preserves_non_tool_messages(self):
        config = MemoryConfig(
            graduated_full_window=0,
            graduated_summary_window=0,
            use_graduated_compaction=True,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        memory.messages.append({"role": "system", "content": "System prompt"})
        memory.messages.append({"role": "user", "content": "Hello"})
        memory.messages.append(_make_tool_message("shell_exec", _make_result_content(data="x" * 100), "tc-1"))
        memory.messages.append({"role": "assistant", "content": "Here's what I found"})

        memory.graduated_compact()

        assert memory.messages[0]["content"] == "System prompt"
        assert memory.messages[1]["content"] == "Hello"
        assert memory.messages[3]["content"] == "Here's what I found"


class TestAutoCompactRouting:
    """_check_auto_compact routes to graduated_compact when flag is set."""

    def test_auto_compact_uses_graduated_when_enabled(self):
        config = MemoryConfig(
            auto_compact_token_threshold=100,  # Very low threshold to trigger
            use_token_threshold=True,
            use_graduated_compaction=True,
            graduated_full_window=1,
            graduated_summary_window=1,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        # Add enough content to exceed 100 token threshold (25 chars/token)
        for i in range(5):
            content = _make_result_content(data="x" * 500)
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        # Trigger auto-compact
        memory._check_auto_compact()

        # Check that graduated compaction was used (one-liner markers)
        has_graduated_marker = any("graduated-compacted" in msg.get("content", "") for msg in memory.messages)
        assert has_graduated_marker

    def test_auto_compact_uses_smart_when_graduated_disabled(self):
        config = MemoryConfig(
            auto_compact_token_threshold=100,
            use_token_threshold=True,
            use_graduated_compaction=False,
            preserve_recent=0,
        )
        memory = Memory(config=config)

        for i in range(5):
            content = _make_result_content(data="x" * 500)
            memory.messages.append(_make_tool_message("shell_exec", content, f"tc-{i}"))

        memory._check_auto_compact()

        # Check that smart_compact was used (compacted markers)
        has_compacted_marker = any("(compacted)" in msg.get("content", "") for msg in memory.messages)
        assert has_compacted_marker


class TestDetectSuccess:
    """_detect_success heuristic."""

    def test_detects_success_true(self):
        assert Memory._detect_success('{"success": true, "data": "ok"}') is True

    def test_detects_success_false(self):
        assert Memory._detect_success('{"success": false, "message": "error"}') is False

    def test_detects_error_keywords(self):
        assert Memory._detect_success("Traceback (most recent call last)") is False

    def test_detects_neutral_as_success(self):
        assert Memory._detect_success("Some normal output data") is True


class TestIsAlreadyCompacted:
    """_is_already_compacted checks all compaction markers."""

    @pytest.mark.parametrize(
        "marker",
        [
            "(compacted)",
            "(removed)",
            "graduated-compacted",
            "_stored_externally",
        ],
    )
    def test_detects_marker(self, marker):
        assert Memory._is_already_compacted(f"some content with {marker} in it") is True

    def test_normal_content_not_compacted(self):
        assert Memory._is_already_compacted("normal tool output") is False
