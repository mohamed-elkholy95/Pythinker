"""Tests for telemetry initialization."""

from unittest.mock import patch, MagicMock


class TestTelemetrySetup:
    def test_otel_disabled_by_default(self):
        """OTEL should not initialize when disabled."""
        with patch("app.core.telemetry.settings") as mock_settings:
            mock_settings.OTEL_ENABLED = False
            mock_settings.SENTRY_DSN = None

            mock_app = MagicMock()
            from app.core.telemetry import setup_telemetry

            # Should not raise
            setup_telemetry(mock_app)

    def test_sentry_disabled_when_no_dsn(self):
        """Sentry should not initialize without DSN."""
        with patch("app.core.telemetry.settings") as mock_settings:
            mock_settings.OTEL_ENABLED = False
            mock_settings.SENTRY_DSN = None

            from app.core.telemetry import _setup_sentry

            # Should not raise
            _setup_sentry()
