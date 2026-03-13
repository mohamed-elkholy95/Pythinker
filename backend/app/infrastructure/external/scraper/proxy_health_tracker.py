"""Proxy health tracker with failure thresholds."""

from __future__ import annotations

import logging
import time

from app.domain.external.stealth_types import ProxyHealth, ProxyStatus

logger = logging.getLogger(__name__)


class ProxyHealthTracker:
    """Track proxy health and rolling latency for the scraper stack."""

    def __init__(self, proxy_urls: list[str], max_failures: int = 3) -> None:
        self._max_failures = max(1, max_failures)
        self._response_times: dict[str, list[float]] = {}
        self._health: dict[str, ProxyHealth] = {proxy_url: ProxyHealth(proxy_url=proxy_url) for proxy_url in proxy_urls}

    def mark_success(self, proxy_url: str, response_time_ms: float | None = None) -> None:
        """Record a successful request."""
        health = self._health.get(proxy_url)
        if health is None:
            return

        previous_status = health.status
        health.success_count += 1
        health.last_success = time.time()
        health.last_error = None
        health.status = ProxyStatus.HEALTHY

        if response_time_ms is not None:
            rolling_times = self._response_times.setdefault(proxy_url, [])
            rolling_times.append(response_time_ms)
            del rolling_times[:-10]
            health.avg_response_time_ms = sum(rolling_times) / len(rolling_times)

        if previous_status == ProxyStatus.UNHEALTHY:
            logger.info("proxy_recovered", extra={"proxy": proxy_url})

    def mark_failure(self, proxy_url: str, error: str) -> None:
        """Record a failed request."""
        health = self._health.get(proxy_url)
        if health is None:
            return

        health.failure_count += 1
        health.last_failure = time.time()
        health.last_error = error[:200]

        if health.failure_count >= self._max_failures:
            health.status = ProxyStatus.UNHEALTHY
            logger.warning(
                "proxy_marked_unhealthy",
                extra={"proxy": proxy_url, "failures": health.failure_count},
            )
            return

        health.status = ProxyStatus.DEGRADED
        logger.info(
            "proxy_marked_degraded",
            extra={"proxy": proxy_url, "failures": health.failure_count},
        )

    def get_health(self, proxy_url: str) -> ProxyHealth:
        """Return health data for a single proxy."""
        return self._health.get(proxy_url, ProxyHealth(proxy_url=proxy_url))

    def get_all_health(self) -> dict[str, ProxyHealth]:
        """Return a shallow copy of current proxy health."""
        return dict(self._health)

    def get_healthy_proxy_urls(self) -> list[str]:
        """Return proxies that are still eligible for selection."""
        return [url for url, health in self._health.items() if health.status != ProxyStatus.UNHEALTHY]

    def reset(self, proxy_url: str) -> None:
        """Reset one proxy to the default UNKNOWN state."""
        if proxy_url not in self._health:
            return
        self._health[proxy_url] = ProxyHealth(proxy_url=proxy_url)
        self._response_times.pop(proxy_url, None)
