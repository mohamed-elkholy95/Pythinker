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

from .base import (
    BaseMetric,
    MetricScore,
    get_all_metrics,
    get_metric,
    register_metric,
)
from .execution_metrics import (
    ResponseTimeMetric,
    TokenCountMetric,
    ToolCallMetric,
)
from .semantic_metrics import (
    KeywordCoverageMetric,
    SimilarityMetric,
)
from .structured_metrics import (
    JsonFieldMetric,
    JsonSchemaMetric,
)
from .text_metrics import (
    ContainsMetric,
    ExactMatchMetric,
    NotContainsMetric,
    RegexMatchMetric,
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
    "ContainsMetric",
    # Text metrics
    "ExactMatchMetric",
    "JsonFieldMetric",
    # Structured metrics
    "JsonSchemaMetric",
    "KeywordCoverageMetric",
    "MetricScore",
    "NotContainsMetric",
    "RegexMatchMetric",
    "ResponseTimeMetric",
    # Semantic metrics
    "SimilarityMetric",
    "TokenCountMetric",
    # Execution metrics
    "ToolCallMetric",
    "get_all_metrics",
    "get_metric",
    "register_metric",
]
