"""Tests for RootCauseAnalyzer — pattern detection, description/recommendation
generation, RootCause model, and the singleton factory."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.repositories.analytics_repository import (
    AgentDecisionAnalytics,
    ToolExecutionAnalytics,
    WorkflowStateAnalytics,
)
from app.domain.services.analyzers.root_cause_analyzer import (
    RootCause,
    RootCauseAnalyzer,
    get_root_cause_analyzer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tool(
    success: bool = True,
    cpu: float | None = None,
    memory_mb: float | None = None,
    session_id: str = "sess-1",
) -> ToolExecutionAnalytics:
    return ToolExecutionAnalytics(
        session_id=session_id,
        tool_name="dummy_tool",
        success=success,
        container_cpu_percent=cpu,
        container_memory_mb=memory_mb,
    )


def make_workflow(
    verification_loops: int = 0,
    stuck: bool = False,
    context_pressure: str | None = None,
    session_id: str = "sess-1",
) -> WorkflowStateAnalytics:
    return WorkflowStateAnalytics(
        session_id=session_id,
        verification_loops=verification_loops,
        stuck_loop_detected=stuck,
        context_pressure=context_pressure,
    )


def make_decision(
    decision_type: str = "mode_selection",
    led_to_error: bool = False,
    session_id: str = "sess-1",
) -> AgentDecisionAnalytics:
    return AgentDecisionAnalytics(
        session_id=session_id,
        decision_type=decision_type,
        led_to_error=led_to_error,
    )


# ---------------------------------------------------------------------------
# RootCause model
# ---------------------------------------------------------------------------


class TestRootCauseModel:
    def test_construction_with_required_fields(self) -> None:
        rc = RootCause(
            cause_type="tool_failure_cascade",
            description="Multiple failures",
            confidence=0.8,
            contributing_factors=["resource_exhaustion"],
            recommended_fix="Review retry logic",
            session_id="abc",
            analyzed_at=datetime.now(UTC),
        )
        assert rc.cause_type == "tool_failure_cascade"
        assert rc.confidence == 0.8
        assert rc.session_id == "abc"
        assert "resource_exhaustion" in rc.contributing_factors

    def test_empty_contributing_factors(self) -> None:
        rc = RootCause(
            cause_type="unknown",
            description="No data",
            confidence=0.0,
            contributing_factors=[],
            recommended_fix="Check logs",
            session_id="x",
            analyzed_at=datetime.now(UTC),
        )
        assert rc.contributing_factors == []

    def test_confidence_boundary_values(self) -> None:
        for conf in (0.0, 0.5, 1.0):
            rc = RootCause(
                cause_type="unknown",
                description="test",
                confidence=conf,
                contributing_factors=[],
                recommended_fix="test",
                session_id="s",
                analyzed_at=datetime.now(UTC),
            )
            assert rc.confidence == conf

    def test_analyzed_at_is_datetime(self) -> None:
        now = datetime.now(UTC)
        rc = RootCause(
            cause_type="x",
            description="d",
            confidence=0.1,
            contributing_factors=[],
            recommended_fix="r",
            session_id="s",
            analyzed_at=now,
        )
        assert rc.analyzed_at == now


# ---------------------------------------------------------------------------
# _check_tool_failure_cascade
# ---------------------------------------------------------------------------


class TestCheckToolFailureCascade:
    analyzer = RootCauseAnalyzer()

    def test_empty_list_returns_zero(self) -> None:
        assert self.analyzer._check_tool_failure_cascade([]) == 0.0

    def test_single_failure_returns_zero(self) -> None:
        tools = [make_tool(success=False)]
        assert self.analyzer._check_tool_failure_cascade(tools) == 0.0

    def test_single_success_returns_zero(self) -> None:
        tools = [make_tool(success=True)]
        assert self.analyzer._check_tool_failure_cascade(tools) == 0.0

    def test_two_successes_returns_zero(self) -> None:
        tools = [make_tool(success=True), make_tool(success=True)]
        assert self.analyzer._check_tool_failure_cascade(tools) == 0.0

    def test_two_consecutive_failures_returns_positive(self) -> None:
        tools = [make_tool(success=False), make_tool(success=False)]
        score = self.analyzer._check_tool_failure_cascade(tools)
        assert score > 0.0

    def test_all_failures_high_score(self) -> None:
        tools = [make_tool(success=False)] * 10
        score = self.analyzer._check_tool_failure_cascade(tools)
        assert score >= 0.9

    def test_score_capped_at_one(self) -> None:
        tools = [make_tool(success=False)] * 20
        score = self.analyzer._check_tool_failure_cascade(tools)
        assert score <= 1.0

    def test_alternating_failures_lower_cascade_score(self) -> None:
        # Alternating pattern: SFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSFSF (S=success, F=fail)
        # High failure rate but low consecutive pairs → moderate score
        tools = [make_tool(success=(i % 2 == 0)) for i in range(10)]
        score_alternating = self.analyzer._check_tool_failure_cascade(tools)

        # All failures: maximum cascade + failure rate
        all_fail = [make_tool(success=False)] * 10
        score_all_fail = self.analyzer._check_tool_failure_cascade(all_fail)

        assert score_all_fail > score_alternating

    def test_mostly_success_with_two_failures_at_end(self) -> None:
        tools = [make_tool(success=True)] * 8 + [make_tool(success=False)] * 2
        score = self.analyzer._check_tool_failure_cascade(tools)
        # Failure rate 20%, cascade_score = 1.0 → 0.5*0.2 + 0.5*1.0 = 0.6
        assert 0.0 < score <= 1.0


# ---------------------------------------------------------------------------
# _check_stuck_loop
# ---------------------------------------------------------------------------


class TestCheckStuckLoop:
    analyzer = RootCauseAnalyzer()

    def test_empty_list_returns_zero(self) -> None:
        assert self.analyzer._check_stuck_loop([]) == 0.0

    def test_low_loops_no_detection_returns_zero(self) -> None:
        states = [make_workflow(verification_loops=2, stuck=False)]
        assert self.analyzer._check_stuck_loop(states) == 0.0

    def test_exactly_five_loops_triggers_score(self) -> None:
        states = [make_workflow(verification_loops=5)]
        score = self.analyzer._check_stuck_loop(states)
        assert score > 0.0

    def test_stuck_detection_flag_alone_triggers_score(self) -> None:
        states = [make_workflow(verification_loops=0, stuck=True)]
        score = self.analyzer._check_stuck_loop(states)
        assert score > 0.0

    def test_high_loops_approaches_one(self) -> None:
        states = [make_workflow(verification_loops=10)]
        score = self.analyzer._check_stuck_loop(states)
        assert score >= 1.0  # 10/10 = 1.0, min(..., 1.0)

    def test_multiple_stuck_detections_boost_score(self) -> None:
        # 3 stuck detections, no extra loops: 0/10 + 3*0.3 = 0.9
        states = [make_workflow(stuck=True)] * 3
        score = self.analyzer._check_stuck_loop(states)
        assert score == pytest.approx(0.9)

    def test_score_capped_at_one(self) -> None:
        states = [make_workflow(verification_loops=20, stuck=True)] * 5
        score = self.analyzer._check_stuck_loop(states)
        assert score <= 1.0

    def test_four_loops_no_stuck_returns_zero(self) -> None:
        states = [make_workflow(verification_loops=4)]
        assert self.analyzer._check_stuck_loop(states) == 0.0


# ---------------------------------------------------------------------------
# _check_resource_exhaustion
# ---------------------------------------------------------------------------


class TestCheckResourceExhaustion:
    analyzer = RootCauseAnalyzer()

    def test_empty_list_returns_zero(self) -> None:
        assert self.analyzer._check_resource_exhaustion([]) == 0.0

    def test_normal_cpu_memory_returns_zero(self) -> None:
        tools = [make_tool(cpu=50.0, memory_mb=512.0)] * 5
        assert self.analyzer._check_resource_exhaustion(tools) == 0.0

    def test_high_cpu_above_threshold_returns_positive(self) -> None:
        # 4 out of 10 above 90% CPU → 40% > 30% threshold
        tools = [make_tool(cpu=95.0)] * 4 + [make_tool(cpu=20.0)] * 6
        score = self.analyzer._check_resource_exhaustion(tools)
        assert score > 0.0

    def test_high_memory_above_threshold_returns_positive(self) -> None:
        # 4 out of 10 above 3500 MB → 40% > 30% threshold
        tools = [make_tool(memory_mb=3600.0)] * 4 + [make_tool(memory_mb=512.0)] * 6
        score = self.analyzer._check_resource_exhaustion(tools)
        assert score > 0.0

    def test_score_capped_at_one(self) -> None:
        tools = [make_tool(cpu=99.0, memory_mb=4000.0)] * 20
        score = self.analyzer._check_resource_exhaustion(tools)
        assert score <= 1.0

    def test_exactly_at_30_percent_threshold_returns_zero(self) -> None:
        # Exactly 30% — condition requires strictly greater (> not >=)
        tools = [make_tool(cpu=95.0)] * 3 + [make_tool(cpu=50.0)] * 7
        score = self.analyzer._check_resource_exhaustion(tools)
        assert score == 0.0

    def test_none_cpu_and_memory_skipped(self) -> None:
        tools = [make_tool(cpu=None, memory_mb=None)] * 5
        assert self.analyzer._check_resource_exhaustion(tools) == 0.0


# ---------------------------------------------------------------------------
# _check_wrong_mode
# ---------------------------------------------------------------------------


class TestCheckWrongMode:
    analyzer = RootCauseAnalyzer()

    def test_empty_decisions_returns_zero(self) -> None:
        assert self.analyzer._check_wrong_mode([]) == 0.0

    def test_no_mode_selection_decisions_returns_zero(self) -> None:
        decisions = [make_decision(decision_type="tool_choice")]
        assert self.analyzer._check_wrong_mode(decisions) == 0.0

    def test_mode_selection_no_error_returns_zero(self) -> None:
        decisions = [make_decision(decision_type="mode_selection", led_to_error=False)]
        assert self.analyzer._check_wrong_mode(decisions) == 0.0

    def test_single_wrong_mode_returns_one(self) -> None:
        decisions = [make_decision(decision_type="mode_selection", led_to_error=True)]
        score = self.analyzer._check_wrong_mode(decisions)
        assert score == 1.0

    def test_half_wrong_mode_returns_half(self) -> None:
        decisions = [
            make_decision(decision_type="mode_selection", led_to_error=True),
            make_decision(decision_type="mode_selection", led_to_error=False),
        ]
        score = self.analyzer._check_wrong_mode(decisions)
        assert score == pytest.approx(0.5)

    def test_score_capped_at_one(self) -> None:
        decisions = [make_decision(decision_type="mode_selection", led_to_error=True)] * 10
        score = self.analyzer._check_wrong_mode(decisions)
        assert score <= 1.0

    def test_mixed_decision_types_only_counts_mode_selection(self) -> None:
        decisions = [
            make_decision(decision_type="tool_choice", led_to_error=True),
            make_decision(decision_type="mode_selection", led_to_error=True),
        ]
        score = self.analyzer._check_wrong_mode(decisions)
        # Only 1 mode_selection, all led to error → 1.0
        assert score == 1.0


# ---------------------------------------------------------------------------
# _check_token_budget
# ---------------------------------------------------------------------------


class TestCheckTokenBudget:
    analyzer = RootCauseAnalyzer()

    def test_empty_list_returns_zero(self) -> None:
        assert self.analyzer._check_token_budget([]) == 0.0

    def test_no_critical_pressure_returns_zero(self) -> None:
        states = [make_workflow(context_pressure="normal")] * 5
        assert self.analyzer._check_token_budget(states) == 0.0

    def test_exactly_50_percent_critical_returns_zero(self) -> None:
        states = [make_workflow(context_pressure="critical")] * 5 + [
            make_workflow(context_pressure="normal")
        ] * 5
        # 5/10 = 50% — condition is > 50% (strictly greater)
        assert self.analyzer._check_token_budget(states) == 0.0

    def test_majority_critical_returns_positive(self) -> None:
        states = [make_workflow(context_pressure="critical")] * 6 + [
            make_workflow(context_pressure="normal")
        ] * 4
        score = self.analyzer._check_token_budget(states)
        assert score > 0.0

    def test_all_critical_returns_one(self) -> None:
        states = [make_workflow(context_pressure="critical")] * 5
        score = self.analyzer._check_token_budget(states)
        assert score == 1.0

    def test_score_capped_at_one(self) -> None:
        states = [make_workflow(context_pressure="critical")] * 20
        score = self.analyzer._check_token_budget(states)
        assert score <= 1.0

    def test_none_pressure_not_counted_as_critical(self) -> None:
        states = [make_workflow(context_pressure=None)] * 5
        assert self.analyzer._check_token_budget(states) == 0.0


# ---------------------------------------------------------------------------
# _generate_description
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    analyzer = RootCauseAnalyzer()

    def _desc(self, cause: str, tools=None, workflows=None, decisions=None) -> str:
        return self.analyzer._generate_description(
            cause,
            tools or [],
            workflows or [],
            decisions or [],
        )

    def test_tool_failure_cascade_includes_counts(self) -> None:
        tools = [make_tool(success=False)] * 3 + [make_tool(success=True)] * 2
        desc = self._desc("tool_failure_cascade", tools=tools)
        assert "3" in desc
        assert "5" in desc

    def test_stuck_loop_includes_max_loops(self) -> None:
        workflows = [make_workflow(verification_loops=7), make_workflow(verification_loops=3)]
        desc = self._desc("stuck_verification_loop", workflows=workflows)
        assert "7" in desc

    def test_resource_exhaustion_fixed_message(self) -> None:
        desc = self._desc("resource_exhaustion")
        assert "resource" in desc.lower() or "container" in desc.lower()

    def test_wrong_mode_selection_message(self) -> None:
        desc = self._desc("wrong_mode_selection")
        assert "mode" in desc.lower()

    def test_token_budget_includes_critical_count(self) -> None:
        workflows = [make_workflow(context_pressure="critical")] * 4
        desc = self._desc("token_budget_exceeded", workflows=workflows)
        assert "4" in desc

    def test_unknown_cause_returns_fallback(self) -> None:
        desc = self._desc("some_unknown_cause")
        assert "some_unknown_cause" in desc

    def test_empty_tool_executions_zero_counts(self) -> None:
        desc = self._desc("tool_failure_cascade")
        assert "0" in desc

    def test_max_loops_zero_when_no_workflows(self) -> None:
        desc = self._desc("stuck_verification_loop")
        assert "0" in desc


# ---------------------------------------------------------------------------
# _generate_recommendation
# ---------------------------------------------------------------------------


class TestGenerateRecommendation:
    analyzer = RootCauseAnalyzer()

    def test_tool_failure_cascade_recommendation(self) -> None:
        rec = self.analyzer._generate_recommendation("tool_failure_cascade")
        assert "retry" in rec.lower() or "sandbox" in rec.lower()

    def test_stuck_loop_recommendation(self) -> None:
        rec = self.analyzer._generate_recommendation("stuck_verification_loop")
        assert "loop" in rec.lower() or "circuit" in rec.lower()

    def test_resource_exhaustion_recommendation(self) -> None:
        rec = self.analyzer._generate_recommendation("resource_exhaustion")
        assert "resource" in rec.lower() or "container" in rec.lower()

    def test_wrong_mode_recommendation(self) -> None:
        rec = self.analyzer._generate_recommendation("wrong_mode_selection")
        assert "mode" in rec.lower() or "intent" in rec.lower()

    def test_token_budget_recommendation(self) -> None:
        rec = self.analyzer._generate_recommendation("token_budget_exceeded")
        assert "context" in rec.lower() or "summarization" in rec.lower()

    def test_unknown_cause_fallback_recommendation(self) -> None:
        rec = self.analyzer._generate_recommendation("xyz_unknown")
        assert len(rec) > 0

    def test_all_known_cause_types_have_specific_recommendation(self) -> None:
        analyzer = RootCauseAnalyzer()
        known = [
            "tool_failure_cascade",
            "stuck_verification_loop",
            "resource_exhaustion",
            "wrong_mode_selection",
            "token_budget_exceeded",
        ]
        fallback = analyzer._generate_recommendation("xyz_unknown")
        for cause in known:
            rec = analyzer._generate_recommendation(cause)
            assert rec != fallback, f"{cause} should have its own recommendation"


# ---------------------------------------------------------------------------
# CAUSE_TYPES class variable
# ---------------------------------------------------------------------------


class TestCauseTypes:
    def test_cause_types_is_list(self) -> None:
        assert isinstance(RootCauseAnalyzer.CAUSE_TYPES, list)

    def test_cause_types_non_empty(self) -> None:
        assert len(RootCauseAnalyzer.CAUSE_TYPES) > 0

    def test_known_causes_in_cause_types(self) -> None:
        types = RootCauseAnalyzer.CAUSE_TYPES
        for cause in (
            "tool_failure_cascade",
            "stuck_verification_loop",
            "resource_exhaustion",
            "wrong_mode_selection",
            "token_budget_exceeded",
        ):
            assert cause in types


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------


class TestGetRootCauseAnalyzer:
    def test_returns_instance(self) -> None:
        instance = get_root_cause_analyzer()
        assert isinstance(instance, RootCauseAnalyzer)

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        a = get_root_cause_analyzer()
        b = get_root_cause_analyzer()
        assert a is b

    def test_singleton_is_reused_across_calls(self) -> None:
        instances = [get_root_cause_analyzer() for _ in range(5)]
        assert all(i is instances[0] for i in instances)


# ---------------------------------------------------------------------------
# analyze_failed_session (async, integration-style with mocked repo)
# ---------------------------------------------------------------------------


class TestAnalyzeFailedSession:
    @pytest.mark.asyncio
    async def test_no_repository_returns_unknown(self) -> None:
        analyzer = RootCauseAnalyzer()
        with patch(
            "app.domain.services.analyzers.root_cause_analyzer.get_analytics_repository",
            return_value=None,
        ):
            result = await analyzer.analyze_failed_session("sess-xyz")

        assert result.cause_type == "unknown"
        assert result.confidence == 0.0
        assert result.session_id == "sess-xyz"
        assert result.contributing_factors == []

    @pytest.mark.asyncio
    async def test_with_all_failures_returns_tool_cascade(self) -> None:
        analyzer = RootCauseAnalyzer()
        tools = [make_tool(success=False)] * 10
        mock_repo = AsyncMock()
        mock_repo.get_tool_executions_for_session.return_value = tools
        mock_repo.get_workflow_states_for_session.return_value = []
        mock_repo.get_agent_decisions_for_session.return_value = []

        with patch(
            "app.domain.services.analyzers.root_cause_analyzer.get_analytics_repository",
            return_value=mock_repo,
        ):
            result = await analyzer.analyze_failed_session("sess-1")

        assert result.cause_type == "tool_failure_cascade"
        assert result.confidence > 0.0
        assert result.session_id == "sess-1"

    @pytest.mark.asyncio
    async def test_stuck_loop_detected_returns_stuck_cause(self) -> None:
        analyzer = RootCauseAnalyzer()
        workflows = [make_workflow(verification_loops=10, stuck=True)]
        mock_repo = AsyncMock()
        mock_repo.get_tool_executions_for_session.return_value = []
        mock_repo.get_workflow_states_for_session.return_value = workflows
        mock_repo.get_agent_decisions_for_session.return_value = []

        with patch(
            "app.domain.services.analyzers.root_cause_analyzer.get_analytics_repository",
            return_value=mock_repo,
        ):
            result = await analyzer.analyze_failed_session("sess-2")

        assert result.cause_type == "stuck_verification_loop"
        assert result.confidence >= 1.0  # capped

    @pytest.mark.asyncio
    async def test_contributing_factors_excludes_best_cause(self) -> None:
        analyzer = RootCauseAnalyzer()
        # All failures (tool cascade dominant) + critical context (token_budget above 0.3 threshold)
        tools = [make_tool(success=False)] * 10
        # 6 out of 10 critical → 60% > 50% → token_budget score = 0.6
        workflows = [make_workflow(context_pressure="critical")] * 6 + [
            make_workflow(context_pressure="normal")
        ] * 4

        mock_repo = AsyncMock()
        mock_repo.get_tool_executions_for_session.return_value = tools
        mock_repo.get_workflow_states_for_session.return_value = workflows
        mock_repo.get_agent_decisions_for_session.return_value = []

        with patch(
            "app.domain.services.analyzers.root_cause_analyzer.get_analytics_repository",
            return_value=mock_repo,
        ):
            result = await analyzer.analyze_failed_session("sess-3")

        assert result.cause_type not in result.contributing_factors

    @pytest.mark.asyncio
    async def test_result_has_valid_analyzed_at(self) -> None:
        analyzer = RootCauseAnalyzer()
        mock_repo = AsyncMock()
        mock_repo.get_tool_executions_for_session.return_value = []
        mock_repo.get_workflow_states_for_session.return_value = []
        mock_repo.get_agent_decisions_for_session.return_value = []

        before = datetime.now(UTC)
        with patch(
            "app.domain.services.analyzers.root_cause_analyzer.get_analytics_repository",
            return_value=mock_repo,
        ):
            result = await analyzer.analyze_failed_session("sess-4")
        after = datetime.now(UTC)

        assert before <= result.analyzed_at <= after

    @pytest.mark.asyncio
    async def test_wrong_mode_all_errors_returns_wrong_mode(self) -> None:
        analyzer = RootCauseAnalyzer()
        decisions = [make_decision(decision_type="mode_selection", led_to_error=True)] * 5
        mock_repo = AsyncMock()
        mock_repo.get_tool_executions_for_session.return_value = []
        mock_repo.get_workflow_states_for_session.return_value = []
        mock_repo.get_agent_decisions_for_session.return_value = decisions

        with patch(
            "app.domain.services.analyzers.root_cause_analyzer.get_analytics_repository",
            return_value=mock_repo,
        ):
            result = await analyzer.analyze_failed_session("sess-5")

        assert result.cause_type == "wrong_mode_selection"
        assert result.confidence == 1.0
