"""
Tests for the stuck detector module.
"""

import pytest
from app.domain.services.agents.stuck_detector import StuckDetector, ResponseRecord


class TestResponseRecord:
    """Tests for ResponseRecord dataclass"""

    def test_create_record(self):
        """Test creating a response record"""
        record = ResponseRecord(
            content_hash="abc123",
            timestamp=None,
            tool_calls=["tool1"],
            content_preview="Test content"
        )
        assert record.content_hash == "abc123"
        assert record.tool_calls == ["tool1"]


class TestStuckDetector:
    """Tests for StuckDetector class"""

    def test_initialization(self):
        """Test detector initialization with custom parameters"""
        detector = StuckDetector(window_size=10, threshold=5)
        assert detector._window_size == 10
        assert detector._threshold == 5

    def test_not_stuck_initially(self):
        """Test detector is not stuck initially"""
        detector = StuckDetector()
        assert detector.is_stuck() is False

    def test_track_unique_responses(self):
        """Test tracking unique responses doesn't trigger stuck detection"""
        detector = StuckDetector(window_size=5, threshold=3)

        responses = [
            {"content": "Response 1", "role": "assistant"},
            {"content": "Response 2", "role": "assistant"},
            {"content": "Response 3", "role": "assistant"},
        ]

        for response in responses:
            is_stuck = detector.track_response(response)
            assert is_stuck is False

    def test_detect_stuck_identical_responses(self):
        """Test detection of identical responses"""
        detector = StuckDetector(window_size=5, threshold=3)

        identical_response = {"content": "I'm stuck in a loop", "role": "assistant"}

        # First two identical responses shouldn't trigger
        detector.track_response(identical_response)
        detector.track_response(identical_response)
        assert detector.is_stuck() is False

        # Third identical response should trigger
        is_stuck = detector.track_response(identical_response)
        assert is_stuck is True
        assert detector.is_stuck() is True

    def test_detect_stuck_with_tool_calls(self):
        """Test detection based on identical tool calls"""
        detector = StuckDetector(window_size=5, threshold=3)

        response_with_tool = {
            "content": "",
            "role": "assistant",
            "tool_calls": [{
                "function": {
                    "name": "shell_exec",
                    "arguments": '{"command": "ls"}'
                }
            }]
        }

        for _ in range(3):
            detector.track_response(response_with_tool)

        assert detector.is_stuck() is True

    def test_stuck_pattern_broken(self):
        """Test that different responses eventually break stuck pattern"""
        detector = StuckDetector(window_size=5, threshold=3)

        identical = {"content": "Same response", "role": "assistant"}
        different = {"content": "Different response", "role": "assistant"}

        # Get into stuck state
        for _ in range(3):
            detector.track_response(identical)
        assert detector.is_stuck() is True

        # Need enough different responses to push identical ones out of window
        # After adding different responses, the pattern should eventually break
        for i in range(3):
            detector.track_response({"content": f"Different {i}", "role": "assistant"})

        # Now the window has fewer than threshold identical responses
        assert detector.is_stuck() is False

    def test_can_attempt_recovery(self):
        """Test recovery attempt availability"""
        detector = StuckDetector()
        assert detector.can_attempt_recovery() is True

        # Use up recovery attempts
        for _ in range(3):
            detector.record_recovery_attempt()

        assert detector.can_attempt_recovery() is False

    def test_recovery_prompt_variations(self):
        """Test that recovery prompts vary by attempt"""
        detector = StuckDetector()

        prompt1 = detector.get_recovery_prompt()
        detector.record_recovery_attempt()

        prompt2 = detector.get_recovery_prompt()
        detector.record_recovery_attempt()

        prompt3 = detector.get_recovery_prompt()

        # Prompts should be different
        assert prompt1 != prompt2
        assert prompt2 != prompt3

    def test_reset(self):
        """Test detector reset"""
        detector = StuckDetector(window_size=5, threshold=3)

        # Get into stuck state
        identical = {"content": "Same", "role": "assistant"}
        for _ in range(3):
            detector.track_response(identical)

        detector.record_recovery_attempt()
        assert detector.is_stuck() is True
        assert detector._recovery_attempts == 1

        # Reset
        detector.reset()
        assert detector.is_stuck() is False
        assert detector._recovery_attempts == 0
        assert len(detector._response_history) == 0

    def test_get_stats(self):
        """Test getting detector statistics"""
        detector = StuckDetector(window_size=5, threshold=3)

        response = {"content": "Test", "role": "assistant"}
        detector.track_response(response)

        stats = detector.get_stats()
        assert stats["window_size"] == 5
        assert stats["threshold"] == 3
        assert stats["responses_tracked"] == 1
        assert stats["is_stuck"] is False

    def test_window_size_limit(self):
        """Test that response history respects window size"""
        detector = StuckDetector(window_size=3, threshold=2)

        for i in range(10):
            detector.track_response({"content": f"Response {i}", "role": "assistant"})

        # Should only keep last 3 responses
        assert len(detector._response_history) == 3
