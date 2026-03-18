"""Tests for enhanced reflection triggers."""

from app.domain.models.reflection import (
    ProgressMetrics,
    ReflectionDecision,
    ReflectionResult,
    ReflectionTrigger,
    ReflectionTriggerType,
    calculate_plan_divergence,
    detect_pattern_change,
)


class TestReflectionTriggerType:
    """Tests for enhanced trigger types."""

    def test_new_trigger_types_exist(self):
        """Test that new trigger types are defined."""
        assert ReflectionTriggerType.PLAN_DIVERGENCE.value == "plan_divergence"
        assert ReflectionTriggerType.PATTERN_CHANGE.value == "pattern_change"
        assert ReflectionTriggerType.CONFIDENCE_DECAY.value == "confidence_decay"
        assert ReflectionTriggerType.USER_REQUESTED.value == "user_requested"
        assert ReflectionTriggerType.QUALITY_DEGRADATION.value == "quality_degradation"


class TestReflectionTrigger:
    """Tests for enhanced ReflectionTrigger."""

    def test_default_config(self):
        """Test default configuration values."""
        trigger = ReflectionTrigger()

        assert trigger.detect_plan_divergence is True
        assert trigger.detect_pattern_change is True
        assert trigger.detect_confidence_decay is True
        assert trigger.confidence_decay_threshold == 0.15

    def test_record_confidence(self):
        """Test confidence history recording."""
        trigger = ReflectionTrigger()

        trigger.record_confidence(0.9)
        trigger.record_confidence(0.85)
        trigger.record_confidence(0.8)

        assert len(trigger._confidence_history) == 3
        assert trigger._confidence_history == [0.9, 0.85, 0.8]

    def test_confidence_history_limited(self):
        """Test that confidence history is limited to 10 values."""
        trigger = ReflectionTrigger()

        for i in range(15):
            trigger.record_confidence(0.5 + i * 0.01)

        assert len(trigger._confidence_history) == 10

    def test_detect_confidence_decay(self):
        """Test confidence decay detection."""
        trigger = ReflectionTrigger()

        # Simulate strongly declining confidence
        # Early: 0.95, 0.90, 0.85 avg = 0.9
        # Recent: 0.6, 0.5, 0.4 avg = 0.5
        # Decay = 0.4 > 0.15 threshold
        confidences = [0.95, 0.90, 0.85, 0.6, 0.5, 0.4]
        for c in confidences:
            trigger.record_confidence(c)

        assert trigger._detect_confidence_decay() is True

    def test_no_decay_with_stable_confidence(self):
        """Test no decay detected with stable confidence."""
        trigger = ReflectionTrigger()

        for _ in range(6):
            trigger.record_confidence(0.8)

        assert trigger._detect_confidence_decay() is False

    def test_no_decay_with_insufficient_history(self):
        """Test no decay with insufficient history."""
        trigger = ReflectionTrigger()

        trigger.record_confidence(0.9)
        trigger.record_confidence(0.5)

        assert trigger._detect_confidence_decay() is False

    def test_should_trigger_records_confidence(self):
        """Test that should_trigger records confidence."""
        trigger = ReflectionTrigger()

        trigger.should_trigger(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
            confidence=0.85,
        )

        assert 0.85 in trigger._confidence_history

    def test_should_trigger_enhanced_user_requested(self):
        """Test user requested trigger has highest priority."""
        trigger = ReflectionTrigger()

        result = trigger.should_trigger_enhanced(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
            user_requested=True,
        )

        assert result == ReflectionTriggerType.USER_REQUESTED

    def test_should_trigger_enhanced_plan_divergence(self):
        """Test plan divergence trigger."""
        trigger = ReflectionTrigger()

        result = trigger.should_trigger_enhanced(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
            plan_divergence=0.5,  # 50% divergence
        )

        assert result == ReflectionTriggerType.PLAN_DIVERGENCE

    def test_should_trigger_enhanced_pattern_change(self):
        """Test pattern change trigger."""
        trigger = ReflectionTrigger()

        result = trigger.should_trigger_enhanced(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
            pattern_change_detected=True,
        )

        assert result == ReflectionTriggerType.PATTERN_CHANGE

    def test_should_trigger_enhanced_falls_back_to_basic(self):
        """Test that enhanced trigger falls back to basic."""
        trigger = ReflectionTrigger()

        result = trigger.should_trigger_enhanced(
            steps_completed=2,
            error_count=0,
            total_attempts=2,
            # No enhanced triggers, but step_interval matches
        )

        assert result == ReflectionTriggerType.STEP_INTERVAL


