"""Alert manager for monitoring thresholds (Phase 6).

Monitors agent metrics and emits alerts when thresholds are exceeded.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Alert(BaseModel):
    """Alert model."""

    alert_type: str
    severity: str  # info, warning, critical
    message: str
    session_id: str | None = None
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertManager:
    """Monitors thresholds and emits alerts."""

    THRESHOLDS: ClassVar[dict[str, float]] = {
        "verification_loop_excessive": 3,
        "token_budget_warning": 0.8,  # 80% usage
        "tool_failure_cascade": 3,
        "stuck_loop_detected": 1,
        "wrong_mode_selection": 0.1,  # >10% of sessions
        "high_error_rate": 0.3,  # >30% error rate
        "slow_response_time": 10.0,  # >10 seconds average
        "failure_prediction_high": 0.85,  # >85% failure probability
    }

    def __init__(self):
        """Initialize alert manager."""
        self._alerts: list[Alert] = []
        self._alert_counts: dict[str, int] = defaultdict(int)
        self._max_alerts = 1000
        self._alert_cooldown: dict[str, datetime] = {}
        self._cooldown_seconds = 300  # 5 minutes

    async def check_thresholds(self, session_id: str, metrics: dict[str, Any]) -> None:
        """Check all thresholds and emit alerts if exceeded.

        Args:
            session_id: Session to check
            metrics: Current metrics for the session
        """
        # Check verification loop
        if metrics.get("verification_loops", 0) > self.THRESHOLDS["verification_loop_excessive"]:
            await self._emit_alert(
                alert_type="verification_loop_excessive",
                severity="warning",
                message=f"Excessive verification loops detected: {metrics['verification_loops']}",
                session_id=session_id,
            )

        # Check token budget
        token_usage = metrics.get("token_usage_percent", 0)
        if token_usage > self.THRESHOLDS["token_budget_warning"]:
            await self._emit_alert(
                alert_type="token_budget_warning",
                severity="warning",
                message=f"Token budget at {token_usage:.0%}",
                session_id=session_id,
            )

        # Check tool failure cascade
        failed_tools = metrics.get("consecutive_tool_failures", 0)
        if failed_tools >= self.THRESHOLDS["tool_failure_cascade"]:
            await self._emit_alert(
                alert_type="tool_failure_cascade",
                severity="critical",
                message=f"Tool failure cascade detected: {failed_tools} consecutive failures",
                session_id=session_id,
            )

        # Check stuck loop
        if metrics.get("stuck_loop_detected", False):
            await self._emit_alert(
                alert_type="stuck_loop_detected",
                severity="warning",
                message="Agent stuck in loop",
                session_id=session_id,
            )

        # Check failure prediction probability
        failure_probability = metrics.get("failure_prediction_probability")
        if failure_probability is not None and failure_probability > self.THRESHOLDS["failure_prediction_high"]:
            await self._emit_alert(
                alert_type="failure_prediction_high",
                severity="warning",
                message=f"High failure probability predicted: {failure_probability:.0%}",
                session_id=session_id,
            )

    async def check_system_thresholds(self, system_metrics: dict[str, Any]) -> None:
        """Check system-wide thresholds.

        Args:
            system_metrics: System-wide metrics
        """
        # Check error rate
        error_rate = system_metrics.get("error_rate", 0)
        if error_rate > self.THRESHOLDS["high_error_rate"]:
            await self._emit_alert(
                alert_type="high_error_rate",
                severity="critical",
                message=f"System error rate elevated: {error_rate:.1%}",
                session_id=None,
            )

        # Check mode selection accuracy
        wrong_mode_rate = system_metrics.get("wrong_mode_rate", 0)
        if wrong_mode_rate > self.THRESHOLDS["wrong_mode_selection"]:
            await self._emit_alert(
                alert_type="wrong_mode_selection",
                severity="warning",
                message=f"Mode selection accuracy degraded: {wrong_mode_rate:.1%} incorrect",
                session_id=None,
            )

        # Check response time
        avg_response_time = system_metrics.get("avg_response_time", 0)
        if avg_response_time > self.THRESHOLDS["slow_response_time"]:
            await self._emit_alert(
                alert_type="slow_response_time",
                severity="warning",
                message=f"Slow response time: {avg_response_time:.1f}s average",
                session_id=None,
            )

    async def _emit_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        session_id: str | None = None,
    ) -> None:
        """Emit an alert with cooldown protection.

        Args:
            alert_type: Type of alert
            severity: Alert severity (info, warning, critical)
            message: Alert message
            session_id: Optional session ID
        """
        # Check cooldown
        cooldown_key = f"{alert_type}:{session_id or 'system'}"
        if cooldown_key in self._alert_cooldown:
            last_alert = self._alert_cooldown[cooldown_key]
            if datetime.now() - last_alert < timedelta(seconds=self._cooldown_seconds):
                logger.debug(f"Alert {alert_type} in cooldown, skipping")
                return

        # Create alert
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            session_id=session_id,
            timestamp=datetime.now(),
        )

        self._alerts.append(alert)
        self._alert_counts[alert_type] += 1
        self._alert_cooldown[cooldown_key] = datetime.now()

        # Trim alerts if too many
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts :]

        # Log alert
        log_level = logging.WARNING if severity == "warning" else logging.CRITICAL
        logger.log(
            log_level,
            f"ALERT [{severity.upper()}] {alert_type}: {message}",
            extra={
                "alert_type": alert_type,
                "severity": severity,
                "session_id": session_id,
            },
        )

    def get_recent_alerts(self, minutes: int = 60) -> list[Alert]:
        """Get recent alerts.

        Args:
            minutes: Number of minutes to look back

        Returns:
            List of recent alerts
        """
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [alert for alert in self._alerts if alert.timestamp >= cutoff]

    def get_alert_counts(self) -> dict[str, int]:
        """Get alert counts by type.

        Returns:
            Dictionary of alert type to count
        """
        return dict(self._alert_counts)

    def clear_alerts(self) -> None:
        """Clear all alerts and counts."""
        self._alerts.clear()
        self._alert_counts.clear()
        self._alert_cooldown.clear()


# Global instance
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance.

    Returns:
        AlertManager instance
    """
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
