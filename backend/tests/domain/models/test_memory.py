"""Tests for memory module — MemoryConfig, ConversationMemory.

Covers:
  - MemoryConfig: defaults, compactable_functions
  - ConversationMemory: add_message, add_messages, get_messages, get_last_message,
    roll_back, smart_compact, graduated_compact, estimate_tokens,
    _is_already_compacted, _detect_success, _build_summary_tier, _build_oneliner_tier
"""

from __future__ import annotations

from app.domain.models.memory import ConversationMemory, MemoryConfig

# ---------------------------------------------------------------------------
# MemoryConfig
# ---------------------------------------------------------------------------


class TestMemoryConfig:
    """MemoryConfig defaults and initialization."""

    def test_defaults(self) -> None:
        cfg = MemoryConfig()
        assert cfg.max_messages == 100
        assert cfg.auto_compact_threshold == 50
        assert cfg.auto_compact_token_threshold == 60000
        assert cfg.use_token_threshold is True
        assert cfg.preserve_recent == 8
        assert cfg.use_graduated_compaction is False

    def test_compactable_functions_populated(self) -> None:
        cfg = MemoryConfig()
        assert "browser_view" in cfg.compactable_functions
        assert "file_read" in cfg.compactable_functions
        assert "shell_exec" in cfg.compactable_functions

    def test_custom_compactable_functions(self) -> None:
        cfg = MemoryConfig(compactable_functions=["custom_tool"])
        assert cfg.compactable_functions == ["custom_tool"]

    def test_graduated_defaults(self) -> None:
        cfg = MemoryConfig()
        assert cfg.graduated_full_window == 5
        assert cfg.graduated_summary_window == 10


# ---------------------------------------------------------------------------
# ConversationMemory — basic operations
# ---------------------------------------------------------------------------


class TestConversationMemoryBasic:
    """ConversationMemory basic message operations."""

    def test_empty_initially(self) -> None:
        mem = ConversationMemory()
        assert mem.get_messages() == []
        assert mem.get_last_message() is None

    def test_add_message(self) -> None:
        mem = ConversationMemory()
        mem.add_message({"role": "user", "content": "hello"})
        assert len(mem.get_messages()) == 1

    def test_add_messages(self) -> None:
        mem = ConversationMemory()
        mem.add_messages(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
        )
        assert len(mem.get_messages()) == 2

    def test_get_last_message(self) -> None:
        mem = ConversationMemory()
        mem.add_message({"role": "user", "content": "first"})
        mem.add_message({"role": "assistant", "content": "second"})
        assert mem.get_last_message()["content"] == "second"

    def test_get_message_role(self) -> None:
        mem = ConversationMemory()
        msg = {"role": "user", "content": "x"}
        assert mem.get_message_role(msg) == "user"

    def test_roll_back(self) -> None:
        mem = ConversationMemory()
        mem.add_message({"role": "user", "content": "first"})
        mem.add_message({"role": "assistant", "content": "second"})
        mem.roll_back()
        assert len(mem.get_messages()) == 1
        assert mem.get_last_message()["content"] == "first"


# ---------------------------------------------------------------------------
# ConversationMemory — smart_compact
# ---------------------------------------------------------------------------


class TestSmartCompact:
    """ConversationMemory.smart_compact."""

    def test_compacts_old_tool_messages(self) -> None:
        cfg = MemoryConfig(use_token_threshold=False, auto_compact_threshold=9999, preserve_recent=2)
        mem = ConversationMemory(config=cfg)
        # Add tool messages followed by recent messages
        mem.messages = [
            {"role": "tool", "function_name": "browser_view", "content": "x" * 500},
            {"role": "tool", "function_name": "file_read", "content": "y" * 500},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent2"},
        ]
        count = mem.smart_compact(preserve_recent=2)
        assert count == 2
        assert "(compacted)" in mem.messages[0]["content"]
        assert "(compacted)" in mem.messages[1]["content"]

    def test_preserves_recent_messages(self) -> None:
        cfg = MemoryConfig(use_token_threshold=False, auto_compact_threshold=9999, preserve_recent=4)
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "tool", "function_name": "file_read", "content": "data1"},
            {"role": "tool", "function_name": "file_read", "content": "data2"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent2"},
        ]
        count = mem.smart_compact(preserve_recent=4)
        assert count == 0  # All within preserve window

    def test_does_not_compact_non_tool(self) -> None:
        cfg = MemoryConfig(use_token_threshold=False, preserve_recent=1)
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "user", "content": "important"},
            {"role": "assistant", "content": "also important"},
            {"role": "user", "content": "recent"},
        ]
        count = mem.smart_compact(preserve_recent=1)
        assert count == 0

    def test_truncates_large_non_compactable_tool(self) -> None:
        cfg = MemoryConfig(use_token_threshold=False, preserve_recent=1)
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "tool", "function_name": "unknown_tool", "content": "x" * 10000},
            {"role": "user", "content": "recent"},
        ]
        count = mem.smart_compact(preserve_recent=1)
        assert count == 1
        assert "truncated" in mem.messages[0]["content"]

    def test_does_not_double_compact(self) -> None:
        cfg = MemoryConfig(use_token_threshold=False, preserve_recent=1)
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "tool", "function_name": "browser_view", "content": "(compacted)"},
            {"role": "user", "content": "recent"},
        ]
        count = mem.smart_compact(preserve_recent=1)
        assert count == 0


