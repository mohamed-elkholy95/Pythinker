"""
Unit tests for ToolEfficiencyMonitor (Analysis Paralysis Detection).

Tests core functionality:
- Initialization with correct parameters
- Tool categorization (READ vs ACTION)
- Consecutive read tracking
- Two-tier threshold detection
- State reset
- Singleton factory
"""

from app.domain.services.agents.tool_efficiency_monitor import (
    EfficiencySignal,
    ToolEfficiencyMonitor,
    get_efficiency_monitor,
)

# ============================================================================
# Test Class 1: EfficiencySignal Structure
# ============================================================================


class TestEfficiencySignalStructure:
    """Test EfficiencySignal dataclass."""

    def test_signal_balanced(self):
        """Balanced signal should have correct structure."""
        signal = EfficiencySignal(
            is_balanced=True,
            read_count=3,
            action_count=2,
            nudge_message=None,
            confidence=1.0,
        )
        assert signal.is_balanced is True
        assert signal.read_count == 3
        assert signal.action_count == 2

    def test_signal_unbalanced(self):
        """Unbalanced signal should have nudge message."""
        signal = EfficiencySignal(
            is_balanced=False,
            read_count=5,
            action_count=0,
            nudge_message="Take action",
            confidence=0.75,
        )
        assert signal.is_balanced is False
        assert signal.nudge_message is not None


# ============================================================================
# Test Class 2: Monitor Initialization
# ============================================================================


class TestMonitorInitialization:
    """Test ToolEfficiencyMonitor initialization."""

    def test_init_with_defaults(self):
        """Monitor should initialize with default parameters."""
        monitor = ToolEfficiencyMonitor()
        assert monitor.window_size == 10
        assert monitor.read_threshold == 5
        assert monitor.strong_threshold == 6
        assert monitor._consecutive_reads == 0

    def test_init_with_custom_params(self):
        """Monitor should accept custom parameters."""
        monitor = ToolEfficiencyMonitor(
            window_size=20,
            read_threshold=3,
            strong_threshold=7,
        )
        assert monitor.window_size == 20
        assert monitor.read_threshold == 3
        assert monitor.strong_threshold == 7


# ============================================================================
# Test Class 3: Tool Categorization
# ============================================================================


class TestToolCategorization:
    """Test tool categorization logic."""

    def test_read_tools_identified(self):
        """Known read tools should be identified."""
        monitor = ToolEfficiencyMonitor()
        read_tools = ["file_read", "file_list", "file_find_by_name", "browser_view", "info_search_web"]
        for tool in read_tools:
            assert monitor._is_read_tool(tool) is True

    def test_action_tools_identified(self):
        """Known action tools should be identified."""
        monitor = ToolEfficiencyMonitor()
        action_tools = ["file_write", "browser_click", "code_execute"]
        for tool in action_tools:
            assert monitor._is_action_tool(tool) is True

    def test_unknown_tool_neither(self):
        """Unknown tools should be neither read nor action."""
        monitor = ToolEfficiencyMonitor()
        assert monitor._is_read_tool("unknown_tool") is False
        assert monitor._is_action_tool("unknown_tool") is False


# ============================================================================
# Test Class 4: Consecutive Read Tracking
# ============================================================================


class TestConsecutiveReadTracking:
    """Test consecutive read counter."""

    def test_record_increments_counter(self):
        """Recording read tools should increment counter."""
        monitor = ToolEfficiencyMonitor()
        assert monitor._consecutive_reads == 0

        monitor.record("file_read")
        assert monitor._consecutive_reads == 1

        monitor.record("browser_view")
        assert monitor._consecutive_reads == 2

    def test_record_resets_on_action(self):
        """Recording action tools should reset counter."""
        monitor = ToolEfficiencyMonitor()
        monitor.record("file_read")
        monitor.record("file_read")
        assert monitor._consecutive_reads == 2

        monitor.record("file_write")
        assert monitor._consecutive_reads == 0


# ============================================================================
# Test Class 5: Threshold Detection
# ============================================================================


class TestThresholdDetection:
    """Test soft and strong threshold detection."""

    def test_balanced_below_threshold(self):
        """Below threshold should return balanced signal."""
        monitor = ToolEfficiencyMonitor(read_threshold=5)
        monitor.record("file_read")
        monitor.record("file_read")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is True
        assert signal.nudge_message is None

    def test_soft_threshold_triggered(self):
        """At read_threshold should return soft nudge."""
        # same_tool_threshold set above the loop count to isolate read-balance detection
        monitor = ToolEfficiencyMonitor(read_threshold=5, strong_threshold=10, same_tool_threshold=20)
        for _ in range(5):
            monitor.record("file_read")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert "⚠️ STOP SEARCHING" in signal.nudge_message
        assert signal.hard_stop is False
        assert signal.confidence == 0.75

    def test_strong_threshold_triggered(self):
        """At strong_threshold should return hard-stop nudge."""
        # same_tool_threshold set above the loop count to isolate read-balance detection
        monitor = ToolEfficiencyMonitor(read_threshold=5, strong_threshold=10, same_tool_threshold=20)
        for _ in range(10):
            monitor.record("file_read")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert "⛔ HARD STOP" in signal.nudge_message
        assert signal.hard_stop is True
        assert signal.confidence == 0.95


# ============================================================================
# Test Class 6: State Reset
# ============================================================================


