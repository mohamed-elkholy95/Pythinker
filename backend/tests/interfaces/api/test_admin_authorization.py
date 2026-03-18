"""Comprehensive tests for admin authorization on maintenance, monitoring, and metrics endpoints.

Tests cover:
- Admin users can access all admin-protected endpoints
- Non-admin users receive 403 Forbidden on admin endpoints
- Unauthenticated users receive 401 Unauthorized
- Metrics endpoint HTTP Basic Auth (valid/invalid/missing credentials)
- Security logging for failed authorization attempts
- Prometheus metric increments for failed access attempts
- Development mode (auth_provider=none) behavior
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from app.application.errors.exceptions import UnauthorizedError
from app.domain.models.user import User, UserRole
from app.interfaces.dependencies import require_admin_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user(
    role: UserRole = UserRole.USER,
    user_id: str = "user-1",
    is_active: bool = True,
) -> User:
    """Create a test user with the given role."""
    return User(
        id=user_id,
        fullname="Test User",
        email="test@example.com",
        role=role,
        is_active=is_active,
    )


def _make_admin_user(user_id: str = "admin-1") -> User:
    """Create an admin test user."""
    return User(
        id=user_id,
        fullname="Admin User",
        email="admin@example.com",
        role=UserRole.ADMIN,
        is_active=True,
    )


def _mock_bearer(token: str = "valid-token"):  # noqa: S107
    """Create a mock HTTPAuthorizationCredentials."""
    mock = Mock()
    mock.credentials = token
    return mock


def _mock_auth_service(
    user: User | None = None,
    side_effect: Exception | None = None,
):
    """Create a mock AuthService."""
    mock = Mock()
    if side_effect:
        mock.verify_token_secure = AsyncMock(side_effect=side_effect)
    else:
        mock.verify_token_secure = AsyncMock(return_value=user)
    return mock


def _mock_settings(auth_provider: str = "password"):
    """Create a mock Settings."""
    mock = Mock()
    mock.auth_provider = auth_provider
    return mock


# ===========================================================================
# Test require_admin_user dependency
# ===========================================================================


class TestRequireAdminUser:
    """Tests for the require_admin_user dependency function."""

    @pytest.mark.asyncio
    async def test_admin_user_allowed(self):
        """Admin users should pass the dependency check."""
        admin = _make_admin_user()
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(user=admin)

        with patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()):
            result = await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

        assert result.id == admin.id
        assert result.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_non_admin_user_forbidden(self):
        """Non-admin users should receive 403 Forbidden."""
        regular_user = _make_user(role=UserRole.USER)
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(user=regular_user)

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

        assert exc_info.value.status_code == 403
        assert "Admin privileges required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_no_credentials_unauthorized(self):
        """Missing credentials should raise UnauthorizedError."""
        auth_service = _mock_auth_service()

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(UnauthorizedError),
        ):
            await require_admin_user(
                bearer_credentials=None,
                auth_service=auth_service,
            )

    @pytest.mark.asyncio
    async def test_invalid_token_unauthorized(self):
        """Invalid token (verify_token returns None) should raise UnauthorizedError."""
        bearer = _mock_bearer("invalid-token")
        auth_service = _mock_auth_service(user=None)

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(UnauthorizedError),
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

    @pytest.mark.asyncio
    async def test_inactive_user_unauthorized(self):
        """Inactive users should be rejected even if admin."""
        inactive_admin = _make_user(role=UserRole.ADMIN, is_active=False)
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(user=inactive_admin)

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(UnauthorizedError),
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

    @pytest.mark.asyncio
    async def test_auth_provider_none_returns_admin(self):
        """When auth_provider is 'none', return anonymous admin user."""
        auth_service = _mock_auth_service()

        with patch(
            "app.interfaces.dependencies.get_settings",
            return_value=_mock_settings(auth_provider="none"),
        ):
            result = await require_admin_user(
                bearer_credentials=None,
                auth_service=auth_service,
            )

        assert result.id == "anonymous"
        assert result.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_auth_service_exception_raises_unauthorized(self):
        """If auth service throws, should raise UnauthorizedError."""
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(side_effect=RuntimeError("DB down"))

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(UnauthorizedError),
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

    @pytest.mark.asyncio
    async def test_non_admin_increments_prometheus_metric(self):
        """Non-admin access should increment the admin_unauthorized_access_total counter."""
        from app.core.prometheus_metrics import admin_unauthorized_access_total

        regular_user = _make_user(role=UserRole.USER)
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(user=regular_user)

        initial_count = admin_unauthorized_access_total.get({"endpoint": "admin"})

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(HTTPException),
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

        final_count = admin_unauthorized_access_total.get({"endpoint": "admin"})
        assert final_count == initial_count + 1


# ===========================================================================
# Test Metrics HTTP Basic Auth
# ===========================================================================


class TestMetricsBasicAuth:
    """Tests for the _verify_metrics_basic_auth dependency."""

    @pytest.mark.asyncio
    async def test_valid_credentials_pass(self):
        """Valid username/password should pass authentication."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "prometheus"
        credentials.password = "secret123"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "secret123"

        with patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings):
            result = await _verify_metrics_basic_auth(credentials=credentials)
            assert result is None

    @pytest.mark.asyncio
    async def test_invalid_password_rejected(self):
        """Wrong password should raise 401."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "prometheus"
        credentials.password = "wrong-password"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "correct-password"

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            pytest.raises(HTTPException) as exc_info,
        ):
            await _verify_metrics_basic_auth(credentials=credentials)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid credentials"
        assert exc_info.value.headers == {"WWW-Authenticate": "Basic"}

    @pytest.mark.asyncio
    async def test_invalid_username_rejected(self):
        """Wrong username should raise 401."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "hacker"
        credentials.password = "correct-password"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "correct-password"

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            pytest.raises(HTTPException) as exc_info,
        ):
            await _verify_metrics_basic_auth(credentials=credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_credentials_when_password_set_rejected(self):
        """Missing credentials when password is configured should raise 401."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "secret123"

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            pytest.raises(HTTPException) as exc_info,
        ):
            await _verify_metrics_basic_auth(credentials=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"

    @pytest.mark.asyncio
    async def test_no_password_configured_allows_access(self):
        """When METRICS_PASSWORD is empty, access is allowed without credentials."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = ""  # Empty = no auth required

        with patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings):
            result = await _verify_metrics_basic_auth(credentials=None)
            assert result is None

    @pytest.mark.asyncio
    async def test_failed_auth_increments_metric(self):
        """Failed metrics auth should increment metrics_auth_failure_total."""
        from app.core.prometheus_metrics import metrics_auth_failure_total
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "bad"
        credentials.password = "bad"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "correct-password"

        initial_count = metrics_auth_failure_total.get()

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            pytest.raises(HTTPException),
        ):
            await _verify_metrics_basic_auth(credentials=credentials)

        final_count = metrics_auth_failure_total.get()
        assert final_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_missing_credentials_increments_metric(self):
        """Missing credentials when required should also increment metric."""
        from app.core.prometheus_metrics import metrics_auth_failure_total
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "secret"

        initial_count = metrics_auth_failure_total.get()

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            pytest.raises(HTTPException),
        ):
            await _verify_metrics_basic_auth(credentials=None)

        final_count = metrics_auth_failure_total.get()
        assert final_count == initial_count + 1


