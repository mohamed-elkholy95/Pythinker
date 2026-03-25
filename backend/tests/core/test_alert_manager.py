"""Tests for AlertManager — threshold monitoring and alert emission."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.alert_manager import Alert, AlertManager, get_alert_manager

# ── Alert Model ─────────────────────────────────────────────────────


class TestAlertModel:
    def test_basic_construction(self):
        alert = Alert(
            alert_type="test",
            severity="warning",
            message="Test alert",
            timestamp=datetime.now(UTC),
        )
        assert alert.alert_type == "test"
        assert alert.session_id is None
        assert alert.metadata == {}

    def test_with_metadata(self):
        alert = Alert(
            alert_type="test",
            severity="critical",
            message="Bad",
            timestamp=datetime.now(UTC),
            metadata={"key": "value"},
        )
        assert alert.metadata["key"] == "value"


# ── check_thresholds ───────────────────────────────────────────────


class TestCheckThresholds:
    @pytest.mark.asyncio
    async def test_verification_loop_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"verification_loops": 5})
        alerts = mgr.get_recent_alerts()
        assert any(a.alert_type == "verification_loop_excessive" for a in alerts)

    @pytest.mark.asyncio
    async def test_no_alert_below_threshold(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"verification_loops": 2})
        alerts = mgr.get_recent_alerts()
        assert not any(a.alert_type == "verification_loop_excessive" for a in alerts)

    @pytest.mark.asyncio
    async def test_token_budget_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"token_usage_percent": 0.9})
        alerts = mgr.get_recent_alerts()
        assert any(a.alert_type == "token_budget_warning" for a in alerts)

    @pytest.mark.asyncio
    async def test_tool_failure_cascade_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"consecutive_tool_failures": 5})
        alerts = mgr.get_recent_alerts()
        cascade = [a for a in alerts if a.alert_type == "tool_failure_cascade"]
        assert len(cascade) == 1
        assert cascade[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_stuck_loop_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"stuck_loop_detected": True})
        alerts = mgr.get_recent_alerts()
        assert any(a.alert_type == "stuck_loop_detected" for a in alerts)

    @pytest.mark.asyncio
    async def test_stuck_loop_false_no_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"stuck_loop_detected": False})
        alerts = mgr.get_recent_alerts()
        assert not any(a.alert_type == "stuck_loop_detected" for a in alerts)

    @pytest.mark.asyncio
    async def test_failure_prediction_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"failure_prediction_probability": 0.9})
        alerts = mgr.get_recent_alerts()
        assert any(a.alert_type == "failure_prediction_high" for a in alerts)

    @pytest.mark.asyncio
    async def test_failure_prediction_none_no_alert(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"failure_prediction_probability": None})
        alerts = mgr.get_recent_alerts()
        assert not any(a.alert_type == "failure_prediction_high" for a in alerts)

    @pytest.mark.asyncio
    async def test_multiple_alerts_from_one_check(self):
        mgr = AlertManager()
        await mgr.check_thresholds(
            "s1",
            {
                "verification_loops": 5,
                "token_usage_percent": 0.95,
                "consecutive_tool_failures": 4,
            },
        )
        alerts = mgr.get_recent_alerts()
        types = {a.alert_type for a in alerts}
        assert "verification_loop_excessive" in types
        assert "token_budget_warning" in types
        assert "tool_failure_cascade" in types


# ── check_system_thresholds ─────────────────────────────────────────


class TestCheckSystemThresholds:
    @pytest.mark.asyncio
    async def test_high_error_rate_alert(self):
        mgr = AlertManager()
        await mgr.check_system_thresholds({"error_rate": 0.5})
        alerts = mgr.get_recent_alerts()
        err = [a for a in alerts if a.alert_type == "high_error_rate"]
        assert len(err) == 1
        assert err[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_wrong_mode_selection_alert(self):
        mgr = AlertManager()
        await mgr.check_system_thresholds({"wrong_mode_rate": 0.2})
        alerts = mgr.get_recent_alerts()
        assert any(a.alert_type == "wrong_mode_selection" for a in alerts)

    @pytest.mark.asyncio
    async def test_slow_response_time_alert(self):
        mgr = AlertManager()
        await mgr.check_system_thresholds({"avg_response_time": 15.0})
        alerts = mgr.get_recent_alerts()
        assert any(a.alert_type == "slow_response_time" for a in alerts)

    @pytest.mark.asyncio
    async def test_no_alert_when_metrics_normal(self):
        mgr = AlertManager()
        await mgr.check_system_thresholds(
            {
                "error_rate": 0.05,
                "wrong_mode_rate": 0.01,
                "avg_response_time": 2.0,
            }
        )
        alerts = mgr.get_recent_alerts()
        assert len(alerts) == 0


# ── Cooldown ────────────────────────────────────────────────────────


class TestCooldown:
    @pytest.mark.asyncio
    async def test_cooldown_prevents_duplicate_alerts(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"verification_loops": 5})
        await mgr.check_thresholds("s1", {"verification_loops": 5})
        alerts = mgr.get_recent_alerts()
        verification = [a for a in alerts if a.alert_type == "verification_loop_excessive"]
        # Second call should be suppressed by cooldown
        assert len(verification) == 1

    @pytest.mark.asyncio
    async def test_different_sessions_not_cooled(self):
        mgr = AlertManager()
        await mgr.check_thresholds("s1", {"verification_loops": 5})
        await mgr.check_thresholds("s2", {"verification_loops": 5})
        alerts = mgr.get_recent_alerts()
        verification = [a for a in alerts if a.alert_type == "verification_loop_excessive"]
        assert len(verification) == 2


# ── Alert History Management ────────────────────────────────────────


class TestAlertHistory:
    @pytest.mark.asyncio
    async def test_max_alerts_enforced(self):
        mgr = AlertManager()
        mgr._max_alerts = 5
        mgr._cooldown_seconds = 0  # Disable cooldown for this test
        for i in range(10):
            await mgr._emit_alert(
                alert_type=f"test_{i}",
                severity="info",
                message=f"Alert {i}",
            )
        assert len(mgr._alerts) == 5

    @pytest.mark.asyncio
    async def test_get_recent_alerts_filters_by_time(self):
        mgr = AlertManager()
        # Add an old alert manually
        old_alert = Alert(
            alert_type="old",
            severity="info",
            message="Old alert",
            timestamp=datetime.now(UTC) - timedelta(hours=2),
        )
        mgr._alerts.append(old_alert)
        # Add a recent alert
        await mgr._emit_alert(
            alert_type="new",
            severity="info",
            message="New alert",
        )
        recent = mgr.get_recent_alerts(minutes=60)
        assert not any(a.alert_type == "old" for a in recent)
        assert any(a.alert_type == "new" for a in recent)

    def test_get_alert_counts(self):
        mgr = AlertManager()
        mgr._alert_counts["test_type"] = 5
        counts = mgr.get_alert_counts()
        assert counts["test_type"] == 5

    @pytest.mark.asyncio
    async def test_clear_alerts(self):
        mgr = AlertManager()
        await mgr._emit_alert(alert_type="test", severity="info", message="msg")
        mgr.clear_alerts()
        assert len(mgr._alerts) == 0
        assert len(mgr._alert_counts) == 0
        assert len(mgr._alert_cooldown) == 0


# ── Singleton ───────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_instance(self):
        mgr = get_alert_manager()
        assert isinstance(mgr, AlertManager)

    def test_is_stable(self):
        m1 = get_alert_manager()
        m2 = get_alert_manager()
        assert m1 is m2
