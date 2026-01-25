"""
Tests for the ReflectionAgent and reflection models.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from app.domain.services.agents.reflection import ReflectionAgent
from app.domain.models.reflection import (
    ReflectionTrigger,
    ReflectionTriggerType,
    ReflectionDecision,
    ReflectionResult,
    ReflectionConfig,
    ProgressMetrics,
)
from app.domain.models.event import ReflectionEvent, ReflectionStatus
from app.domain.models.plan import Plan, Step


class TestReflectionTrigger:
    """Tests for ReflectionTrigger configuration"""

    def test_default_initialization(self):
        """Test default trigger initialization"""
        trigger = ReflectionTrigger()
        assert trigger.step_interval == 2
        assert trigger.reflect_after_error is True
        assert trigger.error_rate_threshold == 0.5
        assert trigger.confidence_threshold == 0.6

    def test_step_interval_trigger(self):
        """Test step interval triggering"""
        trigger = ReflectionTrigger(step_interval=2, min_steps_before_first=1)

        # Should not trigger at step 1
        result = trigger.should_trigger(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
        )
        assert result is None

        # Should trigger at step 2
        result = trigger.should_trigger(
            steps_completed=2,
            error_count=0,
            total_attempts=2,
        )
        assert result == ReflectionTriggerType.STEP_INTERVAL

        # Should trigger at step 4
        result = trigger.should_trigger(
            steps_completed=4,
            error_count=0,
            total_attempts=4,
        )
        assert result == ReflectionTriggerType.STEP_INTERVAL

    def test_error_trigger(self):
        """Test error-based triggering"""
        trigger = ReflectionTrigger(reflect_after_error=True)

        result = trigger.should_trigger(
            steps_completed=1,
            error_count=1,
            total_attempts=1,
            last_had_error=True
        )
        assert result == ReflectionTriggerType.AFTER_ERROR

    def test_error_trigger_disabled(self):
        """Test error triggering when disabled"""
        trigger = ReflectionTrigger(reflect_after_error=False)

        result = trigger.should_trigger(
            steps_completed=1,
            error_count=1,
            total_attempts=1,
            last_had_error=True
        )
        # Should not trigger for error when disabled
        assert result != ReflectionTriggerType.AFTER_ERROR

    def test_high_error_rate_trigger(self):
        """Test high error rate triggering"""
        trigger = ReflectionTrigger(
            error_rate_threshold=0.5,
            reflect_after_error=False  # Disable to test rate threshold
        )

        result = trigger.should_trigger(
            steps_completed=1,
            error_count=6,
            total_attempts=10,  # 60% error rate
        )
        assert result == ReflectionTriggerType.HIGH_ERROR_RATE

    def test_low_confidence_trigger(self):
        """Test low confidence triggering"""
        trigger = ReflectionTrigger(
            confidence_threshold=0.6,
            reflect_after_error=False
        )

        result = trigger.should_trigger(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
            confidence=0.4
        )
        assert result == ReflectionTriggerType.LOW_CONFIDENCE

    def test_stall_trigger(self):
        """Test stall detection triggering"""
        trigger = ReflectionTrigger(
            stall_detection=True,
            reflect_after_error=False
        )

        result = trigger.should_trigger(
            steps_completed=1,
            error_count=0,
            total_attempts=1,
            is_stalled=True
        )
        assert result == ReflectionTriggerType.PROGRESS_STALL


class TestProgressMetrics:
    """Tests for ProgressMetrics dataclass"""

    def test_default_initialization(self):
        """Test default metrics initialization"""
        metrics = ProgressMetrics()
        assert metrics.steps_completed == 0
        assert metrics.success_rate == 1.0  # No failures
        assert metrics.is_stalled is False

    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        metrics = ProgressMetrics()
        metrics.successful_actions = 7
        metrics.failed_actions = 3

        assert metrics.success_rate == 0.7

    def test_estimated_progress(self):
        """Test progress estimation"""
        metrics = ProgressMetrics(
            steps_completed=3,
            total_steps=10
        )
        assert metrics.estimated_progress == 0.3

    def test_stall_detection(self):
        """Test stall detection"""
        metrics = ProgressMetrics(actions_since_progress=2)
        assert metrics.is_stalled is False

        metrics.actions_since_progress = 3
        assert metrics.is_stalled is True

    def test_record_success(self):
        """Test recording successful action"""
        metrics = ProgressMetrics(actions_since_progress=2)
        metrics.record_success()

        assert metrics.successful_actions == 1
        assert metrics.actions_since_progress == 0
        assert metrics.last_progress_at is not None

    def test_record_failure(self):
        """Test recording failed action"""
        metrics = ProgressMetrics()
        metrics.record_failure("Connection timeout")

        assert metrics.failed_actions == 1
        assert len(metrics.errors) == 1
        assert "Connection timeout" in metrics.errors

    def test_error_list_limit(self):
        """Test error list is limited.

        Implementation trims to last 10 when count exceeds 20.
        With 25 errors: at 21 errors trim to 10, then add 4 more = 14.
        """
        metrics = ProgressMetrics()

        for i in range(25):
            metrics.record_failure(f"Error {i}")

        # Should be trimmed to 14 (trim at >20, keep last 10, then add remaining 4)
        assert len(metrics.errors) == 14

    def test_record_step_completed(self):
        """Test recording step completion"""
        metrics = ProgressMetrics(
            steps_completed=0,
            steps_remaining=5,
            total_steps=5,
            actions_since_progress=2
        )
        metrics.record_step_completed()

        assert metrics.steps_completed == 1
        assert metrics.steps_remaining == 4
        assert metrics.actions_since_progress == 0

    def test_to_dict(self):
        """Test dict conversion for prompts"""
        metrics = ProgressMetrics(
            steps_completed=3,
            total_steps=10,
            successful_actions=7,
            failed_actions=3
        )

        result = metrics.to_dict()
        assert result["steps_completed"] == 3
        assert result["total_steps"] == 10
        assert result["success_rate"] == 70.0
        assert result["estimated_progress"] == 30.0


class TestReflectionResult:
    """Tests for ReflectionResult model"""

    def test_continue_result(self):
        """Test CONTINUE decision result"""
        result = ReflectionResult(
            decision=ReflectionDecision.CONTINUE,
            confidence=0.9,
            progress_assessment="On track",
            summary="Continue as planned"
        )
        assert result.decision == ReflectionDecision.CONTINUE
        assert result.strategy_adjustment is None

    def test_adjust_result(self):
        """Test ADJUST decision result"""
        result = ReflectionResult(
            decision=ReflectionDecision.ADJUST_STRATEGY,
            confidence=0.8,
            progress_assessment="Slight deviation",
            strategy_adjustment="Use more specific search terms",
            summary="Minor adjustment needed"
        )
        assert result.decision == ReflectionDecision.ADJUST_STRATEGY
        assert "specific search" in result.strategy_adjustment

    def test_replan_result(self):
        """Test REPLAN decision result"""
        result = ReflectionResult(
            decision=ReflectionDecision.REPLAN,
            confidence=0.7,
            progress_assessment="Strategy not working",
            replan_reason="Original approach blocked",
            summary="Major strategy change needed"
        )
        assert result.decision == ReflectionDecision.REPLAN
        assert result.replan_reason is not None

    def test_escalate_result(self):
        """Test ESCALATE decision result"""
        result = ReflectionResult(
            decision=ReflectionDecision.ESCALATE,
            confidence=0.8,
            progress_assessment="Ambiguous requirement",
            user_question="Do you want option A or option B?",
            summary="Need user clarification"
        )
        assert result.decision == ReflectionDecision.ESCALATE
        assert result.user_question is not None


class TestReflectionConfig:
    """Tests for ReflectionConfig"""

    def test_default_config(self):
        """Test default configuration"""
        config = ReflectionConfig()
        assert config.enabled is True
        assert config.max_reflections_per_task == 10
        assert config.min_steps_between_reflections == 1

    def test_custom_config(self):
        """Test custom configuration"""
        config = ReflectionConfig(
            enabled=False,
            max_reflections_per_task=5,
            min_steps_between_reflections=2
        )
        assert config.enabled is False
        assert config.max_reflections_per_task == 5


class TestReflectionAgent:
    """Tests for ReflectionAgent class"""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM"""
        llm = MagicMock()
        llm.ask = AsyncMock(return_value={
            "content": '{"decision": "continue", "confidence": 0.9, "summary": "OK"}'
        })
        return llm

    @pytest.fixture
    def mock_json_parser(self):
        """Create mock JSON parser"""
        parser = MagicMock()
        parser.parse = AsyncMock(return_value={
            "decision": "continue",
            "confidence": 0.9,
            "progress_assessment": "Good progress",
            "issues_identified": [],
            "summary": "Continue as planned"
        })
        return parser

    @pytest.fixture
    def test_plan(self):
        """Create a test plan"""
        return Plan(
            title="Test Plan",
            goal="Complete the test task",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2"),
                Step(id="3", description="Step 3"),
            ]
        )

    @pytest.fixture
    def test_metrics(self):
        """Create test progress metrics"""
        return ProgressMetrics(
            steps_completed=2,
            steps_remaining=1,
            total_steps=3,
            successful_actions=5,
            failed_actions=1
        )

    def test_initialization(self, mock_llm, mock_json_parser):
        """Test agent initialization"""
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )
        assert agent.config.enabled is True
        assert agent._reflection_count == 0

    def test_should_reflect_disabled(self, mock_llm, mock_json_parser, test_metrics):
        """Test reflection disabled in config"""
        config = ReflectionConfig(enabled=False)
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            config=config
        )

        result = agent.should_reflect(test_metrics)
        assert result is None

    def test_should_reflect_max_reached(self, mock_llm, mock_json_parser, test_metrics):
        """Test max reflections limit"""
        config = ReflectionConfig(max_reflections_per_task=2)
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            config=config
        )
        agent._reflection_count = 2

        result = agent.should_reflect(test_metrics)
        assert result is None

    def test_should_reflect_min_steps(self, mock_llm, mock_json_parser, test_metrics):
        """Test minimum steps between reflections"""
        config = ReflectionConfig(min_steps_between_reflections=3)
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            config=config
        )
        agent._last_reflection_step = 1
        test_metrics.steps_completed = 2

        result = agent.should_reflect(test_metrics)
        assert result is None

    def test_should_reflect_triggered(self, mock_llm, mock_json_parser, test_metrics):
        """Test reflection is triggered"""
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )
        # Set up conditions for trigger
        test_metrics.steps_completed = 2

        result = agent.should_reflect(test_metrics)
        assert result == ReflectionTriggerType.STEP_INTERVAL

    @pytest.mark.asyncio
    async def test_reflect_continue(self, mock_llm, mock_json_parser, test_plan, test_metrics):
        """Test reflection with CONTINUE decision"""
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )

        events = []
        async for event in agent.reflect(
            goal="Complete task",
            plan=test_plan,
            progress=test_metrics,
            trigger_type=ReflectionTriggerType.STEP_INTERVAL
        ):
            events.append(event)

        assert len(events) == 2
        assert events[0].status == ReflectionStatus.TRIGGERED
        assert events[1].status == ReflectionStatus.COMPLETED
        assert events[1].decision == "continue"

    @pytest.mark.asyncio
    async def test_reflect_replan(self, mock_llm, mock_json_parser, test_plan, test_metrics):
        """Test reflection with REPLAN decision"""
        mock_json_parser.parse = AsyncMock(return_value={
            "decision": "replan",
            "confidence": 0.7,
            "progress_assessment": "Strategy failing",
            "issues_identified": ["API unavailable"],
            "replan_reason": "Need alternative approach",
            "summary": "Major change needed"
        })

        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )

        events = []
        async for event in agent.reflect(
            goal="Complete task",
            plan=test_plan,
            progress=test_metrics,
            trigger_type=ReflectionTriggerType.AFTER_ERROR
        ):
            events.append(event)

        result_event = events[-1]
        assert result_event.decision == "replan"

    @pytest.mark.asyncio
    async def test_reflect_error_failopen(self, mock_llm, mock_json_parser, test_plan, test_metrics):
        """Test reflection fails open on error"""
        mock_json_parser.parse = AsyncMock(side_effect=Exception("Parse error"))

        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )

        events = []
        async for event in agent.reflect(
            goal="Complete task",
            plan=test_plan,
            progress=test_metrics,
            trigger_type=ReflectionTriggerType.STEP_INTERVAL
        ):
            events.append(event)

        result_event = events[-1]
        # Should fail open with CONTINUE
        assert result_event.decision == "continue"
        assert result_event.confidence == 0.5

    def test_reset(self, mock_llm, mock_json_parser):
        """Test agent reset"""
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )
        agent._reflection_count = 5
        agent._last_reflection_step = 10

        agent.reset()

        assert agent._reflection_count == 0
        assert agent._last_reflection_step == -1

    def test_get_stats(self, mock_llm, mock_json_parser):
        """Test getting agent statistics"""
        agent = ReflectionAgent(
            llm=mock_llm,
            json_parser=mock_json_parser
        )
        agent._reflection_count = 3
        agent._last_reflection_step = 5

        stats = agent.get_stats()

        assert stats["total_reflections"] == 3
        assert stats["last_reflection_step"] == 5
