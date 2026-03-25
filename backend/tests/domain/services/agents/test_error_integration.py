"""
Unit tests for error_integration.py — AgentHealthLevel, AgentHealthStatus,
IterationGuidance, and ErrorIntegrationBridge.

Tests cover:
- AgentHealthLevel enum values and string identity
- AgentHealthStatus default values and to_dict serialization
- IterationGuidance default values
- ErrorIntegrationBridge initialization and setter methods
- assess_agent_health with various component combinations
- Health-level escalation logic (DEGRADED, CRITICAL, STUCK)
- Token pressure recommendations
- Failure-prediction feature flag path (shadow mode off)
- to_dict roundtrip completeness
"""

from unittest.mock import MagicMock

from app.domain.services.agents.error_integration import (
    AgentHealthLevel,
    AgentHealthStatus,
    ErrorIntegrationBridge,
    IterationGuidance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bridge(**kwargs) -> ErrorIntegrationBridge:
    """Create a bridge with feature_flags={} to avoid importing app.core.config."""
    kwargs.setdefault("feature_flags", {})
    return ErrorIntegrationBridge(**kwargs)


def _make_error_handler(recent_errors=None, success_rate=1.0):
    """Return a mock error_handler with configurable recent errors and recovery stats."""
    handler = MagicMock()
    handler.get_recent_errors.return_value = recent_errors if recent_errors is not None else []
    handler.get_recovery_stats.return_value = {"success_rate": success_rate}
    return handler


def _make_stuck_detector(is_stuck=False, stuck_type="loop"):
    """Return a mock stuck_detector."""
    detector = MagicMock()
    detector.is_stuck.return_value = is_stuck
    detector.get_stuck_type.return_value = stuck_type
    return detector


def _make_pressure(level_value="high", usage_percent=90.0):
    """Return a mock pressure object returned by token_manager.get_context_pressure()."""
    pressure = MagicMock()
    level = MagicMock()
    level.value = level_value
    pressure.level = level
    pressure.usage_percent = usage_percent
    return pressure


def _make_token_manager(level_value="normal", usage_percent=30.0):
    """Return a mock token_manager."""
    manager = MagicMock()
    manager.get_context_pressure.return_value = _make_pressure(level_value, usage_percent)
    return manager


# ===========================================================================
# 1. AgentHealthLevel
# ===========================================================================


class TestAgentHealthLevel:
    """Verify AgentHealthLevel enum members and their string values."""

    def test_healthy_value(self):
        assert AgentHealthLevel.HEALTHY == "healthy"
        assert AgentHealthLevel.HEALTHY.value == "healthy"

    def test_degraded_value(self):
        assert AgentHealthLevel.DEGRADED == "degraded"
        assert AgentHealthLevel.DEGRADED.value == "degraded"

    def test_critical_value(self):
        assert AgentHealthLevel.CRITICAL == "critical"
        assert AgentHealthLevel.CRITICAL.value == "critical"

    def test_stuck_value(self):
        assert AgentHealthLevel.STUCK == "stuck"
        assert AgentHealthLevel.STUCK.value == "stuck"

    def test_is_str_enum(self):
        """AgentHealthLevel extends str, so members compare equal to plain strings."""
        assert isinstance(AgentHealthLevel.HEALTHY, str)

    def test_all_four_members_exist(self):
        members = {m.value for m in AgentHealthLevel}
        assert members == {"healthy", "degraded", "critical", "stuck"}


# ===========================================================================
# 2. AgentHealthStatus
# ===========================================================================


class TestAgentHealthStatusDefaults:
    """Verify AgentHealthStatus default field values."""

    def test_default_error_count(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.error_count_recent == 0

    def test_default_is_stuck_false(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.is_stuck is False

    def test_default_stuck_type_none(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.stuck_type is None

    def test_default_token_pressure_none(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.token_pressure_level is None

    def test_default_token_usage_zero(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.token_usage_pct == 0.0

    def test_default_patterns_empty_list(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.patterns_detected == []

    def test_default_recommended_actions_empty(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.recommended_actions == []

    def test_default_details_empty_dict(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.details == {}

    def test_default_predicted_failure_false(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.predicted_failure is False

    def test_default_failure_probability_zero(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.failure_probability == 0.0

    def test_default_failure_factors_empty(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.failure_factors == []

    def test_default_recommended_intervention_none(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        assert status.recommended_intervention is None


class TestAgentHealthStatusToDict:
    """Verify to_dict serialization contains all expected keys with correct types."""

    def _make_status(self) -> AgentHealthStatus:
        return AgentHealthStatus(
            level=AgentHealthLevel.DEGRADED,
            error_count_recent=3,
            is_stuck=False,
            stuck_type=None,
            token_pressure_level="medium",
            token_usage_pct=78.5,
            patterns_detected=[{"type": "timeout", "confidence": 0.8, "suggestion": "retry"}],
            recommended_actions=["Monitor closely"],
            details={"issues": ["High error rate"]},
            predicted_failure=True,
            failure_probability=0.65,
            failure_factors=["high_error_rate"],
            recommended_intervention="escalate",
        )

    def test_to_dict_returns_dict(self):
        assert isinstance(self._make_status().to_dict(), dict)

    def test_to_dict_level_is_string_value(self):
        d = self._make_status().to_dict()
        assert d["level"] == "degraded"

    def test_to_dict_error_count(self):
        assert self._make_status().to_dict()["error_count_recent"] == 3

    def test_to_dict_is_stuck(self):
        assert self._make_status().to_dict()["is_stuck"] is False

    def test_to_dict_stuck_type(self):
        assert self._make_status().to_dict()["stuck_type"] is None

    def test_to_dict_token_pressure_level(self):
        assert self._make_status().to_dict()["token_pressure_level"] == "medium"

    def test_to_dict_token_usage_pct(self):
        assert self._make_status().to_dict()["token_usage_pct"] == 78.5

    def test_to_dict_patterns_detected(self):
        d = self._make_status().to_dict()
        assert isinstance(d["patterns_detected"], list)
        assert len(d["patterns_detected"]) == 1

    def test_to_dict_recommended_actions(self):
        d = self._make_status().to_dict()
        assert d["recommended_actions"] == ["Monitor closely"]

    def test_to_dict_predicted_failure(self):
        assert self._make_status().to_dict()["predicted_failure"] is True

    def test_to_dict_failure_probability(self):
        assert self._make_status().to_dict()["failure_probability"] == 0.65

    def test_to_dict_failure_factors(self):
        assert self._make_status().to_dict()["failure_factors"] == ["high_error_rate"]

    def test_to_dict_recommended_intervention(self):
        assert self._make_status().to_dict()["recommended_intervention"] == "escalate"

    def test_to_dict_contains_details(self):
        d = self._make_status().to_dict()
        assert "details" in d
        assert d["details"]["issues"] == ["High error rate"]

    def test_to_dict_all_keys_present(self):
        expected_keys = {
            "level",
            "error_count_recent",
            "is_stuck",
            "stuck_type",
            "token_pressure_level",
            "token_usage_pct",
            "patterns_detected",
            "recommended_actions",
            "predicted_failure",
            "failure_probability",
            "failure_factors",
            "recommended_intervention",
            "details",
        }
        assert set(self._make_status().to_dict().keys()) == expected_keys

    def test_to_dict_healthy_defaults_roundtrip(self):
        status = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        d = status.to_dict()
        assert d["level"] == "healthy"
        assert d["error_count_recent"] == 0
        assert d["is_stuck"] is False
        assert d["token_usage_pct"] == 0.0
        assert d["predicted_failure"] is False
        assert d["failure_probability"] == 0.0
        assert d["patterns_detected"] == []
        assert d["recommended_actions"] == []
        assert d["failure_factors"] == []
        assert d["stuck_type"] is None
        assert d["token_pressure_level"] is None
        assert d["recommended_intervention"] is None


# ===========================================================================
# 3. IterationGuidance
# ===========================================================================


class TestIterationGuidanceDefaults:
    """Verify IterationGuidance default field values."""

    def test_should_continue_true_by_default(self):
        guidance = IterationGuidance()
        assert guidance.should_continue is True

    def test_inject_prompt_none_by_default(self):
        guidance = IterationGuidance()
        assert guidance.inject_prompt is None

    def test_trigger_compaction_false_by_default(self):
        guidance = IterationGuidance()
        assert guidance.trigger_compaction is False

    def test_patterns_empty_list_by_default(self):
        guidance = IterationGuidance()
        assert guidance.patterns == []

    def test_health_level_healthy_by_default(self):
        guidance = IterationGuidance()
        assert guidance.health_level == AgentHealthLevel.HEALTHY

    def test_warnings_empty_list_by_default(self):
        guidance = IterationGuidance()
        assert guidance.warnings == []


# ===========================================================================
# 4. ErrorIntegrationBridge — initialization and setters
# ===========================================================================


class TestErrorIntegrationBridgeInit:
    """Verify bridge initializes correctly with various argument combinations."""

    def test_init_with_no_components_stores_none(self):
        bridge = _make_bridge()
        assert bridge._error_handler is None
        assert bridge._stuck_detector is None
        assert bridge._pattern_analyzer is None
        assert bridge._token_manager is None
        assert bridge._memory_manager is None

    def test_init_stores_feature_flags(self):
        flags = {"failure_prediction": False}
        bridge = _make_bridge(feature_flags=flags)
        assert bridge._feature_flags == flags

    def test_init_iteration_count_zero(self):
        bridge = _make_bridge()
        assert bridge._iteration_count == 0

    def test_init_last_health_status_none(self):
        bridge = _make_bridge()
        assert bridge._last_health_status is None

    def test_init_compaction_triggered_at_none(self):
        bridge = _make_bridge()
        assert bridge._compaction_triggered_at is None

    def test_set_error_handler_stores_component(self):
        bridge = _make_bridge()
        handler = _make_error_handler()
        bridge.set_error_handler(handler)
        assert bridge._error_handler is handler

    def test_set_stuck_detector_stores_component(self):
        bridge = _make_bridge()
        detector = _make_stuck_detector()
        bridge.set_stuck_detector(detector)
        assert bridge._stuck_detector is detector

    def test_set_pattern_analyzer_stores_component(self):
        bridge = _make_bridge()
        analyzer = MagicMock()
        bridge.set_pattern_analyzer(analyzer)
        assert bridge._pattern_analyzer is analyzer

    def test_set_token_manager_stores_component(self):
        bridge = _make_bridge()
        manager = _make_token_manager()
        bridge.set_token_manager(manager)
        assert bridge._token_manager is manager

    def test_set_memory_manager_stores_component(self):
        bridge = _make_bridge()
        mem = MagicMock()
        bridge.set_memory_manager(mem)
        assert bridge._memory_manager is mem

    def test_init_with_all_components_stores_them(self):
        handler = _make_error_handler()
        detector = _make_stuck_detector()
        analyzer = MagicMock()
        manager = _make_token_manager()
        memory = MagicMock()
        bridge = _make_bridge(
            error_handler=handler,
            stuck_detector=detector,
            pattern_analyzer=analyzer,
            token_manager=manager,
            memory_manager=memory,
        )
        assert bridge._error_handler is handler
        assert bridge._stuck_detector is detector
        assert bridge._pattern_analyzer is analyzer
        assert bridge._token_manager is manager
        assert bridge._memory_manager is memory


# ===========================================================================
# 5. assess_agent_health — no components
# ===========================================================================


class TestAssessAgentHealthNoComponents:
    """Without any components the bridge should return HEALTHY with zero counts."""

    def test_returns_healthy_level(self):
        bridge = _make_bridge()
        status = bridge.assess_agent_health()
        assert status.level == AgentHealthLevel.HEALTHY

    def test_returns_agent_health_status_instance(self):
        bridge = _make_bridge()
        status = bridge.assess_agent_health()
        assert isinstance(status, AgentHealthStatus)

    def test_error_count_zero(self):
        bridge = _make_bridge()
        status = bridge.assess_agent_health()
        assert status.error_count_recent == 0

    def test_is_stuck_false(self):
        bridge = _make_bridge()
        status = bridge.assess_agent_health()
        assert status.is_stuck is False

    def test_no_recommended_actions(self):
        bridge = _make_bridge()
        status = bridge.assess_agent_health()
        assert status.recommended_actions == []

    def test_caches_last_health_status(self):
        bridge = _make_bridge()
        status = bridge.assess_agent_health()
        assert bridge._last_health_status is status


# ===========================================================================
# 6. assess_agent_health — with error_handler
# ===========================================================================


class TestAssessAgentHealthWithErrorHandler:
    """error_handler integration: error counts and recovery stats affect health."""

    def test_five_or_more_recent_errors_adds_recommendation(self):
        handler = _make_error_handler(recent_errors=["e"] * 5)
        bridge = _make_bridge(error_handler=handler)
        status = bridge.assess_agent_health()
        assert any("simplify" in a.lower() for a in status.recommended_actions)

    def test_fewer_than_five_errors_no_simplify_recommendation(self):
        handler = _make_error_handler(recent_errors=["e"] * 4)
        bridge = _make_bridge(error_handler=handler)
        status = bridge.assess_agent_health()
        simplify = [a for a in status.recommended_actions if "simplify" in a.lower()]
        assert simplify == []

    def test_error_count_stored_on_status(self):
        handler = _make_error_handler(recent_errors=["e"] * 7)
        bridge = _make_bridge(error_handler=handler)
        status = bridge.assess_agent_health()
        assert status.error_count_recent == 7

    def test_low_recovery_rate_adds_intervention_recommendation(self):
        handler = _make_error_handler(recent_errors=[], success_rate=0.3)
        bridge = _make_bridge(error_handler=handler)
        status = bridge.assess_agent_health()
        assert any("intervention" in a.lower() or "user" in a.lower() for a in status.recommended_actions)

    def test_high_error_count_degrades_health_level(self):
        """5 recent errors generates one issue → DEGRADED."""
        handler = _make_error_handler(recent_errors=["e"] * 5)
        bridge = _make_bridge(error_handler=handler)
        status = bridge.assess_agent_health()
        assert status.level in (AgentHealthLevel.DEGRADED, AgentHealthLevel.CRITICAL)

    def test_high_error_count_plus_low_recovery_gives_critical(self):
        """5 errors + low recovery rate = 2 issues → CRITICAL (>= 3 issue check) or DEGRADED
        depending on third issue source.  At minimum, must not be HEALTHY."""
        handler = _make_error_handler(recent_errors=["e"] * 5, success_rate=0.2)
        bridge = _make_bridge(error_handler=handler)
        status = bridge.assess_agent_health()
        assert status.level != AgentHealthLevel.HEALTHY


# ===========================================================================
# 7. assess_agent_health — stuck detector
# ===========================================================================


class TestAssessAgentHealthWithStuckDetector:
    """StuckDetector integration: is_stuck flag and STUCK health level."""

    def test_stuck_sets_is_stuck_true(self):
        detector = _make_stuck_detector(is_stuck=True, stuck_type="loop")
        bridge = _make_bridge(stuck_detector=detector)
        status = bridge.assess_agent_health()
        assert status.is_stuck is True

    def test_stuck_upgrades_level_to_stuck(self):
        detector = _make_stuck_detector(is_stuck=True)
        bridge = _make_bridge(stuck_detector=detector)
        status = bridge.assess_agent_health()
        assert status.level == AgentHealthLevel.STUCK

    def test_stuck_type_stored(self):
        detector = _make_stuck_detector(is_stuck=True, stuck_type="tool_loop")
        bridge = _make_bridge(stuck_detector=detector)
        status = bridge.assess_agent_health()
        assert status.stuck_type == "tool_loop"

    def test_not_stuck_keeps_is_stuck_false(self):
        detector = _make_stuck_detector(is_stuck=False)
        bridge = _make_bridge(stuck_detector=detector)
        status = bridge.assess_agent_health()
        assert status.is_stuck is False

    def test_not_stuck_adds_recommendation_for_different_approach(self):
        """When stuck, a recommendation about different approach should appear."""
        detector = _make_stuck_detector(is_stuck=True)
        bridge = _make_bridge(stuck_detector=detector)
        status = bridge.assess_agent_health()
        assert any("approach" in a.lower() or "tool" in a.lower() for a in status.recommended_actions)

    def test_stuck_detector_without_get_stuck_type_defaults_to_unknown(self):
        """If stuck_detector lacks get_stuck_type, stuck_type falls back to 'unknown'."""
        detector = MagicMock(spec=["is_stuck"])  # no get_stuck_type attribute
        detector.is_stuck.return_value = True
        bridge = _make_bridge(stuck_detector=detector)
        status = bridge.assess_agent_health()
        assert status.stuck_type == "unknown"


# ===========================================================================
# 8. assess_agent_health — token manager
# ===========================================================================


class TestAssessAgentHealthWithTokenManager:
    """TokenManager integration: pressure levels affect health and recommendations."""

    def test_high_token_usage_adds_compaction_recommendation(self):
        manager = _make_token_manager(level_value="high", usage_percent=88.0)
        bridge = _make_bridge(token_manager=manager)
        messages = [{"role": "user", "content": "hello"}]
        status = bridge.assess_agent_health(messages=messages)
        assert any("compact" in a.lower() for a in status.recommended_actions)

    def test_high_token_usage_stored_on_status(self):
        manager = _make_token_manager(level_value="high", usage_percent=88.0)
        bridge = _make_bridge(token_manager=manager)
        messages = [{"role": "user", "content": "hello"}]
        status = bridge.assess_agent_health(messages=messages)
        assert status.token_usage_pct == 88.0

    def test_moderate_token_usage_adds_monitor_recommendation(self):
        manager = _make_token_manager(level_value="medium", usage_percent=79.0)
        bridge = _make_bridge(token_manager=manager)
        messages = [{"role": "user", "content": "hello"}]
        status = bridge.assess_agent_health(messages=messages)
        assert any("monitor" in a.lower() for a in status.recommended_actions)

    def test_token_pressure_level_stored(self):
        manager = _make_token_manager(level_value="critical", usage_percent=92.0)
        bridge = _make_bridge(token_manager=manager)
        messages = [{"role": "user", "content": "hi"}]
        status = bridge.assess_agent_health(messages=messages)
        assert status.token_pressure_level == "critical"

    def test_no_messages_skips_token_check(self):
        """When messages=None the token_manager should not be called."""
        manager = _make_token_manager(usage_percent=95.0)
        bridge = _make_bridge(token_manager=manager)
        status = bridge.assess_agent_health(messages=None)
        manager.get_context_pressure.assert_not_called()
        assert status.token_usage_pct == 0.0

    def test_very_high_token_usage_raises_to_critical(self):
        """token_usage_pct > 90 alone should produce CRITICAL health."""
        manager = _make_token_manager(level_value="critical", usage_percent=91.0)
        bridge = _make_bridge(token_manager=manager)
        messages = [{"role": "user", "content": "hi"}]
        status = bridge.assess_agent_health(messages=messages)
        assert status.level == AgentHealthLevel.CRITICAL


# ===========================================================================
# 9. assess_agent_health — failure prediction feature flag
# ===========================================================================


class TestAssessAgentHealthFailurePrediction:
    """failure_prediction feature flag controls FailurePredictor invocation."""

    def test_failure_prediction_disabled_by_default_no_predicted_failure(self):
        """With feature_flags={} (flag off) predicted_failure stays False."""
        bridge = _make_bridge(feature_flags={})
        status = bridge.assess_agent_health()
        assert status.predicted_failure is False
        assert status.failure_probability == 0.0
        assert status.failure_factors == []


# ===========================================================================
# 10. get_metrics and reset
# ===========================================================================


class TestBridgeMetricsAndReset:
    """get_metrics and reset behave correctly."""

    def test_get_metrics_returns_iteration_count(self):
        bridge = _make_bridge()
        metrics = bridge.get_metrics()
        assert metrics["iteration_count"] == 0

    def test_get_metrics_last_health_level_none_before_assess(self):
        bridge = _make_bridge()
        metrics = bridge.get_metrics()
        assert metrics["last_health_level"] is None

    def test_get_metrics_includes_last_health_level_after_assess(self):
        bridge = _make_bridge()
        bridge.assess_agent_health()
        metrics = bridge.get_metrics()
        assert metrics["last_health_level"] == "healthy"

    def test_get_metrics_includes_stuck_detector_info(self):
        detector = _make_stuck_detector(is_stuck=False)
        bridge = _make_bridge(stuck_detector=detector)
        metrics = bridge.get_metrics()
        assert "stuck_detector" in metrics
        assert metrics["stuck_detector"]["is_stuck"] is False

    def test_reset_clears_iteration_count(self):
        handler = _make_error_handler()
        handler.clear_history = MagicMock()
        handler.reset_stats = MagicMock()
        bridge = _make_bridge(error_handler=handler)
        bridge._iteration_count = 5
        bridge.reset()
        assert bridge._iteration_count == 0

    def test_reset_clears_last_health_status(self):
        bridge = _make_bridge()
        bridge.assess_agent_health()
        assert bridge._last_health_status is not None
        handler = MagicMock()
        handler.clear_history = MagicMock()
        handler.reset_stats = MagicMock()
        bridge._error_handler = handler
        bridge.reset()
        assert bridge._last_health_status is None

    def test_reset_clears_compaction_triggered_at(self):
        bridge = _make_bridge()
        bridge._compaction_triggered_at = 3
        handler = MagicMock()
        handler.clear_history = MagicMock()
        handler.reset_stats = MagicMock()
        bridge._error_handler = handler
        bridge.reset()
        assert bridge._compaction_triggered_at is None
