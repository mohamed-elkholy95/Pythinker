"""
Tests for the token manager module.
"""

import logging

from app.domain.services.agents.token_manager import TokenCount, TokenManager


class TestTokenCount:
    """Tests for TokenCount dataclass"""

    def test_create_token_count(self):
        """Test creating a token count"""
        count = TokenCount(total=100, content_tokens=80, tool_tokens=16, overhead_tokens=4)
        assert count.total == 100
        assert count.content_tokens == 80


class TestTokenManager:
    """Tests for TokenManager class"""

    def test_initialization_default(self):
        """Test default initialization"""
        manager = TokenManager()
        assert manager._model_name == "gpt-4"
        assert manager._max_tokens > 0

    def test_initialization_custom_model(self):
        """Test initialization with custom model"""
        manager = TokenManager(model_name="gpt-4-turbo")
        assert manager._model_name == "gpt-4-turbo"

    def test_count_tokens_empty(self):
        """Test counting tokens in empty string"""
        manager = TokenManager()
        count = manager.count_tokens("")
        assert count == 0

    def test_count_tokens_basic(self):
        """Test counting tokens in basic text"""
        manager = TokenManager()
        count = manager.count_tokens("Hello, world!")
        assert count > 0

    def test_count_message_tokens(self):
        """Test counting tokens in a message"""
        manager = TokenManager()
        message = {"role": "user", "content": "This is a test message with some content."}
        count = manager.count_message_tokens(message)

        assert count.total > 0
        assert count.content_tokens > 0
        assert count.overhead_tokens == 4  # MESSAGE_OVERHEAD

    def test_count_message_tokens_with_tool_calls(self):
        """Test counting tokens in a message with tool calls"""
        manager = TokenManager()
        message = {
            "role": "assistant",
            "content": "Let me execute that.",
            "tool_calls": [{"function": {"name": "shell_exec", "arguments": '{"command": "ls -la"}'}}],
        }
        count = manager.count_message_tokens(message)

        assert count.total > 0
        assert count.tool_tokens > 0

    def test_count_messages_tokens(self):
        """Test counting tokens across multiple messages"""
        manager = TokenManager()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        total = manager.count_messages_tokens(messages)

        assert total > 0

    def test_is_within_limit_true(self):
        """Test checking within limit with small context"""
        manager = TokenManager(max_context_tokens=8192)
        messages = [{"role": "user", "content": "Hello"}]
        assert manager.is_within_limit(messages) is True

    def test_is_within_limit_false(self):
        """Test checking within limit with large context"""
        manager = TokenManager(max_context_tokens=100, safety_margin=0)
        # Create a message that's definitely too long
        long_content = "word " * 1000
        messages = [{"role": "user", "content": long_content}]
        assert manager.is_within_limit(messages) is False

    def test_trim_messages_preserves_system(self):
        """Test that trimming preserves system messages"""
        manager = TokenManager(max_context_tokens=200, safety_margin=50)
        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Message " * 100},
            {"role": "assistant", "content": "Response " * 100},
            {"role": "user", "content": "Recent message"},
        ]

        trimmed, tokens_removed = manager.trim_messages(messages, preserve_system=True, preserve_recent=1)

        # System message should be preserved
        assert trimmed[0]["role"] == "system"
        assert tokens_removed > 0

    def test_trim_messages_preserves_recent(self):
        """Test that trimming preserves recent messages"""
        manager = TokenManager(max_context_tokens=200, safety_margin=50)
        messages = [
            {"role": "system", "content": "System."},
            {"role": "user", "content": "Old message " * 50},
            {"role": "assistant", "content": "Old response " * 50},
            {"role": "user", "content": "Recent question"},
            {"role": "assistant", "content": "Recent answer"},
        ]

        trimmed, _ = manager.trim_messages(messages, preserve_system=True, preserve_recent=2)

        # Check recent messages are preserved
        assert trimmed[-1]["content"] == "Recent answer"
        assert trimmed[-2]["content"] == "Recent question"

    def test_trim_messages_no_change_needed(self):
        """Test trimming when already within limit"""
        manager = TokenManager(max_context_tokens=10000)
        messages = [{"role": "user", "content": "Short message"}]

        trimmed, tokens_removed = manager.trim_messages(messages)

        assert len(trimmed) == 1
        assert tokens_removed == 0

    def test_estimate_response_tokens(self):
        """Test estimating available response tokens"""
        manager = TokenManager(max_context_tokens=8192)

        available = manager.estimate_response_tokens(prompt_tokens=1000)
        assert available > 0
        assert available < 8192

    def test_get_stats(self):
        """Test getting manager statistics"""
        manager = TokenManager(model_name="gpt-4-turbo")
        stats = manager.get_stats()

        assert stats["model"] == "gpt-4-turbo"
        assert "max_tokens" in stats
        assert "effective_limit" in stats
        assert "tiktoken_available" in stats

    def test_trim_messages_reduces_preserve_recent_when_over_limit(self):
        """Test that trimming reduces preserve_recent when system + recent exceeds limit.

        This tests the fix for the bug where available_tokens became negative,
        causing the loop to never keep any trimmable groups (trimmed 0 messages).
        """
        # Create a very small context limit
        manager = TokenManager(max_context_tokens=100, safety_margin=20)  # effective = 80

        # Create messages where system + recent would exceed the effective limit
        messages = [
            {"role": "system", "content": "System prompt."},  # ~4 tokens
            {"role": "user", "content": "Old message " * 20},  # ~40 tokens
            {"role": "assistant", "content": "Old response " * 20},  # ~40 tokens
            {"role": "user", "content": "Recent question with lots of content " * 10},  # ~50+ tokens
            {"role": "assistant", "content": "Recent answer with lots of content " * 10},  # ~50+ tokens
        ]

        # With preserve_recent=4, trying to keep 4 recent messages would exceed limit
        trimmed, tokens_removed = manager.trim_messages(messages, preserve_system=True, preserve_recent=4)

        # The fix should have:
        # 1. Reduced preserve_recent dynamically to fit
        # 2. Actually trimmed some messages (tokens_removed > 0)
        assert tokens_removed > 0, "Should have trimmed some tokens"
        assert len(trimmed) < len(messages), "Should have trimmed some messages"

        # System message should always be preserved
        assert trimmed[0]["role"] == "system"

    def test_trim_messages_handles_huge_system_prompt(self):
        """Test trimming when system prompt alone exceeds limit."""
        # Create a manager with very small limit
        manager = TokenManager(max_context_tokens=50, safety_margin=10)  # effective = 40

        # System prompt that exceeds the entire limit
        messages = [
            {"role": "system", "content": "This is a very long system prompt " * 50},
            {"role": "user", "content": "Hello"},
        ]

        trimmed, tokens_removed = manager.trim_messages(messages, preserve_system=True, preserve_recent=1)

        # Should keep system message even if over limit (can't do much else)
        assert trimmed[0]["role"] == "system"
        # Should have removed the user message
        assert tokens_removed > 0

    def test_trim_messages_limits_warning_churn_on_repeated_overflow(self, caplog):
        """Compaction should emit bounded warnings even when preserve_recent is reduced repeatedly."""
        manager = TokenManager(max_context_tokens=120, safety_margin=20)  # effective = 100
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Old context " * 60},
            {"role": "assistant", "content": "Old response " * 60},
            {"role": "user", "content": "Recent context A " * 60},
            {"role": "assistant", "content": "Recent context B " * 60},
            {"role": "user", "content": "Recent context C " * 60},
        ]

        with caplog.at_level(logging.WARNING):
            _trimmed, _removed = manager.trim_messages(messages, preserve_system=True, preserve_recent=5)

        reduction_warnings = [
            record.message
            for record in caplog.records
            if "Reducing preserve_recent" in record.message
            or "Reduced preserve_recent" in record.message
        ]
        assert len(reduction_warnings) <= 1

    def test_trim_messages_preserves_recent_tool_pairs_when_compacting(self):
        """If a tool response is retained, its assistant tool_call should remain in context."""
        manager = TokenManager(max_context_tokens=220, safety_margin=40)  # effective = 180
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Old context " * 80},
            {"role": "assistant", "content": "Old answer " * 80},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_recent",
                        "type": "function",
                        "function": {"name": "info_search_web", "arguments": '{"query":"recent"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_recent", "name": "info_search_web", "content": '{"ok":true}'},
            {"role": "assistant", "content": "Final response"},
        ]

        trimmed, _removed = manager.trim_messages(messages, preserve_system=True, preserve_recent=2)

        retained_tool_ids = {msg.get("tool_call_id") for msg in trimmed if msg.get("role") == "tool"}
        assistant_tool_ids = {
            tc.get("id")
            for msg in trimmed
            if msg.get("role") == "assistant" and msg.get("tool_calls")
            for tc in msg.get("tool_calls", [])
        }
        assert retained_tool_ids.issubset(assistant_tool_ids)
