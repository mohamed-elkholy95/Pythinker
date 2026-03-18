"""Tests for stuck detector confidence scoring (Phase 4 P1).

Ensures stuck detection uses confidence scoring to reduce false positives.
"""

import pytest

from app.domain.services.agents.stuck_detector import StuckDetector


class TestStuckDetectorConfidence:
    """Test stuck detector confidence scoring."""

    def test_confidence_scoring(self):
        """Test that stuck detection returns confidence score."""
        detector = StuckDetector(threshold=3, window_size=5)

        # Send different responses - should not be stuck
        responses = [
            {"content": "Response 1", "tool_calls": []},
            {"content": "Response 2", "tool_calls": []},
            {"content": "Response 3", "tool_calls": []},
        ]

        for response in responses:
            is_stuck, confidence = detector.track_response(response)
            assert not is_stuck
            assert 0.0 <= confidence <= 1.0

    def test_hash_match_confidence(self):
        """Test that identical responses have high confidence."""
        detector = StuckDetector(threshold=3, window_size=5)

        # Send identical responses - should be stuck with high confidence
        response = {"content": "Same response", "tool_calls": []}

        confidences = []
        for _ in range(4):
            is_stuck, confidence = detector.track_response(response)
            confidences.append(confidence)

        # Final check should be stuck with high confidence
        assert is_stuck
        assert confidence > 0.7

    def test_semantic_similarity_confidence(self):
        """Test that semantically similar responses increase confidence."""
        detector = StuckDetector(threshold=3, window_size=5, enable_semantic=True)

        # Similar but not identical responses
        responses = [
            {"content": "I need to check the error logs", "tool_calls": []},
            {"content": "Let me check the error logs", "tool_calls": []},
            {"content": "Checking the error logs again", "tool_calls": []},
            {"content": "I should check the error logs", "tool_calls": []},
        ]

        confidences = []
        for response in responses:
            _is_stuck, confidence = detector.track_response(response)
            confidences.append(confidence)

        # Should show increasing confidence
        assert confidences[-1] > confidences[0]

    def test_tool_action_pattern_confidence(self):
        """Test that repeated tool actions increase confidence."""
        detector = StuckDetector(threshold=3, window_size=5)

        # Track repeated failed tool actions
        for _ in range(3):
            detector.track_tool_action(
                tool_name="search",
                tool_args={"query": "abc123"},
                success=False,
                error="Not found",
            )

        # Confidence should be elevated due to tool pattern
        response = {"content": "Let me search again", "tool_calls": []}
        _is_stuck, confidence = detector.track_response(response)

        # Should detect stuck pattern or have elevated confidence
        assert confidence > 0.3

    def test_confidence_below_threshold(self):
        """Test that low confidence does not trigger stuck detection."""
        detector = StuckDetector(threshold=3, window_size=5)

        # Slightly similar but not enough for stuck detection
        responses = [
            {"content": "Response A", "tool_calls": []},
            {"content": "Response B", "tool_calls": []},
            {"content": "Response A modified", "tool_calls": []},
        ]

        for response in responses:
            is_stuck, _confidence = detector.track_response(response)

        # Should not be stuck
        assert not is_stuck


@pytest.mark.asyncio
class TestStuckDetectorIntegration:
    """Integration tests for stuck detector confidence."""

    async def test_base_agent_uses_confidence(self):
        """Test that base agent logs stuck detection confidence."""
        # This would be an integration test with actual base agent
        # Placeholder for full implementation
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
