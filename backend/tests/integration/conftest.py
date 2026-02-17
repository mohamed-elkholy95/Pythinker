"""Shared fixtures for integration tests.

Wires real Prometheus counters into the domain AgentMetrics singleton so that
E2E tests can assert on metric increments. Without this, domain services use
no-op counters and metric assertions fail.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def configure_domain_metrics():
    """Wire Prometheus counters into the domain metrics singleton for E2E tests.

    This fixture runs once per test session. It connects the real
    infrastructure Prometheus counters to the domain AgentMetrics interface
    so that assertions like ``assert final_counter > initial_counter`` work.

    After the session, the domain metrics are reset to no-ops to avoid
    cross-session contamination.
    """
    try:
        from app.infrastructure.observability.agent_metrics_adapter import configure_agent_metrics

        configure_agent_metrics()
    except Exception:
        # Graceful degradation: if the adapter cannot be loaded (e.g. prometheus_client
        # not installed), let the tests run with no-ops and fail naturally on assertions.
        pass

    yield

    # Reset to no-ops after the session
    try:
        from app.domain.metrics.agent_metrics import AgentMetrics, set_agent_metrics

        set_agent_metrics(AgentMetrics())
    except Exception:
        pass