class TestCalculatePlanDivergence:
    """Tests for plan divergence calculation."""

    def test_no_divergence_when_matching(self):
        """Test no divergence when execution matches plan."""
        planned_steps = ["Search for Python tutorials", "Browse the results"]
        executed_tools = ["search", "browser"]

        divergence = calculate_plan_divergence(planned_steps, executed_tools)

        assert divergence < 0.3

    def test_high_divergence_when_different(self):
        """Test high divergence when execution differs from plan."""
        planned_steps = ["Search for Python tutorials", "Browse the results"]
        executed_tools = ["shell", "shell", "file"]

        divergence = calculate_plan_divergence(planned_steps, executed_tools)

        assert divergence > 0.5

    def test_zero_divergence_with_empty_inputs(self):
        """Test zero divergence with empty inputs."""
        assert calculate_plan_divergence([], []) == 0.0
        assert calculate_plan_divergence(["Search for X"], []) == 0.0
        assert calculate_plan_divergence([], ["search"]) == 0.0

    def test_partial_divergence(self):
        """Test partial divergence calculation."""
        planned_steps = [
            "Search for info",
            "Browse the page",
            "Run the command",
        ]
        # Executed only search-related tools
        executed_tools = ["search", "search", "search"]

        divergence = calculate_plan_divergence(planned_steps, executed_tools)

        assert 0.3 < divergence < 0.8


class TestDetectPatternChange:
    """Tests for pattern change detection."""

    def test_no_change_with_consistent_pattern(self):
        """Test no change detected with consistent pattern."""
        tool_history = [
            "search",
            "browser",
            "search",
            "browser",
            "search",
            "browser",
            "search",
            "browser",
            "search",
            "browser",
        ]

        assert detect_pattern_change(tool_history) is False

    def test_detect_collapse_to_single_tool(self):
        """Test detection of collapse to single tool."""
        tool_history = [
            "search",
            "browser",
            "file",
            "shell",
            "code",  # Diverse early
            "search",
            "search",
            "search",
            "search",
            "search",  # Single tool later
        ]

        assert detect_pattern_change(tool_history) is True

    def test_detect_new_tools_appearing(self):
        """Test detection of new tools appearing."""
        tool_history = [
            "search",
            "search",
            "search",
            "search",
            "search",
            "browser",
            "shell",
            "file",
            "code",
            "mcp",  # All new tools
        ]

        assert detect_pattern_change(tool_history) is True

    def test_insufficient_history(self):
        """Test that insufficient history returns False."""
        tool_history = ["search", "browser", "file"]

        assert detect_pattern_change(tool_history) is False

    def test_custom_window_size(self):
        """Test with custom window size."""
        # Early window has diverse tools, recent has single tool
        tool_history = [
            "search",
            "browser",
            "file",  # Diverse early (3 tools)
            "search",
            "search",
            "search",  # Single tool (1 tool)
        ]

        # With window_size=3, should detect collapse to single tool
        assert detect_pattern_change(tool_history, window_size=3) is True


