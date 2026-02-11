"""Pytest configuration for evaluation scenarios.

Provides shared fixtures and configuration for Phase 0-5 evaluation tests.
"""

from typing import Any  # noqa: I001

import pytest


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
        "evaluation: mark test as an evaluation scenario",
    )


# =============================================================================
# Helper Functions
# =============================================================================

def evaluation_config(evaluation_mode) -> dict[str, Any]:
    """Return configuration based on evaluation mode.

    Args:
        evaluation_mode: Either 'baseline' or 'enhanced'

    Returns:
        dict: Configuration settings for the mode
    """
    if evaluation_mode == "baseline":
        # Pre-enhancement configuration
        return {
            "duplicate_query_policy_enabled": False,
            "argument_canonicalizer_enabled": False,
            "tool_definition_cache_enabled": False,
            "response_recovery_enabled": False,
            "failure_snapshot_enabled": False,
        }
    # enhanced
    # Post-enhancement configuration
    return {
        "duplicate_query_policy_enabled": True,
        "argument_canonicalizer_enabled": True,
        "tool_definition_cache_enabled": True,
        "response_recovery_enabled": True,
        "failure_snapshot_enabled": True,
    }


class ResultsCollector:
    """Collect evaluation results for reporting."""

    def __init__(self):
        """Initialize results collector."""
        self.results = []

    def add_result(
        self,
        scenario: str,
        metric: str,
        value: float,
        expected_baseline: float,
        expected_enhanced: float,
    ):
        """Add a metric result.

        Args:
            scenario: Test scenario name
            metric: Metric name
            value: Measured value
            expected_baseline: Expected baseline value
            expected_enhanced: Expected enhanced value
        """
        self.results.append({
            "scenario": scenario,
            "metric": metric,
            "value": value,
            "expected_baseline": expected_baseline,
            "expected_enhanced": expected_enhanced,
        })

    def get_results(self) -> dict[str, Any]:
        """Get all collected results.

        Returns:
            dict: All results
        """
        return {
            "results": self.results,
            "summary": {
                "total_metrics": len(self.results),
            },
        }
