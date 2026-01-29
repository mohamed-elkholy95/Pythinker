"""
Tests for the enhanced memory module.
"""

from app.domain.models.memory import Memory, MemoryConfig


class TestMemoryConfig:
    """Tests for MemoryConfig dataclass"""

    def test_default_initialization(self):
        """Test default config initialization"""
        config = MemoryConfig()
        assert config.max_messages == 100
        assert config.auto_compact_threshold == 50
        assert "browser_view" in config.compactable_functions
        assert "shell_exec" in config.compactable_functions

    def test_custom_initialization(self):
        """Test custom config initialization"""
        config = MemoryConfig(
            max_messages=50,
            auto_compact_threshold=25,
            compactable_functions=["custom_tool"]
        )
        assert config.max_messages == 50
        assert config.auto_compact_threshold == 25
        assert config.compactable_functions == ["custom_tool"]


class TestMemory:
    """Tests for enhanced Memory class"""

    def test_initialization(self):
        """Test memory initialization"""
        memory = Memory()
        assert memory.empty is True
        assert memory.messages == []

    def test_add_message(self):
        """Test adding a single message"""
        memory = Memory()
        memory.add_message({"role": "user", "content": "Hello"})

        assert memory.empty is False
        assert len(memory.messages) == 1

    def test_add_messages(self):
        """Test adding multiple messages"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ])

        assert len(memory.messages) == 2

    def test_get_messages(self):
        """Test getting all messages"""
        memory = Memory()
        memory.add_message({"role": "user", "content": "Test"})

        messages = memory.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "Test"

    def test_get_last_message(self):
        """Test getting last message"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"}
        ])

        last = memory.get_last_message()
        assert last["content"] == "Second"

    def test_get_last_message_empty(self):
        """Test getting last message from empty memory"""
        memory = Memory()
        assert memory.get_last_message() is None

    def test_roll_back(self):
        """Test rolling back last message"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"}
        ])

        memory.roll_back()
        assert len(memory.messages) == 1
        assert memory.messages[0]["content"] == "First"

    def test_compact_browser_tools(self):
        """Test legacy compact removes browser tool results"""
        memory = Memory()
        memory.add_messages([
            {"role": "tool", "function_name": "browser_view", "content": "Large content..."},
            {"role": "tool", "function_name": "shell_exec", "content": "Shell output"}
        ])

        memory.compact()

        # browser_view should be compacted
        assert "(removed)" in memory.messages[0]["content"]
        # shell_exec should not be affected by legacy compact
        assert "Shell output" in memory.messages[1]["content"]

    def test_smart_compact(self):
        """Test smart_compact compacts more tool types"""
        memory = Memory()
        memory.config.compactable_functions = ["browser_view", "shell_exec", "file_read"]

        memory.add_messages([
            {"role": "system", "content": "System prompt"},
            {"role": "tool", "function_name": "browser_view", "content": "Browser content"},
            {"role": "tool", "function_name": "shell_exec", "content": "Shell output"},
            {"role": "tool", "function_name": "file_read", "content": "File content"},
            {"role": "user", "content": "Recent message"}  # Should be preserved
        ])

        # Smart compact with preserve_recent=1
        compacted = memory.smart_compact(preserve_recent=1)

        # Should have compacted browser, shell, and file tools
        assert compacted == 3
        assert "(compacted)" in memory.messages[1]["content"]
        assert "(compacted)" in memory.messages[2]["content"]
        assert "(compacted)" in memory.messages[3]["content"]
        # Recent message should be preserved
        assert memory.messages[4]["content"] == "Recent message"

    def test_smart_compact_preserves_recent(self):
        """Test smart_compact preserves recent messages"""
        memory = Memory()
        memory.config.compactable_functions = ["shell_exec"]

        # Add many messages
        for i in range(10):
            memory.add_message({"role": "tool", "function_name": "shell_exec", "content": f"Output {i}"})

        # Compact with preserve_recent=3
        memory.smart_compact(preserve_recent=3)

        # Last 3 should not be compacted
        assert "(compacted)" not in memory.messages[7]["content"]
        assert "(compacted)" not in memory.messages[8]["content"]
        assert "(compacted)" not in memory.messages[9]["content"]

    def test_smart_compact_skips_already_compacted(self):
        """Test smart_compact doesn't re-compact already compacted messages"""
        memory = Memory()
        memory.config.compactable_functions = ["shell_exec"]

        memory.add_message({
            "role": "tool",
            "function_name": "shell_exec",
            "content": '{"success": true, "data": "(compacted)"}'
        })

        compacted = memory.smart_compact(preserve_recent=0)
        assert compacted == 0

    def test_estimate_tokens(self):
        """Test token estimation"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there, how can I help?"}
        ])

        tokens = memory.estimate_tokens()
        assert tokens > 0

    def test_estimate_tokens_empty(self):
        """Test token estimation on empty memory"""
        memory = Memory()
        tokens = memory.estimate_tokens()
        assert tokens == 0

    def test_get_stats(self):
        """Test getting memory statistics"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "tool", "function_name": "test", "content": "Result"}
        ])

        stats = memory.get_stats()

        assert stats["total_messages"] == 3
        assert stats["role_counts"]["user"] == 1
        assert stats["role_counts"]["assistant"] == 1
        assert stats["role_counts"]["tool"] == 1
        assert stats["estimated_tokens"] > 0

    def test_auto_compact_triggered(self):
        """Test auto-compaction is triggered at threshold.

        Must set use_token_threshold=False to use message-count based compaction,
        as the default behavior is token-based.
        """
        # Set low threshold and low preserve_recent so compaction actually happens
        # Must disable token-based threshold to use message count
        config = MemoryConfig(
            auto_compact_threshold=5,
            use_token_threshold=False,  # Use message count, not token count
            compactable_functions=["shell_exec"],
            preserve_recent=2  # Only preserve last 2 messages
        )
        memory = Memory(config=config)

        # Add messages beyond threshold to trigger auto-compact
        for i in range(6):
            memory.add_message({
                "role": "tool",
                "function_name": "shell_exec",
                "content": f"Long output {i}" * 100
            })

        # Auto-compact should have run on the 5th message (at threshold)
        # Messages 0-3 should be compacted, messages 4-5 preserved
        compacted_count = sum(1 for m in memory.messages if "(compacted)" in m.get("content", ""))
        assert compacted_count > 0

    def test_get_message_role(self):
        """Test getting message role"""
        memory = Memory()
        message = {"role": "user", "content": "Test"}

        assert memory.get_message_role(message) == "user"

    def test_empty_property(self):
        """Test empty property"""
        memory = Memory()
        assert memory.empty is True

        memory.add_message({"role": "user", "content": "Test"})
        assert memory.empty is False
