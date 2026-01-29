"""
Tests for the token manager module.
"""

from app.domain.services.agents.token_manager import TokenCount, TokenManager


class TestTokenCount:
    """Tests for TokenCount dataclass"""

    def test_create_token_count(self):
        """Test creating a token count"""
        count = TokenCount(
            total=100,
            content_tokens=80,
            tool_tokens=16,
            overhead_tokens=4
        )
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
        message = {
            "role": "user",
            "content": "This is a test message with some content."
        }
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
            "tool_calls": [{
                "function": {
                    "name": "shell_exec",
                    "arguments": '{"command": "ls -la"}'
                }
            }]
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
            {"role": "assistant", "content": "Hi there!"}
        ]
        total = manager.count_messages_tokens(messages)

        assert total > 0

    def test_is_within_limit_true(self):
        """Test checking within limit with small context"""
        manager = TokenManager(max_context_tokens=8192)
        messages = [
            {"role": "user", "content": "Hello"}
        ]
        assert manager.is_within_limit(messages) is True

    def test_is_within_limit_false(self):
        """Test checking within limit with large context"""
        manager = TokenManager(max_context_tokens=100, safety_margin=0)
        # Create a message that's definitely too long
        long_content = "word " * 1000
        messages = [
            {"role": "user", "content": long_content}
        ]
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

        trimmed, tokens_removed = manager.trim_messages(
            messages,
            preserve_system=True,
            preserve_recent=1
        )

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

        trimmed, _ = manager.trim_messages(
            messages,
            preserve_system=True,
            preserve_recent=2
        )

        # Check recent messages are preserved
        assert trimmed[-1]["content"] == "Recent answer"
        assert trimmed[-2]["content"] == "Recent question"

    def test_trim_messages_no_change_needed(self):
        """Test trimming when already within limit"""
        manager = TokenManager(max_context_tokens=10000)
        messages = [
            {"role": "user", "content": "Short message"}
        ]

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
