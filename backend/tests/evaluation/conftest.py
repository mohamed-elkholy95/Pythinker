"""Pytest configuration for evaluation scenarios.

Provides shared fixtures and configuration for Phase 0-5 evaluation tests.
"""

import pytest

from typing import Any


# =============================================================================
# Evaluation Mode Configuration
# =============================================================================

def pytest_addoption(parser):
    """Add custom command-line options for evaluation mode."""
    parser.addoption(
        "--evaluation-mode",
        action="store",
        default="enhanced",
        choices=["baseline", "enhanced"],
        help="Evaluation mode: baseline (before enhancements) or enhanced (with enhancements)",
    )
    parser.addoption(
        "--output",
        action="store",
        default=None,
        help="Output file path for evaluation results (JSON)",
    )


@pytest.fixture(scope="session")
def evaluation_mode(request):
    """Get the evaluation mode from command-line options."""
    return request.config.getoption("--evaluation-mode")


@pytest.fixture(scope="session")
def evaluation_output_path(request):
    """Get the output file path from command-line options."""
    return request.config.getoption("--output")


# =============================================================================
# Evaluation Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers for evaluation tests."""
    config.addinivalue_line(
        "markers",
        "evaluation: mark test as part of evaluation suite (baseline vs enhanced comparison)"
    )


# =============================================================================
# Evaluation Fixtures
# =============================================================================

@pytest.fixture
def evaluation_config(evaluation_mode) -> dict[str, Any]:
    """Provide evaluation configuration based on mode.

    Returns different settings for baseline vs enhanced mode.
    """
    if evaluation_mode == "baseline":
        return {
            "response_recovery_enabled": False,
            "duplicate_suppression_enabled": False,
            "argument_canonicalization_enabled": False,
            "tool_cache_enabled": False,
            "failure_snapshots_enabled": False,
        }

    # enhanced
    return {
        "response_recovery_enabled": True,
        "duplicate_suppression_enabled": True,
        "argument_canonicalization_enabled": True,
        "tool_cache_enabled": True,
        "failure_snapshots_enabled": True,
    }


@pytest.fixture
def metrics_collector():
    """Collect metrics during evaluation for later analysis.

    Usage:
        metrics_collector.record("recovery_success", 1)
        metrics_collector.increment("cache_hit")
        results = metrics_collector.get_results()
    """
    class MetricsCollector:
        def __init__(self):
            self.metrics: dict[str, float] = {}
            self.counts: dict[str, int] = {}

        def record(self, metric_name: str, value: float):
            """Record a metric value."""
            if metric_name not in self.metrics:
                self.metrics[metric_name] = 0
            self.metrics[metric_name] += value

        def increment(self, counter_name: str, amount: int = 1):
            """Increment a counter."""
            if counter_name not in self.counts:
                self.counts[counter_name] = 0
            self.counts[counter_name] += amount

        def get_results(self) -> dict[str, Any]:
            """Get all collected metrics and counts."""
            return {
                "metrics": self.metrics,
                "counts": self.counts,
            }

        def reset(self):
            """Reset all metrics and counts."""
            self.metrics = {}
            self.counts = {}

    return MetricsCollector()


# =============================================================================
# Evaluation Session Hooks
# =============================================================================

def pytest_sessionstart(session):
    """Hook called at the start of test session."""
    mode = session.config.getoption("--evaluation-mode")
    output = session.config.getoption("--output")

    print("\n" + "="*70)
    print(f"EVALUATION MODE: {mode.upper()}")
    if output:
        print(f"OUTPUT FILE: {output}")
    print("="*70 + "\n")


def pytest_sessionfinish(session, exitstatus):
    """Hook called at the end of test session."""
    output = session.config.getoption("--output")

    if output:
        import json
        from pathlib import Path

        # Collect test results
        results = {
            "evaluation_mode": session.config.getoption("--evaluation-mode"),
            "total_tests": session.testscollected,
            "passed": session.testscollected - session.testsfailed,
            "failed": session.testsfailed,
            "exit_status": exitstatus,
        }

        # Write results to file
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n✅ Evaluation results written to: {output}")


# =============================================================================
# Baseline/Enhanced Feature Toggles
# =============================================================================

@pytest.fixture
def skip_if_baseline(evaluation_mode):
    """Skip test if running in baseline mode.

    Use for tests that require enhanced features.
    """
    if evaluation_mode == "baseline":
        pytest.skip("Test requires enhanced features (not available in baseline)")


@pytest.fixture
def expect_failure_in_baseline(evaluation_mode):
    """Mark test as expected to fail in baseline mode.

    Use for tests that verify enhancement improvements.
    """
    if evaluation_mode == "baseline":
        pytest.xfail("Expected to fail in baseline (fixed in enhanced)")
