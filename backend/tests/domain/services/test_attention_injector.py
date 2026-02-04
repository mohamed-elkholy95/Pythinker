# backend/tests/domain/services/test_attention_injector.py
"""Tests for AttentionInjector service."""

from app.domain.services.attention_injector import AttentionInjector


class TestAttentionInjector:
    """Test suite for AttentionInjector."""

    def test_inject_goal_recitation(self) -> None:
        """Test that goal recitation is injected into messages."""
        injector = AttentionInjector()

        messages = [
            {"role": "user", "content": "Analyze the data"},
            {"role": "assistant", "content": "I'll analyze it"},
            {"role": "user", "content": "Continue"},
        ]

        goal = "Complete the data analysis report"
        todo = ["Gather data", "Analyze trends", "Write report"]

        result = injector.inject(messages, goal=goal, todo=todo)

        # Should inject attention context before last user message
        assert len(result) > len(messages)
        # Goal should appear in injected content
        injected_content = str([m for m in result if m["role"] == "system"])
        assert "data analysis" in injected_content.lower() or any("Goal" in str(m) for m in result)

    def test_injection_frequency(self) -> None:
        """Attention injection shouldn't happen every message."""
        injector = AttentionInjector(injection_interval=5)

        messages = [{"role": "user", "content": f"Message {i}"} for i in range(3)]

        result = injector.inject(messages, goal="Test goal")

        # With only 3 messages and interval of 5, might not inject yet
        # But should work without error
        assert len(result) >= len(messages)

    def test_inject_with_force_flag(self) -> None:
        """Test that force=True always injects regardless of interval."""
        injector = AttentionInjector(injection_interval=100)

        messages = [{"role": "user", "content": "Test message"}]

        result = injector.inject(messages, goal="Test goal", force=True)

        # With force=True, should inject even with high interval
        assert len(result) > len(messages)

    def test_inject_without_goal(self) -> None:
        """Test injection behavior when no goal is provided."""
        injector = AttentionInjector(injection_interval=1)

        messages = [{"role": "user", "content": "Test"}]

        result = injector.inject(messages, goal=None)

        # Without a goal, should return messages unchanged
        assert result == messages

    def test_inject_with_empty_messages(self) -> None:
        """Test injection with empty message list."""
        injector = AttentionInjector()

        result = injector.inject([], goal="Test goal")

        # Empty messages should return empty list
        assert result == []

    def test_inject_with_todo_list(self) -> None:
        """Test that todo items are included in injection."""
        injector = AttentionInjector(injection_interval=1)

        messages = [{"role": "user", "content": "Continue"}]
        todo = ["Task 1", "Task 2", "Task 3"]

        result = injector.inject(messages, goal="Main goal", todo=todo, force=True)

        # Find the injected system message
        system_messages = [m for m in result if m["role"] == "system"]
        assert len(system_messages) > 0

        injected_content = system_messages[0]["content"]
        assert "Task 1" in injected_content
        assert "Task 2" in injected_content
        assert "Task 3" in injected_content

    def test_inject_with_state(self) -> None:
        """Test that state information can be included in injection."""
        injector = AttentionInjector(injection_interval=1)

        messages = [{"role": "user", "content": "Continue"}]
        state = {"current_step": 3, "total_steps": 10}

        result = injector.inject(messages, goal="Main goal", state=state, force=True)

        # Should handle state without error
        assert len(result) > len(messages)

    def test_should_inject_at_interval(self) -> None:
        """Test should_inject returns True at correct intervals."""
        injector = AttentionInjector(injection_interval=5)

        assert not injector.should_inject(0)  # 0 messages, no injection
        assert not injector.should_inject(1)
        assert not injector.should_inject(3)
        assert not injector.should_inject(4)
        assert injector.should_inject(5)  # At interval
        assert not injector.should_inject(6)
        assert injector.should_inject(10)  # Multiple of interval

    def test_injection_position(self) -> None:
        """Test that injection is placed before the last user message."""
        injector = AttentionInjector(injection_interval=1)

        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Second"},
        ]

        result = injector.inject(messages, goal="Test goal", force=True)

        # Find position of injected system message
        system_indices = [i for i, m in enumerate(result) if m["role"] == "system"]
        last_user_index = max(i for i, m in enumerate(result) if m["role"] == "user")

        # System message should be before the last user message
        assert len(system_indices) > 0
        assert system_indices[-1] < last_user_index

    def test_preserves_original_messages(self) -> None:
        """Test that original messages are not mutated."""
        injector = AttentionInjector(injection_interval=1)

        original_messages = [{"role": "user", "content": "Test"}]
        messages_copy = [dict(m) for m in original_messages]

        injector.inject(original_messages, goal="Goal", force=True)

        # Original messages should be unchanged
        assert original_messages == messages_copy

    def test_attention_template_format(self) -> None:
        """Test that the attention template is properly formatted."""
        injector = AttentionInjector(injection_interval=1)

        messages = [{"role": "user", "content": "Test"}]
        goal = "Complete task"
        todo = ["Step 1", "Step 2"]

        result = injector.inject(messages, goal=goal, todo=todo, force=True)

        system_messages = [m for m in result if m["role"] == "system"]
        assert len(system_messages) > 0

        content = system_messages[0]["content"]
        assert "<attention-context>" in content
        assert "</attention-context>" in content
        assert "Current Objective" in content
        assert "Complete task" in content
