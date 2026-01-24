"""Evaluation metrics for scoring agent outputs.

This module provides various metrics for evaluating the quality of
agent outputs, including:

- Exact match: Checks if output exactly matches expected
- Contains: Checks if output contains required strings
- Similarity: Measures semantic similarity
- JSON Schema: Validates output against JSON schema
- Tool Call: Verifies expected tool calls were made
- Response Time: Checks execution time
- Token Count: Verifies token usage

Custom metrics can be registered using the register_metric function.
"""

from tests.evals.metrics.base import (
    BaseMetric,
    MetricScore,
    register_metric,
    get_metric,
    get_all_metrics,
)
from tests.evals.metrics.text_metrics import (
    ExactMatchMetric,
    ContainsMetric,
    NotContainsMetric,
    RegexMatchMetric,
)
from tests.evals.metrics.semantic_metrics import (
    SimilarityMetric,
    KeywordCoverageMetric,
)
from tests.evals.metrics.structured_metrics import (
    JsonSchemaMetric,
    JsonFieldMetric,
)
from tests.evals.metrics.execution_metrics import (
    ToolCallMetric,
    ResponseTimeMetric,
    TokenCountMetric,
)

# Register all built-in metrics
_builtin_metrics = [
    ExactMatchMetric(),
    ContainsMetric(),
    NotContainsMetric(),
    RegexMatchMetric(),
    SimilarityMetric(),
    KeywordCoverageMetric(),
    JsonSchemaMetric(),
    JsonFieldMetric(),
    ToolCallMetric(),
    ResponseTimeMetric(),
    TokenCountMetric(),
]

for metric in _builtin_metrics:
    register_metric(metric)


__all__ = [
    # Base
    "BaseMetric",
    "MetricScore",
    "register_metric",
    "get_metric",
    "get_all_metrics",
    # Text metrics
    "ExactMatchMetric",
    "ContainsMetric",
    "NotContainsMetric",
    "RegexMatchMetric",
    # Semantic metrics
    "SimilarityMetric",
    "KeywordCoverageMetric",
    # Structured metrics
    "JsonSchemaMetric",
    "JsonFieldMetric",
    # Execution metrics
    "ToolCallMetric",
    "ResponseTimeMetric",
    "TokenCountMetric",
]
