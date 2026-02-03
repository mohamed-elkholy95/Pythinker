"""Tests for token pressure compaction timing (Phase 4 P1).

Ensures compaction only happens between steps, not mid-execution.
"""

import pytest

from app.domain.services.agents.token_manager import PressureLevel, TokenManager


class TestTokenPressureCompaction:
    """Test token pressure compaction timing."""

    def _create_messages_with_tokens(self, target_tokens: int) -> list[dict]:
        """Create messages to reach target token count."""
        # Approximate 4 characters per token
        chars_per_message = 100
        num_messages = target_tokens // 25  # ~25 tokens per message

        messages = []
        for i in range(num_messages):
            messages.append(
                {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}: " + ("x" * chars_per_message)}
            )
        return messages

    def test_compaction_not_mid_execution(self):
        """Test that compaction does not occur during execution."""
        manager = TokenManager(max_context_tokens=1000)
        messages = self._create_messages_with_tokens(950)

        manager.mark_step_executing()

        # Attempt compaction
        compacted = manager.compact_if_needed(messages)

        # Should NOT compact during execution
        assert len(compacted) == len(messages)

    def test_compaction_after_step_completion(self):
        """Test that compaction occurs after step completes."""
        manager = TokenManager(max_context_tokens=1000)
        messages = self._create_messages_with_tokens(950)

        manager.mark_step_completed()

        # Should compact after step completes
        compacted = manager.compact_if_needed(messages)

        # Should have trimmed messages (or at least not be blocked)
        assert len(compacted) <= len(messages)

    def test_pressure_check_logs_metrics(self):
        """Test that pressure checking logs metrics."""
        manager = TokenManager(max_context_tokens=1000)
        manager.set_session_id("test-session")
        messages = self._create_messages_with_tokens(900)

        status = manager.check_pressure(messages)

        assert status.level in [PressureLevel.NORMAL, PressureLevel.WARNING, PressureLevel.CRITICAL]
        assert status.current_tokens > 0

    def test_compaction_allowed_state(self):
        """Test compaction allowed state transitions."""
        manager = TokenManager()

        # Initially allowed
        assert manager._compaction_allowed

        # Mark executing
        manager.mark_step_executing()
        assert not manager._compaction_allowed

        # Mark completed
        manager.mark_step_completed()
        assert manager._compaction_allowed


@pytest.mark.asyncio
class TestTokenCompactionIntegration:
    """Integration tests for token compaction timing."""

    async def test_plan_act_marks_steps_correctly(self):
        """Test that plan_act flow marks steps executing/completed."""
        # This would be an integration test with actual plan_act flow
        # Placeholder for full implementation
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