class TestStateReset:
    """Test reset method."""

    def test_reset_clears_counter(self):
        """Reset should clear consecutive read counter."""
        monitor = ToolEfficiencyMonitor()
        monitor.record("file_read")
        monitor.record("file_read")
        assert monitor._consecutive_reads == 2

        monitor.reset()
        assert monitor._consecutive_reads == 0

    def test_reset_clears_window(self):
        """Reset should clear recent tools window."""
        monitor = ToolEfficiencyMonitor()
        for _ in range(5):
            monitor.record("file_read")
        assert len(monitor._recent_tools) == 5

        monitor.reset()
        assert len(monitor._recent_tools) == 0


# ============================================================================
# Test Class 7: Singleton Factory
# ============================================================================


class TestSingletonFactory:
    """Test get_efficiency_monitor singleton."""

    def test_singleton_returns_same_instance(self):
        """Should return same instance on multiple calls."""
        # Clear singleton
        import app.domain.services.agents.tool_efficiency_monitor as module

        module._efficiency_monitor = None

        monitor1 = get_efficiency_monitor()
        monitor2 = get_efficiency_monitor()

        assert monitor1 is monitor2


# ============================================================================
# Test Class 8: Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for full workflow."""

    def test_normal_workflow_no_nudge(self):
        """Normal workflow should not trigger nudges."""
        monitor = ToolEfficiencyMonitor(read_threshold=5)

        # Simulate normal workflow: read → read → write → read → write
        monitor.record("file_read")
        monitor.record("file_read")
        monitor.record("file_write")
        monitor.record("file_read")
        monitor.record("file_write")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is True

    def test_paralysis_workflow_triggers_nudge(self):
        """Analysis paralysis workflow should trigger nudge."""
        monitor = ToolEfficiencyMonitor(read_threshold=5)

        # Simulate paralysis: 5 consecutive reads
        for _ in range(5):
            monitor.record("file_read")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert signal.nudge_message is not None

    def test_recovery_after_action(self):
        """Action after nudge should reset state."""
        monitor = ToolEfficiencyMonitor(read_threshold=5)

        # Trigger nudge
        for _ in range(5):
            monitor.record("file_read")
        signal = monitor.check_efficiency()
        assert signal.is_balanced is False

        # Take action
        monitor.record("file_write")
        signal = monitor.check_efficiency()
        assert signal.is_balanced is True


# ============================================================================
# Test Class 9: Repetitive Same-Tool Detection
# ============================================================================


class TestRepetitiveSameToolDetection:
    """Test detection of consecutive identical tool calls."""

    def test_consecutive_same_action_tool_triggers_nudge(self):
        """4+ consecutive calls to the same action tool should trigger nudge."""
        monitor = ToolEfficiencyMonitor(
            read_threshold=10,
            strong_threshold=15,
            same_tool_threshold=4,
            same_tool_strong_threshold=6,
        )
        for _ in range(4):
            monitor.record("code_execute_python")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert signal.nudge_message is not None
        assert signal.hard_stop is False
        assert signal.signal_type == "repetitive_tool"
        assert "code_execute_python" in signal.nudge_message

    def test_consecutive_same_tool_hard_stop(self):
        """6+ consecutive calls to the same tool should trigger hard stop."""
        monitor = ToolEfficiencyMonitor(
            same_tool_threshold=4,
            same_tool_strong_threshold=6,
        )
        for _ in range(6):
            monitor.record("code_execute_python")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is False
        assert signal.hard_stop is True
        assert signal.signal_type == "repetitive_tool"

    def test_second_repetitive_signal_escalates_to_hard_stop(self):
        """Second repetitive-tool trigger in same sequence should hard-stop."""
        monitor = ToolEfficiencyMonitor(
            same_tool_threshold=4,
            same_tool_strong_threshold=8,  # Keep strong threshold above second trigger.
        )

        for _ in range(4):
            monitor.record("code_execute_python")
        first_signal = monitor.check_efficiency()
        assert first_signal.hard_stop is False

        monitor.record("code_execute_python")
        second_signal = monitor.check_efficiency()
        assert second_signal.hard_stop is True
        assert second_signal.signal_type == "repetitive_tool"

    def test_different_tools_do_not_trigger(self):
        """Alternating tools should not trigger repetitive detection."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        monitor.record("code_execute_python")
        monitor.record("file_write")
        monitor.record("code_execute_python")
        monitor.record("file_write")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is True

    def test_exempt_tools_do_not_trigger(self):
        """Exempt tools (file_write) should not trigger repetitive detection."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        for _ in range(6):
            monitor.record("file_write")

        signal = monitor.check_efficiency()
        # file_write is exempt from repetitive detection — either balanced or non-repetitive signal type
        assert signal.signal_type != "repetitive_tool" or signal.is_balanced is True

    def test_switching_tool_resets_counter(self):
        """Switching to a different tool should reset the consecutive counter."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")
        # Switch tool — resets counter
        monitor.record("file_write")
        monitor.record("code_execute_python")

        signal = monitor.check_efficiency()
        assert signal.is_balanced is True

    def test_reset_clears_same_tool_tracking(self):
        """Reset should clear same-tool tracking state."""
        monitor = ToolEfficiencyMonitor(same_tool_threshold=4)
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")
        monitor.record("code_execute_python")

        monitor.reset()
        assert monitor._consecutive_same_tool == 0
        assert monitor._last_tool_name is None

    def test_research_mode_relaxes_same_tool_thresholds(self):
        """Research mode should relax same-tool thresholds."""
        monitor = ToolEfficiencyMonitor(
            same_tool_threshold=4,
            same_tool_strong_threshold=6,
            research_mode="deep_research",
        )
        # Research mode should increase thresholds
        assert monitor.same_tool_threshold >= 8
        assert monitor.same_tool_strong_threshold >= 10