# ---------------------------------------------------------------------------
# ConversationMemory — graduated_compact
# ---------------------------------------------------------------------------


class TestGraduatedCompact:
    """ConversationMemory.graduated_compact."""

    def test_graduated_tiers(self) -> None:
        cfg = MemoryConfig(
            use_token_threshold=False,
            graduated_full_window=1,
            graduated_summary_window=1,
            preserve_recent=1,
        )
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "tool", "function_name": "file_read", "content": "oldest data " * 100},
            {"role": "tool", "function_name": "file_read", "content": "middle data " * 100},
            {"role": "tool", "function_name": "file_read", "content": "newest data " * 100},
            {"role": "user", "content": "recent"},
        ]
        count = mem.graduated_compact(preserve_recent=1)
        # newest tool (rank 0) → full (kept), middle (rank 1) → summary, oldest (rank 2) → oneliner
        assert count == 2
        assert "graduated-compacted" in mem.messages[0]["content"]  # Oldest → oneliner
        assert "graduated-compacted" in mem.messages[1]["content"]  # Middle → summary

    def test_graduated_no_tools(self) -> None:
        cfg = MemoryConfig()
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        count = mem.graduated_compact()
        assert count == 0

    def test_graduated_skips_already_compacted(self) -> None:
        cfg = MemoryConfig(graduated_full_window=0, graduated_summary_window=0, preserve_recent=1)
        mem = ConversationMemory(config=cfg)
        mem.messages = [
            {"role": "tool", "function_name": "file_read", "content": "(compacted)"},
            {"role": "user", "content": "recent"},
        ]
        count = mem.graduated_compact(preserve_recent=1)
        assert count == 0


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------


class TestStaticHelpers:
    """ConversationMemory static helper methods."""

    def test_is_already_compacted_true(self) -> None:
        assert ConversationMemory._is_already_compacted("(compacted) data") is True
        assert ConversationMemory._is_already_compacted("(removed) data") is True
        assert ConversationMemory._is_already_compacted("graduated-compacted, 500 chars") is True
        assert ConversationMemory._is_already_compacted("_stored_externally") is True

    def test_is_already_compacted_false(self) -> None:
        assert ConversationMemory._is_already_compacted("normal content") is False
        assert ConversationMemory._is_already_compacted("") is False

    def test_detect_success_true(self) -> None:
        assert ConversationMemory._detect_success('{"success": true, "data": "ok"}') is True
        assert ConversationMemory._detect_success('{"success":true}') is True

    def test_detect_success_false(self) -> None:
        assert ConversationMemory._detect_success('{"success": false}') is False
        assert ConversationMemory._detect_success('{"success":false}') is False

    def test_detect_success_heuristic_error(self) -> None:
        assert ConversationMemory._detect_success("Error: connection refused") is False
        assert ConversationMemory._detect_success("Command failed with exit code 1") is False

    def test_detect_success_heuristic_ok(self) -> None:
        assert ConversationMemory._detect_success("Here is the file content") is True

    def test_build_summary_tier(self) -> None:
        summary = ConversationMemory._build_summary_tier("file_read", "content " * 100)
        assert "file_read" in summary
        assert "graduated-compacted" in summary
        assert "OK" in summary or "FAILED" in summary

    def test_build_oneliner_tier(self) -> None:
        oneliner = ConversationMemory._build_oneliner_tier("browser_view", "x" * 5000)
        assert "browser_view" in oneliner
        assert "graduated-compacted" in oneliner
        assert "5000 chars" in oneliner