class TestReflectionResult:
    """Tests for enhanced ReflectionResult."""

    def test_is_high_confidence(self):
        """Test high confidence detection."""
        result = ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.9,
            progress_assessment="Good",
            summary="All good",
        )

        assert result.is_high_confidence is True

        result2 = ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.7,
            progress_assessment="OK",
            summary="OK",
        )

        assert result2.is_high_confidence is False

    def test_is_low_confidence(self):
        """Test low confidence detection."""
        result = ReflectionResult(
            decision=ReflectionDecision.REPLAN,
            confidence=0.4,
            progress_assessment="Issues",
            summary="Problems",
        )

        assert result.is_low_confidence is True

    def test_requires_action(self):
        """Test requires_action property."""
        continue_result = ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.9,
            progress_assessment="OK",
            summary="OK",
        )
        assert continue_result.requires_action is False

        replan_result = ReflectionResult(
            decision=ReflectionDecision.REPLAN,
            confidence=0.8,
            progress_assessment="Need change",
            summary="Replan",
        )
        assert replan_result.requires_action is True

    def test_should_override_low_confidence_replan(self):
        """Test should_override for low confidence decisions."""
        result = ReflectionResult(
            decision=ReflectionDecision.REPLAN,
            confidence=0.2,
            progress_assessment="Maybe replan",
            summary="Uncertain",
        )

        assert result.should_override() is True

    def test_should_not_override_high_confidence(self):
        """Test should_not_override for high confidence."""
        result = ReflectionResult(
            decision=ReflectionDecision.REPLAN,
            confidence=0.5,
            progress_assessment="Definitely replan",
            summary="Clear issues",
        )

        assert result.should_override() is False

    def test_should_not_override_continue(self):
        """Test should_not_override for CONTINUE decisions."""
        result = ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.1,
            progress_assessment="Continue",
            summary="OK",
        )

        # CONTINUE doesn't require user override even with low confidence
        assert result.should_override() is False

    def test_enhanced_fields(self):
        """Test enhanced result fields."""
        result = ReflectionResult(
            decision=ReflectionDecision.ADJUST_STRATEGY,
            confidence=0.75,
            progress_assessment="Needs adjustment",
            summary="Adjust approach",
            decision_factors=["slow progress", "repeated errors"],
            alternative_decisions=["replan", "continue"],
            recommended_actions=["try different tool", "simplify approach"],
        )

        assert len(result.decision_factors) == 2
        assert "slow progress" in result.decision_factors
        assert len(result.recommended_actions) == 2


class TestProgressMetrics:
    """Tests for ProgressMetrics with enhanced triggers."""

    def test_metrics_work_with_triggers(self):
        """Test that metrics integrate with trigger system."""
        metrics = ProgressMetrics(
            steps_completed=3,
            steps_remaining=2,
            total_steps=5,
            successful_actions=8,
            failed_actions=2,
        )

        trigger = ReflectionTrigger()
        result = trigger.should_trigger(
            steps_completed=metrics.steps_completed,
            error_count=metrics.error_count,
            total_attempts=metrics.successful_actions + metrics.failed_actions,
            confidence=0.8,
            is_stalled=metrics.is_stalled,
        )

        # Should not trigger with these good metrics
        assert result is None or result == ReflectionTriggerType.STEP_INTERVAL


class TestIntegration:
    """Integration tests for reflection triggers."""

    def test_full_trigger_flow(self):
        """Test complete trigger evaluation flow."""
        trigger = ReflectionTrigger(
            detect_plan_divergence=True,
            detect_pattern_change=True,
            detect_confidence_decay=True,
        )

        # Simulate declining confidence
        for c in [0.95, 0.90, 0.85, 0.75, 0.70, 0.65]:
            trigger.record_confidence(c)

        # Check for confidence decay trigger
        result = trigger.should_trigger_enhanced(
            steps_completed=5,
            error_count=2,
            total_attempts=10,
            confidence=0.65,
            plan_divergence=0.2,  # Low divergence
            pattern_change_detected=False,
        )

        # Should trigger on confidence decay
        assert result == ReflectionTriggerType.CONFIDENCE_DECAY

    def test_priority_order(self):
        """Test that triggers are checked in priority order."""
        trigger = ReflectionTrigger()

        # User request should always win
        result = trigger.should_trigger_enhanced(
            steps_completed=2,  # Would trigger step_interval
            error_count=10,  # Would trigger high_error_rate
            total_attempts=10,
            plan_divergence=0.9,  # Would trigger divergence
            user_requested=True,  # Should win
        )

        assert result == ReflectionTriggerType.USER_REQUESTED
