"""Tests for ProxyHealthTracker."""

import pytest

from app.domain.external.stealth_types import ProxyStatus
from app.infrastructure.external.scraper.proxy_health_tracker import ProxyHealthTracker


@pytest.fixture
def tracker() -> ProxyHealthTracker:
    return ProxyHealthTracker(
        proxy_urls=["http://proxy1:8080", "http://proxy2:8080"],
        max_failures=2,
    )


class TestProxyHealthTracker:
    """Test suite for ProxyHealthTracker."""

    def test_initial_status_is_unknown(self, tracker: ProxyHealthTracker) -> None:
        """Test that all proxies start as UNKNOWN."""
        health = tracker.get_all_health()
        assert all(item.status == ProxyStatus.UNKNOWN for item in health.values())

    def test_mark_success_sets_healthy(self, tracker: ProxyHealthTracker) -> None:
        """Test that success marks proxy as HEALTHY."""
        tracker.mark_success("http://proxy1:8080", response_time_ms=150.0)

        health = tracker.get_health("http://proxy1:8080")
        assert health.success_count == 1
        assert health.status == ProxyStatus.HEALTHY
        assert health.avg_response_time_ms == 150.0

    def test_mark_failure_degrades_then_unhealthy(self, tracker: ProxyHealthTracker) -> None:
        """Test progressive degradation."""
        proxy = "http://proxy1:8080"

        tracker.mark_failure(proxy, "Connection failed")
        assert tracker.get_health(proxy).status == ProxyStatus.DEGRADED

        tracker.mark_failure(proxy, "Connection failed")
        assert tracker.get_health(proxy).status == ProxyStatus.UNHEALTHY

    def test_get_healthy_proxies_excludes_unhealthy(self, tracker: ProxyHealthTracker) -> None:
        """Test that unhealthy proxies are excluded."""
        tracker.mark_failure("http://proxy1:8080", "err")
        tracker.mark_failure("http://proxy1:8080", "err")

        healthy = tracker.get_healthy_proxy_urls()
        assert "http://proxy1:8080" not in healthy
        assert "http://proxy2:8080" in healthy

    def test_no_proxies_returns_empty(self) -> None:
        """Test empty tracker."""
        tracker = ProxyHealthTracker(proxy_urls=[], max_failures=3)
        assert tracker.get_all_health() == {}
        assert tracker.get_healthy_proxy_urls() == []