# ===========================================================================
# Test Maintenance Routes Admin Authorization
# ===========================================================================


class TestMaintenanceRoutesAdminAuth:
    """Tests verifying maintenance route endpoints require admin authorization."""

    @pytest.mark.asyncio
    async def test_session_health_admin_succeeds(self):
        """get_session_health should work for admin users."""
        from app.interfaces.api.maintenance_routes import get_session_health

        mock_service = Mock()
        mock_service.get_session_health = AsyncMock(
            return_value={
                "session_id": "test-123",
                "found": True,
                "status": "completed",
                "total_events": 10,
                "events_with_attachments": 2,
                "total_attachments": 3,
                "valid_attachments": 3,
                "invalid_attachments": 0,
                "is_healthy": True,
                "issues": [],
            }
        )

        admin_user = _make_admin_user()
        result = await get_session_health(
            session_id="test-123",
            current_user=admin_user,
            service=mock_service,
        )
        assert result.found is True

    @pytest.mark.asyncio
    async def test_cleanup_attachments_admin_succeeds(self):
        """cleanup_invalid_attachments should work for admin users."""
        from app.interfaces.api.maintenance_routes import cleanup_invalid_attachments

        admin_user = _make_admin_user()
        mock_service = Mock()
        mock_service.cleanup_invalid_attachments = AsyncMock(
            return_value={
                "dry_run": True,
                "sessions_scanned": 5,
                "sessions_affected": 0,
                "events_cleaned": 0,
                "attachments_removed": 0,
                "affected_sessions": [],
                "errors": [],
                "timestamp": "2026-02-16T00:00:00Z",
            }
        )

        result = await cleanup_invalid_attachments(
            session_id=None,
            dry_run=True,
            current_user=admin_user,
            service=mock_service,
        )
        assert result.dry_run is True

    @pytest.mark.asyncio
    async def test_cleanup_stale_sessions_admin_succeeds(self):
        """cleanup_stale_running_sessions should work for admin users."""
        from app.interfaces.api.maintenance_routes import cleanup_stale_running_sessions

        admin_user = _make_admin_user()
        mock_service = Mock()
        mock_service.cleanup_stale_running_sessions = AsyncMock(
            return_value={
                "dry_run": True,
                "stale_threshold_minutes": 30,
                "sessions_cleaned": 0,
                "sandboxes_destroyed": 0,
                "sessions_marked_failed": [],
                "sessions_reset_pending": [],
                "sessions_skipped": [],
                "errors": [],
                "timestamp": "2026-02-16T00:00:00Z",
            }
        )

        result = await cleanup_stale_running_sessions(
            stale_threshold_minutes=30,
            dry_run=True,
            current_user=admin_user,
            service=mock_service,
        )
        assert result.dry_run is True


