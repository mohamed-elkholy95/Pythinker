"""Base metric interface and registry.

Defines the abstract base class for metrics and provides
the metric registration and lookup system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricScore:
    """Score from a single metric evaluation.

    Attributes:
        metric_name: Name of the metric that produced this score
        score: Numeric score between 0.0 and 1.0
        passed: Whether the metric considers this a pass
        details: Additional details about the evaluation
        message: Human-readable message about the result
    """
    metric_name: str
    score: float  # 0.0 to 1.0
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "score": self.score,
            "passed": self.passed,
            "details": self.details,
            "message": self.message,
        }


class BaseMetric(ABC):
    """Abstract base class for evaluation metrics.

    Metrics are used to score agent outputs against expected values
    or criteria. Each metric should:
    1. Have a unique name
    2. Implement the evaluate method
    3. Return a MetricScore with score, pass/fail, and details

    Example:
        class MyCustomMetric(BaseMetric):
            name = "my_metric"
            description = "Checks something custom"

            def evaluate(self, actual, expected, context):
                # Custom logic
                score = 0.8
                passed = score >= 0.7
                return MetricScore(
                    metric_name=self.name,
                    score=score,
                    passed=passed,
                    message="Custom check passed"
                )
    """

    name: str = "base"
    description: str = "Base metric"

    @abstractmethod
    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        """Evaluate the actual output against expected criteria.

        Args:
            actual_output: The actual output from the agent
            expected: Dictionary of expected values/criteria from EvalCase
            context: Additional context (timing, tokens, tool calls, etc.)

        Returns:
            MetricScore with the evaluation result
        """
        ...

    def get_threshold(self, expected: dict[str, Any], default: float = 0.7) -> float:
        """Get the threshold for this metric from expected values.

        Args:
            expected: Expected values dictionary
            default: Default threshold if not specified

        Returns:
            The threshold value
        """
        # Look for metric-specific threshold
        thresholds = expected.get("thresholds", {})
        if self.name in thresholds:
            return thresholds[self.name]

        # Look for general threshold
        if "min_score" in expected:
            return expected["min_score"]

        return default


# Global metric registry
_metrics: dict[str, BaseMetric] = {}


def register_metric(metric: BaseMetric) -> None:
    """Register a metric in the global registry.

    Args:
        metric: The metric instance to register
    """
    _metrics[metric.name] = metric


def get_metric(name: str) -> BaseMetric | None:
    """Get a metric by name from the registry.

    Args:
        name: The metric name

    Returns:
        The metric instance or None if not found
    """
    return _metrics.get(name)


def get_all_metrics() -> list[BaseMetric]:
    """Get all registered metrics.

    Returns:
        List of all registered metric instances
    """
    return list(_metrics.values())
