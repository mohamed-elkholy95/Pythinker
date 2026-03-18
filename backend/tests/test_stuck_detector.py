"""
Tests for the stuck detector module.
"""

from app.domain.services.agents.stuck_detector import (
    LoopType,
    ResponseRecord,
    StuckDetector,
)


class TestResponseRecord:
    """Tests for ResponseRecord dataclass"""

    def test_create_record(self):
        """Test creating a response record"""
        record = ResponseRecord(
            content_hash="abc123", timestamp=None, tool_calls=["tool1"], content_preview="Test content"
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
        # Disable semantic detection to test hash-based behavior only
        # (semantic detection can trigger on similarly-structured responses)
        detector = StuckDetector(window_size=5, threshold=3, enable_semantic=False)

        responses = [
            {"content": "Response 1", "role": "assistant"},
            {"content": "Response 2", "role": "assistant"},
            {"content": "Response 3", "role": "assistant"},
        ]

        for response in responses:
            is_stuck, _confidence = detector.track_response(response)
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
        is_stuck, _confidence = detector.track_response(identical_response)
        assert is_stuck is True
        assert detector.is_stuck() is True

    def test_detect_stuck_with_tool_calls(self):
        """Test detection based on identical tool calls"""
        detector = StuckDetector(window_size=5, threshold=3)

        response_with_tool = {
            "content": "",
            "role": "assistant",
            "tool_calls": [{"function": {"name": "shell_exec", "arguments": '{"command": "ls"}'}}],
        }

        for _ in range(3):
            detector.track_response(response_with_tool)

        assert detector.is_stuck() is True

    def test_stuck_pattern_broken(self):
        """Test that different responses eventually break stuck pattern.

        The StuckDetector uses both hash-based and semantic similarity detection.
        To properly break the pattern, we need responses that are distinct enough
        to not trigger semantic similarity (trigram-based embeddings).
        """
        # Disable semantic detection for this test to isolate hash-based behavior
        detector = StuckDetector(window_size=5, threshold=3, enable_semantic=False)

        identical = {"content": "Same response", "role": "assistant"}

        # Get into stuck state via hash matching
        for _ in range(3):
            detector.track_response(identical)
        assert detector.is_stuck() is True

        # Add different responses to break the hash-based pattern
        # With window_size=5 and threshold=3, we need to push out identical responses
        for i in range(3):
            detector.track_response({"content": f"Different response number {i}", "role": "assistant"})

        # Now the window has fewer than threshold identical responses
        assert detector.is_stuck() is False

    def test_can_attempt_recovery(self):
        """Test recovery attempt availability.

        StuckDetector has max_recovery_attempts=5.
        """
        detector = StuckDetector()
        assert detector.can_attempt_recovery() is True

        # Use up recovery attempts (max is 5)
        for _ in range(5):
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


class TestBrowserStuckPatterns:
    """Tests for browser-specific stuck pattern detection"""

    def test_detect_browser_same_page_loop(self):
        """Test detection of navigating to same URL repeatedly"""
        detector = StuckDetector()

        # Simulate repeated navigation to same URL
        same_url_args = {"url": "https://example.com/page"}
        for _ in range(4):
            analysis = detector.track_tool_action(
                tool_name="browser_navigate", tool_args=same_url_args, success=True, result="Page loaded"
            )

        # Should detect browser same page loop
        assert analysis is not None
        assert analysis.loop_type == LoopType.BROWSER_SAME_PAGE_LOOP

    def test_detect_browser_scroll_no_progress(self):
        """Test detection of scrolling without content extraction"""
        detector = StuckDetector()

        # Simulate repeated scrolling without browser_view
        for _ in range(5):
            analysis = detector.track_tool_action(
                tool_name="browser_scroll_down", tool_args={}, success=True, result="Scrolled down"
            )

        # Should detect scroll without progress
        assert analysis is not None
        assert analysis.loop_type == LoopType.BROWSER_SCROLL_NO_PROGRESS

    def test_detect_browser_click_failures(self):
        """Test detection of repeated click failures"""
        detector = StuckDetector()

        # Simulate repeated failed clicks on same element
        click_args = {"index": 5}
        for _ in range(4):
            analysis = detector.track_tool_action(
                tool_name="browser_click", tool_args=click_args, success=False, error="Element not found"
            )

        # Should detect click failures
        assert analysis is not None
        assert analysis.loop_type == LoopType.BROWSER_CLICK_FAILURES

    def test_no_detection_with_browser_view_between_scrolls(self):
        """Test that browser_view breaks scroll stuck pattern"""
        detector = StuckDetector()

        # Scroll, view, scroll, view - should not trigger
        for _ in range(3):
            detector.track_tool_action(tool_name="browser_scroll_down", tool_args={}, success=True, result="Scrolled")
            analysis = detector.track_tool_action(
                tool_name="browser_view", tool_args={}, success=True, result="Page content extracted"
            )

        # Should NOT detect stuck pattern
        assert analysis is None or analysis.loop_type != LoopType.BROWSER_SCROLL_NO_PROGRESS

    def test_different_urls_no_detection(self):
        """Test that navigating to different URLs doesn't trigger"""
        detector = StuckDetector()

        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
            "https://example.com/page4",
        ]

        for url in urls:
            analysis = detector.track_tool_action(
                tool_name="browser_navigate", tool_args={"url": url}, success=True, result="Page loaded"
            )

        # Should NOT detect same page loop
        assert analysis is None or analysis.loop_type != LoopType.BROWSER_SAME_PAGE_LOOP

    def test_excessive_same_tool_skips_distinct_successful_search_burst(self):
        """Distinct successful search queries should not trigger excessive-same-tool loop."""
        detector = StuckDetector()
        analysis = None
        for i in range(9):
            analysis = detector.track_tool_action(
                tool_name="search",
                tool_args={"query": f"topic variation {i}"},
                success=True,
                result=f"Result batch {i}",
            )
        assert analysis is None or analysis.loop_type != LoopType.EXCESSIVE_SAME_TOOL

    def test_excessive_same_tool_still_flags_repeated_search_with_same_args(self):
        """Repeated same-query search calls should continue to trigger detection."""
        detector = StuckDetector()
        analysis = None
        for _ in range(9):
            analysis = detector.track_tool_action(
                tool_name="search",
                tool_args={"query": "same query"},
                success=True,
                result="same result",
            )
        assert analysis is not None
        assert analysis.loop_type == LoopType.EXCESSIVE_SAME_TOOL

    def test_recovery_guidance_for_browser_patterns(self):
        """Test that browser patterns have proper recovery guidance"""
        detector = StuckDetector()

        # Trigger browser click failures
        for _ in range(4):
            detector.track_tool_action(
                tool_name="browser_click", tool_args={"index": 5}, success=False, error="Element not found"
            )

        guidance = detector.get_recovery_guidance()

        # Should contain browser-specific guidance
        assert "browser_view" in guidance.lower() or "element" in guidance.lower()