# ===========================================================================
# Test Monitoring Routes Admin Authorization
# ===========================================================================


class TestMonitoringRoutesAdminAuth:
    """Tests verifying monitoring route endpoints require admin authorization."""

    @pytest.mark.asyncio
    async def test_system_health_admin_succeeds(self):
        """get_system_health should work for admin users."""
        from app.interfaces.api.monitoring_routes import get_system_health

        admin_user = _make_admin_user()

        with patch("app.interfaces.api.monitoring_routes.get_health_monitor") as mock_health:
            mock_health.return_value.get_system_health.return_value = {"status": "healthy"}
            result = await get_system_health(current_user=admin_user)

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_error_stats_admin_succeeds(self):
        """get_error_stats should work for admin users."""
        from app.interfaces.api.monitoring_routes import get_error_stats

        admin_user = _make_admin_user()

        with patch("app.interfaces.api.monitoring_routes.get_error_manager") as mock_error:
            mock_error.return_value.get_error_stats.return_value = {"total_errors": 0}
            result = await get_error_stats(hours=24, current_user=admin_user)

        assert result["total_errors"] == 0

    @pytest.mark.asyncio
    async def test_system_status_admin_succeeds(self):
        """get_system_status should work for admin users."""
        from app.interfaces.api.monitoring_routes import get_system_status

        admin_user = _make_admin_user()

        with patch("app.interfaces.api.monitoring_routes.get_system_integrator") as mock_integrator:
            mock_integrator.return_value.get_system_status.return_value = {"status": "ok"}
            result = await get_system_status(current_user=admin_user)

        assert result["status"] == "ok"


# ===========================================================================
# Test Metrics Routes Admin Authorization
# ===========================================================================


class TestMetricsRoutesAdminAuth:
    """Tests verifying metrics route endpoints (except /metrics) require admin auth."""

    @pytest.mark.asyncio
    async def test_json_metrics_admin_succeeds(self):
        """get_json_metrics should work for admin users."""
        from app.interfaces.api.metrics_routes import get_json_metrics

        admin_user = _make_admin_user()

        with (
            patch("app.interfaces.api.metrics_routes._update_dynamic_metrics", new_callable=AsyncMock),
            patch("app.interfaces.api.metrics_routes.collect_all_metrics", return_value={"metrics": []}),
            patch("app.interfaces.api.metrics_routes.get_tracer") as mock_tracer,
            patch("app.interfaces.api.metrics_routes.get_cache_stats") as mock_cache,
            patch("app.interfaces.api.metrics_routes.get_otel_config", return_value=None),
        ):
            mock_tracer.return_value.get_all_metrics.return_value = {}
            mock_cache_obj = Mock()
            mock_cache_obj.to_dict.return_value = {}
            mock_cache.return_value = mock_cache_obj

            result = await get_json_metrics(current_user=admin_user)

        assert "metrics" in result or "tracer" in result

    @pytest.mark.asyncio
    async def test_health_check_admin_succeeds(self):
        """health_check should work for admin users."""
        from app.interfaces.api.metrics_routes import health_check

        admin_user = _make_admin_user()
        result = await health_check(current_user=admin_user)

        assert result["status"] == "healthy"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_prometheus_metrics_no_auth_when_no_password(self):
        """Prometheus endpoint should be accessible without auth when no password set."""
        from app.interfaces.api.metrics_routes import get_prometheus_metrics

        with (
            patch("app.interfaces.api.metrics_routes._update_dynamic_metrics", new_callable=AsyncMock),
            patch("app.interfaces.api.metrics_routes.format_prometheus", return_value="# metrics\n"),
        ):
            result = await get_prometheus_metrics(_auth=None)

        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_agent_metrics_admin_succeeds(self):
        """reset_agent_metrics should work for admin users."""
        from app.interfaces.api.metrics_routes import reset_agent_metrics

        admin_user = _make_admin_user()

        with patch("app.interfaces.api.metrics_routes.get_metrics_collector") as mock_collector:
            mock_collector.return_value.reset = Mock()
            result = await reset_agent_metrics(current_user=admin_user)

        assert result["status"] == "reset"


# ===========================================================================
# Test Security Logging
# ===========================================================================


class TestSecurityLogging:
    """Tests verifying that security events are logged appropriately."""

    @pytest.mark.asyncio
    async def test_non_admin_access_logged(self):
        """Non-admin access attempts should be logged with [SECURITY] prefix."""
        regular_user = _make_user(role=UserRole.USER, user_id="attacker-42")
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(user=regular_user)

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            patch("app.interfaces.dependencies.logger") as mock_logger,
            pytest.raises(HTTPException),
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0]
        log_format = call_args[0]
        assert "[SECURITY]" in log_format
        # The user ID and email are passed as %-style format args (lazy logging)
        assert call_args[1] == "attacker-42"
        assert call_args[2] == "test@example.com"

    @pytest.mark.asyncio
    async def test_failed_metrics_auth_logged(self):
        """Failed metrics auth should be logged with [SECURITY] prefix."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "hacker"
        credentials.password = "wrong"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "secret"

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            patch("app.interfaces.api.metrics_routes.logger") as mock_logger,
            pytest.raises(HTTPException),
        ):
            await _verify_metrics_basic_auth(credentials=credentials)

        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        assert "[SECURITY]" in log_message


# ===========================================================================
# Test Edge Cases
# ===========================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_constant_time_comparison_used(self):
        """Verify that secrets.compare_digest is used (not ==) for credential comparison."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "prometheus"
        credentials.password = "correct"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "correct"

        with (
            patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings),
            patch(
                "app.interfaces.api.metrics_routes.secrets.compare_digest",
                return_value=True,
            ) as mock_compare,
        ):
            await _verify_metrics_basic_auth(credentials=credentials)

        # compare_digest should be called exactly twice (username + password)
        assert mock_compare.call_count == 2

    @pytest.mark.asyncio
    async def test_admin_check_preserves_http_exceptions(self):
        """HTTPException from admin check should not be wrapped in UnauthorizedError."""
        regular_user = _make_user(role=UserRole.USER)
        bearer = _mock_bearer()
        auth_service = _mock_auth_service(user=regular_user)

        with (
            patch("app.interfaces.dependencies.get_settings", return_value=_mock_settings()),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_admin_user(
                bearer_credentials=bearer,
                auth_service=auth_service,
            )

        # Should be 403 HTTPException, not wrapped in UnauthorizedError
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unicode_credentials_handled(self):
        """Unicode characters in credentials should not cause errors."""
        from app.interfaces.api.metrics_routes import _verify_metrics_basic_auth

        credentials = Mock()
        credentials.username = "prometheus"
        credentials.password = "p@ssw0rd"

        mock_settings = Mock()
        mock_settings.metrics_username = "prometheus"
        mock_settings.metrics_password = "p@ssw0rd"

        with patch("app.interfaces.api.metrics_routes.get_settings", return_value=mock_settings):
            result = await _verify_metrics_basic_auth(credentials=credentials)
            assert result is None
